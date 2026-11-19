"""FR-702 D1: the ADR-3 CodeArtifact union becomes a real model."""

from sdlc.core.models import ArtifactRef
from sdlc.vcs.models import CodeArtifact


def test_code_artifact_defaults_and_roundtrip():
    art = CodeArtifact()
    assert art.files == [] and art.renames == [] and art.stat == "" and art.patch_ref is None
    ref = ArtifactRef(kind="diff", uri="file:///x.patch", sha256="a" * 64)
    art2 = CodeArtifact.model_validate(CodeArtifact(files=["a.py"], patch_ref=ref).model_dump())
    assert art2.patch_ref == ref and art2.files == ["a.py"]


def test_empty_construct_is_the_propose_arm():
    """patch_ref=None + files=[] is the typed-but-unpopulated propose mode
    (spec D1: no either/or validator in v1) — it must stay constructible so
    consumers can treat it as 'no patch' without special-casing the model."""
    art = CodeArtifact(files=["written_file.py"])
    assert art.patch_ref is None
    assert art.files == ["written_file.py"]
