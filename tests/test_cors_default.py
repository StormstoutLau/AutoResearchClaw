"""H-8 / Q19: server defaults must be loopback + explicit origins."""

from __future__ import annotations

import pytest

from researchclaw.config import ServerConfig, validate_server_security


def test_default_host_is_loopback() -> None:
    assert ServerConfig().host == "127.0.0.1"


def test_default_cors_has_no_wildcard() -> None:
    assert "*" not in ServerConfig().cors_origins


def test_wildcard_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_server_security(ServerConfig(cors_origins=("*",)))


def test_non_loopback_without_token_is_rejected() -> None:
    with pytest.raises(ValueError):
        validate_server_security(ServerConfig(host="0.0.0.0"))


def test_non_loopback_with_token_is_allowed() -> None:
    validate_server_security(ServerConfig(host="0.0.0.0", auth_token="token"))


def test_loopback_without_token_is_allowed() -> None:
    validate_server_security(ServerConfig())
