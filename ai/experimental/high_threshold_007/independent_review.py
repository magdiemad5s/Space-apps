from pathlib import Path
from datetime import datetime,timezone
import ast,hashlib,json,math
import numpy as np
import pandas as pd
R=Path(__file__).resolve().parent; AI=R.parents[1]
checks=[]
def check(name,condition):
 if not bool(condition):raise AssertionError(name)
 checks.append(name)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def eq(a,b):
 if a is None:return b is None or (isinstance(b,float) and math.isnan(b))
 return b is not None and math.isclose(float(a),float(b),rel_tol=0,abs_tol=1e-11)
P=read(R/'PLAN.json'); F=read(R/'RUN_FROZEN.json'); E=read(R/'results/EXECUTION_VERIFICATION.json')
check('root plan hash',sha(R/'PLAN.json')=='5399aa38486c4e6e62be78613486182a97a5791fcd9eaafa346209a7cc26a6cb')
check('frozen source hash',sha(R/'run_thresholds.py')==F['script_sha256']==E['script_sha256'])
check('frozen tests hash',sha(R/'test_thresholds.py')==F['unit_tests_sha256'])
check('plan before source freeze before completed run',P['planned_at_utc']<=F['frozen_at_utc']<=E['completed_at_utc'])
source=ast.parse((R/'run_thresholds.py').read_text())
for node in ast.walk(source):
 if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):check('no fitting call '+node.func.attr,node.func.attr not in ['fit','fit_transform','partial_fit'])
for path,h in E['output_files_sha256'].items():check('frozen output '+path,sha(R/path)==h)
for path,h in read(R/'PRESERVATION_BEFORE.json')['sha256'].items():check('protected bytes '+path,sha(AI/path)==h)
L=['low','moderate','high']; cohort_results={}; cohorts=[]
def scores(y,p,b):
 cm=np.zeros((3,3),dtype=np.int64)
 for a,c in zip(y,p):cm[L.index(a),L.index(c)]+=1
 n=len(y); actual=cm.sum(axis=1); pred=cm.sum(axis=0); diag=np.diag(cm)
 tp=int(cm[2,2]); fn=int(cm[2,:2].sum()); fp=int(cm[:2,2].sum()); tn=int(cm[:2,:2].sum())
 per={lab:{'precision':float(diag[i]/pred[i]) if pred[i] else 0.,'recall':float(diag[i]/actual[i]) if actual[i] else 0.,'f1-score':float(2*diag[i]/(actual[i]+pred[i])) if actual[i]+pred[i] else 0.,'support':int(actual[i])} for i,lab in enumerate(L)}
 hi=np.asarray(p)=='high'; old=np.asarray(b)=='high'; yh=np.asarray(y)=='high'; promoted=hi&~old; demoted=old&~hi
 out={'rows':n,'high_support':tp+fn,'non_high_support':fp+tn,'high_tp':tp,'high_fn':fn,'high_fp':fp,'high_tn':tn,'high_recall':tp/(tp+fn),'high_precision':tp/(tp+fp) if tp+fp else None,'high_f1':2*tp/(2*tp+fp+fn),'macro_f1':sum(t['f1-score'] for t in per.values())/3,'accuracy':float(diag.sum()/n),'balanced_accuracy':sum(t['recall'] for t in per.values())/3,'high_false_positive_rate':fp/(fp+tn),'high_false_alarms_per_100_assessments':100*fp/n,'high_prediction_count':tp+fp,'high_predictions_per_100_assessments':100*(tp+fp)/n,'high_promotions':int(promoted.sum()),'high_demotions':int(demoted.sum()),'additional_high_cases_detected':int((promoted&yh).sum()),'additional_false_high_flags':int((promoted&~yh).sum()),'previous_high_cases_lost':int((demoted&yh).sum()),'previous_false_high_flags_removed':int((demoted&~yh).sum())}
 for label in L:
  for k,v in per[label].items():out[f'class_{label}_{k}']=v
 for i,a in enumerate(L):
  for j,c in enumerate(L):out[f'cm_{a}_as_{c}']=int(cm[i,j])
 return out,cm.tolist()
for cohort in ['primary','secondary']:
 d=R/'results'/cohort; S=read(d/'summary.json')
 rows=pd.read_csv(d/'frozenvalidationprobabilities.csv',float_precision='round_trip')
 G=pd.read_csv(d/'allthresholdmetrics.csv',float_precision='round_trip'); Q=pd.read_csv(d/'PRcurve.csv',float_precision='round_trip'); C=pd.read_csv(d/'confusionmatrices.csv',float_precision='round_trip'); U=pd.read_csv(d/'shortlist.csv',float_precision='round_trip')
 check(cohort+' dimensions',len(rows)==P[cohort]['expected_rows'] and rows.participant_id.nunique()==18)
 check(cohort+' record uniqueness',rows.record_id.is_unique and not rows.duplicated(['participant_id','mission_day']).any())
 check(cohort+' rows per person',rows.groupby('participant_id').size().eq(60).all())
 cohorts.append(set(rows.participant_id))
 check(cohort+' grid exactly planned',list(G.threshold)==P['threshold_grid'])
 check(cohort+' no nonfinite score',np.isfinite(rows[['probability_'+l for l in L]].to_numpy()).all())
 check(cohort+' normalized scores',np.allclose(rows[['probability_'+l for l in L]].sum(axis=1),1,atol=1e-9,rtol=0))
 check(cohort+' nonnegative bounded scores',rows[['probability_'+l for l in L]].ge(0).all().all() and rows[['probability_'+l for l in L]].le(1).all().all())
 y=rows.true_label.tolist(); baseline=rows.baseline_prediction.tolist()
 order=S['provenance'].get('classes_in_estimator_order',S['provenance'].get('classes_in_stored_estimator_order'))
 reconstructed=[max(order,key=lambda c:r['probability_'+c]) for r in rows.to_dict('records')]
 check(cohort+' baseline exact argmax',reconstructed==baseline)
 base,cm=scores(y,baseline,baseline)
 check(cohort+' baseline matrix',cm==S['baseline']['confusion_matrix'])
 for key in base:
  if key in S['baseline']:check(cohort+' baseline '+key,eq(base[key],S['baseline'][key]))
 parsed_obs=pd.to_datetime(rows.observation_timestamp_utc,utc=True); parsed_target=pd.to_datetime(rows.target_timestamp_utc,utc=True)
 check(cohort+' one-day target',((parsed_target-parsed_obs).dt.total_seconds()==86400).all())
 high=rows.probability_high.to_numpy(); low=rows.probability_low.to_numpy(); moderate=rows.probability_moderate.to_numpy(); yhigh=np.asarray(y)=='high'; positives=int(yhigh.sum())
 computed=[]
 for _,row in G.iterrows():
  t=float(row.threshold); pred=['high' if ph>=t else ('low' if pl>=pm else 'moderate') for ph,pl,pm in zip(high,low,moderate)]
  m,cm=scores(y,pred,baseline); computed.append({'threshold':t,**m})
  for key,value in m.items():check(f'{cohort} grid {t} {key}',eq(value,row[key]))
 check(cohort+' monotone threshold TP',all(a['high_tp']>=b['high_tp'] for a,b in zip(computed,computed[1:])))
 check(cohort+' monotone threshold FP',all(a['high_fp']>=b['high_fp'] for a,b in zip(computed,computed[1:])))
 check(cohort+' zero threshold all High',computed[0]['high_prediction_count']==len(rows))
 # Every score threshold on PR curve, independently counted rather than sklearn.
 check(cohort+' last PR endpoint has no threshold',pd.isna(Q.iloc[-1].threshold) and bool(Q.iloc[-1].endpoint_without_threshold))
 check(cohort+' last PR endpoint convention',Q.iloc[-1].precision==1 and Q.iloc[-1].recall==0)
 check(cohort+' PR unique scores',list(Q.iloc[:-1].threshold)==sorted(set(high)))
 for i,row in Q.iloc[:-1].iterrows():
  z=high>=row.threshold; tp=int((z&yhigh).sum()); pos=int(z.sum())
  check(f'{cohort} PR{i} precision',eq(tp/pos,row.precision))
  check(f'{cohort} PR{i} recall',eq(tp/positives,row.recall))
  check(f'{cohort} PR{i} threshold label',not row.endpoint_without_threshold)
 tp=fp=0; ap=0.
 for value in sorted(set(high),reverse=True):
  group=high==value; add=int((group&yhigh).sum()); tp+=add; fp+=int((group&~yhigh).sum()); ap+=(add/positives)*(tp/(tp+fp))
 check(cohort+' independently computed AP',eq(ap,S['high_average_precision']))
 check(cohort+' prevalence',eq(positives/len(rows),S['high_prevalence']))
 def chosen(name):
  if name=='baseline_argmax':return None
  if name=='best_high_f1_grid':return max(computed,key=lambda x:(x['high_f1'],x['macro_f1'],x['threshold']))
  if name=='best_macro_f1_grid':return max(computed,key=lambda x:(x['macro_f1'],x['high_recall'],x['threshold']))
  if name.startswith('recall_'):
   minimum=int(name.split('_')[1])/100; valid=[x for x in computed if x['high_recall']>=minimum and x['high_precision'] is not None]
   return max(valid,key=lambda x:(x['high_precision'],x['macro_f1'],x['threshold'])) if valid else None
  valid=[x for x in computed if x['high_precision'] is not None and x['high_precision']>=base['high_precision'] and x['macro_f1']>=base['macro_f1']-.02]
  return max(valid,key=lambda x:(x['high_recall'],x['macro_f1'],x['threshold'])) if valid else None
 shortlisted={}
 for candidate in S['shortlist']:
  name=candidate['candidate_name']; x=chosen(name)
  if name=='baseline_argmax':expected=base; threshold=None; pred=baseline
  elif x is None:check(cohort+' unavailable '+name,not candidate['available']);continue
  else:
   expected=x; threshold=x['threshold']; pred=['high' if ph>=threshold else ('low' if pl>=pm else 'moderate') for ph,pl,pm in zip(high,low,moderate)]
  check(cohort+' selected '+name,eq(threshold,candidate['threshold']))
  ur=U.loc[U.candidate_name.eq(name)].iloc[0]
  for k,v in expected.items():
   if k in candidate['metrics']:check(cohort+' shortlist JSON '+name+' '+k,eq(v,candidate['metrics'][k]))
   if k in ur:check(cohort+' shortlist CSV '+name+' '+k,eq(v,ur[k]))
  _, matrix=scores(y,pred,baseline); cr=C.loc[C.candidate_name.eq(name)]
  check(cohort+' nine confusion entries '+name,len(cr)==9)
  for i,a in enumerate(L):
   for j,c in enumerate(L):check(cohort+' confusion '+name+' '+a+'/'+c,int(cr.loc[cr.actual_label.eq(a)&cr.predicted_label.eq(c),'count'].iloc[0])==matrix[i][j])
  shortlisted[name]={'threshold':threshold,**{k:expected[k] for k in ['high_tp','high_fn','high_fp','high_precision','high_recall','high_f1','macro_f1']}}
 cohort_results[cohort]={'rows':len(rows),'people':rows.participant_id.nunique(),'high_count':positives,'average_precision':ap,'shortlist':shortlisted}
check('distinct cohort people',cohorts[0].isdisjoint(cohorts[1]))
report={'status':'passed_with_scientific_limitations','reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'scope':'Independent read-only source review and manual recomputation from saved validation probabilities; no estimator deserialization, fitting, new model inference or test observation/prediction parsing. Prior files were byte-hashed only for preservation.','checks_passed':len(checks),'checks_failed':0,'plan_sha256':sha(R/'PLAN.json'),'reviewed_script_sha256':sha(R/'run_thresholds.py'),'protected_files_verified':len(read(R/'PRESERVATION_BEFORE.json')['sha256']),'results':cohort_results,'limitations':['Same reused validation sets select and estimate thresholds; apparent gains are exploratory and optimistic.','Both cohorts consist of18virtualparticipants; repeateddays are not independent human validation.','High model score is uncalibrated; threshold is not a medical-risk cutoff.','No threshold is promoted or declared clinically acceptable; an acceptable false-alarm budget remains a team decision.','The old full-argmax baseline is distinct from a fixed0.5High threshold.'], 'checks':checks}
import argparse
parser=argparse.ArgumentParser(description='Recompute saved validation results and check preservation; no model inference.')
parser.add_argument('--output',type=Path,help='Optional new JSON report file; existing files are refused')
args=parser.parse_args()
if args.output is not None:
 with args.output.open('x') as handle: handle.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
