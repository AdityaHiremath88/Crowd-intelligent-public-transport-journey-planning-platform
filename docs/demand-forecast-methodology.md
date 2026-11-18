# Historical ticket-activity baseline and backtest

## Target and terminology

The endpoint `GET /api/v1/crowding/prediction` forecasts **represented ETM passenger ticket volume** (`SUM(passenger_count)`) and **ticket transaction count** (`COUNT(*)`) for a stop-label / local transaction-hour / future date. It does not forecast people physically waiting, confirmed boardings, onboard load or occupancy. Stop IDs in this endpoint are ETM label IDs until a reviewed crosswalk exists.

## Forecast rule

For stop-label `s`, target weekday `w`, transaction hour `h`, and historical service dates `D` no more than 35 days before target `d`, let `y_(s,i,h)` be the observed daily ticket aggregate:

```text
prediction(s,d,h) = mean(y(s,i,h)) for i in D where weekday(i)=weekday(d) and i < d
```

Passenger ticket volume and transaction count are averaged independently. The baseline is simple and explainable; no fitted machine-learning model or confidence probability is used. The reported historical range is the minimum/maximum of comparable daily observations, not a prediction interval.

Evidence gates: target must be 1–14 days in the future; source snapshot age must be no more than 14 days; at least 3 prior comparable daily records are needed. Otherwise response status is `STALE` or `UNAVAILABLE` and numeric predictions are null. Current October data is stale relative to the current November runtime date, so the endpoint abstains.

## Chronological evaluation

Run:

```powershell
python -m scripts.backtest_ticket_activity --holdout-days 7 --lookback-days 28
```

It uses the final seven October dates as holdout, and compares a same-stop/weekday/transaction-hour mean with a same-stop/transaction-hour mean that ignores weekday. Both use only prior dates; no random row split is used. Evaluation unit is daily stop-label × transaction-hour cells for which the dataset contains at least one source row and both baselines have history. Empty groups are not imputed as verified zero; this limits conclusions to observed-positive cells.

Actual supplied ETM results (`outputs/ticket_activity_backtest.json`, generated locally):

| Target | Candidate MAE | Baseline MAE | Candidate RMSE | Baseline RMSE | Matched holdout cells |
|---|---:|---:|---:|---:|---:|
| Represented passenger ticket volume | 1.478 | 1.450 | 2.568 | 2.692 | 164,400 |
| Transaction count | 1.304 | 1.304 | 2.317 | 2.486 | 164,400 |

The weekday-aware candidate lowers RMSE but does not improve passenger-volume MAE; transaction-count MAE is essentially tied. That is mixed evidence, not consistent predictive superiority. The endpoint keeps the transparent weekday/hour historical baseline, calls it baseline-only, and adds no claimed model skill. A later representative month should be held out prospectively before product claims.

## Implementation and limitations

- API: `app/services/demand_forecast_service.py`; endpoint is registered in `app/api/routes/community.py` under `/crowding` because it shares crowd-evidence status routing. Evaluation: `scripts/backtest_ticket_activity.py`.
- Inputs: processed `stop_catalog`, `stop_demand`, `data_quality` in DuckDB. Output: point estimates, number of comparable days, observed range, source maximum date, evidence label and caveats.
- Days with no rows are not included as zero. If source extract completeness is not verified, missing rows may reflect incomplete capture rather than no transactions.
- The 31-day source contains little seasonal history; date-level transactions are correlated. Cell-level MAE/RMSE does not justify occupancy or queue conclusions.
- No prediction interval or probability is reported because one month is insufficient for calibrated uncertainty and the current source fails freshness.


