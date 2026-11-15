#!/usr/bin/env python3
"""Training-only visual/data review for experiment006, before any estimator fit."""
from pathlib import Path
import hashlib
import json
import os
import tempfile

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
OUT=HERE/'reports/eda'
EXTRA=['kss_like_sleepiness_score','samn_perelli_like_fatigue_score','main_sleep_waso_minutes',
       'time_since_last_sleep_hours','nap_sleep_minutes_last_24h','total_sleep_last_24h_hours',
       'prior_3day_sleep_shortfall_hours']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    train_path=HERE/'data/train.csv'
    d=pd.read_csv(train_path)
    config=json.loads((HERE.parents[1]/'data/task_config.json').read_text())
    base=config['tasks']['next_day_fatigue_classification']['predictors']
    target='target_next_day_fatigue_class'
    checks={
        '5040_rows_84_people':len(d)==5040 and d.participant_id.nunique()==84,
        'training_only':d.split.eq('train').all(),
        'explicitly_synthetic':d.is_synthetic.eq(1).all(),
        'all_33_features_present':all(c in d for c in base+EXTRA),
        'unique_records':d.record_id.is_unique,
        'unique_person_day':not d.duplicated(['participant_id','mission_day']).any(),
        'no_missing_features':not d[base+EXTRA].isna().any().any(),
        'finite_features':np.isfinite(d[base+EXTRA].to_numpy()).all(),
        'kss_like_integer_1to9':(d.kss_like_sleepiness_score.between(1,9)&d.kss_like_sleepiness_score.mod(1).eq(0)).all(),
        'sp_like_integer_1to7':(d.samn_perelli_like_fatigue_score.between(1,7)&d.samn_perelli_like_fatigue_score.mod(1).eq(0)).all(),
        'sleep_extras_nonnegative':d[EXTRA[2:]].ge(0).all().all(),
        'total_sleep_at_most24':d.total_sleep_last_24h_hours.le(24).all(),
        'nap_at_most40min':d.nap_sleep_minutes_last_24h.le(40+1e-6).all(),
        'shortfall_at_most24h_over3days':d.prior_3day_sleep_shortfall_hours.le(24).all(),
        'no_identifiers_latents_or_targets_in_features':not any(c.startswith(('target_','latent_','hidden_')) or c in ['participant_id','record_id','split','mission_day'] for c in base+EXTRA),
    }
    checks={k:bool(v) for k,v in checks.items()}
    if not all(checks.values()):raise RuntimeError(checks)
    summary=d[base+EXTRA].describe(percentiles=[.01,.25,.5,.75,.99]).T
    summary['missing']=d[base+EXTRA].isna().sum()
    summary['unique']=d[base+EXTRA].nunique()
    summary.to_csv(OUT/'training_feature_summary.csv')
    distribution=d[target].value_counts().reindex(['low','moderate','high'],fill_value=0)
    distribution.rename_axis('class').reset_index(name='rows').to_csv(OUT/'training_class_counts.csv',index=False)
    correlations=d[base+EXTRA].corr()
    correlations.to_csv(OUT/'training_feature_correlations.csv')
    os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'astra006mpl'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.right':False,'axes.spines.top':False})
    fig,axes=plt.subplots(1,3,figsize=(12,3.7),layout='constrained')
    for ax,col,levels,title in [(axes[0],EXTRA[0],range(1,10),'Synthetic KSS-range proxy (1–9)'),(axes[1],EXTRA[1],range(1,8),'Synthetic Samn–Perelli-range proxy (1–7)')]:
        v=d[col].value_counts().reindex(levels,fill_value=0)
        ax.bar(v.index,v.values,color='#267c92');ax.set_xticks(list(levels));ax.set_title(title);ax.set_ylabel('Training rows')
    axes[2].bar(distribution.index,distribution.values,color=['#459a83','#dfad40','#c26466'])
    axes[2].set_title('Original custom next-day target');axes[2].set_ylabel('Training rows')
    fig.suptitle('Fresh cohort: TRAIN only — simulated proxies, not questionnaire responses')
    fig.savefig(OUT/'questionnaires_and_target.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(2,3,figsize=(12,6.3),layout='constrained')
    labels=['Main-sleep WASO (minutes)','Hours since latest sleep','Nap sleep in 24h (minutes)','Total sleep in 24h (hours)','Prior 3-day shortfall (hours)']
    for ax,col,title in zip(axes.flat,EXTRA[2:],labels):
        ax.hist(d[col],bins=30,color='#267c92',edgecolor='white',linewidth=.3);ax.set_title(title);ax.set_ylabel('Training rows')
    axes[1,2].scatter(d.self_report_fatigue_score,d.samn_perelli_like_fatigue_score,s=3,alpha=.12,color='#a66a36')
    axes[1,2].set(xlabel='Existing custom fatigue score',ylabel='Synthetic SP-range proxy',title='Two noisy views of\nsimulated latent fatigue')
    fig.suptitle('Hypothetical sleep allocations and synthetic proxy relationship — TRAIN only')
    fig.savefig(OUT/'sleep_extension_distributions.png',dpi=170);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8.5,6.5),layout='constrained')
    cols=['self_report_fatigue_score','sleep_duration_hours','sleep_efficiency_pct','sleep_midpoint_deviation_minutes']+EXTRA
    matrix=d[cols].corr()
    shown=ax.imshow(matrix,vmin=-1,vmax=1,cmap='RdBu_r')
    short=['Current fatigue','Main sleep','Sleep efficiency','Midpoint deviation','KSS-range proxy','SP-range proxy','WASO','Time awake','Nap minutes','Total24h sleep','Prior3day shortfall']
    ax.set_xticks(range(len(cols)),short,rotation=65,ha='right',fontsize=8)
    ax.set_yticks(range(len(cols)),short,fontsize=8)
    ax.set_title('TRAIN correlations include designed/derived relationships')
    fig.colorbar(shown,ax=ax,shrink=.75)
    fig.savefig(OUT/'extension_correlations.png',dpi=170);plt.close(fig)
    result={'status':'passed','scope':'TRAIN-only visual EDA before fitting; validation/test CSVs not read',
            'observation_files_read':['data/train.csv'],'train_sha256':sha(train_path),'plan_sha256':sha(HERE/'EXPERIMENT_PLAN.json'),
            'rows':len(d),'people':d.participant_id.nunique(),'features_baseline':len(base),'features_extended':len(base+EXTRA),
            'checks':checks,'class_counts':{str(k):int(v) for k,v in distribution.items()},
            'questionnaire_level_counts':{c:{str(k):int(v) for k,v in d[c].value_counts().sort_index().items()} for c in EXTRA[:2]},
            'zero_variance_features':[c for c in base+EXTRA if d[c].nunique()<=1],
            'decisions':['Keep prespecified 26/28/31/33feature comparisons; do not select features from held-out data.',
                         'Questionnaire proxies share current hidden fatigue with the target process; any benefit can reflect assumed extra latent-state information.',
                         'Sleep timing/WASO mainly re-express existing aggregates, and randomized naps have no causal restoration effect in the base target generator.',
                         'Retain full cohort and original prespecified noise; no extreme-row removal or favorable-noise search.'],
            'models_fitted':False,'clinical_validation':False}
    (OUT/'TRAIN_ONLY_EDA.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
