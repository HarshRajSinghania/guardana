"""Wire the judges `guardana.yaml` configures, through the CLI's endpoint seam.

The wiring lives in `guardana.core.evaluator.config`; a command routes each judge's
endpoint through `build_endpoint`, so the transport its tests substitute reaches the
judges too.
"""

from guardana.cli._endpoint import build_endpoint
from guardana.core.budget import Budgets
from guardana.core.evaluator.config import JudgeMeter, JudgeMeters
from guardana.core.evaluator.config import wire_config_evaluators as _wire
from guardana.core.profile import Profile
from guardana.core.registry import Registry
from guardana.core.target import EndpointTarget


def judge_endpoint(url: str, model: str, api_key: str | None) -> EndpointTarget:
    """Build a judge endpoint through the CLI's transport seam."""
    return build_endpoint(url, model, api_key=api_key)


def wire_config_evaluators(
    registry: Registry, profile: Profile, budgets: Budgets | None = None
) -> JudgeMeters:
    """Register the judges `profile` configures, built on the CLI's endpoints."""
    return _wire(registry, profile, budgets, build=judge_endpoint)


__all__ = ["JudgeMeter", "JudgeMeters", "judge_endpoint", "wire_config_evaluators"]
