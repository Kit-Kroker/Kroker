# FakeMemory.recall crashes on a non-numeric watermark (021 GATE 2 item 4)

| | |
|---|---|
| From | 021 round (GATE 2 ruling 4; skeptic 4A) |
| Size | S |
| Status | open |

**What.** `FakeMemory.recall` (`src/sdlc/memory/fake.py:44`) does `int(watermark)`. A pinned non-numeric watermark (an ISO timestamp, which is what Hindsight's `current_watermark` returns, or a test's `"wm-e74"`) raises `ValueError`. The `recall_snapshot` activity swallows that and returns a **degraded** empty snapshot.

**Why it matters.** `tests/replay/test_graph_golden.py:127` (`test_memo_key_inputs_match_the_pinned_keys`) pins `watermark="wm-e74"`, so its recalls have always been degraded without anyone noticing. 021 T041 re-pins `MEMO_PARITY_KEYS` against that degraded behaviour; once this is fixed, those keys move again. It also blocks testing fake/Hindsight parity on realistic ISO watermarks.

**Shape of a fix.** Treat a non-integer watermark as opaque: no cutoff, or the cutoff at capture time, and keep the string verbatim on the snapshot. Then re-pin `MEMO_PARITY_KEYS` from a capture run.
