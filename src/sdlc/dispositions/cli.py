"""FR-304 (E-50): the human entry point for finding dispositions.

CLI, not HTTP -- the same reasoning capability/cli.py states: a disposition
is an audited write, and the board API serves unauthenticated with a
self-asserted X-Actor header (OQ-11), which cannot provide provenance for
approved_by. Lives beside cli approve/reject/revise in vocabulary: --by is
the approver, --reason is retained as calibration signal.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .models import Disposition, FindingDisposition
from .store import BoardFindingDispositionStore, FindingDispositionStoreError


def add_dispositions_parser(sub) -> None:
    risk = sub.add_parser("risk")
    risksub = risk.add_subparsers(dest="risk_cmd", required=True)

    d = risksub.add_parser("dispose")
    d.add_argument("--project", required=True)
    d.add_argument("--kind", required=True, choices=("vulnerability", "testability"))
    d.add_argument("--key", required=True)
    d.add_argument(
        "--disposition",
        required=True,
        choices=("false_positive", "mitigated_elsewhere", "accepted_risk"),
    )
    d.add_argument("--reason", required=True)
    d.add_argument("--by", required=True, help="approver identity")
    d.add_argument("--db", default=None)

    ls = risksub.add_parser("list")
    ls.add_argument("--project", required=True)
    ls.add_argument("--db", default=None)

    ex = risksub.add_parser("export")
    ex.add_argument("--project", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--db", default=None)


def run_dispositions(args) -> int:
    store = BoardFindingDispositionStore(db=args.db)
    try:
        if args.risk_cmd == "list":
            for row in store.load(args.project):
                print(f"{row.kind}:{row.key}  {row.disposition.value}  by {row.approved_by}")
            return 0

        if args.risk_cmd == "export":
            rows = store.load(args.project)
            payload = {
                "project": args.project,
                "dispositions": [r.model_dump(mode="json") for r in rows],
            }
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            print(f"wrote {out}")
            return 0

        fd = FindingDisposition(
            kind=args.kind,
            key=args.key,
            disposition=Disposition(args.disposition),
            approved_by=args.by,
            reason=args.reason,
            decided_at=datetime.now(UTC),
        )
        version = store.apply(
            args.project,
            fd,
            expected_version=store.registry_version(args.project),
            actor=args.by,
        )
        print(f"dispose: {args.kind}:{args.key} -> registry_version {version}")
        return 0
    except (ValueError, FindingDispositionStoreError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()
