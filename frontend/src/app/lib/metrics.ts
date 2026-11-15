import type { FatigueCategory, Level, MeasurementKey, PersonalBaseline } from '../types';
import { MEASUREMENT_KEYS } from '../types';

export type { MeasurementKey } from '../types';

export type GroupId = 'sleep' | 'heart' | 'cognition' | 'self' | 'load';

type Rule =
  | { kind: 'absolute'; warning: number; critical: number; lowerIsWorse: boolean }
  | { kind: 'baseline'; warningPct: number; criticalPct: number; lowerIsWorse: boolean };

export interface Measure {
  key: MeasurementKey;
  label: string;
  unit: string;
  decimals: number;
  /** Input bounds from the backend (engineering limits, not medical limits) */
  min: number;
  max: number;
  integer: boolean;
  step: number;
  group: GroupId;
  /** Chart y-axis range */
  domain: [number, number];
  /** Key of this measure in the backend's personal baseline, when it has one */
  baselineKey?: string;
  /** Status level rule. Measures without a rule are shown without a color level. */
  rule?: Rule;
  /** Short definition shown under the form field */
  hint: string;
}

/**
 * Bounds and definitions follow FRONTEND_MEASUREMENTS.csv of the AI team. The status rules are the dashboard's own:
 * where and why each applies is written in src/app/lib/guide.ts and shown in the Guide view.
 */
export const MEASURES: Record<MeasurementKey, Measure> = {
  sleep_duration_hours: {
    key: 'sleep_duration_hours',
    label: 'Sleep duration',
    unit: 'h',
    decimals: 1,
    min: 0.1,
    max: 16,
    integer: false,
    step: 0.1,
    group: 'sleep',
    domain: [4, 10],
    baselineKey: 'baseline_sleep_duration_hours',
    rule: { kind: 'absolute', warning: 7, critical: 6, lowerIsWorse: true },
    hint: 'Total sleep of the most recent sleep episode completed before the cutoff.',
  },
  sleep_efficiency_pct: {
    key: 'sleep_efficiency_pct',
    label: 'Sleep efficiency',
    unit: '%',
    decimals: 0,
    min: 10,
    max: 100,
    integer: false,
    step: 0.1,
    group: 'sleep',
    domain: [60, 100],
    rule: { kind: 'absolute', warning: 85, critical: 75, lowerIsWorse: true },
    hint: 'Percent of the sleep opportunity (time in bed) you actually slept.',
  },
  sleep_onset_delay_minutes: {
    key: 'sleep_onset_delay_minutes',
    label: 'Time to fall asleep',
    unit: 'min',
    decimals: 0,
    min: 0,
    max: 300,
    integer: false,
    step: 0.1,
    group: 'sleep',
    domain: [0, 60],
    hint: 'Minutes between bedtime and sleep onset.',
  },
  awakenings_count: {
    key: 'awakenings_count',
    label: 'Awakenings',
    unit: 'times',
    decimals: 0,
    min: 0,
    max: 100,
    integer: true,
    step: 1,
    group: 'sleep',
    domain: [0, 8],
    hint: 'Number of times you woke during the sleep episode (whole number).',
  },
  sleep_midpoint_deviation_minutes: {
    key: 'sleep_midpoint_deviation_minutes',
    label: 'Sleep timing shift',
    unit: 'min',
    decimals: 0,
    min: -720,
    max: 720,
    integer: false,
    step: 0.1,
    group: 'sleep',
    domain: [-120, 120],
    hint: 'Middle of your sleep versus the planned schedule: negative = earlier, positive = later.',
  },
  resting_heart_rate_bpm: {
    key: 'resting_heart_rate_bpm',
    label: 'Resting heart rate',
    unit: 'bpm',
    decimals: 0,
    min: 30,
    max: 220,
    integer: false,
    step: 0.1,
    group: 'heart',
    domain: [50, 100],
    baselineKey: 'baseline_resting_heart_rate_bpm',
    rule: { kind: 'absolute', warning: 90, critical: 101, lowerIsWorse: false },
    hint: 'Mean heart rate in a five-minute quiet seated recording ending before the cutoff.',
  },
  hrv_rmssd_ms: {
    key: 'hrv_rmssd_ms',
    label: 'HRV (RMSSD)',
    unit: 'ms',
    decimals: 0,
    min: 1,
    max: 300,
    integer: false,
    step: 0.1,
    group: 'heart',
    domain: [10, 60],
    baselineKey: 'baseline_hrv_rmssd_ms',
    rule: { kind: 'baseline', warningPct: 20, criticalPct: 35, lowerIsWorse: true },
    hint: 'RMSSD in milliseconds from the same five-minute quiet recording as heart rate.',
  },
  reaction_time_median_ms: {
    key: 'reaction_time_median_ms',
    label: 'Reaction time (median)',
    unit: 'ms',
    decimals: 0,
    min: 100,
    max: 2000,
    integer: false,
    step: 0.1,
    group: 'cognition',
    domain: [250, 450],
    baselineKey: 'baseline_reaction_time_median_ms',
    rule: { kind: 'baseline', warningPct: 10, criticalPct: 20, lowerIsWorse: false },
    hint: 'Median of 60 responses in the variable-duration reaction demo (use the full task in this tab).',
  },
  reaction_time_lapses_count: {
    key: 'reaction_time_lapses_count',
    label: 'Reaction lapses',
    unit: 'of 60',
    decimals: 0,
    min: 0,
    max: 60,
    integer: true,
    step: 1,
    group: 'cognition',
    domain: [0, 30],
    hint: 'How many of the 60 responses took 500 ms or longer (whole number).',
  },
  attention_accuracy_pct: {
    key: 'attention_accuracy_pct',
    label: 'Externally measured attention-task accuracy',
    unit: '%',
    decimals: 0,
    min: 0,
    max: 100,
    integer: false,
    step: 0.1,
    group: 'cognition',
    domain: [60, 100],
    hint: 'Enter percent correct from an external attention task. This app does not administer a complete attention test.',
  },
  self_report_stress_score: {
    key: 'self_report_stress_score',
    label: 'Stress',
    unit: '/ 10',
    decimals: 1,
    min: 0,
    max: 10,
    integer: false,
    step: 0.1,
    group: 'self',
    domain: [0, 10],
    rule: { kind: 'absolute', warning: 5, critical: 7, lowerIsWorse: false },
    hint: 'Custom 0 to 10 score from today\'s check-in; higher means more stress.',
  },
  self_report_fatigue_score: {
    key: 'self_report_fatigue_score',
    label: 'Fatigue (self-report)',
    unit: '/ 10',
    decimals: 1,
    min: 0,
    max: 10,
    integer: false,
    step: 0.1,
    group: 'self',
    domain: [0, 10],
    rule: { kind: 'absolute', warning: 5, critical: 7, lowerIsWorse: false },
    hint: 'Custom 0 to 10 score of how fatigued you feel today; higher means more fatigue.',
  },
  self_report_mood_score: {
    key: 'self_report_mood_score',
    label: 'Mood',
    unit: '/ 10',
    decimals: 1,
    min: 0,
    max: 10,
    integer: false,
    step: 0.1,
    group: 'self',
    domain: [0, 10],
    rule: { kind: 'absolute', warning: 5, critical: 3, lowerIsWorse: true },
    hint: 'Custom 0 to 10 score; higher means a more positive mood.',
  },
  workload_hours: {
    key: 'workload_hours',
    label: 'Workload',
    unit: 'h',
    decimals: 1,
    min: 0,
    max: 24,
    integer: false,
    step: 0.1,
    group: 'load',
    domain: [0, 16],
    hint: 'Non-overlapping duty hours in the 24 hours before the cutoff, excluding sleep.',
  },
  exercise_minutes: {
    key: 'exercise_minutes',
    label: 'Exercise',
    unit: 'min',
    decimals: 0,
    min: 0,
    max: 480,
    integer: false,
    step: 0.1,
    group: 'load',
    domain: [0, 120],
    hint: 'Minutes of exercise in the 24 hours before the cutoff.',
  },
};

export interface Group {
  id: GroupId;
  title: string;
  /** Measure shown big with a chart */
  primary: MeasurementKey;
  members: MeasurementKey[];
}

export const GROUPS: Group[] = [
  {
    id: 'sleep',
    title: 'Sleep',
    primary: 'sleep_duration_hours',
    members: [
      'sleep_duration_hours',
      'sleep_efficiency_pct',
      'sleep_onset_delay_minutes',
      'awakenings_count',
      'sleep_midpoint_deviation_minutes',
    ],
  },
  {
    id: 'heart',
    title: 'Heart',
    primary: 'resting_heart_rate_bpm',
    members: ['resting_heart_rate_bpm', 'hrv_rmssd_ms'],
  },
  {
    id: 'cognition',
    title: 'Reaction & attention',
    primary: 'reaction_time_median_ms',
    members: ['reaction_time_median_ms', 'reaction_time_lapses_count', 'attention_accuracy_pct'],
  },
  {
    id: 'self',
    title: 'Self-report',
    primary: 'self_report_fatigue_score',
    members: ['self_report_fatigue_score', 'self_report_stress_score', 'self_report_mood_score'],
  },
  {
    id: 'load',
    title: 'Workload',
    primary: 'workload_hours',
    members: ['workload_hours', 'exercise_minutes'],
  },
];

/** All measures in display order (group by group). */
export const MEASURE_ORDER: MeasurementKey[] = GROUPS.flatMap((g) => g.members);

export function isMeasurementKey(value: string): value is MeasurementKey {
  return (MEASUREMENT_KEYS as readonly string[]).includes(value);
}

/**
 * Color level of a value, or null when the measure has no rule (or its personal baseline is not ready yet).
 * Baseline rules compare with the astronaut's own calibration baseline, not with a population value.
 */
export function evaluate(key: MeasurementKey, value: number, baseline: PersonalBaseline | null): Level | null {
  const measure = MEASURES[key];
  const rule = measure.rule;
  if (!rule) return null;

  if (rule.kind === 'absolute') {
    if (rule.lowerIsWorse) {
      if (value < rule.critical) return 'critical';
      if (value < rule.warning) return 'warning';
      return 'ok';
    }
    if (value >= rule.critical) return 'critical';
    if (value >= rule.warning) return 'warning';
    return 'ok';
  }

  const base = measure.baselineKey ? baseline?.[measure.baselineKey] : undefined;
  if (!base) return null;
  const changePct = ((value - base) / base) * 100;
  const worse = rule.lowerIsWorse ? -changePct : changePct;
  if (worse >= rule.criticalPct) return 'critical';
  if (worse >= rule.warningPct) return 'warning';
  return 'ok';
}

const SEVERITY: Record<Level, number> = { ok: 0, warning: 1, critical: 2 };

export function worstLevel(levels: (Level | null)[]): Level | null {
  return levels.reduce<Level | null>((worst, l) => {
    if (l === null) return worst;
    return worst === null || SEVERITY[l] > SEVERITY[worst] ? l : worst;
  }, null);
}

export function compareLevels(a: Level, b: Level): number {
  return SEVERITY[b] - SEVERITY[a];
}

export const LEVEL_LABEL: Record<Level, string> = {
  ok: 'Nominal',
  warning: 'Watch',
  critical: 'Action needed',
};

export const CATEGORY_LEVEL: Record<FatigueCategory, Level> = {
  Low: 'ok',
  Moderate: 'warning',
  High: 'critical',
};

export function formatValue(key: MeasurementKey, value: number): string {
  return value.toFixed(MEASURES[key].decimals);
}

/** Change of the value at `index` against the average of up to 7 records before it. */
export function deltaLabel(key: MeasurementKey, values: number[], index: number): string {
  const prior = values.slice(Math.max(0, index - 7), index);
  if (prior.length === 0) return 'First record';
  const avg = prior.reduce((sum, v) => sum + v, 0) / prior.length;
  const delta = values[index] - avg;
  const sign = delta > 0 ? '+' : delta < 0 ? '−' : '±';
  const { decimals, unit } = MEASURES[key];
  return `${sign}${Math.abs(delta).toFixed(decimals)} ${unit} vs prior avg`;
}

const FEATURE_PREFIXES: [string, string][] = [
  ['baseline_', 'Baseline '],
  ['prior_3day_mean_', '3-day mean '],
];

const FEATURE_NAMES: Record<string, string> = {
  sleep_duration_delta_from_baseline_hours: 'Sleep change from baseline',
  heart_rate_delta_from_baseline_bpm: 'Heart rate change from baseline',
  hrv_delta_from_baseline_ms: 'HRV change from baseline',
  reaction_time_change_from_baseline_pct: 'Reaction time change from baseline',
};

/** Readable name for a model feature (a measurement, a baseline value, a recent mean or a change). */
export function featureLabel(feature: string): string {
  if (isMeasurementKey(feature)) return MEASURES[feature].label;
  if (FEATURE_NAMES[feature]) return FEATURE_NAMES[feature];
  for (const [prefix, text] of FEATURE_PREFIXES) {
    if (feature.startsWith(prefix)) {
      const rest = feature.slice(prefix.length);
      const known = MEASURE_ORDER.find((k) => k === rest || k.startsWith(rest.replace(/_ms$|_hours$|_bpm$/, '')));
      return text + (known ? MEASURES[known].label.toLowerCase() : rest.replace(/_/g, ' '));
    }
  }
  return feature.replace(/_/g, ' ');
}
