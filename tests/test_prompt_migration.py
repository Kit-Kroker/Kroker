"""PROMPT_SHAS pins the prompt bytes the repo ships.

E-2 moved prompt bytes from Python constants into files; the original
literals here were computed from roles.py before the constants were deleted,
and the migration invariant was "the bytes did not move while moving". That
held from 2026-07-17 until the 2026-10-19 sweep (31b27dce, FR-041 scrub +
trailing-newline normalisation) moved all eight pinned prompts in one
deliberate commit WITHOUT refreshing this pin: the test then sat red on
main for a month, found at the FR-806 close-out (2026-11-19) -- itself the
failure mode this test exists to make impossible. Since prompts are
versioned assets (FR-806), editing one is legitimate and expected; the rule
now enforced is that a prompt never moves UNNOTICED: a deliberate edit
refreshes its literal here in the same diff, and a red here means a prompt
moved with no pin update.
"""

import hashlib

from sdlc.agents.roles import PROMPT_SHAS, REGISTRY, STAGE_ROLES

PINNED_PROMPT_SHAS = {
    "clarify": "26db68a05e6b307a9f372378694db871b374584fd653af10d7d055953f6e8cc9",
    "architect": "21b8cd74f178a7d0830dd0adca58ea699294f8dffcafb7e461db6cdd52f36afd",
    "plan": "90bf1e5a44ad50328703903309f55d18e7efc3b81cd74c270321b82d59552d9b",
    "devops": "de348e46042afc75617c795f8e0648ed2848daa965d39997db09b30d4745484f",
    "review": "03fa507383d2fe7d62b4ee39c96be73e97b30c30ba472b17dfabdfa953ab115d",
    "analyze": "a2b2759b321740bb470d4aa763e58a63bb4fb137b8e5ff41826746a72e07bb4f",
    "qa": "74bdf8374f9c51b00ab8d1da8b8f3d04e83849d45a1394fb0362e51eb66bb334",
    "merge_verdict": "4d6094487f83c70bd13264c33c0efe811375cb8300b8ff67e91f1b0c2230b66d",
}


def test_prompt_shas_did_not_move():
    # Subset, not equality: new roles (e.g. the optional research role added
    # 2026-07-17) can join PROMPT_SHAS without rocking the invariant. The
    # pinned shas must all still match exactly —
    # THAT is the "prompts didn't move unnoticed" check.
    assert PINNED_PROMPT_SHAS.items() <= PROMPT_SHAS.items()


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
    assert (
        hashlib.sha256(lf.read_text(encoding="utf-8").encode()).hexdigest()
        == hashlib.sha256(crlf.read_text(encoding="utf-8").encode()).hexdigest()
    )
