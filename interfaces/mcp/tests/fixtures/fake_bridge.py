"""A scripted bridge for cargo test (022 T016).

Speaks contracts/bridge-protocol.md on stdin/stdout, stdlib only. argv[1]
is a scenario JSON; every request received is appended (one JSON object
per line) to the scenario's record_path so Rust tests can assert what the
server actually forwarded.

Scenario shape:
    {
      "record_path": "…",          # required: jsonl of received requests
      "describe": {…},             # optional canned describe frame;
                                    #  default: the twelve canned tools
      "preview": [step, …],        # FIFO per op; each step:
      "call": [step, …],           #   {"lines": ["raw json", …],
                                    #    "exit": 9}   # die instead of replying
      "on_missing_step": "ok"      # default terminal ok:true value "…"
    }

A step's raw lines are written verbatim (so a test can emit an oversize
line or interleaved progress frames); without "lines" the step replies
with a canned terminal frame for that op.

Step consumption is durable ACROSS bridge respawns: a cursor file
(record_path + ".cursor") records how many steps of each op queue were
consumed, so a respawned child continues the scenario instead of
replaying it (the supervisor tests rely on this).
"""

import json
import os
import sys


def isolate_stdout():
    proto = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return proto


def load_cursor(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"preview": 0, "call": 0}


def save_cursor(path, cursor):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cursor, fh)
    os.replace(tmp, path)


CANNED_TOOLS = [
    "list_runs",
    "get_run",
    "follow",
    "inbox",
    "list_projects",
    "get_project",
    "list_tasks",
    "project_events",
    "read_artifact",
    "start_run",
    "answer_question",
    "decide_gate",
]


def default_describe():
    tools = []
    for name in CANNED_TOOLS:
        write = name in ("start_run", "answer_question", "decide_gate")
        tools.append(
            {
                "name": name,
                "description": f"canned {name}",
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": None,
                "read_only": not write,
                "confirm": "none",
                "progress": False,
            }
        )
    for d in tools:
        if d["name"] == "follow":
            d["progress"] = True
        if d["name"] == "start_run":
            d["confirm"] = "start"
        if d["name"] in ("answer_question", "decide_gate"):
            d["confirm"] = "pending"
    return {"op": "describe", "protocol": 1, "tools": tools}


def load_scenario(arg: str) -> dict:
    """argv[1] is a path to the scenario JSON (or inline JSON as a fallback)."""
    stripped = arg.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    with open(arg, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    scenario = load_scenario(sys.argv[1]) if len(sys.argv) > 1 else {}
    record_path = scenario.get("record_path")
    cursor_path = (
        scenario.get("cursor_path")
        or ((record_path + ".cursor") if record_path else None)
    )
    cursor = load_cursor(cursor_path) if cursor_path else {"preview": 0, "call": 0}
    proto = isolate_stdout()
    steps = {"preview": list(scenario.get("preview", [])), "call": list(scenario.get("call", []))}
    for op, consumed in cursor.items():
        if op in steps and isinstance(consumed, int):
            del steps[op][:consumed]
    describe = scenario.get("describe") or default_describe()

    def save_cursor_now():
        if cursor_path:
            save_cursor(cursor_path, cursor)

    def send(obj):
        proto.write((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))

    def record(entry):
        if record_path:
            with open(record_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, separators=(",", ":")) + "\n")
                fh.flush()

    for line in sys.stdin.buffer:
        try:
            req = json.loads(line)
        except ValueError:
            continue
        op = req.get("op")
        if op == "init":
            record({"op": "init", "actor": req.get("actor"), "protocol": req.get("protocol")})
            send(describe)
            continue
        if op in ("preview", "call"):
            record(
                {
                    "op": op,
                    "id": req.get("id"),
                    "tool": req.get("tool"),
                    "args": req.get("args"),
                    "expect_digest": req.get("expect_digest"),
                }
            )
            queue = steps[op]
            if queue:
                step = queue.pop(0)
                cursor[op] = cursor.get(op, 0) + 1
                save_cursor_now()
                for raw in step.get("lines", []):
                    proto.write((raw + "\n").encode("utf-8"))
                if "exit" in step:
                    sys.stderr.write(f"fake bridge exiting on {op}\n")
                    sys.stderr.flush()
                    os._exit(int(step["exit"]))
                if "frame" in step:
                    send(dict(step["frame"], id=req.get("id")))
                continue
            if op == "preview":
                send(
                    {
                        "id": req.get("id"),
                        "ok": True,
                        "value": {
                            "message": "canned preview",
                            "digest": "0" * 64,
                        },
                    }
                )
            else:
                send({"id": req.get("id"), "ok": True, "value": "canned result"})
        elif op == "cancel":
            record({"op": "cancel", "id": req.get("id")})


if __name__ == "__main__":
    main()
