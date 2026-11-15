#!/usr/bin/env python3
"""Render the audit's completed results as a standalone Arabic HTML/PDF.

Run after audit_core.py, replay/audit_replay.py and api/run_api_integrity.py.
Rendering requires Playwright + Chromium + an Arabic system font. No data or
model files are written by this renderer.
"""
from pathlib import Path
import argparse
import base64
import csv
import html
import json

HERE=Path(__file__).resolve().parent
STEM='ASTRA_SHIELD_Data_Audit_AR'


def read(name):
    return json.loads((HERE/name).read_text())


def p(text,cls=''):
    return f'<p class="{cls}">{text}</p>'


def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+x+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+x+'</td>' for x in r)+'</tr>' for r in rows)+'</tbody></table>'


def note(text):
    return '<aside>'+text+'</aside>'


def code(text):
    return '<pre dir="ltr">'+html.escape(text)+'</pre>'


def img(name):
    encoded=base64.b64encode((HERE/name).read_bytes()).decode()
    return '<img alt="Audit plot" src="data:image/png;base64,'+encoded+'">'


def build():
    c=read('core_summary.json'); r=read('replay/checks.json'); a=read('api/API_CONTRACT_INTEGRITY.json')
    assert c['checks_failed']==0 and r['failed_assertions']==0 and a['status']=='passed'
    current=next(row for row in csv.DictReader((HERE/'replay/recovered_session_summary.csv').open()) if row['record_id']=='SIM_001_D+008')
    pages=[]
    def page(title,body):
        n=len(pages)+1
        pages.append(f'<section class="sheet"><div class="brand" dir="ltr">ASTRA-SHIELD / DATA INTEGRITY AUDIT</div><h1>{title}</h1>'+body+f'<footer><span>15 نوفمبر 2026 · توقيت عمّان</span><span>{n:02d}</span></footer></section>')

    page('١ · نتيجة التدقيق',
        note('<b>نجحت فحوص الاتساق المحددة للداتا الحالية.</b> لم تظهر أخطاء تستدعي حذف صفوف أو تعويض قيم. هذا لا يعني أن المحاكاة قياسات بشرية صحيحة طبيًا، ولا أن القياسات الجديدة أصبحت موجودة أو مستخدمة بالموديل.')+
        p('يغطي التقرير الملف الرئيسي: <b>7,200 صف ×46 عمودًا</b>، وملف المصدر raw: <b>8,160 صفًا لـ120 شخصًا افتراضيًا</b>. تظل الداتا والموديل الأصليان محفوظين دون تعديل؛ لا تدريب جديد ولا تغيير للميزات أو الأهداف.')+
        table(['الفحص','النتيجة'],[
            ['فحوص البنية والحسابات والتاريخ والتقسيم',f'<b>{c["checks_passed"]}/{c["checks_total"]}</b> نجحت؛ تشمل 8 اختبارات اكتشاف إفساد متعمّد لنسخة مؤقتة.'],
            ['قيم مفقودة في الأعمدة الموجودة / صفوف مكررة','0 / 0. هذا لا يحسب القياسات المقترحة التي لا توجد لها أعمدة أصلًا.'],
            ['إعادة توليد المصدر الأصلي','7 من 7 ملفات تطابقت حرفيًا byte-for-byte.'],
            ['إعادة فحص الاستجابات الفردية','8,160 جلسة ×60 = 489,600 استجابة؛ كل وسيط وعدد هفوات يطابق مصدره.'],
            ['تفاصيل فحص إعادة التشغيل',f'{r["check_groups"]} مجموعة؛ {r["individual_assertions"]:,} تحقق فردي؛ صفر فشل.'],
            ['اختبارات Python الحالية','21 اختبارًا نجحت؛ تشمل مسارات FastAPI داخل العملية.'],
            ['اختبارات TypeScript الحالية','16 اختبارًا نجحت، وكذلك فحص الأنواع الصارم.'],
            ['تطابق ميزات جميع الصفوف','7,200 صف عبر Python وTypeScript؛ أقصى فرق عددي في المقارنات =0.'],
        ])+
        p('الأعداد أعلاه فئات مختلفة من الفحوص ولا تُجمع لتوحي بعدد اختبارات مستقلة. ضوابط فساد النسخ المؤقتة أثبتت كشف هدف خاطئ وbaseline خاطئ وتاريخ غير صحيح وعدد هفوات مستحيل ونسبة انتباه خاطئة وNaN وInfinity واختلاط تقسيم الشخص.')+
        p('فحصنا جميع الأقسام للتأكد من سلامة البيانات فقط. لم تُستخدم نتائج الاختبار لاختيار موديل أو تنظيف صفوف أو تقدير أداء تنبؤي جديد. الرسوم ومراجعة القيم المتطرفة تستخدم بيانات التدريب فقط.'))

    page('٢ · الرد على الملاحظات الست',
        table(['الملاحظة','ما تحقق منه التدقيق','ما لم يُحسم'],[
            ['P / Q / R — الاستجابة','الوسيط وعدد ≥500 ms محسوبان من نفس 60 استجابة لكل جلسة.','لا يوجد توقيت محفّزات أو مدة فعلية أو false starts. التسمية الصحيحة: synthetic 60-trial reaction-time task. وصف خمس دقائق القديم لا يثبت تنفيذًا زمنيًا.'],
            ['S / T / U — الانتباه','عدد صحيح بين0و40، والدقة = الصحيح÷40×100، تطابق المصدر.','لا توجد مهمة عرض/استجابة بشرية محددة أو اختبار واجهة فعلية. تظل محاكاة فقط.'],
            ['AA / AC — اليوميات','نصوص غير فارغة وفريدة كاملةً؛ مصدرها بنوك قوالب ووسم توليدي. الخدمة تصف المخرج experimental.','لا توجد صلاحية مثبتة للغة بشرية حقيقية أو العربية أو تقييم نفسي. تفرّد النص الكامل لا يلغي تكرار القوالب.'],
            ['I–M — النوم','سقف الكفاءة والكمون واليقظة الافتراضية وميزانية24ساعة متسقة.','لا توجد أوقات نوم/استيقاظ أو قيلولة أو WASO مقاسة. ثلاث دقائق لكل استيقاظ افتراض للسقف، وليست مدة مقاسة.'],
            ['N / O — القلب وRMSSD','القيم والأحداث المحقونة تطابق المولّد وحدوده العددية.','لا ECG أو فواصل NN أو جهاز فعلي أو تحقق جودة إشارة. نوع الجهاز وظروف القياس الفعلية غير مختبرة.'],
            ['التصنيفات والتنبيهات','الأهداف تتبع حدود4و7 المعلنة. الخدمة تعرض clinical_validation:false والنقاط كمؤشر تجريبي.','لا توجد حدود طبية مثبتة، ولا معايرة لاحتمال خطر طبي. عرض التحذيرات في Angular/Ionic لم يُختبر.'],
        ])+
        note('وجود المعادلة الصحيحة والتحقق من تنفيذها يحل سؤال الاتساق البرمجي. جمع قياسات فعلية وتعريف بروتوكول الواجهة والتحقق العلمي خطوات منفصلة لا يمكن استبدالها بفحص CSV.')+
        p('المصادر المرجعية لتمييز القياسات: <a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC3250369/">Consensus Sleep Diary</a> و<a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC3197786/">دراسة PVT-B</a>. لا تُنسب معاملات المحاكاة إلى هاتين الدراستين.'))

    page('٣ · أمثلة حسابية تم التحقق منها',
        '<h2>المثال الذي أثار سؤال الهفوات</h2>'+table(['السجل SIM_001_D+008','القيمة بعد إعادة بناء نفس الاستجابات'],[
            ['عدد الاستجابات','60'],
            ['الوسيط',f'{float(current["reaction_time_median_ms"]):.3f} ms'],
            ['عدد ≥500 ms — التعريف الأصلي',current['reaction_time_lapses_count']],
            ['عدد ≥355 ms — حساب افتراضي فقط',current['counterfactual_lapses_ge355_count']],
        ])+
        p('إذن وسيط357.958 مع هفوتين صحيح وفق500ms. تطبيق355ms على نفس الاستجابات يعطي31، ولا يحوّل الجلسة إلى اختبار PVT-B معتمد. لم نغيّر حد الهفوات أو أي قيمة في الداتا.')+
        '<h2>الـbaseline ومتوسط الأيام السابقة</h2>'+p('أعيد حساب المراجع الأربعة لكل شخص من أيام−6إلى0 فقط، ثم الفروق ومتوسطات الأيام t−3 وt−2 وt−1. مطابقة كاملة ضمن دقة التصدير. لا تدخل قيمة اليوم أو المستقبل في متوسط الماضي.')+
        table(['مثال SIM_001','القيمة'],[
            ['baseline وسيط الاستجابة، متوسط7أيام','322.237429 ms'],
            ['متوسط الاستجابة السابق لليوم1، أيام−2و−1و0','323.076 ms'],
            ['هدف التعب لليوم60 = درجة اليوم61 في raw','6.830'],
            ['هدف الاستجابة لليوم60 = وسيط اليوم61','360.631 ms'],
            ['تصنيف الهدف السابق','moderate، لأن 4≤6.83&lt;7'],
        ])+
        p('تحققنا من مصدر كل أهداف الـ7,200 صف، بما فيها آخر يوم لكل الأشخاص الـ120، ومن تطابق وقت الهدف مع +24ساعة. اليوم61 مخصص لتزويد أهداف اليوم60 وليس صف تدريب بلا هدف لاحق.')+
        '<h2>التقسيم وعدم التسريب</h2>'+p('84 شخصًا للتدريب،18للتحقق،18للاختبار. لا يوجد شخص مشترك بين الأقسام؛ ملفات الأقسام تطابق الجزء الصحيح من الملف الرئيسي. الأهداف والمعرّفات وبيانات القسم ليست ضمن الميزات الـ26.'))

    page('٤ · الرسوم ومراجعة القيم المتطرفة',
        img('sleep_consistency.png')+
        p(f'الرسم العلوي: لا يوجد هامش سالب في قيود النوم والوقت المفحوصة. أقل وقت متبقٍ في جميع الصفوف ≈{c["minimum_remaining_daily_hours"]*60:.2f} دقيقة بعد فرصة النوم والعمل والرياضة. اجتياز هذا الحساب لا يثبت دقة جهاز أو سجل نوم فعلي.','caption')+
        img('baseline_history.png')+
        p('الرسم السفلي: أسبوع معايرة سابق، baseline ثابت، ومتوسط يتحرك باستخدام الأيام السابقة فقط. الشخص المعروض من قسم التدريب.','caption')+
        note(f'مراجعة التدريب وجدت <b>{c["noise_review"]["flagged_rows"]} صفًا متطرفًا إحصائيًا من5,040</b> وفق قاعدة robust z المعلنة. جميعها تحمل علم حدث فسيولوجي محقون أصلًا. هذه حالات مقصودة في المحاكاة وليست تلقائيًا أخطاء يجب حذفها. عدد الصفوف المحذوفة والقيم المعوّضة: <b>صفر</b>.')+
        p('توجد أيضًا ميزات مترابطة بسبب وجود القياس ومرجعه وفرقه. سُجّل ذلك في training_correlated_features.csv دون حذف آلي. لم يُجرَ اختبار جديد يدّعي أن إزالة الضوضاء تحسن الأداء.','caption'))

    page('٥ · هل يمكن إضافة القياسات الجديدة؟',
        p('<b>نعم كمرشحات جمع أو تدريب مستقبلي، لكن لا تُضاف إلى الموديل الحالي بمجرد إنشاء عمود.</b> تحتاج تعريفًا وقيمًا متاحة عند التنبؤ، ثم تجربة منفصلة لتحديد فائدتها. فحص التدقيق لا يملأها ولا يثبت تحسنًا متوقعًا.')+
        table(['القياس','التعامل الصحيح'],[
            ['KSS وSamn–Perelli','إجابتان منفصلتان: نعاس1–9 وتعب1–7. لا تحويل من درجة W. قيمة الهدف نفسه ممنوعة كميزة؛ درجة اليوم قد تكون مرشحًا لتنبؤ الغد.'],
            ['Sleep onset / wake / time awake','أوقات مع تاريخ ومنطقة زمنية ومصدر. عرّف هل مدة اليقظة منذ النوم الرئيسي أم آخر نوم بما فيه القيلولة. لا يمكن استنتاجها من المجاميع القديمة.'],
            ['القيلولة وWASO وإجمالي24ساعة','سجل حلقات النوم وفترات اليقظة؛ الإجمالي يقتصر على نافذة الـ24ساعة قبل التنبؤ دون تداخل أو عدّ مزدوج. وقت بداية/نهاية الحلقة وحده لا يثبت مدة النوم الفعلية.'],
            ['هدف النوم والنقص خلال3أيام','هدف محدد ومسجّل، ومتوسط baseline ليس احتياجًا بيولوجيًا معلومًا. احسب النقص من نوافذ يومية سابقة غير متداخلة.'],
            ['PVT false starts','تعريف بروتوكول وسجل أحداث للاستجابة؛ لا يمكن حسابها من الوسيط والهفوات. ليست60−عدد الهفوات.'],
            ['الكافيين والرياضة الحديثة','جرعات/نشاط مؤرخ؛ إجمالي رياضة اليوم لا يساوي آخر ساعتين. فائدتها للموديل تحتاج تقييمًا.'],
            ['الأعراض والأدوية','سياق مُبلّغ عنه مع حالة عدم المعرفة. الموديل الحالي لا يدعم فرزًا طبيًا؛ تنبيه الأعراض مسار منفصل يحتاج قواعد معتمدة.'],
            ['PHQ-2 وGAD-2','اختياريان وبنافذة أسبوعين؛ لا يستبدلان المزاج والضغط اليومي، ولا حاجة لفرضهما على الـMVP الحالي.'],
        ])+
        note('في فهرس الطلبات21بندًا: بندا الهفوات وساعات العمل موجودان أصلًا بشكل اصطناعي، و19بندًا غير موجود، منها PHQ-2 وGAD-2 الاختياريان. العدد ليس19اختبارًا فاشلًا أو شرطًا إلزاميًا؛ هي معلومات لم تُجمع. المجهول لا يتحول إلى صفر أو إجابات مختلقة.')+
        p('قائمة التفاصيل: requested_measurements.csv. قوائم «ضروري» في الصور توصيات تصميم وليست بذاتها دليلًا على اشتراط NASA لكل مقياس.'))

    page('٦ · توافق الـAPI وطريقة إعادة الفحص',
        table(['الفحص','النتيجة وحدودها'],[
            ['Python لكل صف',f'{a["python_all_rows"]["strict_schema_rows"]:,} صف؛ مقارنة {a["python_all_rows"]["scalar_feature_values_compared"]:,} قيمة ميزة؛ أكبر فرق0.'],
            ['TypeScript لكل التاريخ',f'{a["typescript_all_rows"]["canonical_observations_validated"]:,} ملاحظة:840معايرة و7,200جاهزة؛ مقارنة {a["typescript_all_rows"]["numeric_history_values_compared"]:,} قيمة؛ أكبر فرق0.'],
            ['مدخلات غير صالحة',f'Python: {a["python_invalid_input_cases_rejected_by_both_schema_and_feature_builder"]} حالة مرفوضة كما ينبغي. TypeScript: {a["typescript_all_rows"]["invalid_input_cases_rejected"]} حالة و4فحوص تميّز المجهول عن الصفر.'],
            ['أسماء الحقول الجديدة',f'{len(a["new_measurement_fields"])} اسمًا بما فيها أسماء بديلة: EXPECTED_UNSUPPORTED. Python422 داخل FastAPI، وTypeScript رفض من دالة التحقق؛ ليست جميعها تجارب HTTPخارجية.'],
        ])+
        note('الـAPI الحالي يرفض الحقول الجديدة؛ لا ترسلوها بالطلب القديم ولا تعيدوا تسميتها كأنها القياسات الحالية. إضافة جمعها تحتاج عقدًا وتخزينًا منفصلين أو نسخة API جديدة. استخدامها كتنبؤ يحتاج بيانات تدريب متوافقة وإعادة تقييم.')+
        p('الاختبارات استخدمت الاعتماديات المثبتة الحالية، وليست تثبيتًا نظيفًا على جهاز جديد. لم تتوفر واجهة Angular/Ionic للفحص. لم نكرر تقرير29اختبار TCP القديم ولم نغيّره. هذا التدقيق لا يختبر أجهزة أو صحة بشرية أو نشرًا فعليًا.')+
        '<h2>إعادة تشغيل التدقيق من جذر المستودع</h2>'+code('python ai/reports/data_integrity_2026_11_15/audit_core.py\npython ai/reports/data_integrity_2026_11_15/replay/audit_replay.py\npython ai/reports/data_integrity_2026_11_15/api/run_api_integrity.py\npython ai/reports/data_integrity_2026_11_15/render_report.py --pdf')+
        p('راجع README.md لكل قسم للاعتماديات والأمر الفعلي. إعادة المصدر تتطلب Python3.12 وNumPy2.3.5 وpandas2.2.3. renderer يحتاج Playwright وChromium وخطًا عربيًا. المخرجات تُكتب داخل مجلد التقرير فقط.')+
        p('ملفات الأدلة: core_checks.csv، core_summary.json، negative_controls.json، preservation.json، replay/checks.json، api/API_CONTRACT_INTEGRITY.json. الحالات الداخلية المستعادة في replay أدوات تدقيق فقط؛ لا تُضاف إلى ميزات الموديل.')+
        p('<b>القرار:</b> نستطيع إبقاء النسخة الحالية كديمو اصطناعي متسق مع تعريفاته. القياسات الجديدة والاختبارات البشرية والواجهة الفعلية تبقى أعمالًا غير مكتملة، ولا يصح إعلان حلها لمجرد نجاح هذا التدقيق.'))

    css='''@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;background:#e8edf3;color:#172b3d;font:11pt/1.55 'Noto Naskh Arabic','DejaVu Sans',sans-serif}.sheet{width:210mm;min-height:297mm;padding:14mm 15mm 18mm;margin:7mm auto;background:white;position:relative;break-after:page}.sheet:last-child{break-after:auto}.brand{font:8pt 'DejaVu Sans',sans-serif;color:#43738b;letter-spacing:1.3px;border-bottom:2px solid #147c8e;padding-bottom:5mm}h1{font-size:23pt;line-height:1.3;color:#163e54;margin:6mm 0 4mm}h2{font-size:14pt;color:#176779;margin:3mm 0 1mm}p{margin:2.3mm 0}aside{background:#fcf5e6;border-right:3px solid #d4a244;padding:3mm 4mm;margin:3mm 0}table{border-collapse:collapse;width:100%;font-size:10pt;margin:3mm 0}th{background:#eaf2f5;text-align:right;color:#163e54}td,th{padding:2mm;border-bottom:1px solid #dce5ea;vertical-align:top}th:first-child{width:27%}pre{font:7.7pt/1.6 'DejaVu Sans Mono',monospace;background:#eef4f7;border-left:3px solid #147c8e;white-space:pre-wrap;overflow-wrap:anywhere;padding:2.5mm;text-align:left;unicode-bidi:isolate}img{display:block;width:100%;margin:3mm 0}.caption{font-size:9.5pt}footer{position:absolute;bottom:8mm;left:15mm;right:15mm;border-top:1px solid #ccd8e0;padding-top:2mm;display:flex;justify-content:space-between;font-size:8pt;color:#5e7484}a{color:#08768c;text-decoration:none}@media print{body{background:white}.sheet{margin:0;min-height:0;height:297mm}}'''
    output='<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>ASTRA-SHIELD — تقرير تدقيق الداتا</title><style>'+css+'</style></head><body>'+''.join(pages)+'</body></html>'
    (HERE/(STEM+'.html')).write_text(output,encoding='utf-8')
    return len(pages)


def pdf(browser_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pl:
        browser=pl.chromium.launch(executable_path=browser_path,headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page()
        page.set_content((HERE/(STEM+'.html')).read_text())
        page.evaluate('document.fonts.ready')
        page.emulate_media(media='print')
        overflow=page.evaluate('''()=>[...document.querySelectorAll('.sheet')].map((s,i)=>{const f=s.querySelector('footer');const b=Math.max(...[...s.children].filter(c=>c!==f).map(c=>c.getBoundingClientRect().bottom));return {page:i+1,overlap:Math.max(0,b-f.getBoundingClientRect().top),extra:s.scrollHeight-s.clientHeight}}).filter(x=>x.overlap>0||x.extra>1)''')
        if overflow:raise RuntimeError('Report overflow: '+json.dumps(overflow))
        page.pdf(path=str(HERE/(STEM+'.pdf')),format='A4',prefer_css_page_size=True,print_background=True)
        browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pdf',action='store_true');parser.add_argument('--chromium',default='/usr/bin/chromium');args=parser.parse_args()
    print('Report pages:',build())
    if args.pdf:pdf(args.chromium)
