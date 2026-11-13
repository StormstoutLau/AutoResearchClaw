"""Docker-based sandbox for experiment code execution with GPU passthrough.

Uses a single-container, three-phase execution model:
  Phase 0: pip install from requirements.txt (if present)
  Phase 1: Run setup.py for dataset downloads (if present)
  Phase 2: Run the experiment script (main.py)

All phases run in the same container, so pip-installed packages
persist into the experiment phase. Network can be disabled after
setup via iptables (``setup_only`` policy).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from researchclaw.config import DockerSandboxConfig
from researchclaw.experiment.sandbox import (
    SandboxResult,
    parse_metrics,
    validate_entry_point,
    validate_entry_point_resolved,
)

logger = logging.getLogger(__name__)

_CONTAINER_COUNTER = 0
_counter_lock = threading.Lock()


def _next_container_name() -> str:
    global _CONTAINER_COUNTER  # noqa: PLW0603
    with _counter_lock:
        _CONTAINER_COUNTER += 1
        return f"rc-exp-{_CONTAINER_COUNTER}-{os.getpid()}"


class _TtlWatcher(threading.Thread):
    """Per-sandbox TTL guardian for one container.

    Lifecycle: sleep until ``deadline = start + ttl_sec`` (polling with
    ``ttl_poll_sec`` granularity), then ``docker kill -s TERM``, wait
    ``kill_grace_sec`` for a graceful exit (harness finalizes artifacts on
    SIGTERM), then ``docker kill`` (SIGKILL) if still running.

    Scope: this watcher only ever targets the single container it was
    created for — never other runs' containers (no docker ps sweeps).
    All failures degrade to warnings and never affect the main execution.
    """

    def __init__(
        self,
        container_name: str,
        ttl_sec: float,
        kill_grace_sec: float,
        poll_sec: float,
    ) -> None:
        super().__init__(daemon=True, name=f"rc-ttl-{container_name}")
        self._container = container_name
        self._ttl = float(ttl_sec)
        self._grace = float(kill_grace_sec)
        self._poll = float(poll_sec)
        self._stop = threading.Event()
        self._fired = False

    def stop(self) -> None:
        """Signal the watcher to give up (called from the main flow)."""
        self._stop.set()

    @property
    def fired(self) -> bool:
        """True once the TTL deadline was reached and TERM was issued."""
        return self._fired

    def run(self) -> None:  # noqa: D102
        deadline = time.monotonic() + self._ttl
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if self._stop.wait(min(self._poll, remaining)):
                return  # stopped before deadline — container exited normally
        if self._stop.is_set():
            return
        self._fire()

    def _fire(self) -> None:
        self._fired = True
        logger.warning(
            "TTL (%.0fs) expired for container %s — sending SIGTERM",
            self._ttl, self._container,
        )
        self._kill(["docker", "kill", "-s", "TERM", self._container])
        # Grace window: harness SIGTERM handler finalizes artifacts here.
        if self._stop.wait(self._grace):
            return  # container exited during grace (main flow stopped us)
        logger.warning(
            "Container %s survived TTL grace (%.0fs) — sending SIGKILL",
            self._container, self._grace,
        )
        self._kill(["docker", "kill", self._container])

    @staticmethod
    def _kill(cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, capture_output=True, timeout=10, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("TTL kill failed for %s: %s", cmd[-1], exc)


# Packages already in the Docker image — skip during auto-detect.
_BUILTIN_PACKAGES = {
    # PyTorch ecosystem
    "torch", "torchvision", "torchaudio", "torchdiffeq",
    # Scientific / ML
    "numpy", "scipy", "sklearn", "pandas", "matplotlib", "seaborn",
    "tqdm", "gymnasium", "networkx",
    # Extended ML ecosystem
    "timm", "einops", "torchmetrics", "albumentations", "kornia",
    "h5py", "tensorboard",
    # HuggingFace / LLM stack
    "transformers", "datasets", "accelerate", "peft", "trl",
    "bitsandbytes", "sentencepiece", "protobuf", "tokenizers",
    "safetensors", "evaluate",
    # Other pre-installed
    "yaml", "PIL", "mujoco",
    # Python stdlib
    "os", "sys", "math", "random", "json", "csv", "re", "time",
    "collections", "itertools", "functools", "pathlib", "typing",
    "dataclasses", "abc", "copy", "io", "logging", "argparse",
    "datetime", "hashlib", "pickle", "subprocess", "shutil",
    "tempfile", "warnings", "unittest", "contextlib", "operator",
    "string", "textwrap", "struct", "statistics", "glob",
    "urllib", "http", "email", "html", "xml",
}

# Map import names to pip package names.
_IMPORT_TO_PIP = {
    "torchdiffeq": "torchdiffeq",
    "torch_geometric": "torch-geometric",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio",
    "cv2": "opencv-python",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "gym": "gymnasium",
    "ogb": "ogb",
    "dgl": "dgl",
    "lightning": "lightning",
    "pytorch_lightning": "pytorch-lightning",
    "wandb": "wandb",
    "optuna": "optuna",
}


class DockerSandbox:
    """Execute experiment code inside a Docker container.

    Same public API as :class:`ExperimentSandbox` so the pipeline can use
    either backend transparently.

    The container uses ``entrypoint.sh`` which runs three phases in sequence:
      0. ``pip install -r requirements.txt`` (if file present in /workspace)
      1. ``python3 setup.py`` (if file present in /workspace)
      2. ``python3 <entry_point>``

    Network policy controls when network is available:
      - ``"none"``:       No network at any point (``--network none``)
      - ``"setup_only"``: Network during Phase 0+1, disabled via iptables before Phase 2
      - ``"pip_only"``:   Network during Phase 0 only (legacy compat, same as setup_only)
      - ``"full"``:       Network available throughout all phases
    """

    def __init__(self, config: DockerSandboxConfig, workdir: Path) -> None:
        self.config = config
        self.workdir = workdir.resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._run_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, code: str, *, timeout_sec: int = 300,
            run_id: str | None = None) -> SandboxResult:
        """Run a single Python code string inside a container."""
        self._run_counter += 1
        staging = self.workdir / f"_docker_run_{self._run_counter}"
        staging.mkdir(parents=True, exist_ok=True)

        script_path = staging / "main.py"
        script_path.write_text(code, encoding="utf-8")

        # Inject experiment harness
        self._inject_harness(staging)

        return self._execute(
            staging, entry_point="main.py", timeout_sec=timeout_sec,
            run_id=run_id,
        )

    def run_project(
        self,
        project_dir: Path,
        *,
        entry_point: str = "main.py",
        timeout_sec: int = 300,
        args: list[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        run_id: str | None = None,
    ) -> SandboxResult:
        """Run a multi-file experiment project inside a container."""
        self._run_counter += 1
        staging = self.workdir / f"_docker_project_{self._run_counter}"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)

        # Pre-copy syntax validation — fail fast before any I/O
        err = validate_entry_point(entry_point)
        if err:
            return SandboxResult(
                returncode=-1, stdout="", stderr=err,
                elapsed_sec=0.0, metrics={},
            )

        # Inject harness first (immutable)
        self._inject_harness(staging)

        # Copy project files and subdirectories (skip harness overwrite)
        import shutil as _shutil
        for src_item in project_dir.iterdir():
            dest = staging / src_item.name
            if src_item.name == "experiment_harness.py":
                logger.warning(
                    "Project contains experiment_harness.py — skipping (immutable)"
                )
                continue
            if src_item.is_file():
                dest.write_bytes(src_item.read_bytes())
            elif src_item.is_dir() and not src_item.name.startswith((".", "__")):
                _shutil.copytree(src_item, dest, dirs_exist_ok=True)

        # Post-copy resolve check — catches symlink-based escapes
        err = validate_entry_point_resolved(staging, entry_point)
        if err:
            return SandboxResult(
                returncode=-1, stdout="", stderr=err,
                elapsed_sec=0.0, metrics={},
            )

        entry = staging / entry_point
        if not entry.exists():
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr=f"Entry point {entry_point} not found in project",
                elapsed_sec=0.0,
                metrics={},
            )

        return self._execute(
            staging,
            entry_point=entry_point,
            timeout_sec=timeout_sec,
            entry_args=args,
            env_overrides=env_overrides,
            run_id=run_id,
        )

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def check_docker_available() -> bool:
        """Return True if the Docker daemon is reachable."""
        try:
            cp = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def check_nvidia_runtime() -> bool:
        """Return True if the NVIDIA Container Toolkit is available."""
        try:
            cp = subprocess.run(
                ["docker", "run", "--rm", "--gpus", "all",
                 "nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04",
                 "nvidia-smi"],
                capture_output=True,
                timeout=30,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def ensure_image(image: str) -> bool:
        """Return True if *image* exists locally (does NOT pull)."""
        try:
            cp = subprocess.run(
                ["docker", "image", "inspect", image],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _inject_harness(target_dir: Path) -> None:
        harness_src = Path(__file__).parent / "harness_template.py"
        if harness_src.exists():
            dest = target_dir / "experiment_harness.py"
            dest.write_text(harness_src.read_text(encoding="utf-8"), encoding="utf-8")
            logger.debug("Injected experiment harness into %s", target_dir)
        else:
            logger.warning("Harness template not found at %s", harness_src)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _execute(
        self,
        staging_dir: Path,
        *,
        entry_point: str,
        timeout_sec: int,
        entry_args: list[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        run_id: str | None = None,
    ) -> SandboxResult:
        """Core execution: single container, three-phase via entrypoint.sh."""
        cfg = self.config
        container_name = _next_container_name()

        # Auto-generate requirements.txt if packages need installing
        if cfg.network_policy in ("pip_only", "setup_only", "full"):
            self._write_requirements_txt(staging_dir)

        # Build the docker run command
        cmd = self._build_run_command(
            staging_dir,
            entry_point=entry_point,
            container_name=container_name,
            entry_args=entry_args,
            env_overrides=env_overrides,
            run_id=run_id,
        )

        # TTL guardian: only with an explicit run_id (never sweep other
        # runs' containers) and only when enabled via ttl_sec > 0.
        watcher: _TtlWatcher | None = None
        if run_id and cfg.ttl_sec > 0:
            watcher = _TtlWatcher(
                container_name,
                ttl_sec=cfg.ttl_sec,
                kill_grace_sec=cfg.kill_grace_sec,
                poll_sec=cfg.ttl_poll_sec,
            )
            watcher.start()

        start = time.monotonic()
        timed_out = False
        inspected: tuple[bool, int] | None = None
        try:
            logger.debug("Docker run command: %s", cmd)
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            returncode = completed.returncode
            elapsed = time.monotonic() - start
            # Container state readback for falsifiable 137 attribution.
            # Without --rm the container still exists here; unparseable
            # output degrades to None (no fabricated attribution).
            inspected = self._inspect_container(container_name)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            returncode = -1
            # Force-kill the container on timeout
            self._kill_container(container_name)
            elapsed = time.monotonic() - start
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - start
            if watcher is not None:
                watcher.stop()
                watcher.join(timeout=cfg.kill_grace_sec + 1.0)
            return SandboxResult(
                returncode=-1,
                stdout="",
                stderr=f"Docker execution error: {exc}",
                elapsed_sec=elapsed,
                metrics={},
            )
        finally:
            # TTL guardian must never outlive the execution.
            if watcher is not None:
                watcher.stop()
                watcher.join(timeout=cfg.kill_grace_sec + 1.0)
            # Always clean up the container regardless of how we exit.
            # docker rm -f is idempotent: safe even if container was
            # already removed, already dead, or never created.
            if not cfg.keep_containers:
                self._remove_container(container_name)

        # Parse metrics from stdout
        metrics = parse_metrics(stdout)

        # Try to read structured results.json from staging dir (volume-mounted)
        results_json_path = staging_dir / "results.json"
        if results_json_path.exists():
            try:
                structured = json.loads(
                    results_json_path.read_text(encoding="utf-8")
                )
                if isinstance(structured, dict):
                    for k, v in structured.items():
                        if k not in metrics:
                            try:
                                metrics[k] = float(v)
                            except (TypeError, ValueError):
                                pass
            except (json.JSONDecodeError, OSError):
                pass

        return SandboxResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            elapsed_sec=elapsed,
            metrics=metrics,
            timed_out=timed_out,
            limit_reason=self._attribute_limit(
                ttl_fired=(watcher.fired if watcher is not None else False),
                timed_out=timed_out,
                inspected=inspected,
            ),
        )

    def _build_run_command(
        self,
        staging_dir: Path,
        *,
        entry_point: str,
        container_name: str,
        entry_args: list[str] | None = None,
        env_overrides: dict[str, str] | None = None,
        run_id: str | None = None,
    ) -> list[str]:
        """Build the ``docker run`` command list.

        The container uses ``entrypoint.sh`` which handles:
          Phase 0: pip install requirements.txt
          Phase 1: python3 setup.py
          Phase 2: python3 <entry_point>

        Network policy determines --network and RC_SETUP_ONLY_NETWORK env.
        No ``--rm``: the container must stay inspectable after exit so
        OOM/137 can be attributed from ``State.OOMKilled``/``ExitCode``
        (G4-M4 A4-3); cleanup is handled by the ``_execute`` finally block.
        """
        cfg = self.config
        cmd = [
            "docker", "run",
            "--name", container_name,
            "-v", f"{staging_dir}:/workspace",
            "-w", "/workspace",
            f"--memory={cfg.memory_limit_mb}m",
            f"--shm-size={cfg.shm_size_mb}m",
        ]

        # --- Resource quotas (G4-M4 A4-2) ---
        # NOTE: --cpus over-limit is throttling, never 137 (P-100 D-3);
        # attribution must not treat a CPU-starved exit as OOM.
        if cfg.cpu_limit > 0:
            cmd.append(f"--cpus={cfg.cpu_limit:g}")
        if cfg.pids_limit > 0:
            cmd.append(f"--pids-limit={cfg.pids_limit}")

        # --- Provenance labels ---
        # rc.run ties the container to a pipeline run (TTL scope, forensics).
        # rc.tool is omitted on the experiment path (no tool context here).
        if run_id:
            cmd.extend(["--label", f"rc.run={run_id}"])

        # --- Network policy ---
        # On POSIX, run the container as the host user so that files
        # written to the bind-mounted volume are owned by the caller.
        # os.getuid / os.getgid are not available on Windows; fall back
        # to running as the default container user (usually root).
        def _user_flag() -> list[str]:
            if sys.platform == "win32":
                return []
            return ["--user", f"{os.getuid()}:{os.getgid()}"]

        if cfg.network_policy == "none":
            # Fully isolated — no network at any point
            cmd.extend(["--network", "none"])
            cmd.extend(_user_flag())
        elif cfg.network_policy in ("setup_only", "pip_only"):
            # Network during Phase 0+1, disabled via iptables before Phase 2.
            # Run as host user so experiment can write results.json to volume.
            # iptables requires NET_ADMIN but will gracefully degrade if
            # the user lacks root — network remains available but the code
            # has already been validated by the pipeline security check.
            cmd.extend(["-e", "RC_SETUP_ONLY_NETWORK=1"])
            cmd.extend(_user_flag())
            cmd.extend(["--cap-add=NET_ADMIN"])
        elif cfg.network_policy == "full":
            # Full network throughout — for development/debugging
            cmd.extend(_user_flag())

        # Mount pre-cached datasets
        # Priority: /opt/datasets (system) > ~/.cache/datasets (user)
        datasets_host = Path("/opt/datasets")
        user_datasets = Path.home() / ".cache" / "datasets"
        if datasets_host.is_dir():
            cmd.extend(["-v", f"{datasets_host}:/workspace/data:ro"])
        elif user_datasets.is_dir():
            cmd.extend(["-v", f"{user_datasets}:/workspace/data:rw"])
        else:
            # Create user-level cache so containers can download datasets
            user_datasets.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-v", f"{user_datasets}:/workspace/data:rw"])

        # Mount HuggingFace model cache (read-only for model weights).
        # BUG-103 fix: Don't set HF_HOME to the read-only mount — the
        # transformers library writes token/telemetry files under HF_HOME.
        # Instead, use HF_HUB_CACHE for read-only model access and let
        # HF_HOME default to a writable location inside the container.
        hf_mounted = False
        _hf_hub_cache = "/home/researcher/.cache/huggingface/hub"
        hf_home_env = os.environ.get("HF_HOME", "").strip()
        if hf_home_env:
            xdg_hf = Path(hf_home_env).resolve()
            if xdg_hf.is_dir():
                cmd.extend(["-v", f"{xdg_hf}:{_hf_hub_cache}:ro"])
                cmd.extend(["-e", f"HF_HUB_CACHE={_hf_hub_cache}"])
                hf_mounted = True
        if not hf_mounted:
            hf_cache_host = Path.home() / ".cache" / "huggingface"
            if hf_cache_host.is_dir():
                cmd.extend(["-v", f"{hf_cache_host}:{_hf_hub_cache}:ro"])
                cmd.extend(["-e", f"HF_HUB_CACHE={_hf_hub_cache}"])

        # BUG-107 fix: Set TORCH_HOME to writable location so torchvision
        # can download pretrained model weights (e.g., Inception-v3 for FID).
        cmd.extend(["-e", "TORCH_HOME=/workspace/.cache/torch"])

        # BUG-R52-03: Set HOME to a writable directory.  The container runs
        # as the host user (--user UID:GID) whose HOME defaults to "/" when
        # no matching passwd entry exists.  pip --user then fails with
        # "Permission denied: '/.local'".
        cmd.extend(["-e", "HOME=/workspace/.home"])

        # Pass HF token if available (for gated model downloads)
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            cmd.extend(["-e", f"HF_TOKEN={hf_token}"])

        # GPU passthrough
        if cfg.gpu_enabled:
            if cfg.gpu_device_ids:
                device_spec = ",".join(str(d) for d in cfg.gpu_device_ids)
                cmd.extend(["--gpus", f"device={device_spec}"])
            else:
                cmd.extend(["--gpus", "all"])

        _SAFE_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        if env_overrides:
            for name, value in sorted(env_overrides.items()):
                if not value or not _SAFE_ENV_NAME.match(name):
                    continue
                # Strip null bytes from values to prevent subprocess ValueError
                safe_value = str(value).replace("\x00", "")
                cmd.extend(["-e", f"{name}={safe_value}"])

        # Image + entry point (passed as CMD arg to entrypoint.sh)
        cmd.append(cfg.image)
        cmd.append(entry_point)
        if entry_args:
            cmd.extend(entry_args)

        return cmd

    def _write_requirements_txt(self, staging_dir: Path) -> None:
        """Generate requirements.txt in staging dir from auto-detected imports
        and explicit pip_pre_install, unless one already exists (LLM-generated).
        """
        req_path = staging_dir / "requirements.txt"

        # If the LLM already generated a requirements.txt, respect it but
        # append any pip_pre_install packages not already listed.
        existing_reqs: set[str] = set()
        if req_path.exists():
            for line in req_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract package name (before any version specifier)
                    pkg = re.split(r"[><=!~\[]", line)[0].strip().lower()
                    existing_reqs.add(pkg)

        # Collect additional packages to install
        packages: list[str] = []

        # From config pip_pre_install
        for pkg in self.config.pip_pre_install:
            pkg_base = re.split(r"[><=!~\[]", pkg)[0].strip().lower()
            if pkg_base not in existing_reqs:
                packages.append(pkg)
                existing_reqs.add(pkg_base)

        # Auto-detect from imports
        if self.config.auto_install_deps:
            detected = self._detect_pip_packages(staging_dir)
            for pkg in detected:
                pkg_base = pkg.lower()
                if pkg_base not in existing_reqs:
                    packages.append(pkg)
                    existing_reqs.add(pkg_base)

        if not packages and not req_path.exists():
            return  # Nothing to install

        if packages:
            mode = "a" if req_path.exists() else "w"
            with open(req_path, mode, encoding="utf-8") as f:
                if mode == "a":
                    f.write("\n# Auto-detected by ResearchClaw\n")
                for pkg in packages:
                    f.write(pkg + "\n")
            logger.info("requirements.txt updated: %s", packages)

    @staticmethod
    def _detect_pip_packages(staging_dir: Path) -> list[str]:
        """Scan Python files for import statements and return pip package names."""
        import_re = re.compile(
            r"^\s*(?:import|from)\s+([\w.]+)", re.MULTILINE
        )
        # Exclude local project modules (any .py file in staging_dir, recursive)
        # BUG-DA8-13: Use rglob to also scan subdirectories
        local_modules = {
            pyf.stem for pyf in staging_dir.rglob("*.py")
        }
        detected: list[str] = []
        for pyf in staging_dir.rglob("*.py"):
            if pyf.name == "setup.py":
                continue  # Don't scan setup.py for experiment deps
            text = pyf.read_text(encoding="utf-8", errors="replace")
            for m in import_re.finditer(text):
                top_module = m.group(1).split(".")[0]
                if top_module in _BUILTIN_PACKAGES:
                    continue
                if top_module in local_modules:
                    continue  # Skip local project modules
                pip_name = _IMPORT_TO_PIP.get(top_module, top_module)
                if pip_name not in detected:
                    detected.append(pip_name)

        return detected

    @staticmethod
    def _inspect_container(name: str) -> tuple[bool, int] | None:
        """Read ``State.OOMKilled``/``State.ExitCode`` for a stopped container.

        Returns ``(oomkilled, exitcode)`` on success, or ``None`` when the
        inspect fails or the output is unparseable — attribution must never
        be fabricated from a best-effort guess.
        """
        try:
            cp = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{.State.OOMKilled}} {{.State.ExitCode}}", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            if cp.returncode != 0:
                return None
            parts = cp.stdout.strip().split()
            if len(parts) != 2:
                return None
            oom = parts[0].strip().lower()
            if oom not in ("true", "false"):
                return None
            return (oom == "true", int(parts[1]))
        except (ValueError, FileNotFoundError, subprocess.TimeoutExpired,
                OSError):
            return None

    @staticmethod
    def _attribute_limit(
        *,
        ttl_fired: bool,
        timed_out: bool,
        inspected: tuple[bool, int] | None,
    ) -> str | None:
        """Single mapping from execution evidence to ``limit_reason``.

        Priority (frozen in spec/arc-g4-m4-sandbox-limits/DESIGN.md §2.2 D-5,
        M0 §6): ttl_timeout > resource_limit > timeout > None. This is the
        ONLY place that interprets 137/TTL evidence — call sites must not
        re-attribute.
        """
        if ttl_fired:
            return "ttl_timeout"
        if inspected is not None and (inspected[0] or inspected[1] == 137):
            return "resource_limit"
        if timed_out:
            return "timeout"
        return None

    @staticmethod
    def _kill_container(name: str) -> None:
        try:
            subprocess.run(
                ["docker", "kill", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    @staticmethod
    def _remove_container(name: str) -> None:
        try:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
