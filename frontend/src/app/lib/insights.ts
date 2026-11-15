import type { DayRecord, Level, PersonalBaseline, Recommendation } from '../types';
import { CATEGORY_LEVEL, MEASURE_ORDER, compareLevels, evaluate, type MeasurementKey } from './metrics';

/**
 * Dashboard guidance built from the astronaut's own measurements (never from SHAP reasons, which are model
 * attributions and not medical causes), followed by the generic advisory lines returned with a forecast.
 */
export function buildRecommendations(record: DayRecord | undefined, baseline: PersonalBaseline | null): Recommendation[] {
  if (!record) return [];
  const m = record.measurements;
  const level = (key: MeasurementKey): Level | null => evaluate(key, m[key], baseline);
  const recs: (Recommendation & { priority: Level })[] = [];
  const add = (r: Recommendation & { priority: Level }) => recs.push(r);

  const sleep = level('sleep_duration_hours');
  const heart = level('resting_heart_rate_bpm');
  const fatigue = level('self_report_fatigue_score');
  const stress = level('self_report_stress_score');
  const mood = level('self_report_mood_score');

  if (heart === 'critical') {
    add({
      id: 'surgeon',
      priority: 'critical',
      action: 'Seek review of the resting heart-rate reading',
      reason: 'The reading is in a prototype review band. Follow mission medical procedures; concerning symptoms require prompt review without waiting for another recording.',
    });
  }
  if (record.forecast && CATEGORY_LEVEL[record.forecast.category] === 'critical') {
    add({
      id: 'schedule',
      priority: 'critical',
      action: "Review tomorrow's work and rest schedule",
      reason: 'The forecast is High. Go through the schedule with the responsible crew or mission-support person.',
    });
  }
  if (fatigue === 'critical') {
    add({
      id: 'postpone',
      priority: 'critical',
      action: 'Seek review before an upcoming safety-critical task',
      reason: 'Reported fatigue is high under this prototype display rule. Discuss current symptoms and task demands with the responsible crew or medical support.',
    });
  }
  if (sleep === 'critical') {
    add({
      id: 'rest',
      priority: 'critical',
      action: 'Review sleep opportunity and duty demands',
      reason: 'Reported sleep is short under this prototype display rule. Review recent sleep history and follow the approved work/rest plan.',
    });
  } else if (sleep === 'warning') {
    add({
      id: 'sleep-more',
      priority: 'warning',
      action: 'Review recent sleep and the planned rest period',
      reason: 'Sleep duration alone does not establish current alertness. Consider symptoms, sleep history and upcoming duties under mission procedures.',
    });
  }
  const efficiency = level('sleep_efficiency_pct');
  if (efficiency && efficiency !== 'ok') {
    add({
      id: 'light',
      priority: 'warning',
      action: 'Review the sleep environment and recording quality',
      reason: 'Low reported efficiency can have several explanations. Discuss sleep conditions and follow the approved sleep and lighting plan.',
    });
  }
  if (heart === 'warning' || level('hrv_rmssd_ms') === 'warning' || level('hrv_rmssd_ms') === 'critical') {
    add({
      id: 'recheck',
      priority: 'warning',
      action: 'Check recording conditions and follow the remeasurement protocol',
      reason: 'Recent exercise, posture and recording quality can affect heart rate and HRV. Follow mission procedures; symptoms should not wait for a repeat reading.',
    });
  }
  const reaction = level('reaction_time_median_ms');
  if (reaction && reaction !== 'ok') {
    add({
      id: 'retest',
      priority: 'warning',
      action: 'Review reaction-task conditions and upcoming duties',
      reason: 'A slower result can reflect several factors, including device timing. Follow the task protocol for any repeat; this browser demonstration does not establish readiness.',
    });
  }
  if ((stress && stress !== 'ok') || (mood && mood !== 'ok')) {
    add({
      id: 'connect',
      priority: 'warning',
      action: 'Consider a private check-in with an appropriate support person',
      reason: 'Reported stress or mood has entered a prototype review band. Discuss context and support needs; these ratings do not diagnose a condition.',
    });
  }

  recs.sort((a, b) => compareLevels(a.priority, b.priority));
  const local: Recommendation[] = recs.slice(0, 4);

  if (!record.forecast) {
    local.push({
      id: 'forecast-unavailable',
      priority: 'none',
      action: 'No forecast-based recommendation available.',
      reason: record.status === 'collecting_baseline'
        ? 'This record is part of calibration and has no forecast. Any measurement guidance shown separately uses prototype display rules.'
        : 'No usable prediction is available for this record. Any measurement concerns remain relevant; missing output is not a normal assessment.',
    });
  }

  const advisory: Recommendation[] = (record.forecast?.advisoryActions ?? []).map((text, i) => ({
    id: `advisory-${i}`,
    priority: 'none',
    action: text,
    reason: record.forecast?.origin === 'simulated_example'
      ? 'Example advisory. Saved fictional presentation content; no model request was made.'
      : 'Advisory returned with this record’s model-generated forecast. This prototype makes no autonomous medical or mission decisions.',
  }));

  return [...local, ...advisory].slice(0, 6);
}

/** Overall color level of a record: worst level of the measurements that have one. */
export function recordLevel(record: DayRecord, baseline: PersonalBaseline | null): Level | null {
  let worst: Level | null = null;
  for (const key of MEASURE_ORDER) {
    const l = evaluate(key, record.measurements[key], baseline);
    if (l === null) continue;
    if (worst === null || compareLevels(l, worst) < 0) worst = l;
  }
  return worst;
}
