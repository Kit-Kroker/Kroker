# cat-cafe-monitoring: requirement list for the grown oracle

**For GATE 2 (ruling R9).** No test is written before the user approves
this list. It becomes `benchmarks/cases/cat-cafe-monitoring/tasks.yaml`.

Every requirement is taken from the case text in `case.yaml`: Task 1,
Task 2, or the interface contract. Nothing is added to the case. The case
text is not edited.

## Rules for every test

1. A test reaches the product only through the interface contract: the
   ASGI object `app:app`, `POST /telemetry`, `GET /floorplan`, `GET /cats`,
   `GET /cats/{id}`.
2. A test takes zone coordinates from the product's own `/floorplan`. No
   coordinate, distance or threshold is pinned.
3. A test asserts only what the case text states. Where the text leaves a
   rule to the implementer, the scenario is built at an extreme no
   reasonable rule disputes (a cat that does not move, on a zone, for
   several readings).
4. No sleeps, no randomness, no wall clock. Timestamps derive from one
   fixed base.
5. The 12 existing tests are kept as they are.

## Requirements

| # | Id | Source in the case text | Error class | Tests now | Target |
|---|---|---|---|---|---|
| 1 | `act_eating` | Task 1: eating, from distance to food bowls | functional | 1 | 2 |
| 2 | `act_drinking` | Task 1: drinking, from distance to water bowls | functional | 1 | 2 |
| 3 | `act_sleeping` | Task 1: sleeping, from rest areas and breathing rate | functional | 1 | 2 |
| 4 | `act_litter_box` | Task 1: using the litter box | functional | 1 | 2 |
| 5 | `act_playing_fighting` | Task 1: playing and fighting | functional | 1 | 3 |
| 6 | `act_vocabulary` | Contract: activity is one of six values or null | api_contract | 0 | 2 |
| 7 | `mon_movement` | Task 2: the movement of all cats; contract: a reading for a new cat begins tracking | functional | 1 | 3 |
| 8 | `mon_floorplan` | Case text: the plan includes rest areas, litter boxes, water bowls, food bowls; contract: `GET /floorplan` | api_contract | 0 | 3 |
| 9 | `mon_cats_shape` | Contract: `GET /cats` rows carry id, x, y, activity, at_risk; at_risk is a boolean | api_contract | 0 | 2 |
| 10 | `mon_detail` | Task 2: detailed sensor data per cat; contract: `GET /cats/{id}` | functional | 1 | 3 |
| 11 | `mon_history_window` | Task 2: history for the last 24 hours; contract: relative to the cat's newest reading | data_integrity | 1 | 3 |
| 12 | `mon_unknown_cat` | Contract: unknown id gives 404 | error_handling | 1 | 1 |
| 13 | `risk_flag` | Task 2: risk analysis per cat from collar data | functional | 3 | 5 |
| 14 | `telemetry_ingest` | Contract: `POST /telemetry` gives 2xx and is processed as a collar reading | api_contract | 0 | 2 |
| 15 | `import_no_autostart` | Contract: importing `app:app` must not start the generator | api_contract | 0 | 1 |
| | **Total** | | | **12** | **36** |

The spec allows 30 to 40. The target of each row may move by one while
the total stays in that range and no row drops below its present count.

## What the new tests cover (intent, not code)

- **1 to 4**: a second scenario per activity in which two cats sit on
  different zones at once and each gets its own activity.
- **5**: two cats together away from every zone, fast, high breathing
  rate: both are playing or fighting (either value passes, as today); a
  lone cat in the same state is not asserted either way; the pair is
  judged per cat.
- **6**: across several scenarios every `activity` value is in the
  allowed set or null.
- **7**: the latest reading wins; two cats move independently; a first
  reading for an unseen `cat_id` makes it appear in `GET /cats`.
- **8**: status 200; `zones` is a list; every kind is one of the four;
  all four kinds are present; `x` and `y` are numbers.
- **9**: every row has the five fields; `at_risk` is a boolean.
- **10**: the detail carries the latest reading; history entries carry
  timestamp, x, y, breathing_rate; history is that cat's only.
- **11**: a reading older than 24 hours before the newest is absent; one
  inside the window is present; the window follows the cat's newest
  reading, not another cat's and not the clock.
- **13**: risk is per cat (one at risk beside one that is not, both at
  sustained extremes as in the three existing tests); the `at_risk` field
  is present and boolean in the row of a cat with a single reading, with
  no claim about its value.
- **14**: a valid reading returns 2xx; a posted reading is visible in
  both views.
- **15**: after import and with nothing posted, two reads of `GET /cats`
  return the same thing.

## Left out on purpose

- "Ten cats live in the cafe": with the generator not started on import,
  the contract does not say how many cats exist before the first
  reading.
- "Marked in red", "show in real time on the floor plan": presentation.
  The contract exposes `at_risk`, not a colour.
- Any breathing-rate threshold between the extremes: the text leaves it
  free.
- Telling playing from fighting: the text gives no rule.
- Malformed telemetry: the contract states no error behaviour for it.
