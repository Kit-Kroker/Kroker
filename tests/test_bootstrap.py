def test_light_modules_import():
    # These must import with only temporalio + pydantic present.
    import sdlc.models  # noqa: F401
    import sdlc.harness.adapters  # noqa: F401
    import sdlc.activities  # noqa: F401


def test_git_repo_fixture(git_repo):
    from pathlib import Path
    assert (Path(git_repo) / "README.md").read_text() == "seed\n"
