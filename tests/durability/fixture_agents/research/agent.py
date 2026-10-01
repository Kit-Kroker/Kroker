"""Contract-test fixture agent: the NEW (003) research 5-argument `build`
shape (tool_paths + provider kept positional, `capabilities` keyword-only).

Records what the loader handed it on `received_capabilities`, tool paths and
provider included, so the loader contract tests can assert the whole call.

No @dataclass: this module is exec'd by loader._load_build without a
sys.modules entry, and dataclass processing needs the module registered
(it resolves via sys.modules.get(cls.__module__).__dict__).
"""

from __future__ import annotations


class BuiltAgent:
    def __init__(
        self, name: str, received_capabilities: list, tool_paths: list, provider: str
    ) -> None:
        self.name = name
        self.received_capabilities = received_capabilities
        self.tool_paths = tool_paths
        self.provider = provider


def build(
    model: str,
    instructions: str,
    model_settings,
    tool_paths: list[str],
    provider: str,
    *,
    capabilities=(),
) -> BuiltAgent:
    return BuiltAgent("research_agent", list(capabilities), list(tool_paths), provider)
