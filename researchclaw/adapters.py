"""Typed adapter interfaces and deterministic recording stubs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Capability flags already reported, so a long run logs each warning once.
_warned_capabilities: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    if key in _warned_capabilities:
        return
    _warned_capabilities.add(key)
    logger.warning(message)


@dataclass(frozen=True)
class FetchResponse:
    url: str
    status_code: int
    text: str


@dataclass(frozen=True)
class BrowserPage:
    url: str
    title: str


class CronAdapter(Protocol):
    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str: ...


class MessageAdapter(Protocol):
    def notify(self, channel: str, subject: str, body: str) -> str: ...


class MemoryAdapter(Protocol):
    def append(self, namespace: str, content: str) -> str: ...


class SessionsAdapter(Protocol):
    def spawn(self, name: str, command: tuple[str, ...]) -> str: ...


class WebFetchAdapter(Protocol):
    def fetch(self, url: str) -> FetchResponse: ...


class BrowserAdapter(Protocol):
    def open(self, url: str) -> BrowserPage: ...


@dataclass
class RecordingCronAdapter:
    calls: list[tuple[str, int, str]] = field(default_factory=list)

    def schedule_resume(self, run_id: str, stage_id: int, reason: str) -> str:
        self.calls.append((run_id, stage_id, reason))
        return f"cron-{len(self.calls)}"


@dataclass
class RecordingMessageAdapter:
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def notify(self, channel: str, subject: str, body: str) -> str:
        self.calls.append((channel, subject, body))
        return f"message-{len(self.calls)}"


@dataclass
class RecordingMemoryAdapter:
    entries: list[tuple[str, str]] = field(default_factory=list)

    def append(self, namespace: str, content: str) -> str:
        self.entries.append((namespace, content))
        return f"memory-{len(self.entries)}"


@dataclass
class RecordingSessionsAdapter:
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def spawn(self, name: str, command: tuple[str, ...]) -> str:
        self.calls.append((name, command))
        return f"session-{len(self.calls)}"


@dataclass
class RecordingWebFetchAdapter:
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str) -> FetchResponse:
        self.calls.append(url)
        return FetchResponse(url=url, status_code=200, text=f"stub fetch for {url}")


@dataclass
class RecordingBrowserAdapter:
    calls: list[str] = field(default_factory=list)

    def open(self, url: str) -> BrowserPage:
        self.calls.append(url)
        return BrowserPage(url=url, title=f"Stub browser page for {url}")


@dataclass
class MCPMessageAdapter:
    """MessageAdapter backed by an MCP tool call.

    Deprecated placeholder kept only for backward-compatible imports; it does
    not perform any I/O and must not be used to claim real delivery. Prefer
    :class:`RecordingMessageAdapter` plus a host-injected implementation.
    """

    server_uri: str = "http://localhost:3000"

    def notify(self, channel: str, subject: str, body: str) -> str:
        return f"mcp-notify-{channel}"


@dataclass
class MCPWebFetchAdapter:
    """WebFetchAdapter backed by an MCP tool call (no I/O — see above)."""

    server_uri: str = "http://localhost:3000"

    def fetch(self, url: str) -> FetchResponse:
        return FetchResponse(url=url, status_code=200, text=f"mcp fetch for {url}")


@dataclass
class AdapterBundle:
    cron: CronAdapter = field(default_factory=RecordingCronAdapter)
    message: MessageAdapter = field(default_factory=RecordingMessageAdapter)
    memory: MemoryAdapter = field(default_factory=RecordingMemoryAdapter)
    sessions: SessionsAdapter = field(default_factory=RecordingSessionsAdapter)
    web_fetch: WebFetchAdapter = field(default_factory=RecordingWebFetchAdapter)
    browser: BrowserAdapter = field(default_factory=RecordingBrowserAdapter)
    hitl: object | None = None

    @classmethod
    def from_config(cls, config: object) -> AdapterBundle:
        """Build an AdapterBundle from RCConfig.

        Only recording stubs are returned: this package ships no real
        OpenClaw/MCP transport (decision D7). Enabling a capability in config
        logs a one-time warning so the absence of side effects is explicit
        rather than a silent fake success. Hosts wire real adapters by
        assigning to the bundle fields directly.
        """
        bundle = cls()

        mcp_cfg = getattr(config, "mcp", None)
        if mcp_cfg is not None and getattr(mcp_cfg, "server_enabled", False):
            _warn_once(
                "mcp.server_enabled",
                "mcp.server_enabled=True, but this build ships only recording "
                "adapters — notifications and web fetches stay local. Inject "
                "real adapters via AdapterBundle to enable the bridge.",
            )

        bridge = getattr(config, "openclaw_bridge", None)
        if bridge is not None:
            for flag in (
                "use_message",
                "use_web_fetch",
                "use_browser",
                "use_cron",
                "use_memory",
                "use_sessions_spawn",
            ):
                if getattr(bridge, flag, False):
                    _warn_once(
                        f"openclaw_bridge.{flag}",
                        f"openclaw_bridge.{flag}=True, but no OpenClaw endpoint "
                        "is configured and this build ships only recording "
                        "adapters. The flag is inert until a host injects a "
                        "real adapter into AdapterBundle.",
                    )
        return bundle
