"""Contract-test fixture agent: the NEW (003) 3-argument `build` shape.

Records what the loader handed it on `received_capabilities` so the loader
contract tests can assert exactly what crossed the seam. Deliberately not a
real pydantic_ai.Agent: the loader contract is about the CALL, not the agent.

No @dataclass: this module is exec'd by loader._load_build without a
sys.modules entry, and dataclass processing needs the module registered
(it resolves via sys.modules.get(cls.__module__).__dict__).
"""

from __future__ import annotations


class BuiltAgent:
    def __init__(self, name: str, received_capabilities: list) -> None:
        self.name = name
        self.received_capabilities = received_capabilities


def build(model: str, instructions: str, model_settings, *, capabilities=()) -> BuiltAgent:
    return BuiltAgent("planner_agent", list(capabilities))
