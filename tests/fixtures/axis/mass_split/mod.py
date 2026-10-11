"""Mass-split fixture (round 015, contract §1.1).

Hand-computed, mass(f) = CC * sqrt(SLOC), SLOC = endline - lineno + 1:

    flat_a   CC=2  SLOC=9  -> 2*3  =  6
    flat_b   CC=6  SLOC=16 -> 6*4  = 24
    flat_c   CC=6  SLOC=25 -> 6*5  = 30
    monster  CC=12 SLOC=25 -> 12*5 = 60   (CC > 10: the eroded mass)

    under = 6 + 24 + 30 = 60; over = 60; total = 120
    erosion = 60 / 120 = 0.5 exactly

Every SLOC is a perfect square so each mass is an integer and the 0.5
is exact in floating point. Docstring padding sets the spans; it adds
no complexity. Every if is two lines: the file is ruff-format stable
(one-line ifs would be reformatted and break the calibration).
"""


def flat_a(x):
    """One branch over nine lines.

    Padding keeps the span a perfect square:
    padded out to the ninth line.
    """
    if x:
        return 1
    return 0


def flat_b(x):
    """Five branches over sixteen lines.

    The span is a perfect square: 6*4 = 24.
    """
    if x == 1:
        return 1
    if x == 2:
        return 2
    if x == 3:
        return 3
    if x == 4:
        return 4
    if x == 5:
        return 5
    return 0


def flat_c(x):
    """Five branches over twenty-five lines.

    The span is a perfect square: 6 * sqrt(25) = 30.
    Padding lines below tune the span; they
    add no complexity and change no mass.
    This block of prose is the fixture's
    arithmetic device, nothing more: five
    ifs, one base path, a perfect square
    of a body, and a mass that is exactly
    thirty. The hand-count in the module
    docstring is the expectation the test
    asserts; radon only reports the spans.
    """
    if x == 1:
        return 1
    if x == 2:
        return 2
    if x == 3:
        return 3
    if x == 4:
        return 4
    if x == 5:
        return 5
    return 0


def monster(x):
    """Eleven ifs, CC=12, twenty-five lines: 12*5 = 60."""
    if x == 1:
        return 1
    if x == 2:
        return 2
    if x == 3:
        return 3
    if x == 4:
        return 4
    if x == 5:
        return 5
    if x == 6:
        return 6
    if x == 7:
        return 7
    if x == 8:
        return 8
    if x == 9:
        return 9
    if x == 10:
        return 10
    if x == 11:
        return 11
    return 0
