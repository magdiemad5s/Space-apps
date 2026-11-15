#!/usr/bin/env python3
"""Build the Arabic data-generation handout without altering frozen data.

From this directory: python build_guide.py
For PDF rendering: python build_guide.py --pdf
Data checks require numpy/pandas; PDF additionally requires Playwright,
Chromium, and an Arabic font (Noto Naskh Arabic recommended).
"""
from pathlib import Path
import argparse
import csv
import hashlib
import html
import importlib.metadata
import json
import shutil

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / 'data'
STEM = 'ASTRA_SHIELD_Data_Generation_Guide_AR'
REPO_URL = 'https://github.com/magdiemad5s/Space-apps/blob/main/ai/data/'


def esc(value):
    return html.escape(str(value))


def eq(value):
    return '<pre dir="ltr">' + esc(value.strip()) + '</pre>'


def p(value, cls=''):
    return f'<p class="{cls}">{value}</p>'


def note(value):
    return '<aside>' + value + '</aside>'


def source(start, end=None):
    end = end or start
    return p(f'مرجع التنفيذ: <a href="{REPO_URL}source_generator.py#L{start}-L{end}">'
             f'<span dir="ltr">source_generator.py · L{start}–L{end}</span></a>', 'source')


def table(headers, rows, cls=''):
    return f'<table class="{cls}"><thead><tr>' + ''.join('<th>'+x+'</th>' for x in headers) + \
        '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+x+'</td>' for x in row)+'</tr>' for row in rows) + '</tbody></table>'


def code(text):
    return '<code dir="ltr">' + esc(text) + '</code>'


def excel(n):
    out = ''
    while n:
        n, d = divmod(n - 1, 26)
        out = chr(65 + d) + out
    return out


# Formula notation is defined in the guide. One entry for every main CSV column.
# tuple: Arabic meaning, exact derivation, source line range, guide section.
FORMULAS = {
 'record_id': ('معرّف سجل الشخص واليوم', "f'{participant_id}_D{mission_day:+04d}'", '111', '2'),
 'participant_id': ('معرّف شخص افتراضي', "f'SIM_{n:03d}'; n = 1..120", '61-66', '2'),
 'observation_timestamp_utc': ('موعد توفر قياسات اليوم', "2026-01-01T18:00:00Z + (mission_day - 1) days", '13,109,112', '2'),
 'mission_day': ('رقم اليوم؛ ليس رقم صف إكسل', 'raw: -6..61 inclusive; main: 1..60 inclusive', '75,134', '2'),
 'split': ('تقسيم ثابت حسب الشخص', 'rng.permutation(1..120); first 84 train, next 18 validation, last 18 test', '61-63', '2'),
 'is_synthetic': ('علم البيانات الاصطناعية', '1', '113', '1'),
 'data_origin': ('مصدر البيانات', "'synthetic'", '114', '1'),
 'generator_version': ('إصدار المولّد', "'astra_synthetic_v1.0'", '12,114', '1'),
 'sleep_duration_hours': ('مدة النوم بالساعات', 'R3(sleep_need + N(0, 0.35 if cal else 0.7) - 0.27*max(0,L-7) - 0.11*S - 0.55*abs(C)/180, 3.2, 9.8)', '83', '4'),
 'sleep_efficiency_pct': ('كفاءة النوم الاصطناعية', 'E0=R3(96-0.85*S-0.05*abs(C)+N(0,2.2),58,99); cap=100*sleep/(sleep+(latency+3*awakenings)/60); min(E0,floor(1000*cap)/1000)', '84,87-90', '4'),
 'sleep_onset_delay_minutes': ('تأخر بدء النوم بالدقائق', 'R3(8 + 2.7*S + 0.06*abs(C) + N(0,5), 1, 90)', '85', '4'),
 'awakenings_count': ('عدد الاستيقاظات', 'int(clip(Poisson(0.6 + 0.15*S + 0.007*abs(C)),0,10))', '86', '4'),
 'sleep_midpoint_deviation_minutes': ('انحراف منتصف النوم بالدقائق', 'round(C,3); C=clip(0.65*C_prev+N(0,15 if cal else 38)+12*D,-180,180)', '82,117', '3'),
 'resting_heart_rate_bpm': ('نبض الراحة الاصطناعي', 'R3(hr_base + 0.75*S + 0.65*F + N(0,2.2) + event*U(13,24),40,125)', '97', '6'),
 'hrv_rmssd_ms': ('قيمة RMSSD اصطناعية دون تخطيط قلب خام', 'R3(hrv_base*exp(-0.035*S-0.035*F+N(0,0.08))*(U(0.45,0.72) if event else 1),8,115)', '98', '6'),
 'reaction_time_median_ms': ('وسيط زمن الاستجابة', 'R3(median(rt_trials_after_replacement),150,800); 60 trials; see section 7', '99-104', '7'),
 'reaction_time_lapses_count': ('عدد الاستجابات التي بلغت 500 ms أو أكثر', 'sum(rt_trials_after_replacement >= 500)', '105', '7'),
 'reaction_time_trials_count': ('عدد محاولات المحاكاة الثابت', '60', '100,120', '7'),
 'attention_correct_count': ('الإجابات الصحيحة في مهمة انتباه منفصلة', 'int(Binomial(40,p_attention)); p_attention=clip(0.995-0.008*F-0.0025*S+N(0,0.015),0.65,0.995)', '106-107', '7'),
 'attention_trials_count': ('عدد محاولات مهمة الانتباه', '40', '121', '7'),
 'attention_accuracy_pct': ('نسبة الإجابات الصحيحة', 'round(100*attention_correct_count/40,3)', '121', '7'),
 'self_report_stress_score': ('محاكاة التقييم الذاتي للضغط', 'R3(S + N(0,0.7),0,10)', '94', '5'),
 'self_report_fatigue_score': ('محاكاة التقييم الذاتي للتعب', 'R3(F + N(0,0.65),0,10)', '93', '5'),
 'self_report_mood_score': ('محاكاة المزاج؛ الأعلى أفضل', 'R3(8.6 - 0.30*S - 0.23*F + N(0,0.9),0,10)', '95', '5'),
 'workload_hours': ('ساعات العمل', 'R3(N(6.6 if cal else 8.2,1.1)+D,3,15)', '79', '3'),
 'exercise_minutes': ('مدة الرياضة بالدقائق', 'R3(N(55 if cal else 42,18)-3*D,0,110)', '80', '3'),
 'journal_text': ('نص يوميات إنجليزي مركّب من قوالب', 'Unique template composition from TEMPLATES[split][journal_class], ops, context, fatigue and an integer in [2,24]; up to 1000 uniqueness attempts', '17-53,125', '9'),
 'target_current_physiology_event_injected': ('وسم حدث محقون للمحاكاة', 'int((not cal) and U(0,1)<0.065)', '96,126', '6'),
 'target_journal_stress_class': ('وسم فئة لغة اليوميات', 'class_of(clip(S+N(0,1),0,10)); not class_of(V)', '108,127', '9'),
 'baseline_sleep_duration_hours': ('متوسط نوم أيام المعايرة السبعة', 'round(mean(sleep_duration_hours[d] for d in -6..0),6), per participant', '131-136', '8'),
 'baseline_resting_heart_rate_bpm': ('متوسط نبض أيام المعايرة السبعة', 'round(mean(resting_heart_rate_bpm[d] for d in -6..0),6), per participant', '131-136', '8'),
 'baseline_hrv_rmssd_ms': ('متوسط RMSSD لأيام المعايرة السبعة', 'round(mean(hrv_rmssd_ms[d] for d in -6..0),6), per participant', '131-136', '8'),
 'baseline_reaction_time_median_ms': ('متوسط وسطاء الاستجابة خلال المعايرة', 'round(mean(reaction_time_median_ms[d] for d in -6..0),6), per participant', '131-136', '8'),
 'sleep_duration_delta_from_baseline_hours': ('فرق النوم الحالي عن المرجع', 'round(sleep_duration_hours-baseline_sleep_duration_hours,6)', '137', '8'),
 'heart_rate_delta_from_baseline_bpm': ('فرق النبض الحالي عن المرجع', 'round(resting_heart_rate_bpm-baseline_resting_heart_rate_bpm,6)', '138', '8'),
 'hrv_delta_from_baseline_ms': ('فرق RMSSD الحالي عن المرجع', 'round(hrv_rmssd_ms-baseline_hrv_rmssd_ms,6)', '139', '8'),
 'reaction_time_change_from_baseline_pct': ('تغير وسيط الاستجابة عن المرجع كنسبة', 'round(100*(reaction_time_median_ms/baseline_reaction_time_median_ms-1),6)', '140', '8'),
 'baseline_days_count': ('عدد أيام المعايرة', '7', '141', '8'),
 'prior_3day_mean_sleep_hours': ('متوسط النوم للأيام الثلاثة السابقة فقط', "raw.groupby('participant_id')['sleep_duration_hours'].transform(lambda s: s.shift(1).rolling(3,min_periods=3).mean()).round(6); select main days", '143-145', '8'),
 'prior_3day_mean_resting_heart_rate_bpm': ('متوسط النبض للأيام الثلاثة السابقة فقط', "raw.groupby('participant_id')['resting_heart_rate_bpm'].transform(lambda s: s.shift(1).rolling(3,min_periods=3).mean()).round(6); select main days", '143-145', '8'),
 'prior_3day_mean_reaction_time_ms': ('متوسط وسطاء الاستجابة للأيام الثلاثة السابقة', "raw.groupby('participant_id')['reaction_time_median_ms'].transform(lambda s: s.shift(1).rolling(3,min_periods=3).mean()).round(6); select main days", '143-145', '8'),
 'target_timestamp_utc': ('تاريخ تحقق الهدف في اليوم التالي', 'observation_timestamp_utc[t+1], same participant; exactly +24 hours', '147-149', '10'),
 'target_next_day_fatigue_score': ('تقييم التعب الاصطناعي في اليوم التالي', 'self_report_fatigue_score[t+1], same participant', '147-149', '10'),
 'target_next_day_reaction_time_median_ms': ('وسيط الاستجابة في اليوم التالي', 'reaction_time_median_ms[t+1], same participant', '147-149', '10'),
 'prediction_horizon_hours': ('أفق التنبؤ بالساعات', '24', '150', '10'),
 'target_next_day_fatigue_class': ('تصنيف درجة التعب المبلّغ المحاكاة في اليوم التالي', 'class_of(target_next_day_fatigue_score); low if x<4, moderate if 4<=x<7, high if x>=7', '54-55,151', '10'),
}


def audit():
    ml = pd.read_csv(DATA / 'astra_shield_synthetic_ml.csv')
    raw = pd.read_csv(DATA / 'raw_observations.csv')
    assert list(ml.columns) == list(FORMULAS), 'Column coverage/order mismatch'
    checks = {}
    checks['main_shape_7200_by_46'] = ml.shape == (7200, 46)
    checks['raw_shape_8160_rows'] = len(raw) == 8160
    checks['unique_person_day_keys'] = not raw.duplicated(['participant_id', 'mission_day']).any()
    checks['no_missing_values_main_or_raw'] = not (ml.isna().any().any() or raw.isna().any().any())
    future = raw[['participant_id','mission_day','observation_timestamp_utc','self_report_fatigue_score','reaction_time_median_ms','split','record_role']].copy()
    future['mission_day'] -= 1
    joined = ml.merge(future, on=['participant_id','mission_day'], how='left', suffixes=('', '_future'), validate='one_to_one', indicator=True)
    checks['all_7200_targets_have_next_day_source'] = joined['_merge'].eq('both').all()
    for target, observed in [('target_next_day_fatigue_score','self_report_fatigue_score_future'),('target_next_day_reaction_time_median_ms','reaction_time_median_ms_future'),('target_timestamp_utc','observation_timestamp_utc_future')]:
        checks['exact_match_'+target] = joined[target].eq(joined[observed]).all()
    checks['targets_same_split'] = joined.split.eq(joined.split_future).all()
    checks['horizon_24_hours'] = (pd.to_datetime(joined.target_timestamp_utc,utc=True)-pd.to_datetime(joined.observation_timestamp_utc,utc=True)).eq(pd.Timedelta(hours=24)).all()
    classes = ml.target_next_day_fatigue_score.map(lambda x: 'low' if x < 4 else ('moderate' if x < 7 else 'high'))
    checks['class_cutoffs_match'] = classes.eq(ml.target_next_day_fatigue_class).all()
    final = joined[joined.mission_day.eq(60)]
    checks['all_120_final_outcomes_present'] = len(final) == 120 and final.record_role.eq('future_outcome_only').all()
    checks['raw_trials_constant_60'] = raw.reaction_time_trials_count.eq(60).all()
    checks['raw_lapse_counts_integral_in_range'] = (raw.reaction_time_lapses_count.between(0,60) & raw.reaction_time_lapses_count.mod(1).eq(0)).all()
    checks['raw_attention_formula'] = raw.attention_accuracy_pct.eq((100*raw.attention_correct_count/40).round(3)).all() and raw.attention_trials_count.eq(40).all()
    bases = ['sleep_duration_hours','resting_heart_rate_bpm','hrv_rmssd_ms','reaction_time_median_ms']
    b = raw[raw.mission_day.le(0)].groupby('participant_id')[bases].mean()
    for c in bases:
        checks['baseline_'+c] = np.allclose(ml['baseline_'+c], ml.participant_id.map(b[c]).round(6), rtol=0, atol=1e-6)
    for c, out in [('sleep_duration_hours','prior_3day_mean_sleep_hours'),('resting_heart_rate_bpm','prior_3day_mean_resting_heart_rate_bpm'),('reaction_time_median_ms','prior_3day_mean_reaction_time_ms')]:
        rolling = raw.groupby('participant_id')[c].transform(lambda s: s.shift(1).rolling(3,min_periods=3).mean()).round(6)
        expected = raw.assign(expected=rolling)[['record_id','expected']]
        paired = ml.merge(expected,on='record_id',validate='one_to_one')
        checks[out] = np.allclose(paired[out], paired.expected, rtol=0, atol=1e-6)
    for observed, baseline, derived in [
        ('sleep_duration_hours','baseline_sleep_duration_hours','sleep_duration_delta_from_baseline_hours'),
        ('resting_heart_rate_bpm','baseline_resting_heart_rate_bpm','heart_rate_delta_from_baseline_bpm'),
        ('hrv_rmssd_ms','baseline_hrv_rmssd_ms','hrv_delta_from_baseline_ms')]:
        checks[derived] = np.allclose(ml[derived],(ml[observed]-ml[baseline]).round(6),rtol=0,atol=1e-6)
    checks['reaction_delta_pct'] = np.allclose(ml.reaction_time_change_from_baseline_pct,((ml.reaction_time_median_ms/ml.baseline_reaction_time_median_ms-1)*100).round(6),rtol=0,atol=1e-6)
    config = json.loads((DATA/'task_config.json').read_text())
    predictors = config['tasks']['next_day_fatigue_classification']['predictors']
    checks['26_numeric_predictors_without_targets_or_ids'] = len(predictors)==26 and not any(c.startswith('target_') or c in ['participant_id','record_id','reaction_time_trials_count'] for c in predictors)
    checks = {k: bool(v) for k,v in checks.items()}
    assert all(checks.values()), checks
    files = ['source_generator.py','astra_shield_synthetic_ml.csv','raw_observations.csv','task_config.json','data_dictionary.csv']
    result = {'scope':'Data provenance and deterministic derivations only; no training or predictive evaluation. Reading held-out records here did not select or change a model.', 'checks':checks,'sha256':{f:hashlib.sha256((DATA/f).read_bytes()).hexdigest() for f in files},'limitations':['Latent states, per-trial arrays and random draws are absent from the exported CSVs; stochastic equations are verified against generator source, not inverted from the CSV.','Consistency does not establish scientific or clinical validity.']}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return ml, raw, result


def build():
    ml, raw, verification = audit()
    dictionary = {r['column_name']:r for r in csv.DictReader((DATA/'data_dictionary.csv').open())}
    records = []
    for n,(name,(meaning,formula,lines,section)) in enumerate(FORMULAS.items(),1):
        records.append({'excel_column':excel(n),'column_name':name,'meaning_ar':meaning,'equation_or_derivation':formula,'unit':dictionary[name]['unit'],'role':dictionary[name]['role'],'guide_section':section,'source_lines':lines})
    with (HERE/'ASTRA_SHIELD_Column_Equations.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
    shutil.copyfile(DATA/'source_generator.py',HERE/'ASTRA_SHIELD_original_generator.py')
    pages=[]
    def page(title,body,subtitle=''):
        n=len(pages)+1
        pages.append(f'<section class="sheet" id="section-{n}"><div class="brand" dir="ltr">ASTRA-SHIELD / DATA GENERATION</div><h1>{title}</h1>'+(p(subtitle,'sub') if subtitle else '')+body+f'<footer><span>محاكاة اصطناعية · astra_synthetic_v1.0</span><span>{n:02d}</span></footer></section>')

    page('١ · كيف صُنعت الداتا؟',
         p('مرجع المعادلات والتعريفات لفريق <b>ASTRA-SHIELD</b>، مطابق لكود توليد النسخة الأصلية ذات <b>7,200 صف و46 عمودًا</b>. يشمل الأعمدة من A إلى AT، الحالات الداخلية غير المصدّرة، قواعد المعايرة، وتكوين الأهداف.')+
         note('<b>المصدر الفعلي لكل القيم هو محاكاة برمجية.</b> لا توجد إجابات أشخاص حقيقيين أو قياسات روّاد فضاء أو بيانات NASA مقاسة داخل هذا الملف. معاملات المعادلات افتراضات هندسية لم تُقدَّر أو تُعايَر باستخدام بيانات بشرية حقيقية، وليست حدودًا أو معادلات طبية معتمدة.')+
         '<h2>أجوبة مباشرة عن الأسئلة المتكررة</h2>'+table(['السؤال','الإجابة'],[
             ['هل V وW وX إجابات استبيان؟','هي محاكاة لتقييم ذاتي من 0 إلى 10؛ ليست استبيانًا حقيقيًا أو KSS/PSS.'],
             ['لماذا توجد كسور عشرية؟','المولّد يضيف ضوضاء عشوائية ويقرّب معظم القياسات إلى 3 منازل.'],
             ['هل 60 محاولة تعني خمس دقائق؟','لا. الكود يولّد 60 استجابة ولا يحاكي الزمن المنقضي أو توقيت المحفّزات.'],
             ['ما تعريف الهفوة؟','استجابة تبلغ 500 ms أو أكثر؛ ليس حد PVT-B البالغ 355 ms.'],
             ['هل baseline اليوم الأول بلا تاريخ؟','لا. توجد 7 أيام اصطناعية سابقة، من −6 إلى 0، في ملف raw.'],
             ['من أين أهداف آخر يوم؟','اليوم 61 في raw يزوّد أهداف اليوم 60 في الملف الرئيسي.'],
         ])+
         '<h2>دليل القراءة</h2>'+p('٢: الرموز والبنية • ٣: الجدول والضغط • ٤: النوم • ٥: التعب ودرجات V/W/X • ٦: القلب والأحداث • ٧: الاستجابة والانتباه • ٨: baseline والتاريخ • ٩: اليوميات • ١٠: أهداف الغد • ١١–١٢: فهرس كل الأعمدة • ١٣: إعادة الإنتاج والتحقق.')+
         p('المرفقات: PDF للقراءة، HTML بنفس المحتوى، CSV لفهرس معادلات الأعمدة، ونسخة مطابقة من مولّد Python. التاريخ: 14 نوفمبر 2026.', 'small'),
         'ملف تسليم تقني بالعربية · معادلات البيانات وليست معادلات الموديل المتدرّب')

    page('٢ · الرموز والبنية والتهيئة',
         table(['الرمز','التعريف الدقيق'],[
             [code('N(mu, sigma)'),'سحب طبيعي بمتوسط mu وانحراف معياري sigma، وليس تباينًا.'],
             [code('U(a,b)'),'سحب منتظم مستمر ضمن [a,b) بحسب واجهة NumPy؛ الحد الأعلى غير مقصود كقيمة مشمولة.'],
             [code('clip(x,a,b)'),'حصر القيمة بين a وb.'],
             [code('R3(x,a,b)'),'clip أولًا ثم round إلى 3 منازل. round يتبع سلوك Python للأعداد العائمة.'],
             [code('S, F, C, D, L'),'ضغط داخلي، تعب داخلي، انحراف منتصف النوم، ضغط جدول، ساعات عمل.'],
             [code('cal = (t <= 0)'),'اليوم من أيام المعايرة. كل ظهور لتوزيع عشوائي يمثل سحبًا جديدًا؛ الحالات المرحّلة مستثناة.'],
         ])+
         '<h2>تهيئة مستقلة لكل شخص قبل اليوم −6</h2>'+eq('hr_base  ~ U(52,76)      hrv_base ~ U(32,76)\nrt_base  ~ U(225,295)    sleep_need ~ U(7.4,8.5)\nF_initial ~ U(1.3,3.5)   S_initial ~ U(1.6,3.6)\nC_initial ~ N(0,12)')+
         p('هذه ثوابت وحالات داخلية، وليست أعمدة baseline الموجودة بالشيت. يبدأ كل شخص بهذه الحالة قبل توليد يوم −6، ثم تتطور S وF وC يوميًا. لا تُصدّر هذه الحالات كاملة ولا تُقرّب أثناء ترحيلها. المعادلات مرتبة للشرح؛ ترتيب السحوبات اللازم للتطابق الحرفي محفوظ في كود Python المرفق.')+
         '<h2>حجم البيانات والوقت والتقسيم</h2>'+eq('SEED = 20261114; rng = numpy.random.default_rng(SEED)\nparticipants = SIM_001 ... SIM_120\nraw days = -6 ... 61    -> 120 * 68 = 8160 rows\nmain days = 1 ... 60    -> 120 * 60 = 7200 rows\ntimestamp(t) = 2026-01-01T18:00:00Z + (t-1) days')+
         p('تُخلط قائمة الأشخاص عشوائيًا مرة واحدة: أول 84 للتدريب (5,040 صفًا)، ثم 18 للتحقق (1,080)، ثم 18 للاختبار (1,080). النسبة 70/15/15 <b>بالشخص</b>؛ جميع أيام الشخص تبقى في نفس القسم. التوليد نفسه يمر على الأشخاص بترتيب المعرّفات.')+source(59,75))

    page('٣ · ضغط الجدول والعمل والضغط الداخلي',
         p('تُحسب هذه الخطوات بالترتيب لكل يوم. D متغير ضغط جدول مخفي؛ قد يكون سالبًا في الفرع الطبيعي، أي يوم أخف من المعتاد.')+
         '<h2>ضغط الجدول D</h2>'+eq('if cal: D = 0\nelse:\n    if U(0,1) < 0.19: D ~ U(1.8,4.2)\n    else:             D ~ N(0,0.7)')+
         '<h2>Y · ساعات العمل، وZ · دقائق الرياضة</h2>'+eq('L = R3(N(6.6 if cal else 8.2, 1.1) + D, 3, 15)\nexercise = R3(N(55 if cal else 42, 18) - 3*D, 0, 110)')+
         p('تُستخدم ساعات العمل L بعد التقريب في المعادلات التالية. الرياضة مُخرَج سياقي في المحاكاة؛ لا يدخل exercise مباشرة في معادلة التعب الحالية.')+
         '<h2>الضغط الداخلي S</h2>'+eq('S_t = clip(\n  0.58*S_previous\n  + 0.42*(2.1 + 0.7*max(0,L-7) + 0.8*D)\n  + N(0,0.8),\n  0,10\n)')+
         p('S_previous هو <b>الضغط الداخلي السابق</b>، وليس العمود V السابق. S_t نفسه غير مُقرّب ويُستخدم في النوم والتعب والقلب والمزاج واليوميات.')+
         '<h2>M · انحراف توقيت النوم</h2>'+eq('C_t = clip(\n  0.65*C_previous + N(0,15 if cal else 38) + 12*D,\n  -180,180\n)\nsleep_midpoint_deviation_minutes = round(C_t,3)')+
         p('C بوحدة الدقيقة: السالب أبكر والموجب متأخر بالنسبة للموعد المخطط للشخص الافتراضي. تستخدم المعادلات C الداخلي قبل تقريب نسخة العمود M.')+source(76,83))

    page('٤ · أعمدة النوم I إلى M',
         '<h2>I · مدة النوم بالساعات</h2>'+eq('sleep = R3(\n  sleep_need + N(0,0.35 if cal else 0.7)\n  - 0.27*max(0,L-7) - 0.11*S - 0.55*abs(C)/180,\n  3.2,9.8\n)')+
         '<h2>K · تأخر بدء النوم بالدقائق، وL · الاستيقاظات</h2>'+eq('latency = R3(8 + 2.7*S + 0.06*abs(C) + N(0,5),1,90)\nawakenings = int(clip(\n  Poisson(0.6 + 0.15*S + 0.007*abs(C)),0,10\n))')+
         p('Poisson ينتج عددًا صحيحًا غير سالب. تنبيه رمزي: L داخل المعادلات يعني ساعات العمل؛ أما حرف عمود إكسل L فيعني عدد الاستيقاظات.')+
         '<h2>J · كفاءة النوم</h2>'+eq('efficiency_initial = R3(\n  96 - 0.85*S - 0.05*abs(C) + N(0,2.2),58,99\n)\ncap = 100*sleep / (sleep + (latency + 3*awakenings)/60)\nefficiency = min(efficiency_initial, floor(1000*cap)/1000)')+
         p('السقف يفرض أن فرصة النوم تشمل تأخر البدء وثلاث دقائق يقظة على الأقل لكل استيقاظ. floor يقرّب السقف إلى الأسفل لأقرب 0.001 نقطة مئوية. هذا افتراض اتساق هندسي للمحاكاة، وليس قياسًا من جهاز نوم.')+
         note('تفصيل مهم: الحد 58 يطبّق في الحساب الأولي فقط؛ لا يعيد الكود فرضه بعد أخذ min مع السقف. لذلك لا ينبغي وصف 58 بأنه حد مضمون لكل إعادة تصميم للمولّد، حتى لو حققته البيانات الحالية.')+
         p('هذه المعادلات تستخدم مدة النوم والكمون والاستيقاظات المولّدة والمقرّبة. لا توجد موجات نوم أو سجل حركة خام اشتُقت منه هذه الأعمدة.')+source(83,90))

    page('٥ · التعب الداخلي ودرجات V وW وX',
         '<h2>التعب الداخلي F قبل حساب التقارير</h2>'+eq('F_t = clip(\n  0.57*F_previous\n  + 0.43*(1.8 + 1.35*max(0,sleep_need-sleep)\n          + 0.50*max(0,L-7) + 0.20*S\n          + 0.8*abs(C)/180)\n  + N(0,0.62),\n  0,10\n)')+
         p('العوامل هي استمرار التعب، نقص النوم عن احتياج الشخص الافتراضي، عبء العمل، الضغط الداخلي وانحراف توقيت النوم. F_previous ليس قيمة W السابقة، ولا تُحفظ F كعمود في الملف.')+
         '<h2>W · درجة التعب الذاتي المحاكاة</h2>'+eq('self_report_fatigue_score = R3(F_t + N(0,0.65),0,10)')+
         '<h2>V · درجة الضغط الذاتي المحاكاة</h2>'+eq('self_report_stress_score = R3(S_t + N(0,0.7),0,10)')+
         '<h2>X · درجة المزاج المحاكاة</h2>'+eq('self_report_mood_score = R3(\n  8.6 - 0.30*S_t - 0.23*F_t + N(0,0.9),0,10\n)')+
         note('لا يوجد هنا استبيان مُجاب عنه. كلمة self_report تصف نوع القياس الذي تحاكيه القيم. V وW: الأعلى ضغط أو تعب أكبر. X: الأعلى مزاج أفضل. معادلة X تستخدم S وF الداخليين، لا V وW مباشرة.')+
         p('الضوضاء المقصودة تمثل اختلاف الإبلاغ في المحاكاة؛ ليست خطأ إدخال يجب حذفه تلقائيًا. ثوابت 8.6 و0.30 و0.23 وباقي المعاملات اختيارات للمولّد وليست تقديرات مُثبتة علميًا.')+source(91,95))

    page('٦ · القلب وHRV والأحداث المحقونة',
         '<h2>AB · علم الحدث الفسيولوجي الاصطناعي</h2>'+eq('event = 0 if cal else int(U(0,1) < 0.065)\ntarget_current_physiology_event_injected = event')+
         p('احتمال الحدث 6.5% لكل يوم خارج المعايرة. عند حدوثه يضيف المولّد ارتفاعًا للنبض وخفضًا لـRMSSD. العلم يصف حقنًا برمجيًا، وليس تشخيصًا أو حدثًا صحيًا مثبتًا.')+
         '<h2>N · نبض الراحة</h2>'+eq('resting_heart_rate_bpm = R3(\n  hr_base + 0.75*S + 0.65*F + N(0,2.2)\n  + event*U(13,24),\n  40,125\n)')+
         '<h2>O · قيمة HRV من نوع RMSSD</h2>'+eq('event_factor = U(0.45,0.72) if event else 1\nhrv_rmssd_ms = R3(\n  hrv_base * exp(-0.035*S - 0.035*F + N(0,0.08))\n  * event_factor,\n  8,115\n)')+
         p('exp هي الدالة الأسّية الطبيعية. الضوضاء في معادلة HRV تدخل داخل الأس، وليست إضافة مباشرة بوحدة ms. معامل الحدث بين 0.45 و0.72 يُضرب في القيمة قبل تطبيق حدود القص.')+
         note('hr_base وhrv_base ثوابت مخفية عند تهيئة الشخص؛ ليست baseline_resting_heart_rate_bpm أو baseline_hrv_rmssd_ms. الأعمدة الأخيرة متوسطات قياسات أيام المعايرة بعد توليدها.')+
         p('وصف القياس المقصود هو تقييم راحة؛ الكود لا يولّد ECG أو فواصل ضربات NN، ولا يحسب RMSSD من إشارة فعلية. لذلك الناتج محاكاة لقيمة ملخصة فقط. علم AB مخصص للتقييم، ويُستبعد من مدخلات كاشف الشذوذ ومن ميزات التصنيف.')+source(96,98))

    page('٧ · الاستجابة والانتباه P إلى U',
         '<h2>توليد 60 استجابة في الجلسة</h2>'+eq('m = rt_base + 11*F + 3*S + 0.08*abs(C)\nrt[j] ~ LogNormal(mean=ln(m), sigma=0.12), j=1..60\np_lapse = clip(0.005 + 0.0055*F + 0.002*S,0.005,0.16)\nmask[j] = (U(0,1) < p_lapse)\nif mask[j]: rt[j] = U(500,1100)')+
         p('m هو وسيط توزيع الأساس النظري قبل الاستبدال، وليس وسيط العينة النهائي. في NumPy معلمتا lognormal تخصان التوزيع الطبيعي للوغاريتم. قد تتجاوز بعض الاستجابات 500 حتى دون الاستبدال.')+
         '<h2>P وQ وR · الملخصات من نفس الاستجابات</h2>'+eq('P = R3(median(rt[1..60]),150,800)\nQ = count(rt[j] >= 500)\nR = 60\nmedian for 60 sorted trials = (rt_sorted[30]+rt_sorted[31])/2')+
         p('Q يُعدّ بعد الاستبدال من <b>كل</b> الاستجابات، ولا يساوي بالضرورة عدد عناصر mask. وسيط P يُقص ويُقرّب بعد الحساب، أما Q فيُحسب من الاستجابات غير المقرّبة. المصفوفة الفردية لا تُصدّر في CSV.')+
         note('<b>تصحيح وصف التوقيت:</b> ورد وصف five-minute في ملفات المصدر القديمة، لكن لا توجد محاكاة لفواصل المحفّزات أو الزمن المنقضي. التعريف المنفّذ هو 60 استجابة بحد هفوة ≥500 ms؛ ليس اختبار PVT أو PVT-B مُتحققًا منه. لا يضمن اختبار زمني فعلي 60 محاولة.')+
         '<h2>S وT وU · مهمة انتباه منفصلة</h2>'+eq('p_attention = clip(\n  0.995 - 0.008*F - 0.0025*S + N(0,0.015),0.65,0.995\n)\nattention_correct_count ~ Binomial(40,p_attention)\nattention_trials_count = 40\nattention_accuracy_pct = round(100*attention_correct_count/40,3)')+
         p('النسبة تتحرك بخطوات 2.5 نقطة مئوية. هذه المهمة منفصلة عن محاولات زمن الاستجابة؛ لا تُحسب دقتها من عدد الهفوات. S داخل المعادلة يعني الضغط الداخلي، لا حرف عمود الإجابات الصحيحة.')+source(99,107))

    page('٨ · baseline والفروق ومتوسطات التاريخ',
         '<h2>AD إلى AG · المرجع الشخصي الثابت</h2>'+eq('baseline_X = round(mean(X[d] for d=-6,-5,-4,-3,-2,-1,0),6)\nX in {sleep_duration_hours, resting_heart_rate_bpm,\n      hrv_rmssd_ms, reaction_time_median_ms}\nbaseline_days_count = 7')+
         p('يُحسب المرجع لكل شخص على حدة، بعد توليد الأيام السبعة فعلًا في raw. يبقى ثابتًا خلال أيام المهمة. baseline الخاص بالاستجابة هو <b>متوسط الوسيط اليومي</b>، وليس وسيط جميع محاولات الأسبوع مجتمعة.')+
         '<h2>AH إلى AK · فروق اليوم عن المرجع</h2>'+eq('sleep_delta = round(sleep - baseline_sleep,6)\nheart_rate_delta = round(HR - baseline_HR,6)\nhrv_delta = round(HRV - baseline_HRV,6)\nreaction_change_pct = round(100*(RT/baseline_RT - 1),6)')+
         p('تُستخدم قيم baseline بعد تقريبها إلى 6 منازل. القيمة الموجبة لتغير الاستجابة تعني وسيطًا أبطأ من المرجع.')+
         '<h2>AM وAN وAO · الأيام الثلاثة السابقة فقط</h2>'+eq('prior_3day_mean_X[t] = round((X[t-3]+X[t-2]+X[t-1])/3,6)\nX in {sleep_duration_hours, resting_heart_rate_bpm,\n      reaction_time_median_ms}\n# Per participant, sorted by day:\nseries.shift(1).rolling(3,min_periods=3).mean()')+
         p('اليوم الحالي t واليوم التالي مستبعدان. في اليوم 1 تُستخدم أيام −2 و−1 و0. التقسيم والحسابات داخل الشخص تمنع اختلاط تاريخ شخص بتاريخ شخص آخر.')+
         table(['مثال موثّق للشخص SIM_001','القيمة'],[
             ['baseline النوم AD',code('8.021857 hours')],
             ['baseline النبض AE',code('69.714143 bpm')],
             ['baseline الاستجابة AG',code('322.237429 ms')],
             ['متوسط الاستجابة السابق لليوم 1، AO',code('323.076 ms')],
         ])+source(130,145))

    page('٩ · اليوميات ووسم الضغط النصّي',
         '<h2>AC · فئة لغة اليوميات</h2>'+eq('journal_score = clip(S + N(0,1),0,10)\nclass_of(x):\n    low       if x < 4\n    moderate  if 4 <= x < 7\n    high      if x >= 7\ntarget_journal_stress_class = class_of(journal_score)')+
         p('هذا الوسم يُستخرج من الضغط الداخلي مع سحب ضوضاء جديد، مستقل عن ضوضاء العمود V. لذلك ليس مطلوبًا أن يطابق تصنيف V. الحدود 4 و7 فئات تجريبية وليست حدودًا سريرية.')+
         '<h2>AA · تركيب نص اليوميات</h2>'+eq('bank = TEMPLATES[split]\ntext = class_sentence + " I " + operation_1 + " and "\n       + operation_2 + ". " + context_sentence + " "\n       + fatigue_sentence + " I recorded "\n       + integer(2..24) + " checklist items for follow-up."')+
         p('يختار المولّد جملة من بنك الفئة low/moderate/high، عمليتين من ops، جملة سياق، وجملة عن الطاقة. الاختيارات عشوائية ويمكن أن تتكرر العملية داخل النص. عدد البنود عدد صحيح من 2 إلى 24 شاملًا.')+
         p('توجد بنوك جمل منفصلة للتدريب والتحقق والاختبار. يفحص المولّد تفرّد النص الكامل باستخدام مجموعة عالمية used_journals؛ عند التكرار يعيد المحاولة حتى 1,000 مرة ثم يرفع خطأ. كل بنك يحتوي 4 جمل لكل فئة، و8 عمليات، و8 سياقات، و4 جمل عن الطاقة.')+
         note('اليوميات ليست نصوص روّاد فضاء ولا تفريغًا صوتيًا. جملة الطاقة تُختار من بنك قوالب ولا تحوّل قيمة W إلى نص. نجاح نموذج النص على هذه القوالب لا يثبت فهم الضغط في لغة المستخدمين الحقيقيين.')+
         p('كل الجمل الإنجليزية الأصلية موجودة في مصفوفة TEMPLATES ضمن ملف Python المرفق. اختلاف البنوك يقلل تكرار الصياغات بين الأقسام، لكنه لا يحوّل النصوص الاصطناعية إلى اختبار لغوي واقعي.')+source(17,54)+source(108,128))

    page('١٠ · أهداف الغد وسبب وجودها في آخر صف',
         '<h2>AP إلى AT · تحويل القياس اللاحق إلى هدف</h2>'+eq('target_timestamp_utc[t] = observation_timestamp_utc[t+1]\nAQ = target_next_day_fatigue_score[t] = W[t+1]\nAR = target_next_day_reaction_time_median_ms[t] = P[t+1]\nAS = prediction_horizon_hours = 24\nAT = class_of(AQ)\n# Within the same participant: shift(-1)')+
         p('AT يصنّف <b>درجة التعب المبلّغ المحاكاة لليوم التالي</b> بعد القص والتقريب، وليس التعب الداخلي F ولا تعب اليوم الحالي. حدود low/moderate/high هي نفسها 4 و7.')+
         '<h2>لماذا ينتهي الملف الرئيسي عند اليوم 60؟</h2>'+p('اليوم 61 موجود في raw بوسم future_outcome_only، لتوفير أهداف اليوم 60. لا يدخل كصف تدريب جديد لأنه لا يوجد يوم 62 يزوّده بهدف. صف إكسل 61 للشخص الأول = اليوم 60 عند احتساب صف العناوين.')+
         table(['السجل','الوقت / القيمة'],[
             [code('SIM_001_D+060'),code('2026-03-01T18:00:00Z')],
             [code('SIM_001_D+061'),code('2026-03-02T18:00:00Z')],
             ['AQ لليوم 60 = W لليوم 61',code('6.830')],
             ['AR لليوم 60 = P لليوم 61',code('360.631 ms')],
             ['AT لليوم 60',code('moderate')],
         ])+
         '<h2>مسموح كهدف، ممنوع كمدخل</h2>'+p('استخدام مستقبل صف التدريب كهدف هو أساس التعلّم الموجّه. التسريب يحصل إذا دخلت هذه القيم ضمن ميزات اليوم، أو استُخدمت بيانات الاختبار لاختيار الموديل. ملف task_config.json يحدد قوائم الميزات ويستبعد الأهداف والمعرّفات.')+
         p('يحتوي الملف الرئيسي 26 ميزة رقمية للمهمة الأساسية: 15 قياسًا حاليًا + 4 baselines + 4 فروق + 3 متوسطات سابقة. النص له مهمة منفصلة. لا تُستخدم الأعمدة الـ46 جميعها كميزات.')+
         note('record_role موجود في raw فقط: baseline_calibration للأيام ≤0، وprediction_observation للأيام 1–60، وfuture_outcome_only لليوم 61. ملف raw مصدر تدقيق وليس جدول ميزات جاهزًا للتدريب.')+source(130,153))

    role_ar={'predictor':'ميزة رقمية','text_predictor':'نص لمهمة منفصلة','metadata':'بيانات وصفية','target':'هدف / وسم'}
    for n,(begin,end) in enumerate([(0,23),(23,46)],11):
        rows=[]
        for r in records[begin:end]:
            rows.append([code(r['excel_column']),code(r['column_name']),esc(r['meaning_ar']),esc(role_ar[r['role']]),esc(r['guide_section'])])
        page(f'{"١١" if n==11 else "١٢"} · فهرس الأعمدة {excel(begin+1)}–{excel(end)}',
             p('الحروف تطابق ترتيب الأعمدة الأصلي دون حذف أو إعادة ترتيب. CSV المرفق يحتوي معادلة كل عمود، وحدته، دوره، ورقم سطر المصدر. الرموز داخل المعادلات تُعرّف في الأقسام السابقة.')+
             table(['حرف','اسم العمود','المعنى','الدور','قسم'],rows,'columns')+
             p('كون العمود رقميًا لا يعني أنه ميزة تدريب. القوائم المعتمدة موجودة في task_config.json. معلومات المصدر والتقسيم والمعرّفات والأهداف تُستبعد من الميزات.', 'small'))

    page('١٣ · إعادة الإنتاج وحدود الاستنتاج',
         '<h2>إعادة إنشاء الداتا في مجلد جديد</h2>'+eq('python -m venv .venv\n# Activate the environment for your operating system.\npython -m pip install numpy==2.3.5 pandas==2.2.3\n# Place ONLY a copy of ASTRA_SHIELD_original_generator.py\n# in a new empty folder, then run it there:\npython ASTRA_SHIELD_original_generator.py')+
         p('البيئة الأصلية Python 3.12. يكتب السكربت المخرجات <b>بجانب ملف السكربت نفسه</b>، وليس بالضرورة داخل مجلد Terminal الحالي. لا تشغّل النسخة الموجودة داخل ai/data فوق الملفات المجمدة. لا يحتاج التوليد GPU أو بيانات إنترنت أو تدريب موديل.')+
         p('يُنتج السكربت الملف الرئيسي وraw وparticipant_splits والقاموس وtask_config وgeneration_metadata وsource_manifest. ملفات train/validation/test منفصلة في المشروع؛ هذا السكربت وحده لا يصدّرها. عمود split يحدد كيفية فصلها.')+
         '<h2>البذرة وحدها لا تكفي إذا تغيّر الكود</h2>'+p('يستخدم جميع التوليد مولّد أرقام عشوائية واحدًا. ترتيب السحوبات، فروع الشروط، توليد اليوميات ومحاولات إزالة تكرارها تؤثر في القيم التالية. لتكرار الملف نفسه، استخدم نسخة السكربت المرفقة بلا تعديل وفي عملية Python جديدة، مع إصدارات المكتبات المحددة.')+
         '<h2>ما الذي تم التحقق منه؟</h2>'+p(f'تحقّق بناء هذا الدليل من تطابق جميع أهداف الـ7,200 صف مع raw، بما فيها آخر يوم لكل شخص، ومن التوقيت +24 ساعة، والفئات، والـbaseline، ومتوسطات الماضي والفروق. اجتازت الفحوص المحددة وعددها <b>{len(verification["checks"])}</b>. النتائج والبصمات محفوظة في verification.json. هذا تدقيق مصدر واتساق؛ لم يتضمن تدريبًا أو اختيار موديل أو إعادة تقييم أدائه.')+
         note('لا يمكن استرجاع الحالات الداخلية أو السحوبات أو كل الاستجابات الفردية من CSV وحده. الدليل يشرح خوارزمية التوليد الفعلية؛ لا يدّعي إثبات صحة افتراضاتها الطبية. العلاقات التي يتعلمها الموديل هنا هي علاقات صُمّمت في المحاكاة.')+
         p('إعادة بناء هذا الدليل: build_guide.py، مع NumPy/Pandas. لإنتاج PDF أضف --pdf مع Playwright وChromium وخط عربي. النسخة HTML تعمل دون مكتبات أو اتصال. تفاصيل بيئة التقرير في report_environment.json.', 'small')+
         p('<b>بصمة الملف الرئيسي SHA-256:</b>', 'small')+eq(verification['sha256']['astra_shield_synthetic_ml.csv'])+
         p('<a href="'+REPO_URL+'source_generator.py">كود التوليد</a> · <a href="'+REPO_URL+'data_dictionary.csv">القاموس الأصلي</a> · <a href="'+REPO_URL+'raw_observations.csv">السجلات الخام</a> · <a href="'+REPO_URL+'task_config.json">قوائم الميزات والأهداف</a>', 'small'))

    css='''
    @page {size:A4; margin:0;}
    * {box-sizing:border-box;}
    body {margin:0;background:#e8edf3;color:#16273b;font-family:'Noto Naskh Arabic','DejaVu Sans',sans-serif;font-size:11pt;line-height:1.55;}
    .sheet {width:210mm;min-height:297mm;position:relative;padding:14mm 15mm 18mm;margin:7mm auto;background:white;break-after:page;}
    .sheet:last-child {break-after:auto;}
    .brand {font-family:'DejaVu Sans',sans-serif;font-size:8pt;letter-spacing:1.8px;color:#43738b;border-bottom:2px solid #137b8c;padding-bottom:5mm;}
    h1 {font-size:22pt;margin:7mm 0 3mm;color:#113a53;line-height:1.35;}
    h2 {font-size:14pt;color:#176779;margin:4mm 0 1mm;}
    p {margin:2mm 0;}
    .sub {color:#567083;font-size:12pt;}
    .small,.source {font-size:9pt;color:#4e6575;}
    pre {font-family:'DejaVu Sans Mono',monospace;font-size:9pt;line-height:1.5;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;background:#eff4f8;border-left:3px solid #137b8c;border-radius:3px;padding:2.3mm 3mm;margin:2mm 0;unicode-bidi:isolate;}
    code {font-family:'DejaVu Sans Mono',monospace;font-size:8.6pt;unicode-bidi:isolate;display:inline-block;text-align:left;overflow-wrap:anywhere;}
    aside {border-right:3px solid #ce9c3f;background:#fcf6e8;padding:3mm 4mm;margin:3mm 0;}
    table {width:100%;border-collapse:collapse;margin:3mm 0;font-size:10pt;}
    th {background:#e8f1f5;color:#113a53;text-align:right;}
    td,th {border-bottom:1px solid #dce5ea;padding:1.5mm 2mm;vertical-align:top;}
    .columns {font-size:9pt;table-layout:fixed;}
    .columns td,.columns th {padding:1.35mm 1.2mm;line-height:1.35;}
    .columns th:nth-child(1) {width:7%;}
    .columns th:nth-child(2) {width:43%;}
    .columns th:nth-child(3) {width:30%;}
    .columns th:nth-child(4) {width:14%;}
    .columns th:nth-child(5) {width:6%;}
    .columns code {font-size:7.5pt;}
    a {color:#08778c;text-decoration:none;}
    footer {position:absolute;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #cad7df;display:flex;justify-content:space-between;padding-top:2mm;font-size:8pt;color:#5e7484;}
    @media print {body{background:white;} .sheet{margin:0;height:297mm;min-height:0;}}
    '''
    document='<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>ASTRA-SHIELD — معادلات توليد البيانات</title><style>'+css+'</style></head><body>'+''.join(pages)+'</body></html>'
    (HERE/(STEM+'.html')).write_text(document,encoding='utf-8')
    packages={m:importlib.metadata.version(m) for m in ['numpy','pandas']}
    try:
        packages['playwright']=importlib.metadata.version('playwright')
    except importlib.metadata.PackageNotFoundError:
        packages['playwright']=None
    env={'python':'3.12 recommended','report_packages':packages,'pdf_browser':'Chromium at /usr/bin/chromium (override --chromium)','font':'Noto Naskh Arabic','command':'python build_guide.py --pdf','data_reproduction_packages':{'numpy':'2.3.5','pandas':'2.2.3'},'note':'No model fitting or dataset generation is performed by this report builder.'}
    (HERE/'report_environment.json').write_text(json.dumps(env,indent=2)+'\n')
    return len(pages)


def render_pdf(chromium):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pl:
        browser=pl.chromium.launch(executable_path=chromium,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1100,'height':1200},device_scale_factor=1)
        page.set_content((HERE/(STEM+'.html')).read_text(encoding='utf-8'))
        page.evaluate('document.fonts.ready')
        page.emulate_media(media='print')
        overflow=page.evaluate('''() => [...document.querySelectorAll('.sheet')].map((s,i)=>{const f=s.querySelector('footer');const bottom=Math.max(...[...s.children].filter(c=>c!==f).map(c=>c.getBoundingClientRect().bottom));return {section:i+1,overlap_px:Math.max(0,bottom-f.getBoundingClientRect().top),scroll_excess:s.scrollHeight-s.clientHeight};}).filter(x=>x.overlap_px>0||x.scroll_excess>1)''')
        if overflow:
            browser.close()
            raise RuntimeError('Page overflow: '+json.dumps(overflow))
        page.pdf(path=str(HERE/(STEM+'.pdf')),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=False)
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',action='store_true')
    parser.add_argument('--chromium',default='/usr/bin/chromium')
    args=parser.parse_args()
    print('Built sections:',build())
    if args.pdf:
        render_pdf(args.chromium)
        print('PDF:',HERE/(STEM+'.pdf'))
