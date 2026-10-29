"""PR-6 contract tests: documented Python API (DOC-01/02) and adapter
honesty (ADP-01..04)."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from researchclaw.adapters import (
    AdapterBundle,
    RecordingBrowserAdapter,
    RecordingCronAdapter,
    RecordingMemoryAdapter,
    RecordingMessageAdapter,
    RecordingSessionsAdapter,
    RecordingWebFetchAdapter,
    _warned_capabilities,
)
from researchclaw.config import RCConfig

REPO_ROOT = Path(__file__).resolve().parents[1]


def _config(mcp_enabled: bool = False, **bridge_flags) -> RCConfig:
    data = {
        "project": {"name": "demo"},
        "research": {"topic": "Test topic"},
        "runtime": {"timezone": "UTC"},
        "notifications": {"channel": "console"},
        "knowledge_base": {"root": "docs/kb"},
        "llm": {
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "api_key_env": "OPENAI_API_KEY",
        },
        "experiment": {"mode": "sandbox"},
        "mcp": {"server_enabled": mcp_enabled},
    }
    if bridge_flags:
        data["openclaw_bridge"] = bridge_flags
    return RCConfig.from_dict(data, check_paths=False)


@pytest.fixture(autouse=True)
def _clear_warning_cache():
    _warned_capabilities.clear()
    yield
    _warned_capabilities.clear()


# ── DOC-01: README Python snippet actually imports ─────────────


def _readme_python_blocks() -> list[str]:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return re.findall(r"```python\n(.*?)```", text, flags=re.DOTALL)


def test_doc01_readme_imports_resolve() -> None:
    blocks = _readme_python_blocks()
    assert blocks, "README must keep at least one python example"

    import_lines: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith(("from researchclaw", "import researchclaw")):
                import_lines.append(stripped)
    assert import_lines, "README python examples should import researchclaw"

    namespace: dict[str, object] = {}
    for line in import_lines:
        exec(line, namespace)  # noqa: S102 - fixed strings from our own README

    from researchclaw.pipeline import execute_pipeline

    assert callable(execute_pipeline)


def test_doc01_pipeline_exports_public_api() -> None:
    import researchclaw.pipeline as pipeline

    for name in (
        "execute_pipeline",
        "execute_iterative_pipeline",
        "Stage",
        "StageStatus",
        "StageResult",
        "StageContract",
        "CONTRACTS",
        "STAGE_SEQUENCE",
    ):
        assert name in pipeline.__all__
        assert hasattr(pipeline, name)


# ── DOC-02: no phantom Runner API anywhere ────────────────────


def test_doc02_no_runner_class_in_docs() -> None:
    paths = [REPO_ROOT / "README.md"]
    paths.extend(sorted((REPO_ROOT / "docs").glob("*.md")))
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in paths
        if "Runner(" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], f"stale Runner(...) references: {offenders}"


# ── ADP-01/02: from_config only returns recording stubs ───────

_RECORDING_TYPES = (
    RecordingCronAdapter,
    RecordingMessageAdapter,
    RecordingMemoryAdapter,
    RecordingSessionsAdapter,
    RecordingWebFetchAdapter,
    RecordingBrowserAdapter,
)


def _assert_all_recording(bundle: AdapterBundle) -> None:
    for field_name in ("cron", "message", "memory", "sessions", "web_fetch", "browser"):
        assert isinstance(getattr(bundle, field_name), _RECORDING_TYPES), field_name


def test_adp02_default_config_returns_recording_adapters() -> None:
    bundle = AdapterBundle.from_config(_config())
    _assert_all_recording(bundle)


def test_adp01_mcp_enabled_stays_recording_and_warns(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="researchclaw.adapters"):
        bundle = AdapterBundle.from_config(_config(mcp_enabled=True))
    _assert_all_recording(bundle)
    warnings = [r for r in caplog.records if "mcp.server_enabled" in r.getMessage()]
    assert len(warnings) == 1


def test_adp01_warning_is_emitted_once(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="researchclaw.adapters"):
        AdapterBundle.from_config(_config(mcp_enabled=True))
        AdapterBundle.from_config(_config(mcp_enabled=True))
    warnings = [r for r in caplog.records if "mcp.server_enabled" in r.getMessage()]
    assert len(warnings) == 1


def test_adp01_openclaw_flags_do_not_fake_success(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="researchclaw.adapters"):
        bundle = AdapterBundle.from_config(
            _config(use_message=True, use_web_fetch=True)
        )
    _assert_all_recording(bundle)
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "openclaw_bridge.use_message" in messages
    assert "openclaw_bridge.use_web_fetch" in messages


# ── ADP-03: adapter failures never abort a stage ──────────────


class _ExplodingMessageAdapter:
    def notify(self, channel: str, subject: str, body: str) -> str:
        raise RuntimeError("bridge down")


class _ExplodingMemoryAdapter:
    def append(self, namespace: str, content: str) -> str:
        raise RuntimeError("memory down")


def test_adp03_failing_message_adapter_is_swallowed(caplog) -> None:
    from researchclaw.pipeline.executor import _notify_safely

    bundle = AdapterBundle(message=_ExplodingMessageAdapter())
    with caplog.at_level(logging.WARNING, logger="researchclaw.pipeline.executor"):
        _notify_safely(bundle, "console", "subject", "body")  # must not raise
    assert any("message adapter failed" in r.getMessage() for r in caplog.records)


def test_adp03_failing_memory_adapter_is_swallowed(caplog) -> None:
    from researchclaw.pipeline.executor import _remember_safely

    bundle = AdapterBundle(memory=_ExplodingMemoryAdapter())
    with caplog.at_level(logging.WARNING, logger="researchclaw.pipeline.executor"):
        _remember_safely(bundle, "stages", "entry")  # must not raise
    assert any("memory adapter failed" in r.getMessage() for r in caplog.records)


# ── ADP-04: CLI/server never force from_config ───────────────


def test_adp04_cli_uses_default_bundle() -> None:
    source = (REPO_ROOT / "researchclaw" / "cli.py").read_text(encoding="utf-8")
    assert "adapters = AdapterBundle()" in source
    assert "AdapterBundle.from_config(" not in source


def test_adp04_server_uses_default_bundle() -> None:
    server_dir = REPO_ROOT / "researchclaw" / "server"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in server_dir.rglob("*.py")
        if "AdapterBundle.from_config(" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []
