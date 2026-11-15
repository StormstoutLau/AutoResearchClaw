"""Contract: every sandbox backend mirrors SandboxProtocol's keyword surface."""

from __future__ import annotations

import inspect

import pytest

from researchclaw.experiment.biology_agent_sandbox import BiologyAgentSandbox
from researchclaw.experiment.colab_sandbox import ColabDriveSandbox
from researchclaw.experiment.collider_agent_sandbox import ColliderAgentSandbox
from researchclaw.experiment.docker_sandbox import DockerSandbox
from researchclaw.experiment.sandbox import ExperimentSandbox, SandboxProtocol
from researchclaw.experiment.ssh_sandbox import SshRemoteSandbox
from researchclaw.experiment.stat_agent_sandbox import StatAgentSandbox

_IMPLS = (
    ExperimentSandbox,
    DockerSandbox,
    SshRemoteSandbox,
    ColabDriveSandbox,
    ColliderAgentSandbox,
    BiologyAgentSandbox,
    StatAgentSandbox,
)


def _kw_only(fn) -> tuple[str, ...]:
    return tuple(
        name
        for name, param in inspect.signature(fn).parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY
    )


@pytest.mark.parametrize("method", ["run", "run_project"])
def test_keyword_surface_matches_protocol(method: str) -> None:
    expected = _kw_only(getattr(SandboxProtocol, method))
    assert "run_id" in expected
    for impl in _IMPLS:
        assert _kw_only(getattr(impl, method)) == expected, impl.__name__
