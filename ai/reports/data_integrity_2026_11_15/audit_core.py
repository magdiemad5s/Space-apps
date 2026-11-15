#!/usr/bin/env python3
"""Read-only integrity audit of the frozen cohort; writes only this report folder.

Run from any directory with the project Python environment. Includes held-out
records solely for structural/provenance checks, never fitting, model selection,
or predictive-performance estimation. No row repair or deletion is performed.
"""
from pathlib import Path
import csv
import hashlib
import io
import json
import os
import tempfile

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parent
AI = OUT.parents[1]
DATA = AI / 'data'
TOL = 1e-6


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluate(main, raw, partitions, config, dictionary):
    checks = []
    examples = []

    def check(name, valid, scope, detail, frame=None):
        values = np.atleast_1d(np.asarray(valid, dtype=bool))
        invalid = ~values
        checks.append({'check':name, 'status':'PASS' if not invalid.any() else 'FAIL',
                       'scope':scope, 'evaluated_items':int(len(values)),
                       'invalid_items':int(invalid.sum()),'detail':detail})
        if invalid.any() and frame is not None and len(frame)==len(values):
            for pos in np.flatnonzero(invalid)[:10]:
                row=frame.iloc[pos]
                examples.append({'check':name,'scope':scope,'record_id':str(row.get('record_id','')),'participant_id':str(row.get('participant_id','')),'mission_day':int(row.get('mission_day',0))})

    check('main_shape',main.shape==(7200,46),'main','Original cohort: 120 people x60 forecast days, 46 columns.')
    check('raw_shape',raw.shape==(8160,30),'raw','120 people x68 days (-6..61), 30 source columns.')
    bounds={
        'sleep_duration_hours':(3.2,9.8),'sleep_efficiency_pct':(58,99),
        'sleep_onset_delay_minutes':(1,90),'awakenings_count':(0,10),
        'sleep_midpoint_deviation_minutes':(-180,180),'resting_heart_rate_bpm':(40,125),
        'hrv_rmssd_ms':(8,115),'reaction_time_median_ms':(150,800),
        'reaction_time_lapses_count':(0,60),'attention_correct_count':(0,40),
        'attention_accuracy_pct':(0,100),'self_report_stress_score':(0,10),
        'self_report_fatigue_score':(0,10),'self_report_mood_score':(0,10),
        'workload_hours':(3,15),'exercise_minutes':(0,110),
    }
    for name,frame,days in [('main',main,list(range(1,61))),('raw',raw,list(range(-6,62)))]:
        check(name+'_missing_cells',~frame.isna().any(axis=1),name,'No missing cells in existing supplied columns; does not assert requested new measurements exist.',frame)
        num=frame.select_dtypes('number')
        check(name+'_finite_numbers',np.isfinite(num.to_numpy()).all(axis=1),name,'Reject NaN/infinity across numeric fields.',frame)
        for key,duplicated in [('duplicate_rows',frame.duplicated()),('duplicate_ids',frame.record_id.duplicated()),('duplicate_person_days',frame.duplicated(['participant_id','mission_day']))]:
            check(name+'_'+key,~duplicated,name,'Repeated person IDs and repeated baseline values alone are expected; duplicate records are not.',frame)
        check(name+'_synthetic_provenance',frame.is_synthetic.eq(1)&frame.data_origin.eq('synthetic')&frame.generator_version.eq('astra_synthetic_v1.0'),name,'No real NASA measurements.',frame)
        check(name+'_person_schedule',frame.groupby('participant_id').mission_day.apply(lambda x:x.tolist()==days).to_numpy(),name,'Sorted, complete daily sequence for each person.')
        check(name+'_person_count',frame.participant_id.nunique()==120,name,'Expected 120 virtual people.')
        check(name+'_fixed_split',frame.groupby('participant_id').split.nunique().eq(1).to_numpy(),name,'A person cannot cross partitions.')
        stamps=pd.to_datetime(frame.observation_timestamp_utc,utc=True,errors='coerce')
        expected=pd.Timestamp('2026-01-01T18:00:00Z')+pd.to_timedelta(frame.mission_day-1,unit='D')
        check(name+'_timestamp_from_day',stamps.eq(expected)&frame.observation_timestamp_utc.str.endswith('Z'),name,'Exact UTC cutoff and calendar mapping; no guess from spreadsheet row number.',frame)
        ids=[f'{p}_D{int(t):+04d}' for p,t in zip(frame.participant_id,frame.mission_day)]
        check(name+'_record_id_construction',frame.record_id.eq(ids),name,'Record IDs encode the same participant and day as the row.',frame)
        for field,(lo,hi) in bounds.items():
            check(name+'_range_'+field,frame[field].between(lo,hi),name,f'Observed frozen-cohort range [{lo},{hi}]; engineering assumptions, not clinical limits. Efficiency lower limit is not guaranteed after its cap for arbitrary future simulations.' if field=='sleep_efficiency_pct' else f'Simulator range [{lo},{hi}], not a medical normal range.',frame)
        for field in ['awakenings_count','reaction_time_lapses_count','reaction_time_trials_count','attention_correct_count','attention_trials_count','target_current_physiology_event_injected']:
            check(name+'_integer_'+field,frame[field].mod(1).eq(0),name,'Discrete counts/flags cannot be fractional.',frame)
        check(name+'_rt_trials_60',frame.reaction_time_trials_count.eq(60),name,'Fixed synthetic-response count; no elapsed-duration validation.',frame)
        check(name+'_attention_trials_40',frame.attention_trials_count.eq(40),name,'Separate simulated attention task.',frame)
        check(name+'_attention_accuracy',np.isclose(frame.attention_accuracy_pct,100*frame.attention_correct_count/frame.attention_trials_count,rtol=0,atol=TOL),name,'Correct/trials x100; not reaction-time lapse accuracy.',frame)
        median=frame.reaction_time_median_ms
        lapses=frame.reaction_time_lapses_count
        valid=~((median.gt(500.0005)&lapses.lt(30))|(median.lt(499.9995)&lapses.gt(30)))
        check(name+'_median_lapse_necessary_constraint',valid,name,'Necessary even-sample median/count consistency at500ms, allowing reported rounding. Replay independently checks exact trial arrays.',frame)
        opportunity=frame.sleep_duration_hours/(frame.sleep_efficiency_pct/100)
        awake=(opportunity-frame.sleep_duration_hours)*60
        check(name+'_sleep_efficiency_cap',awake+TOL >= frame.sleep_onset_delay_minutes+3*frame.awakenings_count,name,'Synthetic minimum3awake minutes per awakening; not measured WASO.',frame)
        check(name+'_daily_budget',opportunity+frame.workload_hours+frame.exercise_minutes/60<=24+TOL,name,'Observed synthetic sleep opportunity+duty+exercise fits24h. Generator does not explicitly clip total daily budget.',frame)
        check(name+'_binary_event',frame.target_current_physiology_event_injected.isin([0,1]),name,'Event annotation binary; not a diagnosis.',frame)
        check(name+'_nonempty_journal',frame.journal_text.map(lambda s:isinstance(s,str) and len(s.strip())>20),name,'Generated text, not real-language validation.',frame)
        check(name+'_unique_journals',~frame.journal_text.duplicated(),name,'Global complete-string uniqueness; template fragments still repeat.',frame)
        check(name+'_valid_journal_labels',frame.target_journal_stress_class.isin(['low','moderate','high']),name,'Generated language label, separate from observed stress score.',frame)

    check('calibration_has_no_injected_events',raw.loc[raw.mission_day.le(0),'target_current_physiology_event_injected'].eq(0),'raw_calibration','No events injected in calibration; does not prove healthy humans.')
    roles=np.where(raw.mission_day.le(0),'baseline_calibration',np.where(raw.mission_day.eq(61),'future_outcome_only','prediction_observation'))
    check('raw_record_roles',raw.record_role.eq(roles),'raw','840 calibration +7200 prediction +120 future-outcome rows; excluded by table design, not cleaning.',raw)
    aligned=raw.set_index('record_id',drop=False).loc[main.record_id]
    shared=[c for c in main.columns if c in raw.columns]
    equal=main[shared].reset_index(drop=True).eq(aligned[shared].reset_index(drop=True)).all(axis=1)
    check('main_observations_equal_raw',equal,'main','Each current observation is copied from its same-day source record.',main)
    lookup=raw.set_index(['participant_id','mission_day'])
    next_index=pd.MultiIndex.from_arrays([main.participant_id,main.mission_day+1])
    future=lookup.reindex(next_index)
    for target,current in [('target_next_day_fatigue_score','self_report_fatigue_score'),('target_next_day_reaction_time_median_ms','reaction_time_median_ms'),('target_timestamp_utc','observation_timestamp_utc')]:
        check('future_source_'+target,main[target].to_numpy()==future[current].to_numpy(),'main','Exact same-person next-day outcome, including raw day61.',main)
    check('future_source_same_split',main.split.to_numpy()==future.split.to_numpy(),'main','No future outcome pulled from another partition/person.',main)
    horizon=pd.to_datetime(main.target_timestamp_utc,utc=True)-pd.to_datetime(main.observation_timestamp_utc,utc=True)
    check('horizon_24h',horizon.eq(pd.Timedelta(hours=24))&main.prediction_horizon_hours.eq(24),'main','Labels are exactly24h ahead.',main)
    expected=np.where(main.target_next_day_fatigue_score<4,'low',np.where(main.target_next_day_fatigue_score<7,'moderate','high'))
    check('fatigue_class_rule',main.target_next_day_fatigue_class.eq(expected),'main','Bins next-day observed synthetic0–10score, not latent fatigue/KSS/SP.',main)
    check('final_day_outcome_source',future.loc[(slice(None),61),'record_role'].eq('future_outcome_only'),'final120','Day60 labels have explicit day61 raw source.')
    for field in ['sleep_duration_hours','resting_heart_rate_bpm','hrv_rmssd_ms','reaction_time_median_ms']:
        baseline=raw[raw.mission_day.le(0)].groupby('participant_id')[field].mean().round(6)
        check('baseline_'+field,np.isclose(main['baseline_'+field],main.participant_id.map(baseline),rtol=0,atol=TOL),'main','Seven earlier days−6..0, fixed per person.',main)
        check('baseline_constant_'+field,main.groupby('participant_id')['baseline_'+field].nunique().eq(1),'persons','Repeated baseline is intentional, not duplicate-data noise.')
    check('baseline_days_count',main.baseline_days_count.eq(7),'main','Seven calibration days.',main)
    for current,derived in [('sleep_duration_hours','sleep_duration_delta_from_baseline_hours'),('resting_heart_rate_bpm','heart_rate_delta_from_baseline_bpm'),('hrv_rmssd_ms','hrv_delta_from_baseline_ms')]:
        expected=(main[current]-main['baseline_'+current]).round(6)
        check(derived,np.isclose(main[derived],expected,rtol=0,atol=TOL),'main','Difference from already rounded personal baseline.',main)
    expected=((main.reaction_time_median_ms/main.baseline_reaction_time_median_ms-1)*100).round(6)
    check('reaction_time_change_from_baseline_pct',np.isclose(main.reaction_time_change_from_baseline_pct,expected,rtol=0,atol=TOL),'main','Relative change, not absolutemilliseconds.',main)
    for current,derived in [('sleep_duration_hours','prior_3day_mean_sleep_hours'),('resting_heart_rate_bpm','prior_3day_mean_resting_heart_rate_bpm'),('reaction_time_median_ms','prior_3day_mean_reaction_time_ms')]:
        # Explicit day-key joins independently verify the rolling implementation.
        arrays=[]
        for lag in [3,2,1]:
            idx=pd.MultiIndex.from_arrays([main.participant_id,main.mission_day-lag])
            arrays.append(lookup.reindex(idx)[current].to_numpy())
        expected=np.round(np.stack(arrays).mean(axis=0),6)
        check(derived,np.isclose(main[derived],expected,rtol=0,atol=TOL),'main','Only same-person t−3,t−2,t−1; no current/future day.',main)

    mapping=main[['participant_id','split']].drop_duplicates()
    check('partition_person_counts',mapping.split.value_counts().to_dict()=={'train':84,'validation':18,'test':18},'partition','70/15/15by person, not random daily rows.')
    for split,count in [('train',5040),('validation',1080),('test',1080)]:
        part=partitions[split]
        reference=main[main.split.eq(split)].reset_index(drop=True)
        check(split+'_row_count',len(part)==count,'partition','Expected frozen split size.')
        check(split+'_identical_to_main_subset',part.equals(reference),'partition','Identical column order, row order, values and dtypes to the matching main subset.')
    sets={k:set(v.participant_id) for k,v in partitions.items()}
    check('partitions_person_disjoint',not(sets['train']&sets['validation'] or sets['train']&sets['test'] or sets['validation']&sets['test']),'partition','No person shared across train/validation/test.')
    check('dictionary_coverage',dictionary.column_name.is_unique and set(dictionary.column_name)==set(main.columns)|set(raw.columns),'schema','Dictionary covers all main and raw columns exactly once.')
    roles=dictionary.set_index('column_name').role.to_dict()
    for task,spec in config['tasks'].items():
        feats=spec['predictors']
        valid=len(feats)==len(set(feats)) and all(c in main and roles.get(c) in ['predictor','text_predictor'] and not c.startswith('target_') for c in feats)
        check(task+'_feature_allowlist',valid,'schema','Exclude outcomes, IDs, partition/provenance and protocol constants; text allowed only when declared.')
        check(task+'_label_not_feature',spec.get('target',spec.get('evaluation_target')) not in feats,'schema','The task label cannot also be a predictor.')
    predictors=config['tasks']['next_day_fatigue_classification']['predictors']
    check('primary_has_26_predictors',len(predictors)==26,'schema','15current+4baseline+4delta+3history.')
    check('primary_no_constant_predictors',main[predictors].nunique().gt(1),'schema','Constant metadata excluded; correlated baseline/delta features are not errors.')
    check('primary_no_duplicate_predictor_vectors',~main[predictors].duplicated(),'main','Exact vectors only; no unsupported near-duplicate/no-noise claim.',main)
    return checks, examples


REQUESTED = [
 ('kss_sleepiness_score','KSS (1–9)','not_collected','Separate integer response with instrument version, anchors, language and timestamp; no conversion from W.'),
 ('samn_perelli_fatigue_score','Samn–Perelli (1–7)','not_collected','Separate integer fatigue response; cannot rename/rescale W or automatically replace its next-day target.'),
 ('sleep_onset_time_utc','Sleep onset time','not_collected','Actual/estimated onset timestamp with source; cannot invert duration and midpoint deviation into clocktime.'),
 ('wake_time_utc','Final awakening time','not_collected','Final awakening from defined episode, distinct from getting out of bed.'),
 ('time_awake_hours','Time awake','not_derivable','Time from latest actual sleep end to assessment, including naps if protocol so defines.'),
 ('nap_start_time_utc','Nap start','not_collected','Store multiple sleep episodes; one pair cannot represent multiple naps.'),
 ('nap_end_time_utc','Nap end','not_collected','Known complete episode before cutoff; unknown is not no nap.'),
 ('nap_duration_minutes','Nap sleep duration','not_derivable','Actual sleep time, accounting for waking within the nap; not automatically elapsed time.'),
 ('total_sleep_24h_hours','Sleep within last24h','not_derivable','Sum nonoverlapping sleep segments intersecting exactly [cutoff−24h,cutoff), including naps.'),
 ('waso_minutes','Wake after sleep onset','not_collected','Sum waking after initial onset and before final awakening; not3*awakenings or an unassigned efficiency residual.'),
 ('sleep_target_hours','Configured sleep goal','not_collected','An explicit recorded goal; calibration mean is not proven physiological need.'),
 ('sleep_deficit_3day_hours','Prior3day sleep shortfall','not_derivable','Requires known per-day targets and totals over3previous nonoverlapping daily windows; not a validated biological debt measure.'),
 ('reaction_time_false_starts_count','Reaction-task false starts','not_collected','Need per-response events/protocol; cannot compute as60−lapses. Unknown is not zero.'),
 ('reaction_time_lapses_count','Reaction-task lapses','present_synthetic','Already Q, ≥500ms among60synthetic responses. PVT-B355ms is a different protocol.'),
 ('caffeine_mg_last_6h','Caffeine last6h','not_collected','Dose estimates and timestamps; no retrospective inference from heart rate.'),
 ('exercise_minutes_last_2h','Exercise last2h','not_collected','Requires timestamped activity; daily exercise_minutes is not a2h total.'),
 ('acute_symptoms_present','Acute symptoms','not_collected','Explicit report including unknown/unanswered; no automatic medical triage inferred from demo score.'),
 ('workload_hours','Workload duration','present_synthetic','Existing24h duty duration only; not a validated mental-workload questionnaire.'),
 ('medication_use','Medication context','not_collected','Explicit reported context/time; no synthetic-model medical conclusion about medication effects.'),
 ('phq2_score','PHQ-2 optional screening','not_collected_optional','Separate two-week instrument; optional, not a daily mood proxy or current-model input.'),
 ('gad2_score','GAD-2 optional screening','not_collected_optional','Separate two-week instrument; optional, not a daily stress proxy or current-model input.'),
]


def mutation_checks(main,raw,parts,config,dictionary):
    cases=[]
    def run(name,mutator,required):
        changed=main.copy(deep=True)
        mutator(changed)
        checks,_=evaluate(changed,raw,parts,config,dictionary)
        failures={x['check'] for x in checks if x['status']=='FAIL'}
        cases.append({'case':name,'expected_detection':required,'detected':required in failures,'failures':sorted(failures)})
    run('wrong_future_fatigue',lambda x:x.__setitem__('target_next_day_fatigue_score',x.target_next_day_fatigue_score.mask(x.index==0,0.123)),'future_source_target_next_day_fatigue_score')
    run('wrong_baseline',lambda x:x.__setitem__('baseline_resting_heart_rate_bpm',x.baseline_resting_heart_rate_bpm.mask(x.index==0,999)),'baseline_resting_heart_rate_bpm')
    run('current_day_substituted_for_prior3',lambda x:x.__setitem__('prior_3day_mean_reaction_time_ms',x.prior_3day_mean_reaction_time_ms.mask(x.index==0,x.reaction_time_median_ms.iloc[0])),'prior_3day_mean_reaction_time_ms')
    run('impossible_lapse_count',lambda x:x.__setitem__('reaction_time_lapses_count',x.reaction_time_lapses_count.mask(x.index==0,61)),'main_range_reaction_time_lapses_count')
    run('wrong_attention_percentage',lambda x:x.__setitem__('attention_accuracy_pct',x.attention_accuracy_pct.mask(x.index==0,12.345)),'main_attention_accuracy')
    run('nonfinite_measurement',lambda x:x.__setitem__('resting_heart_rate_bpm',x.resting_heart_rate_bpm.mask(x.index==0,np.inf)),'main_finite_numbers')
    run('missing_measurement',lambda x:x.__setitem__('self_report_fatigue_score',x.self_report_fatigue_score.mask(x.index==0,np.nan)),'main_missing_cells')
    run('person_changes_split',lambda x:x.__setitem__('split',x.split.mask(x.index==0,'test' if x.split.iloc[0]!='test' else 'train')),'main_fixed_split')
    return cases


def plots(train,raw):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'astra-integrity-mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    opportunity=train.sleep_duration_hours/(train.sleep_efficiency_pct/100)
    sleep_margin=(opportunity-train.sleep_duration_hours)*60-train.sleep_onset_delay_minutes-3*train.awakenings_count
    day_margin=24-opportunity-train.workload_hours-train.exercise_minutes/60
    fig,axs=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    for ax,values,title,unit in [(axs[0],sleep_margin,'Sleep consistency margin','minutes beyond onset + 3 min/awakening'),(axs[1],day_margin,'Unallocated daily time','hours after sleep opportunity + duty + exercise')]:
        ax.hist(values,bins=30,color='#237d95',edgecolor='white',linewidth=.3)
        ax.axvline(0,color='#c54a42',linestyle='--');ax.set_title(title);ax.set_xlabel(unit);ax.set_ylabel('Training records')
    fig.suptitle('Synthetic TRAIN only: non-negative margins support arithmetic consistency')
    fig.savefig(OUT/'sleep_consistency.png',dpi=170);plt.close(fig)
    first=raw[(raw.participant_id=='SIM_001') & raw.mission_day.le(12)].copy()
    history=first.reaction_time_median_ms.shift(1).rolling(3).mean()
    baseline=first[first.mission_day.le(0)].reaction_time_median_ms.mean()
    fig,ax=plt.subplots(figsize=(10,3.6),layout='constrained')
    ax.plot(first.mission_day,first.reaction_time_median_ms,'o-',label='Current daily median',color='#237d95')
    ax.plot(first.mission_day,history,'s--',label='Mean of previous3days',color='#b07e31')
    ax.axhline(baseline,label='Fixed7day calibration mean',color='#55715a')
    ax.axvspan(-6,.3,alpha=.09,color='#237d95',label='Calibration days−6..0')
    ax.set(xlabel='Simulation day',ylabel='Reaction time (ms)',title='SIM_001 (training): earlier calibration and causal history')
    ax.legend(fontsize=8,ncol=2);fig.savefig(OUT/'baseline_history.png',dpi=170);plt.close(fig)


def main():
    before={p.name:sha(p) for p in DATA.iterdir() if p.is_file()}
    artifact_before=sha(AI/'artifacts/bundle.joblib')
    d=pd.read_csv(DATA/'astra_shield_synthetic_ml.csv')
    r=pd.read_csv(DATA/'raw_observations.csv')
    config=json.loads((DATA/'task_config.json').read_text())
    dictionary=pd.read_csv(DATA/'data_dictionary.csv',keep_default_na=False)
    parts={k:pd.read_csv(DATA/f'{k}.csv') for k in ['train','validation','test']}
    checks,examples=evaluate(d,r,parts,config,dictionary)
    mutations=mutation_checks(d,r,parts,config,dictionary)
    for row in mutations:
        checks.append({'check':'negative_control_'+row['case'],'status':'PASS' if row['detected'] else 'FAIL','scope':'in_memory_copy_only','evaluated_items':1,'invalid_items':int(not row['detected']),'detail':'Audit must detect deliberate corruption; no source file was changed.'})
    pd.DataFrame(checks).to_csv(OUT/'core_checks.csv',index=False)
    pd.DataFrame(examples,columns=['check','scope','record_id','participant_id','mission_day']).to_csv(OUT/'invalid_row_examples.csv',index=False)
    (OUT/'negative_controls.json').write_text(json.dumps(mutations,indent=2)+'\n')
    requested=pd.DataFrame(REQUESTED,columns=['field','measurement','status','required_action'])
    requested['present_in_current_csv']=requested.field.isin(d.columns)
    requested['included_in_current_model']=requested.field.isin(config['tasks']['next_day_fatigue_classification']['predictors'])
    requested['old_missing_values_policy']='Do not fabricate or fill with zero; store unknown until actually collected or explicitly simulated in a new version.'
    requested.to_csv(OUT/'requested_measurements.csv',index=False)
    # Descriptive TRAIN-only outlier review; flags never trigger deletion.
    train=parts['train']
    deltas=['sleep_duration_delta_from_baseline_hours','heart_rate_delta_from_baseline_bpm','hrv_delta_from_baseline_ms','reaction_time_change_from_baseline_pct']
    median=train[deltas].median()
    mad=(train[deltas]-median).abs().median()
    z=0.6744897501960817*(train[deltas]-median)/mad.replace(0,np.nan)
    flags=z.abs().gt(4.5).any(axis=1)
    noise={'scope':'Descriptive training-only review; no corruption diagnosis or cleaning/performance experiment.',
           'rule':'Any |0.6744897501960817*(x-median)/MAD|>4.5 over4baseline deltas; train-only location and scale.',
           'training_rows':len(train),'flagged_rows':int(flags.sum()),'injected_events_total':int(train.target_current_physiology_event_injected.sum()),
           'flagged_with_injected_event':int(train.loc[flags,'target_current_physiology_event_injected'].sum()),
           'rows_removed':0,'interpretation':'Generated random variation and injected events are intentional. Statistical extremeness is not an invalid-record label; new evidence of cleaning benefit requires separate evaluation.'}
    (OUT/'noise_review.json').write_text(json.dumps(noise,indent=2)+'\n')
    train.loc[flags,['record_id','participant_id',*deltas,'target_current_physiology_event_injected']].to_csv(OUT/'training_extreme_review.csv',index=False)
    corr=train[config['tasks']['next_day_fatigue_classification']['predictors']].corr()
    pairs=[]
    for i,a in enumerate(corr):
        for b in list(corr)[i+1:]:
            if abs(corr.loc[a,b])>=.85:
                pairs.append({'feature_1':a,'feature_2':b,'pearson_r':float(corr.loc[a,b]),'action':'Document related/derived inputs; do not automatically remove features.'})
    pd.DataFrame(pairs,columns=['feature_1','feature_2','pearson_r','action']).to_csv(OUT/'training_correlated_features.csv',index=False)
    plots(train,r)
    after={p.name:sha(p) for p in DATA.iterdir() if p.is_file()}
    frozen=json.loads((AI/'artifacts/frozen_manifest.json').read_text())
    frozen_match={name:sha(AI/name)==digest for name,digest in {**frozen['data_sha256'],**frozen['artifact_sha256']}.items()}
    integrity={'data_files_before_sha256':before,'data_files_after_sha256':after,'all_data_files_unchanged':before==after,
               'model_before_sha256':artifact_before,'model_after_sha256':sha(AI/'artifacts/bundle.joblib'),
               'model_unchanged':artifact_before==sha(AI/'artifacts/bundle.joblib'),'frozen_manifest_matches':frozen_match}
    assert integrity['all_data_files_unchanged'] and integrity['model_unchanged'] and all(frozen_match.values()),integrity
    (OUT/'preservation.json').write_text(json.dumps(integrity,indent=2)+'\n')
    opportunity=d.sleep_duration_hours/(d.sleep_efficiency_pct/100)
    summary={'snapshot_date':'2026-11-15','user_timezone':'Asia/Amman',
             'scope':'All-cohort integrity and source checks only. Held-out data were not used for fitting, feature selection, cleaning choices or new predictive-performance estimates. Descriptive plots/outlier review use train records only.',
             'main_rows':len(d),'main_columns':len(d.columns),'raw_rows':len(r),'participants':d.participant_id.nunique(),
             'checks_total':len(checks),'checks_passed':sum(x['status']=='PASS' for x in checks),'checks_failed':sum(x['status']=='FAIL' for x in checks),
             'missing_cells_existing_main_columns':int(d.isna().sum().sum()),'exact_duplicate_rows':int(d.duplicated().sum()),
             'minimum_remaining_daily_hours':float((24-opportunity-d.workload_hours-d.exercise_minutes/60).min()),
             'minimum_sleep_consistency_margin_minutes':float(((opportunity-d.sleep_duration_hours)*60-d.sleep_onset_delay_minutes-3*d.awakenings_count).min()),
             'reaction_median_range_ms':[float(r.reaction_time_median_ms.min()),float(r.reaction_time_median_ms.max())],
             'lapse_range':[int(r.reaction_time_lapses_count.min()),int(r.reaction_time_lapses_count.max())],
             'requested_measurements_total':len(requested),'requested_fields_absent':int((~requested.present_in_current_csv).sum()),
             'cleaning_rows_removed':0,'imputed_cells':0,'clinical_validation':False,'new_model_training':False,
             'data_and_model_unchanged':True,'negative_controls_all_detected':all(x['detected'] for x in mutations),'noise_review':noise}
    (OUT/'core_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))
    if summary['checks_failed']:
        raise SystemExit('Integrity audit found failures; inspect core_checks.csv. No automatic repair performed.')


if __name__=='__main__':
    main()
