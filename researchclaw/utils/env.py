"""Subprocess environment construction (H-6).

Only an explicit allowlist of non-secret variables is propagated to child
processes.  Secrets such as API keys, cloud credentials and proxy URLs with
embedded credentials are never forwarded implicitly.
"""

from __future__ import annotations

import os

# Variables required to start an interpreter/toolchain.  Deliberately excludes
# anything matching token/key/secret/password/proxy/credential.
SAFE_ENV_KEYS: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "PYTHONUNBUFFERED",
        "PYTHONPATH",
        "PYTHONHOME",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        # Windows process bootstrap
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "COMSPEC",
        "PATHEXT",
        "WINDIR",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "PROGRAMFILES",
        # GPU visibility (not a credential)
        "CUDA_VISIBLE_DEVICES",
        "NVIDIA_VISIBLE_DEVICES",
        "CUDA_HOME",
    }
)


def build_subprocess_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return a minimal environment for a child process.

    ``overrides`` are trusted, caller-supplied values (for example sandbox
    configuration) and are applied after the allowlist.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key in SAFE_ENV_KEYS or key.startswith("LC_")
    }
    env.setdefault("PYTHONUNBUFFERED", "1")
    if overrides:
        env.update({str(k): str(v) for k, v in overrides.items()})
    return env
