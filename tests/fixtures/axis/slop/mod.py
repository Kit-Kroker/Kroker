"""Slop fixture (round 015, data-model §4): one rule marker per construct.

Hand-count (the test asserts these, not the engine's opinion):

    except-pass    the `except Exception:` handler (2 lines: clause+pass)
    bare-except    the `except:` handler (2 lines: clause+assignment)
    print-call     `print(first, second)` (1 line)
    debugger-call  `breakpoint()` (1 line)
    nested-ternary the inner conditional expression (1 line)
    if-deep-4      the innermost `if:` of four (2 lines: clause+body)

    9 flagged lines, no overlaps. Verbosity = 9 / non-blank LOC.
"""


def sloppy(x, first, second):
    try:
        first = 1
    except Exception:
        pass
    try:
        second = 2
    except:  # noqa: E722 — the slop under test, not a style slip
        second = 3
    print(first, second)
    breakpoint()
    chosen = 1 if x else (2 if first else 3)
    if first:
        if second:
            if chosen:
                if x:
                    kept = 1  # noqa: F841 — ditto
    return chosen
