# Journey ranking methodology

## Candidate construction before scoring

`POST /api/v1/journeys/search` first finds feasible schedule itineraries. It does not score an impossible connection. For each feasible candidate, time component is:

`T = (arrival time - requested departure time) / max_elapsed_time_among_candidates`

Here the elapsed time comprises initial wait plus scheduled journey duration; the duration includes transfer layovers. Transfer component is `X = number_of_transfers / max(1, requested_max_transfers)`. If crowd is unavailable it is missing, never zero crowd. Remaining time/transfer weights are renormalized:

`Score = (w_time*T + w_transfer*X) / (w_time + w_transfer)`

Lower is better. Current initial `(time, crowd, transfers)` weight assumptions are Fastest `(0.80,0.10,0.10)`, Balanced `(0.50,0.35,0.15)`, Comfort `(0.20,0.65,0.15)`. Since crowd is unavailable, production scores currently use time and transfer only after renormalization; the response explicitly warns Comfort cannot optimize crowd.

## Interpretation and limitations

- Weights are configurable engineering assumptions; no user preference or outcome study calibrated them.
- Per-query normalization means scores compare only options in the same response; scores are not probabilities or comparable utilities across searches.
- Comfort ranking does not mean lower crowd in current mode.
- Walking and transfer-specific penalties are not modeled separately; `waiting_seconds` is returned but not a separate score term.
- When crowd is later present, crowd exposure must aggregate ridden segment load times duration/distance or another user-interpretable measure, propagate uncertainty/coverage, and avoid a zero default for unknown segments.
- Future multivariate ranking should retain a Pareto set for time, transfers, walk and confidence before preference scoring so one dimension does not conceal dominated options.


