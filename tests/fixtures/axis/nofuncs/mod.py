"""No-functions fixture (round 015): module-level code only.

No function block exists, so erosion has no denominator: the honest
reading is not-measured with reason "no functions", never 0.0
(contract §1.1, spec edge case "a docs-only result").
"""

VALUE = 1
OTHER = VALUE + 1
TABLE = {VALUE: OTHER}
