# Forty-trial Flanker collection prototype

This is a standalone, browser-usable TypeScript trial-plan and scoring module. It has no Node imports, HTTP calls, trained-model updates, or Angular/Ionic components. **No live backend or model contract has been changed.**

The protocol is a deliberately specified **demonstration**, not an established clinical, astronaut-readiness, or validated device test. Its three-second response deadline is a project choice, not a claim of a clinical standard.

## Exact protocol

- Protocol ID: `astra-flanker-40-demo`; version: `0.1.0`.
- Four practice trials: one in each congruency × center-direction cell.
- Forty scored main trials: 20 congruent and 20 incongruent, with **10 in each condition × center-left/right cell**.
- Five actual arrow glyphs are shown; the **center arrow** defines the correct left/right response. Examples: `←←←←←`, `→→→→→`, `→→←→→`, `←←→←←`.
- Practice precedes the scored block. Fisher–Yates shuffles practice and main blocks separately; an injectable RNG permits deterministic tests. Save the original trial plan before administration.
- The response deadline is actual stimulus onset + **3,000 ms**. The first directional response with `0 <= RT < 3000` is accepted. Exactly 3,000 ms or later is a timeout, even if its direction is correct.
- Wrong accepted responses and timeouts both count as incorrect in the denominator, but retain distinct `incorrect` and `timeout` statuses. A late response's actual RT is retained for audit, with no accepted RT/response.
- There is deliberately no lower human-validity cutoff in this prototype. RT = 0 passes its numerical rules, but does not establish plausible or accurately measured human performance.
- A no-response timeout cannot be recorded before its real deadline.
- A completed protocol requires **44 unique ordered records**: four practice records followed by forty main records. Summaries exclude the four practice results.
- Interrupted, declared-invalid, visibility-hidden or window-blurred sessions cannot produce an accuracy summary. Missing, duplicated, reordered, overlapping, inconsistent or non-finite trial records also invalidate the session.

No intertrial interval, fixation schedule or total session duration is claimed by this module. The collector must choose and version those administration details before real use. A three-second maximum per trial does not make this a five-minute PVT.

## Functions and outputs

```ts
import { createFlankerPlan, scoreFlankerSession } from "./flanker.ts";
import type { FlankerSession } from "./flanker.ts";

const originalPlan = createFlankerPlan("session_001");
// Persist originalPlan and render it using the chosen frontend implementation.
// Build a real FlankerSession from actual recorded events, not synthetic defaults.
const result = scoreFlankerSession(originalPlan, collectedSession as FlankerSession);
```

The two entry points are `createFlankerPlan(sessionId, rng?)` and `scoreFlankerSession(savedOriginalPlan, submission)`. The scorer derives expected stimuli, directions and deadlines from the original plan. It does not accept submitted correctness labels. A future backend must retain its own original plan; a client must not be allowed to replace that plan when submitting answers. The pure module alone is not an authenticated or tamper-proof assessment system.

A valid completed demonstration returns:

- `attention_trials_count = 40`;
- `attention_correct_count`, excluding all practice trials;
- `attention_accuracy_pct = correct / 40 * 100`;
- separate `flanker_*` RT, wrong-response and timeout summaries;
- protocol/version, prototype provenance, raw trial records and per-trial scores;
- `clinical_validation: false` and `existing_model_compatibility_established: false`.

Correct-response RT means and medians exclude wrong responses and timeouts. When no correct responses exist, these RT summaries are **null**, not fabricated zero milliseconds. Congruent/incongruent RT differences are descriptive only.

Invalid or interrupted results have **null summary counters/accuracy/RT**, with audit records retained. They must not be displayed as a complete forty-trial assessment. `trial_results` may contain a validated partial prefix for audit; its presence is not a valid session summary.

## Browser collector responsibilities — not implemented here

1. Record `performance.timeOrigin` and use one session's `performance.now()` clock for all onset, response, end and assessment-reference timestamps. Do not mix wall-clock UTC milliseconds with relative RTs or timestamps from a reloaded page.
2. Render the exact saved five-arrow string with a consistent visible layout/font/spacing. Record onset after the rendering step actually used by the collector; do not use the planned schedule timestamp as observed onset. `requestAnimationFrame` can help synchronize browser work but does not prove the exact pixel-on-screen or hardware onset.
3. Record only the first directional keypress/tap for the active trial; ignore keyboard auto-repeat (`event.repeat`) and later presses. Preserve the actual key/touch identifier for audit. `response.direction` must follow the collector's declared key/tap mapping; the scorer cannot verify that mapping from free-text `raw_key`.
4. Derive the response deadline from recorded onset, hide/finish the trial at that deadline, and schedule the timeout only after 3,000 ms. Browser timer/event-loop delay may cause later callback delivery: compare recorded event RT to the deadline rather than accepting late keys because the callback fired late.
5. Record actual trial end; the next trial must not begin before it. Preserve any observed late event as late audit data, never as a correct accepted response.
6. Record `visibilitychange` to hidden and window blur as quality events. Stop/mark the session invalid; do not silently resume and treat it as a valid completion.
7. `ended_at_ms` must precede/equal the same-clock assessment reference. Negative, non-finite or future response/end timestamps are rejected. These are internal consistency checks, not proof that a dishonest client used a real clock.
8. Save complete protocol metadata and raw records before submitting to a future collection endpoint. The user interface, actual rendering, mobile touch latency, device calibration, storage and authenticated API remain separate work.

The module and tests do not demonstrate that a real browser rendered stimuli, measured timing accurately, ignored repeated keys, or captured every focus event. No Angular/Ionic source has been supplied or tested.

## Current backend/model compatibility

The current `/api/v1/assess` allowlist accepts only `attention_accuracy_pct` among these summary/metadata fields. It does **not** accept `attention_trials_count`, `attention_correct_count`, Flanker RT fields, protocol metadata or raw trial arrays as extra inputs. The Python model endpoint is likewise strict.

This output therefore needs a separately agreed **collection/storage contract and frontend wiring**. This module provides no automatic adapter that pushes its score into the existing model. Matching a forty-trial count or a 0–100 numeric shape does not validate transfer from the current model's simulated Bernoulli attention scores to a real Flanker task.

Never copy a Flanker RT into `reaction_time_median_ms` or `PVT_speed_seconds`. PVT and Flanker are different tasks/protocols. New model use needs explicitly compatible data and evaluation; the frozen existing model remains unchanged.

## Local checks using the existing backend dev tools

From this directory, after the existing proposed backend dependencies are available:

```sh
../backend_review/proposed_backend/node_modules/.bin/tsc --noEmit -p tsconfig.json
../backend_review/proposed_backend/node_modules/.bin/tsx --test flanker.test.ts
```

No new npm installation is required. The module itself has no runtime dependency. Tests use synthetic event fixtures for deterministic protocol/scoring verification, not measured human responses. In the managed workspace, the test runner needs approved execution outside its sandbox because tsx uses a local IPC pipe.

## ملخص للفريق

هذا module TypeScript مستقل لتجربة Flanker: أربع محاولات تدريبية ثم 40 محاولة محسوبة، موزعة بالتساوي حسب التوافق واتجاه السهم الأوسط. الإجابة قبل 3000ms تُحسب، وعند 3000ms أو بعدها تُحسب timeout. الخطأ والـtimeout كلاهما غير صحيح، لكن نحتفظ بنوع كل واحد. المحاولات التدريبية لا تدخل في النسبة.

الجلسة الناقصة أو غير الصالحة لا تُرجع accuracy وهمية. التوقيت والتسجيل الفعلي وواجهة Angular/Ionic لم تُبنَ هنا. حقول البروتوكول والنتائج الخام تحتاج اتفاق تخزين وربط منفصل؛ لا تمرروها مباشرة إلى API الحالي، ولا تخلطوا Flanker RT مع PVT. الموديل الحالي لم يتغير، وتشابه عدد المحاولات لا يثبت صلاحية علمية أو طبية.
