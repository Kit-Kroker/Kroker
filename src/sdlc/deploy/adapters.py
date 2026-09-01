"""Hosting adapters (ADR-19, FR-1105).

A DeployAdapter resolves a DeployPlan into the commands that apply it, read
the running version, and restore a prior one. Structurally identical to
toolchain/adapters.py and harness/adapters.py: an ABC + concrete adapters +
a module-level registry dict.

The adapter object is PURE -- it produces command strings and identity only,
never spawns a child process. Execution lives in Temporal activities
(deploy/activities.py), exactly as ToolchainAdapter never runs a test.

Two adapters ship. FR-1105 requires one reference (compose); script is the
second because a seam with a single implementation quietly becomes a
substrate -- and it preserves any target repo that already has `make deploy`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from ..models import DeployConfig, DeployPlan


class DeployKind(StrEnum):
    COMPOSE = "compose"
    SCRIPT = "script"


class DeployAdapter(ABC):
    kind: DeployKind

    def __init__(self, cfg: DeployConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def apply_cmd(self, plan: DeployPlan) -> str:
        """Command bringing `plan.version` up."""

    @abstractmethod
    def current_version_cmd(self, plan: DeployPlan) -> str:
        """Command whose stdout identifies the currently running version.
        Empty stdout means nothing is deployed yet (first-ever deploy)."""

    @abstractmethod
    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        """Command restoring a specific prior version."""

    @abstractmethod
    def endpoint(self, plan: DeployPlan) -> str:
        """Base URL `http` smoke checks resolve their paths against."""

    def env(self, plan: DeployPlan, version: str | None = None) -> dict[str, str]:
        """Environment exported to every command. `version` overrides the
        plan's own -- rollback must run with the PRIOR version in scope, not
        the one that just failed."""
        env = {
            "DEPLOY_ENV": plan.environment,
            "DEPLOY_VERSION": version or plan.version,
        }
        if plan.flag is not None:
            env["DEPLOY_FLAG"] = plan.flag.name
            env["DEPLOY_COHORT"] = plan.flag.cohort
        return env


class ComposeAdapter(DeployAdapter):
    """FR-1105 reference adapter. Assumes the target repo's compose file
    reads ${IMAGE_TAG} for the image it builds/runs."""

    kind = DeployKind.COMPOSE
    DEFAULT_BASE_URL = "http://localhost:8000"

    def apply_cmd(self, plan: DeployPlan) -> str:
        # --wait blocks until containers report healthy (or the compose
        # healthcheck fails), so a green exit code means something is up --
        # the smoke checks then decide whether it WORKS.
        return "docker compose up -d --build --wait"

    def current_version_cmd(self, plan: DeployPlan) -> str:
        return "docker compose images --format json"

    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        # --no-build on purpose: the prior image already exists, and
        # rebuilding would re-run the very build we are escaping.
        return "docker compose up -d --no-build --wait"

    def endpoint(self, plan: DeployPlan) -> str:
        return self.cfg.base_url or self.DEFAULT_BASE_URL

    def env(self, plan: DeployPlan, version: str | None = None) -> dict[str, str]:
        env = super().env(plan, version)
        env["IMAGE_TAG"] = version or plan.version
        return env


class ScriptAdapter(DeployAdapter):
    """The generalization of the pre-E-67 hardcoded deploy shell-out.
    Delegates semantics to a convention the target repo already owns."""

    kind = DeployKind.SCRIPT
    DEFAULTS = {"deploy": "make deploy", "rollback": "make rollback", "version": "make version"}

    def _cmd(self, key: str) -> str:
        return self.cfg.commands.get(key, self.DEFAULTS[key])

    def apply_cmd(self, plan: DeployPlan) -> str:
        return self._cmd("deploy")

    def current_version_cmd(self, plan: DeployPlan) -> str:
        return self._cmd("version")

    def rollback_cmd(self, plan: DeployPlan, to_version: str) -> str:
        return self._cmd("rollback")

    def endpoint(self, plan: DeployPlan) -> str:
        return self.cfg.base_url or ""


# Classes, not instances (unlike TOOLCHAINS) -- a deploy adapter is
# constructed with the run's DeployConfig, so there is no useful singleton.
ADAPTERS: dict[DeployKind, type[DeployAdapter]] = {
    DeployKind.COMPOSE: ComposeAdapter,
    DeployKind.SCRIPT: ScriptAdapter,
}


def resolve(cfg: DeployConfig) -> DeployAdapter:
    """FR-1105: resolved from configuration, never from an agent artifact."""
    return ADAPTERS[DeployKind(cfg.adapter)](cfg)
