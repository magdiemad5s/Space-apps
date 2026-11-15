# Frontend integration contract

**The Angular/Ionic frontend calls the TypeScript application API.** The backend prepares the personal baseline and historical summaries, then calls the private Python model. The team's actual frontend is now included under [frontend/](../../frontend/README.md), using the same-origin `/api/v1` proxy. New browser checks are recorded in [integration-reports](../../integration-reports/); older AI integration reports predate that frontend.

## Daily submission

Send `POST /api/v1/assess` with:

- `astronaut_id`.
- `observation_timestamp_utc`: a timezone-aware daily prediction cutoff.
- All 15 numeric measurements below.
- Optional `journal_text` as a string or `null`.

| Field | Unit / meaning |
|---|---|
| `sleep_duration_hours` | Hours of the completed sleep episode |
| `sleep_efficiency_pct` | Percentage of sleep opportunity spent asleep |
| `sleep_onset_delay_minutes` | Minutes before sleep onset |
| `awakenings_count` | Whole count |
| `sleep_midpoint_deviation_minutes` | Signed minutes relative to the planned sleep schedule |
| `resting_heart_rate_bpm` | Resting beats/minute |
| `hrv_rmssd_ms` | RMSSD in milliseconds |
| `reaction_time_median_ms` | Median response time in milliseconds |
| `reaction_time_lapses_count` | Whole count of responses ≥500 ms in the defined task |
| `attention_accuracy_pct` | Percentage correct in the separate attention task |
| `self_report_stress_score` | Custom 0–10 score; higher means more stress |
| `self_report_fatigue_score` | Today's custom 0–10 fatigue score |
| `self_report_mood_score` | Custom 0–10 score; higher means more positive mood |
| `workload_hours` | Non-overlapping duty hours |
| `exercise_minutes` | Exercise minutes |

Use the [measurement CSV](../integration/backend_review/proposed_backend/FRONTEND_MEASUREMENTS.csv) for recording windows and input bounds, and the [day-eight example](../integration/backend_review/proposed_backend/examples/assess_request_day8.json) for the JSON shape. Bounds validate the prototype's inputs; they are not clinical thresholds.

The earlier payload's sleep-quality score is not sleep efficiency. Generic HRV is not necessarily RMSSD. The old `PVT_speed_seconds` field cannot be converted into this model's reaction-time measurement merely by multiplying it by 1,000. Measurement protocols and units must agree.

The current model's reaction-time inputs come from a **60-response synthetic session**, with lapses counted at **≥500 ms** and the median calculated from the same responses. The simulator does not implement elapsed test time; the earlier five-minute description is not a timing guarantee. It is not a validated PVT/PVT-B implementation. The API accepts a lapse count from 0 to 60 but does not accept or verify the underlying trial count. A valid payload therefore does not establish that the frontend measured the same task. Confirm the actual collection protocol before connecting a real timed test; variable trial counts or a 355 ms threshold require an explicit contract/data review and model evaluation. See the [simulation clarification](../data/README.md#what-the-60-reaction-time-trials-mean).

The separate [Flanker prototype module](../integration/flanker_prototype/README.md)
provides a balanced 40-trial attention task plan and strict session scoring, with
four practice trials excluded. It is a frontend collection building block;
actual Angular/Ionic rendering, device timing checks and backend storage are not
implemented here. Its correct/40 accuracy matches the existing column's numeric
shape, but the original synthetic attention data did not come from Flanker.
Real-task model compatibility therefore remains unvalidated. Store its versioned
raw records separately, keep all Flanker response-time fields separate from the
model's reaction-time/PVT fields, and do not post its full result object to the
current strict `/assess` endpoint. Counts and protocol metadata are not accepted
by that existing payload contract.

Submit actual numbers, not numeric strings. Do not send targets, baseline means, calculated deltas, legacy aliases, or extra fields. The backend calculates the historical inputs itself.

## Calibration and time

The first **seven consecutive daily records** establish a fixed personal reference. Records must use the same UTC cutoff exactly 24 hours apart; the cutoff is not just the time someone pressed Submit. Prediction starts at **record eight**, using only the earlier calibration and the preceding three days.

The current prototype rejects gaps and out-of-order observations. Missing-day recovery remains future work. A computational seven-day reference is not proof that those days represent a clinically healthy state.

## UI states

| Response | Frontend behavior |
|---|---|
| `202`, `collecting_baseline` | Show calibration progress; no predicted fatigue label or fabricated score |
| `201`, `completed` | Show the next-day category, prototype points, and three explanation reasons |
| `422` | Show invalid-input feedback; do not treat the observation as saved |
| `409` | Explain duplicate, stale, or gapped history; repeated clicks must not add calibration days |
| `502` / `503` / `504`, `model_unavailable` | Check `observation_saved`; measurements may be saved while prediction is unavailable |

After a model outage, the **latest failed observation** can be retried with the identical body and timestamp. The backend updates that record instead of adding another day. A completed record is not a new daily observation when submitted again.

## Results and graphs

- Bind the index display to **`fatigue_points`**, labeled as a prototype score out of 100. `fatigue_risk_percentage` is deprecated and remains `null`.
- Explain that the category concerns tomorrow's simulated fatigue. Other current anomaly and journal outputs have different scopes.
- `top_contributing_factors` contains actual SHAP reason objects for the fatigue classifier. Keep the feature/value/direction context; do not turn an attribution into a causal medical recommendation.
- `fatigue_score` is from a separate 0–10 regression model and need not match the classifier's category band.
- `GET /api/v1/astronauts/:id/history` returns raw **`observations`** as well as assessment history and baseline information. Graph the observations with their actual timestamps and distinguish calibration records from predictions.
- `GET /api/v1/health` reports actual model reachability/readiness. An environment variable alone does not establish a working connection.

## Required application test

Exercise the actual Angular/Ionic app through calibration, an eighth-day prediction, history graphs, invalid and duplicate submissions, a model outage, and an identical retry after recovery. Confirm the app reaches the correct backend address on the presentation device; its `localhost` may be a different host.

The included nine-day synthetic loader is suitable for a quick demonstration, with its simulated origin clearly disclosed. Verify history persistence across a restart on the machine that will be used for the demo.
