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
  const recs: Recommendation[] = [];
  const add = (r: Recommendation) => recs.push(r);

  const sleep = level('sleep_duration_hours');
  const heart = level('resting_heart_rate_bpm');
  const fatigue = level('self_report_fatigue_score');
  const stress = level('self_report_stress_score');
  const mood = level('self_report_mood_score');

  if (heart === 'critical') {
    add({
      id: 'surgeon',
      priority: 'critical',
      action: 'Contact the flight surgeon',
      reason: 'A resting heart rate over 100 bpm needs a medical review. Rest 10 minutes and measure again first.',
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
      action: 'Postpone safety-critical tasks',
      reason: 'At this level of reported fatigue, slow reactions and lapses raise the risk of errors.',
    });
  }
  if (sleep === 'critical') {
    add({
      id: 'rest',
      priority: 'critical',
      action: 'Take a protected 8-hour sleep period',
      reason: 'Recovering the sleep deficit is the fastest way to lower fatigue.',
    });
  } else if (sleep === 'warning') {
    add({
      id: 'sleep-more',
      priority: 'warning',
      action: 'Add 60 minutes of sleep tonight',
      reason: 'Adults need 7 or more hours; short sleep is a main driver of fatigue.',
    });
  }
  const efficiency = level('sleep_efficiency_pct');
  if (efficiency && efficiency !== 'ok') {
    add({
      id: 'light',
      priority: 'warning',
      action: 'Dim cabin lighting 2 hours before sleep',
      reason: 'Bright evening light delays the body clock and breaks up sleep.',
    });
  }
  if (heart === 'warning' || level('hrv_rmssd_ms') === 'warning' || level('hrv_rmssd_ms') === 'critical') {
    add({
      id: 'recheck',
      priority: 'warning',
      action: 'Rest 10 minutes, then repeat the quiet heart recording',
      reason: 'Stress, exercise and fluid shifts can change heart rate and HRV for a short time.',
    });
  }
  const reaction = level('reaction_time_median_ms');
  if (reaction && reaction !== 'ok') {
    add({
      id: 'retest',
      priority: 'warning',
      action: 'Repeat the reaction test after your next rest period',
      reason: 'A second test shows whether the slowdown is temporary.',
    });
  }
  if ((stress && stress !== 'ok') || (mood && mood !== 'ok')) {
    add({
      id: 'connect',
      priority: 'warning',
      action: 'Do 10 minutes of paced breathing and talk with a crewmate',
      reason: 'Isolation and confinement raise stress and lower mood; staying connected helps.',
    });
  }

  recs.sort((a, b) => compareLevels(a.priority, b.priority));
  const local = recs.slice(0, 4);

  if (local.length === 0 && !record.forecast) {
    local.push({
      id: 'keep',
      priority: 'ok',
      action: 'Keep your current routine',
      reason: 'The measurements that have a level are within range. Complete the next daily record on time.',
    });
  }

  const advisory: Recommendation[] = (record.forecast?.advisoryActions ?? []).map((text, i) => ({
    id: `advisory-${i}`,
    priority: 'ok',
    action: text,
    reason: 'Advisory line from the model service. This prototype makes no autonomous medical or mission decisions.',
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
