# Maintenance log

Two kinds of entry live here.

**Manual entries** record decisions a person made: method changes, parameter
changes, data corrections, alert investigations. Add them to the first table
and bump `model_version` in `config.yaml` when the method or parameters change.

**Run entries** are appended automatically by `pipeline/run.py`. Rows with
mode `backfill` are replays of historical quarters produced in one sitting to
test the monitoring logic. They are not evidence that the job was running at
the time. Only `live` rows are real scheduled or manual runs.

## Manual entries

| Date | Version | Change | Reason |
|---|---|---|---|
| 2026-10-06 | 1.0.0 | Initial release. Primary estimator: scaled synthetic control on QoQ membership growth. | First build. Plain DiD and convex synthetic control rejected because UCAN lies outside the donors' convex hull and the pre-period gap trends (see README). |
| 2026-10-06 | 1.0.0 | OPEN: first live run raised `model_drift` (monitor donor weights moved 0.88 L1 between the 2026Q1 replay and the 2026Q2 run). No change made. | Looked at `registry/runs.csv`: the 12-quarter rolling fit puts all weight on EMEA and the scale moved from about 0.5 to 1.35. The prediction error itself is inside limits (z = +1.9). Likely cause is a short training window with three collinear donors, not a real change in UCAN. Candidate fix for 1.1.0: fit the monitor on the donor average (one slope) or lengthen `train_quarters`. |

## Run entries

| Run (UTC) | Mode | Latest quarter | Version | Data sha | Alerts | Note |
|---|---|---|---|---|---|---|
| 2026-10-07 02:07 | backfill | 2022Q4 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2023Q1 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2023Q2 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2023Q3 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2023Q4 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2024Q1 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2024Q2 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2024Q3 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2024Q4 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2025Q1 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2025Q2 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2025Q3 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2025Q4 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:07 | backfill | 2026Q1 | 1.0.0 | 41e3b43fe58d | no alerts | historical replay, not a live run |
| 2026-10-07 02:08 | live | 2026Q2 | 1.0.0 | 41e3b43fe58d | model_drift: monitor donor weights moved by 0.88 (L1) since the last run | first live run, started by hand |
