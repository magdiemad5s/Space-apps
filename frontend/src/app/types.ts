/**
 * Data contract between the dashboard and the ASTRA-SHIELD backend (proposed_backend of the AI team).
 * The dashboard sends 15 canonical measurements per daily record and shows what the backend returns.
 */

export type Level = 'ok' | 'warning' | 'critical';

/** Canonical measurement names, exactly as the backend expects them. */
export const MEASUREMENT_KEYS = [
  'sleep_duration_hours',
  'sleep_efficiency_pct',
  'sleep_onset_delay_minutes',
  'awakenings_count',
  'sleep_midpoint_deviation_minutes',
  'resting_heart_rate_bpm',
  'hrv_rmssd_ms',
  'reaction_time_median_ms',
  'reaction_time_lapses_count',
  'attention_accuracy_pct',
  'self_report_stress_score',
  'self_report_fatigue_score',
  'self_report_mood_score',
  'workload_hours',
  'exercise_minutes',
] as const;

export type MeasurementKey = (typeof MEASUREMENT_KEYS)[number];
export type Measurements = Record<MeasurementKey, number>;

export type RecordStatus = 'collecting_baseline' | 'model_unavailable' | 'completed';
export type FatigueCategory = 'Low' | 'Moderate' | 'High';

/** One SHAP reason from the fatigue classifier (an attribution, not a medical cause). */
export interface Reason {
  feature: string;
  value: number;
  shapValue: number;
  direction: 'supports_prediction' | 'opposes_prediction' | 'neutral';
}

/** Next-day forecast. Only present for a completed record. */
export interface Forecast {
  /** Provenance of this forecast, independent of whether the backend is currently online. */
  origin: 'model_service' | 'simulated_example';
  /** Prototype severity index, 0 to 100. Not a medical percentage. */
  points: number;
  category: FatigueCategory;
  /** Separate 0 to 10 regression model; may disagree with the category band */
  score: number | null;
  /** Uncalibrated class probabilities of the classifier (the index is 50·moderate + 100·high) */
  probabilities: { low: number; moderate: number; high: number } | null;
  targetTimestamp: string | null;
  reasons: Reason[];
  advisoryActions: string[];
  reactionForecastMs: number | null;
  outOfRangeFeatures: string[];
  physiologyOutlier: boolean | null;
}

export interface DayRecord {
  /** 1-based record number for this astronaut */
  index: number;
  /** Daily cutoff of the observation, ISO UTC */
  timestamp: string;
  measurements: Measurements;
  /** Preserve exact optional note for an identical saved-outage retry. */
  journalText?: string | null;
  status: RecordStatus;
  forecast: Forecast | null;
}

export interface Recommendation {
  id: string;
  priority: Level | 'none';
  action: string;
  reason: string;
}

export type PersonalBaseline = Record<string, number>;

export interface Snapshot {
  astronautId: string;
  /** 'backend' = history read from the running backend; 'demo' = simulated example records */
  source: 'backend' | 'demo';
  backend: { online: boolean; modelReady: boolean };
  calibrationRequired: number;
  /** Oldest first */
  records: DayRecord[];
  baseline: PersonalBaseline | null;
}
