from pydantic_ai.settings import ModelSettings

from agents.research.agent import build


def test_build_agent_provider_fake():
    # When provider is fake, capabilities should NOT include CodeMode
    agent = build("test", "sys prompt", ModelSettings(), [], "fake")
    assert "CodeMode" not in str(agent._root_capability)


def test_build_agent_provider_real():
    agent = build("test", "sys prompt", ModelSettings(), [], "exa")
    assert "CodeMode" in str(agent._root_capability)
    assert "ExaSearch" in str(agent._root_capability)
