"""PROMPT_SHAS must be byte-identical across the instructions.md migration.

E-2 moves prompt bytes from Python constants into files. Per the registry
spec's finding 1 that buys no memoization capability -- the hash is over the
same bytes -- so the ONLY way this migration can be wrong is if a prompt
changed while moving. These literals were computed from roles.py before the
constants were deleted. A diff here is a migration bug, never an improvement.
"""
import hashlib

from sdlc.agents.roles import PROMPT_SHAS, REGISTRY, STAGE_ROLES

PRE_MIGRATION_SHAS = {
    "clarify": "f40fbf6ef7451def3717c0270315e5d3c3897ba288cf96a06daec064454e0560",
    "architect": "a7ca1e578f2db831689208eb1d1f965e3d42f7adbbafc132d095905715fd9fc6",
    "plan": "ffe6717f887ca9d6f7f6f7276b3d0a688a8dc7c76d17d1ef0e06bae4c470563e",
    "devops": "9d18988b3d1180ed20e93748bb93559bb6c1cb645606eebcdde212d12d866e57",
    "review": "dcaa8df20374b514a5ac329bef9ac1c42d4e03fe6b264f2496ecb41c6fd635f3",
    "analyze": "16c37dbf71d1d83800f9904ac835e62b91439066b0d235eb7a274531ec2f71b3",
    "qa": "f3a65764d65ec2f4c9b46fdb5ab404a414df9edaf579ec729145b173689a6179",
    "merge_verdict": "a63d593b33ad800bd2251de9c31482315094aea978e41aa306ba759234614c6c",
}


def test_prompt_shas_did_not_move():
    assert PROMPT_SHAS == PRE_MIGRATION_SHAS


def test_every_proposer_role_has_instructions():
    for role in set(STAGE_ROLES.values()):
        assert REGISTRY[role].instructions, f"{role} has no instructions"


def test_harness_roles_have_no_instructions():
    for role in ("dev", "test", "devops"):
        assert REGISTRY[role].instructions is None


def test_crlf_and_lf_instructions_hash_identically(tmp_path):
    """git autocrlf checks these files out with CRLF on Windows. The loader
    reads with universal newlines so the hash is over LF either way -- if that
    ever stops being true, PROMPT_SHAS moves on Windows only, which is a
    miserable bug to find. Pin it."""
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"line one\nline two")
    crlf.write_bytes(b"line one\r\nline two")
    assert (hashlib.sha256(lf.read_text(encoding="utf-8").encode()).hexdigest()
            == hashlib.sha256(crlf.read_text(encoding="utf-8").encode()).hexdigest())
