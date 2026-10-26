"""Surface pydantic-ai 2.61 / harness 0.61 added on top of the frozen
pre-migration fixture (tests/replay/fixtures/agent_activities_pre_migration.json).

The fixture is never regenerated (SG-2 family rule), so the upgrade's own
additions are declared here, next to the tests that compare against it, and
kept separate from the fixture's expected_registered_delta.
"""

# harness 0.61 registers each Exa toolset tool as its own capability activity
# (research_agent only, provider exa).
ADDED_ACTIVITY_SUFFIXES = (
    "__capability__exa_search__web_search",
    "__capability__exa_search__get_page",
    "__capability__exa_search__deep_search",
)

# pydantic-ai 2.61's Temporal model-activity retry policy also refuses to
# retry these workspace failures.
ADDED_NON_RETRYABLE = frozenset(
    {
        "WorkspaceOutputLimitError",
        "WorkspaceReadOnlyError",
        "WorkspaceTimeoutError",
        "WorkspaceUnavailableError",
    }
)
