#!/usr/bin/env python3
"""Generate reproducible ASTRA-SHIELD synthetic demonstration observations.
No real astronaut measurements; assumptions are not fitted to human biology.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
SEED = 20261114
VERSION = 'astra_synthetic_v1.0'
START = pd.Timestamp('2026-01-01T18:00:00Z')
SOURCE = 'ASTRA-SHIELD proposal and uncalibrated custom simulation; no measured NASA data'
rng = np.random.default_rng(SEED)

TEMPLATES = {
 'train': {
 'low': ['I felt composed during the scheduled work.', 'The tasks felt manageable and I stayed at ease.', 'My workload was comfortable and I felt settled.', 'I approached the routine calmly today.'],
 'moderate': ['I noticed some tension while working through the plan.', 'A few interruptions left me somewhat strained.', 'I felt pressure at times but could continue the routine.', 'I had mixed feelings about how the shift went.'],
 'high': ['The demands felt overwhelming and I struggled to settle.', 'I felt intensely pressured by the continuing demands.', 'Persistent tension made the shift difficult for me.', 'I found it hard to unwind after the demanding work.'],
 'ops': ['checked the ventilation panel', 'organized sample containers', 'reviewed the exercise schedule', 'inspected the storage rack', 'prepared instrument notes', 'updated the task board', 'tested a spare connector', 'sorted the maintenance tools'],
 'context': ['There were several interruptions.', 'The cabin was quiet for a while.', 'I worked alongside a teammate.', 'The checklist had changed.', 'I had a scheduled meal break.', 'A message from home arrived.', 'I reviewed the plan with the team.', 'There was time to review my notes.'],
 'fatigue': ['My energy varied as the day went on.', 'I noticed how my energy changed between activities.', 'I paid attention to my pace during the routine.', 'I paused briefly between scheduled tasks.'],
 },
 'validation': {
 'low': ['I was relaxed while completing my assignments.', 'The duties seemed straightforward and I remained untroubled.', 'I felt confident about the ordinary work.', 'The day left me with a steady sense of calm.'],
 'moderate': ['I was a little unsettled by the competing demands.', 'Some uneasiness came and went throughout my duties.', 'I felt stretched by parts of the schedule.', 'A measure of strain followed the unplanned changes.'],
 'high': ['I was deeply distressed by the pressure of the assignments.', 'The strain felt relentless and hard to manage.', 'I felt swamped by the demands throughout the shift.', 'I remained very agitated after finishing the work.'],
 'ops': ['catalogued the replacement seals', 'rearranged supply boxes', 'verified the camera mounts', 'prepared the session timer', 'reviewed the cargo inventory', 'examined a water filter', 'configured a practice console', 'cleaned the work surface'],
 'context': ['An appointment was rescheduled.', 'A colleague offered assistance.', 'I had an extended discussion.', 'The workspace was crowded.', 'I revisited earlier instructions.', 'A reminder arrived late.', 'I ate with the other crew.', 'The background noise varied.'],
 'fatigue': ['My alertness was uneven across the shift.', 'I considered my level of energy after each assignment.', 'I took a short pause during a transition.', 'I tried to keep a consistent pace.'],
 },
 'test': {
 'low': ['I handled the planned duties with little worry.', 'I felt peaceful about my responsibilities.', 'The routine brought no particular feeling of strain.', 'My assignments left me feeling unhurried.'],
 'moderate': ['I was occasionally worried by the pace of the duties.', 'The schedule left me mildly on edge.', 'A few moments felt taxing during my responsibilities.', 'I carried a noticeable but manageable sense of pressure.'],
 'high': ['I felt severely burdened by everything required of me.', 'The pressure was exhausting and I could not relax.', 'I was highly anxious about keeping up with the duties.', 'The emotional burden felt extreme throughout the routine.'],
 'ops': ['examined the lighting controls', 'labelled experimental trays', 'rehearsed an equipment handover', 'reviewed the communications queue', 'checked the glove inventory', 'inspected the camera battery', 'assembled a practice fixture', 'recorded the supply rotation'],
 'context': ['A briefing ran longer than expected.', 'I exchanged notes with another crew member.', 'The next session began early.', 'There was a change of priorities.', 'I reread a set of guidance notes.', 'I spent a period working alone.', 'The handover went through several details.', 'A planned conversation took place.'],
 'fatigue': ['I kept track of changes in my alertness.', 'I gave some thought to how rested I felt.', 'My pace shifted between the different duties.', 'I took a moment to assess my energy.'],
 }
}
used_journals = set()
def choose(values):
 return values[int(rng.integers(len(values)))]
def journal(split, level):
 bank = TEMPLATES[split]
 for _ in range(1000):
  text = f"{choose(bank[level])} I {choose(bank['ops'])} and {choose(bank['ops'])}. {choose(bank['context'])} {choose(bank['fatigue'])} I recorded {int(rng.integers(2, 25))} checklist items for follow-up."
  if text not in used_journals:
   used_journals.add(text)
   return text
 raise RuntimeError('Unable to generate unique journal')
def class_of(score):
 return 'low' if score < 4 else ('moderate' if score < 7 else 'high')
def rounded(value, lo, hi, digits=3):
 return round(float(np.clip(value, lo, hi)), digits)

def generate():
 # Participant-disjoint deterministic assignment, randomized before generation.
 ids = np.arange(1, 121)
 split_order = rng.permutation(ids)
 assignment = {int(i): ('train' if n < 84 else ('validation' if n < 102 else 'test')) for n, i in enumerate(split_order)}
 records = []
 for n in ids:
  pid = f'SIM_{n:03d}'
  split = assignment[int(n)]
  hr_base = rng.uniform(52, 76)
  hrv_base = rng.uniform(32, 76)
  rt_base = rng.uniform(225, 295)
  sleep_need = rng.uniform(7.4, 8.5)
  fatigue = rng.uniform(1.3, 3.5)
  stress = rng.uniform(1.6, 3.6)
  circadian = rng.normal(0, 12)
  for day in range(-6, 62):
   calibration = day <= 0
   # Hidden schedule perturbations and persistence; these latents are not saved.
   duty_pressure = 0 if calibration else (rng.uniform(1.8, 4.2) if rng.random() < .19 else rng.normal(0, .7))
   workload = rounded(rng.normal(6.6 if calibration else 8.2, 1.1) + duty_pressure, 3, 15)
   exercise = rounded(rng.normal(55 if calibration else 42, 18) - 3*duty_pressure, 0, 110)
   stress = np.clip(.58*stress + .42*(2.1 + .7*max(0, workload-7) + .8*duty_pressure) + rng.normal(0,.8), 0, 10)
   circadian = np.clip(.65*circadian + rng.normal(0, 15 if calibration else 38) + duty_pressure*12, -180, 180)
   sleep = rounded(sleep_need + rng.normal(0,.35 if calibration else .7) - .27*max(0,workload-7) - .11*stress - abs(circadian)/180*.55, 3.2, 9.8)
   efficiency = rounded(96 - .85*stress - .05*abs(circadian) + rng.normal(0,2.2), 58, 99)
   latency = rounded(8 + 2.7*stress + .06*abs(circadian) + rng.normal(0,5), 1, 90)
   awakenings = int(np.clip(rng.poisson(.6+.15*stress+.007*abs(circadian)), 0, 10))
   # Total sleep opportunity includes onset delay plus at least three minutes
   # awake per awakening. Round the efficiency cap downward for consistency.
   max_efficiency = 100*sleep/(sleep+(latency+3*awakenings)/60)
   efficiency = min(efficiency, float(np.floor(max_efficiency*1000)/1000))
   # Dynamic fatigue is noisy, persistent, and affected by unobserved conditions.
   fatigue = np.clip(.57*fatigue + .43*(1.8 + 1.35*max(0,sleep_need-sleep) + .50*max(0,workload-7) + .20*stress + abs(circadian)/180*.8) + rng.normal(0,.62), 0, 10)
   fatigue_report = rounded(fatigue+rng.normal(0,.65), 0, 10)
   stress_report = rounded(stress+rng.normal(0,.7), 0, 10)
   mood_report = rounded(8.6-.30*stress-.23*fatigue+rng.normal(0,.9), 0, 10)
   event = int(not calibration and rng.random() < .065)
   hr = rounded(hr_base+.75*stress+.65*fatigue+rng.normal(0,2.2)+event*rng.uniform(13,24), 40, 125)
   hrv = rounded(hrv_base*np.exp(-.035*stress-.035*fatigue+rng.normal(0,.08))*(rng.uniform(.45,.72) if event else 1), 8, 115)
   trial_median = rt_base+11*fatigue+3*stress+abs(circadian)*.08
   rt_trials = rng.lognormal(np.log(trial_median), .12, 60)
   lapse_probability = np.clip(.005+.0055*fatigue+.002*stress, .005, .16)
   lapse_mask = rng.random(60) < lapse_probability
   rt_trials[lapse_mask] = rng.uniform(500,1100,int(lapse_mask.sum()))
   rt = rounded(np.median(rt_trials), 150, 800)
   lapses = int((rt_trials >= 500).sum())
   attention_prob = np.clip(.995-.008*fatigue-.0025*stress+rng.normal(0,.015), .65, .995)
   correct = int(rng.binomial(40,attention_prob))
   journal_level = class_of(float(np.clip(stress+rng.normal(0,1),0,10)))
   timestamp = START+pd.Timedelta(days=day-1)
   records.append({
    'record_id':f'{pid}_D{day:+04d}', 'participant_id':pid,
    'observation_timestamp_utc':timestamp.strftime('%Y-%m-%dT%H:%M:%SZ'),
    'mission_day':day, 'split':split, 'is_synthetic':1,
    'data_origin':'synthetic', 'generator_version':VERSION,
    'sleep_duration_hours':sleep, 'sleep_efficiency_pct':efficiency,
    'sleep_onset_delay_minutes':latency, 'awakenings_count':awakenings,
    'sleep_midpoint_deviation_minutes':round(float(circadian),3),
    'resting_heart_rate_bpm':hr, 'hrv_rmssd_ms':hrv,
    'reaction_time_median_ms':rt, 'reaction_time_lapses_count':lapses,
    'reaction_time_trials_count':60, 'attention_correct_count':correct,
    'attention_trials_count':40, 'attention_accuracy_pct':round(correct/40*100,3),
    'self_report_stress_score':stress_report,
    'self_report_fatigue_score':fatigue_report, 'self_report_mood_score':mood_report,
    'workload_hours':workload, 'exercise_minutes':exercise,
    'journal_text':journal(split,journal_level),
    'target_current_physiology_event_injected':event,
    'target_journal_stress_class':journal_level,
   })
 raw=pd.DataFrame(records).sort_values(['participant_id','mission_day']).reset_index(drop=True)
 raw['record_role']=np.where(raw.mission_day<=0,'baseline_calibration',np.where(raw.mission_day==61,'future_outcome_only','prediction_observation'))
 baseline_cols=['sleep_duration_hours','resting_heart_rate_bpm','hrv_rmssd_ms','reaction_time_median_ms']
 baseline=raw[raw.mission_day<=0].groupby('participant_id')[baseline_cols].mean()
 names={c:'baseline_'+c for c in baseline_cols}
 data=raw[(raw.mission_day>=1)&(raw.mission_day<=60)].drop(columns='record_role').copy()
 for c in baseline_cols:
  data[names[c]]=data.participant_id.map(baseline[c]).round(6)
 data['sleep_duration_delta_from_baseline_hours']=(data.sleep_duration_hours-data.baseline_sleep_duration_hours).round(6)
 data['heart_rate_delta_from_baseline_bpm']=(data.resting_heart_rate_bpm-data.baseline_resting_heart_rate_bpm).round(6)
 data['hrv_delta_from_baseline_ms']=(data.hrv_rmssd_ms-data.baseline_hrv_rmssd_ms).round(6)
 data['reaction_time_change_from_baseline_pct']=((data.reaction_time_median_ms/data.baseline_reaction_time_median_ms-1)*100).round(6)
 data['baseline_days_count']=7
 # Strictly past-only mean of preceding three days, including calibration initially.
 for c, new in [('sleep_duration_hours','prior_3day_mean_sleep_hours'),('resting_heart_rate_bpm','prior_3day_mean_resting_heart_rate_bpm'),('reaction_time_median_ms','prior_3day_mean_reaction_time_ms')]:
  prior=raw.groupby('participant_id')[c].transform(lambda s:s.shift(1).rolling(3,min_periods=3).mean())
  data[new]=prior.loc[data.index].round(6)
 future=raw.copy()
 for c,new in [('observation_timestamp_utc','target_timestamp_utc'),('self_report_fatigue_score','target_next_day_fatigue_score'),('reaction_time_median_ms','target_next_day_reaction_time_median_ms')]:
  shifted=raw.groupby('participant_id')[c].shift(-1)
  data[new]=shifted.loc[data.index]
 data['prediction_horizon_hours']=24
 data['target_next_day_fatigue_class']=data.target_next_day_fatigue_score.map(class_of)
 data=data.reset_index(drop=True)
 assert not data.isna().any().any()
 raw.to_csv(OUT/'raw_observations.csv',index=False,encoding='utf-8',float_format='%.6f')
 data.to_csv(OUT/'astra_shield_synthetic_ml.csv',index=False,encoding='utf-8',float_format='%.6f')
 raw[['participant_id','split']].drop_duplicates().to_csv(OUT/'participant_splits.csv',index=False)
 return data,raw

# Dictionary stores task roles, units, windows, and exact derivations.
def dictionary(data,raw):
 specs={}
 def add(c,desc,group,use,role,unit,window,derive='',allowed=''):
  specs[c]={'column_name':c,'description':desc,'modality':group,'use_case':use,'role':role,'dtype':('integer' if pd.api.types.is_integer_dtype(data[c] if c in data else raw[c]) else ('float' if pd.api.types.is_float_dtype(data[c] if c in data else raw[c]) else 'string')),'unit':unit,'allowed_values_or_range':allowed,'measurement_window':window,'availability_time':('next day at 18:00 UTC; unavailable to predictors' if c.startswith('target_next_day') or c=='target_timestamp_utc' else 'day t by 18:00 UTC; labels excluded from predictors'),'source':SOURCE,'derivation':derive or 'Generated by uncalibrated stochastic simulator; not a real measurement','missing_value_policy':'No missing values in this demonstration; real deployments must preserve missingness','model_usage_notes':('Excluded from all predictor allowlists' if role not in ['predictor','text_predictor'] else 'Use only the task_config.json allowlists; fit learned preprocessing on training split only')}
 for c,desc in {
 'record_id':'Unique synthetic participant-day record identifier', 'participant_id':'Virtual participant grouping identifier; not a real astronaut',
 'observation_timestamp_utc':'Prediction cutoff; all day t observations available by this timestamp',
 'mission_day':'Simulation day; prediction days 1..60', 'split':'Fixed participant-disjoint model development split',
 'is_synthetic':'Explicit synthetic observation flag; always 1', 'data_origin':'Provenance; always synthetic',
 'generator_version':'Version of reproducible simulation code', 'baseline_days_count':'Number of fixed premission calibration days; always 7',
 'prediction_horizon_hours':'Time between prediction cutoff and future target; always 24',
 'target_timestamp_utc':'Timestamp of the outcome observation, exactly 24 hours after cutoff',
 'record_role':'Audit-only role: calibration, prediction observation, or future outcome only'
 }.items():
  add(c,desc,'metadata','provenance; splitting; time alignment','metadata','hours' if c=='prediction_horizon_hours' else ('day' if c=='mission_day' else 'not_applicable'),'not_applicable',allowed={'split':'train|validation|test','is_synthetic':'1','data_origin':'synthetic','mission_day':'-6..61 in raw; 1..60 in ML','baseline_days_count':'7','prediction_horizon_hours':'24'}.get(c,''))
 obs={
 'sleep_duration_hours':('Total simulated sleep duration','sleep','sleep and fatigue forecasting','hours','most recent sleep episode completed before cutoff','3.2..9.8'),
 'sleep_efficiency_pct':('Simulated percent of sleep opportunity spent asleep; opportunity includes onset delay and at least three awake minutes per awakening','sleep','sleep and fatigue forecasting','percent','most recent completed sleep episode','58..99'),
 'sleep_onset_delay_minutes':('Simulated delay between bedtime and sleep onset','sleep','sleep and fatigue forecasting','minutes','most recent completed sleep episode','1..90'),
 'awakenings_count':('Simulated number of awakenings','sleep','sleep and fatigue forecasting','count','most recent completed sleep episode','0..10'),
 'sleep_midpoint_deviation_minutes':('Signed midpoint deviation from the virtual participant planned sleep schedule; negative earlier, positive later','sleep','circadian pattern monitoring','minutes','most recent completed sleep episode','-180..180'),
 'resting_heart_rate_bpm':('Simulated mean resting heart rate during a seated-equivalent quiet recording','physiology','physiological anomaly detection; fatigue forecasting','beats/minute','five-minute quiet assessment ending before cutoff','40..125'),
 'hrv_rmssd_ms':('Simulated root mean square successive difference of normal beat intervals; no raw ECG or beat intervals supplied','physiology','physiological anomaly detection; fatigue forecasting','milliseconds','same five-minute quiet assessment as heart rate','8..115'),
 'reaction_time_median_ms':('Median of 60 simulated responses in a five-minute PVT-like demonstration; not a validated clinical PVT','cognition','cognitive performance tracking; next-day forecasting','milliseconds','five-minute simulated test before cutoff','150..800'),
 'reaction_time_lapses_count':('Number of simulated response times greater than or equal to 500 ms among 60 trials','cognition','attention and cognitive performance tracking','count','same five-minute PVT-like test','0..60'),
 'reaction_time_trials_count':('Number of simulated reaction-time responses; constant 60','cognition','test protocol metadata','count','same five-minute PVT-like test','60'),
 'attention_correct_count':('Correct responses in a separate 40-trial simulated attention task','cognition','attention performance tracking','count','separate attention test completed before cutoff','0..40'),
 'attention_trials_count':('Number of simulated attention trials; constant 40','cognition','test protocol metadata','count','same separate attention task','40'),
 'attention_accuracy_pct':('Correct responses divided by attention trials times 100','cognition','attention performance tracking; fatigue forecasting','percent','same separate attention task','0..100'),
 'self_report_stress_score':('Custom simulated self-reported stress, higher means more stress; not a validated questionnaire','behavior','multimodal fatigue forecasting','custom 0..10 score','daily check-in before cutoff','0..10'),
 'self_report_fatigue_score':('Custom simulated self-reported fatigue, higher means greater fatigue; not KSS or a diagnosis','behavior','current fatigue tracking; next-day forecasting','custom 0..10 score','daily check-in before cutoff','0..10'),
 'self_report_mood_score':('Custom simulated mood, higher means more positive mood; not a validated questionnaire','behavior','well-being trend monitoring; fatigue forecasting','custom 0..10 score','daily check-in before cutoff','0..10'),
 'workload_hours':('Simulated operational duty duration, excluding the sleep episode','context','fatigue forecasting','hours','24 hours ending at cutoff','3..15'),
 'exercise_minutes':('Simulated exercise duration','context','fatigue forecasting','minutes','24 hours ending at cutoff','0..110'),
 }
 for c,(desc,group,use,unit,window,bounds) in obs.items():
  role='metadata' if c in ['reaction_time_trials_count','attention_trials_count','attention_correct_count'] else 'predictor'
  add(c,desc,group,use,role,unit,window,derive=('Initial stochastic efficiency capped at 100*sleep_duration_hours/(sleep_duration_hours+(sleep_onset_delay_minutes+3*awakenings_count)/60), rounded down to 0.001 percentage point' if c=='sleep_efficiency_pct' else ''),allowed=bounds)
 add('journal_text','Unique generated English daily reflection; no actual astronaut language or audio','text','journal stress classification; interface demonstration','text_predictor','text','reflection submitted before day t cutoff',allowed='nonempty UTF-8 text')
 for orig in ['sleep_duration_hours','resting_heart_rate_bpm','hrv_rmssd_ms','reaction_time_median_ms']:
  c='baseline_'+orig
  unit=specs[orig]['unit']
  add(c,'Fixed personal baseline for '+orig,'baseline','personalization; anomaly detection; forecasting','predictor',unit,'seven calibration days -6..0 only',derive=f'Mean of {orig} over participant calibration days -6..0; fixed for all mission days')
 deltas={
 'sleep_duration_delta_from_baseline_hours':('Sleep duration minus fixed calibration mean','sleep','hours','sleep_duration_hours - baseline_sleep_duration_hours'),
 'heart_rate_delta_from_baseline_bpm':('Resting heart rate minus fixed calibration mean','physiology','beats/minute','resting_heart_rate_bpm - baseline_resting_heart_rate_bpm'),
 'hrv_delta_from_baseline_ms':('RMSSD minus fixed calibration mean','physiology','milliseconds','hrv_rmssd_ms - baseline_hrv_rmssd_ms'),
 'reaction_time_change_from_baseline_pct':('Percent change in median response time relative to fixed calibration mean; positive means slower','cognition','percent','100 * (reaction_time_median_ms / baseline_reaction_time_median_ms - 1)'),
 }
 for c,(desc,group,unit,derive) in deltas.items():
  add(c,desc,group,'personalized change monitoring; forecasting','predictor',unit,'current day t relative to calibration days -6..0',derive)
 for c,orig,unit in [('prior_3day_mean_sleep_hours','sleep_duration_hours','hours'),('prior_3day_mean_resting_heart_rate_bpm','resting_heart_rate_bpm','beats/minute'),('prior_3day_mean_reaction_time_ms','reaction_time_median_ms','milliseconds')]:
  add(c,'Strictly past-only three-day mean of '+orig,'history','time-series forecasting','predictor',unit,'days t-3, t-2, t-1 only',derive=f'Within participant {orig}.shift(1).rolling(3).mean(); calibration observations used for earliest days')
 add('target_next_day_fatigue_score','Simulated self-reported fatigue on following day; primary regression target','target','next-day fatigue regression','target','custom 0..10 score','day t+1 check-in','Exact following-day self_report_fatigue_score; stochastic simulator, not medical ground truth','0..10')
 add('target_next_day_fatigue_class','Prototype categorical next-day fatigue label derived from future simulated custom fatigue score','target','next-day fatigue classification','target','category','day t+1 check-in','low if score <4; moderate if 4<=score<7; high if score>=7. These are arbitrary demo cutoffs, not clinical thresholds.','low|moderate|high')
 add('target_next_day_reaction_time_median_ms','Simulated next-day median response time; regression target','target','next-day cognitive performance regression','target','milliseconds','day t+1 five-minute PVT-like test','Exact following-day reaction_time_median_ms','150..800')
 add('target_current_physiology_event_injected','Simulator annotation that elevated heart rate and reduced RMSSD were injected; not a disease label','target','Isolation Forest evaluation only','target','binary','current day quiet measurement','Bernoulli event with probability .065 outside calibration; adds HR 13..24 bpm and multiplies RMSSD by .45...72','0|1')
 add('target_journal_stress_class','Generator annotation for the intended stress language in the synthetic journal; not a human assessment','target','journal stress classification','target','category','current day journal','Class of hidden stress plus random noise using prototype 4/7 cutoffs; independent of observed self-report noise','low|moderate|high')
 rows=[dict(specs[c],file_presence='main_and_raw' if c in raw and c in data else ('main_only' if c in data else 'raw_audit_only')) for c in list(data.columns)+[c for c in raw if c not in data]]
 pd.DataFrame(rows).to_csv(OUT/'data_dictionary.csv',index=False,encoding='utf-8')
 predictors=[c for c in data if specs[c]['role']=='predictor']
 physiology=['resting_heart_rate_bpm','hrv_rmssd_ms','baseline_resting_heart_rate_bpm','baseline_hrv_rmssd_ms','heart_rate_delta_from_baseline_bpm','hrv_delta_from_baseline_ms','prior_3day_mean_resting_heart_rate_bpm']
 config={
  'dataset':'astra_shield_synthetic_ml.csv','data_origin':'synthetic_only','is_clinically_validated':False,
  'seed':SEED,'prediction_cutoff':'18:00 UTC each day','forecast_horizon_hours':24,
  'group_column':'participant_id','split_column':'split','raw_audit_file':'raw_observations.csv',
  'preprocessing':'Select only task allowlists. Train imputation/scaling/text vocabulary on train only. Never use raw_observations.csv as a predictor table or include any target as a predictor.',
  'label_cutoffs':{'low':'score < 4','moderate':'4 <= score < 7','high':'score >= 7','meaning':'custom simulator categories; not clinical'},
  'tasks':{
   'next_day_fatigue_classification':{'predictors':predictors,'target':'target_next_day_fatigue_class','evaluation':'macro F1 and per-class precision/recall on held-out participants; simulator fidelity only'},
   'next_day_fatigue_regression':{'predictors':predictors,'target':'target_next_day_fatigue_score','evaluation':'MAE/RMSE on held-out participants; simulator fidelity only'},
   'next_day_reaction_time_regression':{'predictors':predictors,'target':'target_next_day_reaction_time_median_ms','evaluation':'MAE/RMSE on held-out participants; simulator fidelity only'},
   'physiology_anomaly_detection':{'predictors':physiology,'evaluation_target':'target_current_physiology_event_injected','training':'Fit unsupervised detector on training participants without target; target is only for evaluation, not normal-subset selection','evaluation':'injected-event precision/recall; not clinical event detection'},
   'journal_stress_classification':{'predictors':['journal_text'],'target':'target_journal_stress_class','evaluation':'held-out participants and split-specific sentence banks; synthetic language performance only'},
  },
  'excluded_from_all_predictor_sets':[c for c in data if c not in predictors and c!='journal_text'],
  'not_supported':['medical diagnosis','clinical probability calibration','astronaut deployment validation','speech or audio model training','actual radiation exposure prediction'],
 }
 (OUT/'task_config.json').write_text(json.dumps(config,indent=2)+'\n')
 (OUT/'generation_metadata.json').write_text(json.dumps({'seed':SEED,'version':VERSION,'virtual_participants':120,'main_rows':len(data),'raw_rows':len(raw),'calibration_days':[-6,0],'main_days':[1,60],'raw_days':[-6,61],'split_participants':{'train':84,'validation':18,'test':18},'numpy_version':np.__version__,'pandas_version':pd.__version__,'raw_includes_held_out_future_data':'audit_only; never use as a predictor table','calibrated_to_real_data':False},indent=2)+'\n')
 pd.DataFrame([
 {'source_id':'proposal','source_type':'user_supplied_project_requirements','url_or_path':'ASTRA-SHIELD AI-Powered Predictive Health and Cognitive Performance Monitoring for Astronauts.pdf','purpose':'Defines four project modalities and requirement to distinguish simulated from real data','provides_measurements':False,'license_or_status':'User-supplied project document; not redistributed here'},
 {'source_id':'nasa_standard_measures','source_type':'background_only','url_or_path':'https://www.nasa.gov/reference/standard-measures/','purpose':'Conceptual support for consistent measurements and personal time-series; no records copied','provides_measurements':False,'license_or_status':'Linked as scientific background; no source content redistributed'},
 {'source_id':'nasa_archer','source_type':'background_only','url_or_path':'https://www.nasa.gov/reference/archer/','purpose':'Conceptual support for activity, sleep and behavioral observations; no records copied','provides_measurements':False,'license_or_status':'Linked as scientific background; no source content redistributed'},
 {'source_id':'custom_simulator','source_type':'synthetic_generator','url_or_path':'generate_dataset.py','purpose':'Actual source of every value and every label in these CSV files','provides_measurements':False,'license_or_status':'New generated project artifact; no third-party measurement records used'},
 ]).to_csv(OUT/'source_manifest.csv',index=False)

if __name__=='__main__':
 data,raw=generate()
 dictionary(data,raw)
 print(json.dumps({'main_rows':len(data),'main_columns':len(data.columns),'raw_rows':len(raw),'fatigue_classes':data.target_next_day_fatigue_class.value_counts().to_dict(),'split_rows':data.split.value_counts().to_dict()},indent=2))
