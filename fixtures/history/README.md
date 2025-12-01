# History fixtures

Earlier per-sprint analysis artifacts, in the analyzer's output shape, consumed
through `--history`. The analyzer keeps same-board, earlier sprints ordered by
sprint date (not numeric ID) and excludes everything else with a recorded
reason.

| Directory | Sprint | Fate |
| --- | --- | --- |
| `sprint-40/` | 410, closed 2026-07-25 | used, first in sprint-date order |
| `sprint-41/` | 400, closed 2026-08-08 | used, second (ID 400 < 410, but started later) |
| `latest/` | copy of sprint 41 | excluded: duplicate of the same sprint (latest copy) |
| `sprint-42/` | 420, in-progress rerun | excluded: current sprint rerun |
| `other-board/` | board 99 | excluded: different board |

Deliberate comparison cases:

- `sprint-40` carries a null `over_100` and `aging_7d` value; null prior values
  are skipped in the average, and when all priors are null the metric has empty
  history and null `previous`/`historical_average`.
- `sprint-41` records a changed denominator for `taxonomy.unplanned`, so that
  metric is excluded as an incompatible definition rather than silently
  compared.
- Both priors are `final` observations, so in-progress current runs exclude
  them from delivery-outcome metrics with a kind-mismatch reason, while flow
  and taxonomy metrics remain comparable.
