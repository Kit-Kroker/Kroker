"""FR-702: CodeArtifact (ADR-3) — one materialized code change."""

from sdlc.core.models import ArtifactRef
from sdlc.vcs.models import CodeArtifact


def test_code_artifact_defaults_and_roundtrip():
    art = CodeArtifact()
    assert art.files == [] and art.renames == [] and art.stat == "" and art.patch_ref is None
    ref = ArtifactRef(kind="diff", uri="file:///x.patch", sha256="a" * 64)
    art2 = CodeArtifact.model_validate(CodeArtifact(files=["a.py"], patch_ref=ref).model_dump())
    assert art2.patch_ref == ref and art2.files == ["a.py"]
