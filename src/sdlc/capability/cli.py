"""FR-913 (E-47a): the human entry point for identity corrections.

CLI, not HTTP, and that is a constraint rather than a convenience. A
correction rewrites identity that delivered client documents cite -- the
highest-trust write in this design -- and the board API serves
unauthenticated with a self-asserted X-Actor header (OQ-11). An
unauthenticated header cannot provide provenance for approved_by on an
audited override. Exposing these verbs over HTTP becomes reasonable when
OQ-11 closes, not before.

Lives beside cli approve/reject/revise in vocabulary: --by is the approver,
--reason is retained as calibration signal.
"""
from __future__ import annotations

import sys

from .corrections import CorrectionOp, IdentityCorrection, apply_correction
from .export import write_export
from .store import BoardIdentityStore, IdentityStoreError

_ABSORB = ("merge", "reattach")


def add_capability_parser(sub) -> None:
    cap = sub.add_parser("capability")
    capsub = cap.add_subparsers(dest="cap_cmd", required=True)

    for name in _ABSORB:
        c = capsub.add_parser(name)
        c.add_argument("--project", required=True)
        c.add_argument("--from", dest="source", required=True)
        c.add_argument("--into", dest="target", required=True)
        c.add_argument("--reason", required=True)
        c.add_argument("--by", required=True, help="approver identity")
        c.add_argument("--db", default=None)

    s = capsub.add_parser("split")
    s.add_argument("--project", required=True)
    s.add_argument("--from", dest="source", required=True)
    s.add_argument("--member", action="append", default=[],
                   help="fingerprint member moving to the new id; repeatable")
    s.add_argument("--reason", required=True)
    s.add_argument("--by", required=True, help="approver identity")
    s.add_argument("--db", default=None)

    ls = capsub.add_parser("list")
    ls.add_argument("--project", required=True)
    ls.add_argument("--db", default=None)

    ex = capsub.add_parser("export")
    ex.add_argument("--project", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--db", default=None)


def run_capability(args) -> int:
    store = BoardIdentityStore(db=args.db)
    try:
        if args.cap_cmd == "list":
            for row in store.load(args.project):
                suffix = (f" -> {row.merged_into}" if row.merged_into else "")
                print(f"{row.bc_id}  {row.status.value}{suffix}")
            return 0

        if args.cap_cmd == "export":
            path = write_export(args.out, args.project,
                                store.load(args.project))
            print(f"wrote {path}")
            return 0

        correction = IdentityCorrection(
            operation=CorrectionOp(args.cap_cmd),
            approved_by=args.by, reason=args.reason,
            source_bc_id=args.source,
            target_bc_id=getattr(args, "target", None),
            partition=list(getattr(args, "member", [])))
        version = apply_correction(store, args.project, correction)
        print(f"{args.cap_cmd}: {args.source} -> registry_version {version}")
        return 0
    except (ValueError, IdentityStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
