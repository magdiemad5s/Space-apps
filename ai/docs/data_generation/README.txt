ASTRA-SHIELD — دليل معادلات توليد البيانات

للمشاركة مع الفريق، أرسل الملفات بشكل منفصل دون ضغط:
1. ASTRA_SHIELD_Data_Generation_Guide_AR.pdf: الدليل العربي الكامل، 13 صفحة.
2. ASTRA_SHIELD_Column_Equations.csv: فهرس الأعمدة الـ46 ومعادلاتها.
3. ASTRA_SHIELD_original_generator.py: نسخة مطابقة لكود التوليد الأصلي.

HTML is the same guide in a browser-readable format, with no external assets.
verification.json records 27 data-provenance/derivation checks and source hashes.
report_environment.json records the report-rendering package versions.

Rebuild the guide from this directory in the repository:
    python -m pip install -r requirements-guide.txt
    python build_guide.py
    python build_guide.py --pdf
The PDF step needs local Chromium and an Arabic font, preferably Noto Naskh Arabic.
Use --chromium /path/to/chromium if its executable is not /usr/bin/chromium.
HTML/CSV generation only requires NumPy and pandas; Playwright is PDF-only.
The builder reads ../../data and writes only files in this guide directory.
It does not fit a model, regenerate the dataset, or change frozen inputs.

To reproduce the DATA instead of this GUIDE:
Use Python 3.12, NumPy 2.3.5, pandas 2.2.3. Copy ONLY the original-generator
attachment into a new empty directory and run it once in a fresh process.
The generator writes beside its own script, overwriting same-named outputs.
Do not execute the copy in ai/data over the frozen dataset.

All values are synthetic. "Self report" fields simulate responses rather than
containing answers from real people. The response task is fixed at 60 trials
with lapses >=500 ms; the generator does not implement a timed five-minute test.
See the PDF for latent states, rounding, baselines, history and future labels.
