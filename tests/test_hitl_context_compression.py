"""P-175: ContextManager wired into HITL chat and stage context."""
from __future__ import annotations

from pathlib import Path

from researchclaw.hitl.chat import ChatSession, build_stage_context
from researchclaw.hitl.collaboration import CollaborationSession
from researchclaw.hitl.context_manager import ContextManager


class _FakeLLM:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def chat(self, messages: list[dict[str, str]]) -> object:
        self.messages = messages
        return type("_Resp", (), {"content": "ok"})()


def test_summarize_artifact_is_extractive_and_bounded(tmp_path: Path) -> None:
    cm = ContextManager(tmp_path)
    content = "# Heading\n" + "".join(
        f"result {i}: improvement 0.{i}\n" for i in range(600)
    )

    summary = cm.summarize_artifact(content, max_chars=200)

    assert "# Heading" in summary
    assert "lines" in summary
    assert len(summary) <= 300


def test_compress_messages_keeps_system_and_recent_turns(tmp_path: Path) -> None:
    cm = ContextManager(tmp_path, max_total_chars=500)
    messages = [{"role": "system", "content": "S" * 100}]
    for i in range(20):
        messages.append({"role": "user", "content": f"u{i}" + "x" * 50})
        messages.append({"role": "assistant", "content": f"a{i}" + "y" * 50})

    compressed = cm.compress_messages(messages)

    assert compressed[0]["role"] == "system"
    assert compressed[-1]["content"].startswith("a19")
    assert any("omitted" in m["content"] for m in compressed)
    assert sum(len(m["content"]) for m in compressed) <= 700


def test_chat_session_compresses_before_llm_call(tmp_path: Path) -> None:
    cm = ContextManager(tmp_path, max_total_chars=300)
    session = ChatSession(context_manager=cm)
    session.add_system_message("S" * 50)
    for i in range(10):
        session.add_human_message(f"q{i}" + "x" * 40)
        session.add_ai_message(f"a{i}" + "y" * 40)
    llm = _FakeLLM()

    session.get_ai_response(llm)

    assert llm.messages[0]["role"] == "system"
    assert sum(len(m["content"]) for m in llm.messages) <= 500


def test_build_stage_context_summarizes_large_artifact(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-08"
    stage_dir.mkdir()
    (stage_dir / "hypotheses.md").write_text(
        "# Hypothesis\n" + "result line\n" * 800, encoding="utf-8"
    )
    cm = ContextManager(tmp_path)

    context = build_stage_context(
        8,
        "HYPOTHESIS_GEN",
        "topic",
        tmp_path,
        artifacts=("hypotheses.md",),
        context_manager=cm,
    )

    assert "Hypothesis" in context
    assert "key lines" in context
    assert len(context) < 6000


def test_collaboration_wires_context_manager(tmp_path: Path) -> None:
    stage_dir = tmp_path / "stage-08"
    stage_dir.mkdir()
    (stage_dir / "hypotheses.md").write_text("short", encoding="utf-8")
    collab = CollaborationSession()

    collab.initialize(
        8, "HYPOTHESIS_GEN", "topic", tmp_path,
        artifacts=("hypotheses.md",),
    )

    assert isinstance(collab.chat.context_manager, ContextManager)
    assert collab.chat.context_manager.max_total_chars > 0
