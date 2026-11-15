import type { MeasurementKey } from '../types';
import type { Level } from '../types';

export interface Source {
  short: string;
  label: string;
  url: string;
}

export const SOURCES = {
  hrpHazards: {
    short: 'NASA HRP hazards',
    label: 'NASA Human Research Program: 5 Hazards of Human Spaceflight',
    url: 'https://www.nasa.gov/hrp/hazards/',
  },
  hrpRisks: {
    short: 'NASA HRP risks',
    label: 'NASA Human Research Program: Risks of Human Spaceflight',
    url: 'https://www.nasa.gov/hrp/risks/',
  },
  rstSpinoff: {
    short: 'NASA Spinoff 2013',
    label: 'NASA Spinoff 2013: the Reaction Self Test fatigue check developed for astronauts',
    url: 'https://spinoff.nasa.gov/Spinoff2013/hm_1.html',
  },
  rstStudy: {
    short: 'ISS Reaction Self Test study',
    label:
      'Sleep deficiency in spaceflight is associated with degraded neurobehavioral functions and elevated stress in astronauts on six-month missions aboard the ISS (PMC8919197)',
    url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC8919197/',
  },
  barger: {
    short: 'Barger et al. 2014',
    label: 'Barger et al. 2014, The Lancet Neurology: sleep deficiency and sleep medication use in astronauts (PMC4188436)',
    url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC4188436/',
  },
  aasm: {
    short: 'AASM/SRS 2015',
    label: 'AASM and Sleep Research Society 2015 consensus: adults should sleep 7 or more hours per night (PMC4434546)',
    url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/',
  },
  aha: {
    short: 'American Heart Association',
    label: 'American Heart Association: Tachycardia, fast heart rate',
    url: 'https://www.heart.org/en/health-topics/arrhythmia/about-arrhythmia/tachycardia--fast-heart-rate',
  },
  pvtb: {
    short: 'Basner et al. 2011',
    label: 'Basner et al. 2011: Validity and sensitivity of a brief Psychomotor Vigilance Test (PVT-B) (PMC3197786)',
    url: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786/',
  },
  astraRepo: {
    short: 'ASTRA-SHIELD AI repository',
    label: 'ASTRA-SHIELD AI repository (team): data dictionary, measurement definitions, model findings and limits',
    url: 'https://github.com/magdiemad5s/Space-apps',
  },
} satisfies Record<string, Source>;

export type SourceId = keyof typeof SOURCES;

export interface MeasureGuide {
  measure: string;
  why: string;
  /** What each color means. Omitted when the measure has no level. */
  levels?: Record<Level, string>;
  /** Where the levels come from, or that the measure has no level */
  basis: string;
  escalate?: string;
  sources: SourceId[];
}

const NO_LEVEL =
  'No color level is defined for this measurement. The model still uses it, and it is shown for context.';

export const GUIDE: Record<MeasurementKey, MeasureGuide> = {
  sleep_duration_hours: {
    measure:
      'Total sleep of the most recent sleep episode that ended before the daily cutoff. Take it from your sleep tracker.',
    why: 'Crews have 8.5 hours scheduled for sleep, yet measured sleep on the ISS averages about 6 hours. Light, noise, workload and shifting schedules disturb the body clock.',
    levels: { ok: '7 h or more', warning: '6 – 6.9 h', critical: 'under 6 h' },
    basis:
      '7 hours is the adult recommendation from AASM and the Sleep Research Society. On the ISS, sleep under 6 hours was linked to slower responses, more stress and higher workload.',
    escalate:
      'Three nights in a row under 6 hours, or poor sleep together with low mood: raise it with the flight surgeon.',
    sources: ['barger', 'aasm', 'rstStudy', 'hrpRisks'],
  },
  sleep_efficiency_pct: {
    measure:
      'Percent of your sleep opportunity (from bedtime, including the time to fall asleep and awake periods) that you actually slept. Take it from your sleep tracker.',
    why: 'Low efficiency means delayed or broken sleep, so the hours alone can overstate how well you recovered.',
    levels: { ok: '85% or more', warning: '75 – 84%', critical: 'under 75%' },
    basis: 'Team assumption (a commonly used 85% cut-off). The model uses the raw value.',
    escalate: 'Low efficiency for several nights even with enough hours: talk to the flight surgeon.',
    sources: ['astraRepo'],
  },
  sleep_onset_delay_minutes: {
    measure: 'Minutes between going to bed and falling asleep, for the most recent sleep episode.',
    why: 'Long delays can reflect stress, bright light or a shifted schedule.',
    basis: NO_LEVEL,
    sources: ['astraRepo'],
  },
  awakenings_count: {
    measure: 'Number of times you woke up during the most recent sleep episode (a whole number).',
    why: 'Frequent awakenings break up sleep and lower its quality.',
    basis: NO_LEVEL,
    sources: ['astraRepo'],
  },
  sleep_midpoint_deviation_minutes: {
    measure:
      'How far the middle of your sleep was from your planned sleep schedule, in minutes: negative means earlier, positive means later.',
    why: 'Shifts of the sleep window disturb the body clock, which is common with changing duty schedules.',
    basis: NO_LEVEL,
    sources: ['astraRepo', 'hrpHazards'],
  },
  resting_heart_rate_bpm: {
    measure:
      'Sit still and relaxed for a five-minute recording that ends before the daily cutoff. Log the mean heart rate from your watch or strap.',
    why: 'In weightlessness, body fluids shift toward the head and the heart and blood vessels adapt. This can change heart rate and raise cardiovascular risk.',
    levels: { ok: 'under 90 bpm', warning: '90 – 100 bpm', critical: 'over 100 bpm' },
    basis:
      'A resting rate over 100 bpm is tachycardia (American Heart Association). The 90 bpm watch level is a team assumption.',
    escalate:
      'Over 100 bpm at rest after re-measuring, or any chest pain, palpitations, dizziness or fainting: contact the flight surgeon now.',
    sources: ['aha', 'hrpRisks'],
  },
  hrv_rmssd_ms: {
    measure:
      'Take it from the same five-minute quiet recording as heart rate. It must be RMSSD in milliseconds; other HRV measures are not interchangeable.',
    why: 'Heart rate variability usually drops with stress, poor sleep and fatigue, so a low value can be an early sign of strain.',
    levels: {
      ok: 'less than 20% below your baseline',
      warning: '20 – 34% below your baseline',
      critical: '35% or more below your baseline',
    },
    basis:
      'HRV differs a lot between people, so the level compares with your own calibration baseline (available after 7 records). The percentages are a team assumption.',
    escalate:
      'A large drop together with a high resting heart rate or poor sleep: tell the crew and ask the flight surgeon.',
    sources: ['hrpRisks', 'astraRepo'],
  },
  reaction_time_median_ms: {
    measure:
      'Use the reaction test in the Check-in tab: tap as soon as the pad turns green, 60 times. Only a completed full task can populate the form; the 10-response quick demo cannot. Duration varies, with random waits of 2–6 seconds in the full task. Take it at the same time each day.',
    why: "Sleep loss and fatigue slow reactions and cause lapses of attention. NASA's Reaction Self Test uses this kind of test on the ISS so astronauts can check their own fatigue.",
    levels: {
      ok: 'less than 10% above your baseline',
      warning: '10 – 19% above your baseline',
      critical: '20% or more above your baseline',
    },
    basis:
      'The level compares with your own calibration baseline (available after 7 records). The percentages are a team assumption. The test is a PVT-like demonstration, not a validated clinical PVT.',
    escalate:
      'Action level on two tests in a row: postpone safety-critical tasks and tell the crew. Together with poor sleep, raise it with the flight surgeon.',
    sources: ['rstSpinoff', 'rstStudy', 'pvtb'],
  },
  reaction_time_lapses_count: {
    measure: 'Count how many of the 60 responses in the reaction test took 500 ms or longer (a whole number).',
    why: 'Lapses are missed or very slow responses. They rise with sleep loss.',
    basis: `${NO_LEVEL} In this test a lapse is a response of 500 ms or more.`,
    sources: ['pvtb', 'astraRepo'],
  },
  attention_accuracy_pct: {
    measure: 'Externally measured percent correct in an attention task, entered manually. This app does not administer a complete attention test. If not measured, leave it blank; the current model requires a supplied value before a record can be saved and used for a forecast.',
    why: 'Accuracy can fall when you are tired even if your speed holds.',
    basis: NO_LEVEL,
    sources: ['astraRepo'],
  },
  self_report_stress_score: {
    measure: 'In the daily check-in, rate your stress from 0 (none) to 10 (extreme). Rate quickly and honestly.',
    why: 'Isolation, confinement, workload and distance from Earth can raise stress and affect sleep, mood and teamwork on long missions.',
    levels: { ok: 'under 5', warning: '5 – 6.9', critical: '7 or more' },
    basis: 'Team assumption. This is a custom score, not a validated questionnaire.',
    escalate:
      'Stress of 7 or more for several days, or stress that affects sleep or teamwork: talk to the flight surgeon or the behavioral health support team.',
    sources: ['hrpRisks', 'hrpHazards'],
  },
  self_report_fatigue_score: {
    measure:
      'In the daily check-in, rate how fatigued you feel today from 0 (none) to 10 (extreme). It is a custom score, not the KSS.',
    why: 'Your own sense of fatigue is an early and useful signal, and it is one of the strongest inputs of the forecast model.',
    levels: { ok: 'under 5', warning: '5 – 6.9', critical: '7 or more' },
    basis: 'Team assumption. This is a custom score, not a validated questionnaire.',
    escalate: 'Fatigue of 7 or more: postpone safety-critical tasks and tell the crew.',
    sources: ['astraRepo', 'rstStudy'],
  },
  self_report_mood_score: {
    measure: 'In the daily check-in, rate how you feel from 0 (very low) to 10 (great). The trend matters more than one day.',
    why: 'Isolation, confinement and distance from Earth can affect mood, behavior and teamwork on long missions.',
    levels: { ok: '5 – 10', warning: '3 – 4.9', critical: 'under 3' },
    basis: 'Team assumption. This is a custom score, not a validated questionnaire.',
    escalate:
      'Low mood for several days, trouble sleeping, or any thoughts of self-harm: talk to the flight surgeon or the behavioral health support team.',
    sources: ['hrpRisks', 'hrpHazards'],
  },
  workload_hours: {
    measure: 'Duty hours in the 24 hours before the daily cutoff, without overlaps and without the sleep episode.',
    why: 'Long duty days are a main driver of fatigue and cut into recovery time.',
    basis: NO_LEVEL,
    sources: ['astraRepo', 'hrpRisks'],
  },
  exercise_minutes: {
    measure: 'Minutes of exercise in the 24 hours before the daily cutoff.',
    why: 'Daily exercise counters bone and muscle loss in weightlessness.',
    basis: NO_LEVEL,
    sources: ['hrpRisks', 'astraRepo'],
  },
};
