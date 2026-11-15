import { Component, computed, input, output } from '@angular/core';
import type { DayRecord, Level } from '../types';
import { CATEGORY_LEVEL } from '../lib/metrics';

const fmt = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
});

interface Prob {
  key: 'low' | 'moderate' | 'high';
  label: string;
  value: number;
  pct: number;
  level: Level;
}

/**
 * Next-day forecast of the selected record: category and index, the model's class probabilities and the index over
 * time. Calibration and unavailable records show their own state instead.
 */
@Component({
  selector: 'article[appFatigueCard]',
  host: { class: 'card forecast-card', '[attr.data-level]': 'level() ?? \'none\'' },
  template: `
    <header>
      <h3>Next-day fatigue forecast</h3>
      @if (dateText()) {
        <span class="fc-date">{{ dateText() }}</span>
      }
    </header>

    @switch (state()) {
      @case ('forecast') {
        <p class="mini-label fc-origin">{{ forecastOrigin() }}</p>
        <div class="fc-body">
          <section class="fc-main">
            <p class="fc-category">{{ category() }}</p>
            <p class="fc-index">
              <strong>{{ points() }}</strong>
              <span>/ 100 index</span>
            </p>
            <p class="fc-note">Prototype Fatigue Index, not a medical percentage or clinical risk probability.</p>
          </section>

          <section class="fc-probs">
            @if (probs().length > 0) {
              <p class="mini-label">Uncalibrated model class outputs</p>
              <div class="prob-bar" role="img" [attr.aria-label]="probsLabel()">
                @for (p of probs(); track p.key) {
                  <span [attr.data-level]="p.level" [style.flex]="p.value + ' 1 0'"></span>
                }
              </div>
              <ul class="prob-legend">
                @for (p of probs(); track p.key) {
                  <li [attr.data-level]="p.level">
                    <i aria-hidden="true"></i>{{ p.label }} <b>{{ p.pct }}%</b>
                  </li>
                }
              </ul>
              <p class="fc-foot">Rounded percentages may not total 100%.</p>
            }
            <ul class="fc-rows">
              <li>
                <span>Score estimate (separate model)</span>
                <b>{{ score() === null ? 'Unavailable' : score() + ' / 10' }}</b>
              </li>
              @if (reaction() !== null) {
                <li>
                  <span>Median reaction forecast</span>
                  <b>{{ reaction() }} ms</b>
                </li>
              }
            </ul>
          </section>

          <section class="fc-trend">
            <p class="mini-label">Index by record</p>
            <svg class="fc-spark" viewBox="0 0 200 72" role="img" [attr.aria-label]="'Forecast index over ' + spark().length + ' records'">
              <line x1="0" x2="200" [attr.y1]="y(50)" [attr.y2]="y(50)" class="fc-grid" />
              <line x1="0" x2="200" [attr.y1]="y(0)" [attr.y2]="y(0)" class="fc-grid" />
              @if (spark().length > 1) {
                <polyline [attr.points]="sparkLine()" class="fc-line" />
              }
              @for (p of spark(); track p.index) {
                <circle [attr.cx]="p.x" [attr.cy]="p.y" [attr.r]="p.selected ? 5 : 3" [attr.data-level]="p.level" [class.selected]="p.selected" />
              }
            </svg>
            <p class="fc-trend-cap">{{ sparkCaption() }}</p>
          </section>
        </div>
        <p class="fc-foot">
          {{ forecast()?.origin === 'simulated_example' ? 'Saved fictional example; no model request is made in this mode.' : 'Model-generated result for this record; not a new inference on every view.' }}
          Model training used synthetic data. Limits are in the Guide.
        </p>
      }

      @case ('calibrating') {
        <div class="fc-state">
          <p class="fc-category">Calibrating</p>
          <ol class="calib-steps" [attr.aria-label]="'Record ' + record()?.index + ' of ' + required()">
            @for (i of steps(); track i) {
              <li [class.done]="i <= (record()?.index ?? 0)" [class.current]="i === record()?.index">{{ i }}</li>
            }
          </ol>
          <p class="fc-note">
            Record {{ record()?.index }} of {{ required() }}. The first {{ required() }} daily records build your fixed
            personal baseline. Eligible records can receive a forecast from record {{ required() + 1 }} when the service is available.
          </p>
        </div>
      }

      @case ('unavailable') {
        <div class="fc-state">
          <p class="fc-category">No forecast</p>
          <p class="fc-note">This record is saved, but no usable model prediction is available for it.</p>
          @if (record()?.status === 'model_unavailable') {
            <button type="button" class="btn" (click)="openCheckIn.emit()">Retry in Check-in</button>
          } @else {
            <p class="fc-note">Refresh data to check the backend result.</p>
          }
        </div>
      }

      @default {
        <div class="fc-state">
          <p class="fc-note">No records yet. Add the first daily record in the Check-in tab.</p>
        </div>
      }
    }
  `,
})
export class FatigueCard {
  readonly record = input<DayRecord | null>(null);
  readonly records = input.required<DayRecord[]>();
  readonly required = input(7);
  readonly openCheckIn = output<void>();

  protected readonly state = computed<'forecast' | 'calibrating' | 'unavailable' | 'none'>(() => {
    const r = this.record();
    if (!r) return 'none';
    if (r.forecast) return 'forecast';
    return r.status === 'collecting_baseline' ? 'calibrating' : 'unavailable';
  });

  protected readonly forecast = computed(() => this.record()?.forecast ?? null);
  protected readonly forecastOrigin = computed(() => this.forecast()?.origin === 'simulated_example'
    ? 'Simulated example forecast' : 'Model-generated forecast');
  protected readonly level = computed<Level | null>(() => {
    const f = this.forecast();
    return f ? CATEGORY_LEVEL[f.category] : null;
  });
  protected readonly category = computed(() => this.forecast()?.category ?? '');
  protected readonly points = computed(() => Math.round((this.forecast()?.points ?? 0) * 10) / 10);
  protected readonly score = computed(() => { const score = this.forecast()?.score; return score == null ? null : score.toFixed(1); });
  protected readonly reaction = computed(() => {
    const ms = this.forecast()?.reactionForecastMs;
    return ms === null || ms === undefined ? null : Math.round(ms);
  });
  protected readonly dateText = computed(() => {
    const f = this.forecast();
    if (f?.targetTimestamp && Number.isFinite(Date.parse(f.targetTimestamp))) return `for ${fmt.format(new Date(f.targetTimestamp))} UTC`;
    if (f) return 'Target date unavailable';
    const r = this.record();
    return r ? `record ${r.index}` : '';
  });
  protected readonly steps = computed(() => Array.from({ length: this.required() }, (_, i) => i + 1));

  protected readonly probs = computed<Prob[]>(() => {
    const p = this.forecast()?.probabilities;
    if (!p) return [];
    const rows: [Prob['key'], string, Level][] = [
      ['low', 'Low', 'ok'],
      ['moderate', 'Moderate', 'warning'],
      ['high', 'High', 'critical'],
    ];
    return rows.map(([key, label, level]) => ({ key, label, level, value: p[key], pct: Math.round(p[key] * 100) }));
  });
  protected readonly probsLabel = computed(() =>
    this.probs()
      .map((p) => `${p.label} ${p.pct}%`)
      .join(', '),
  );

  protected y(points: number): number {
    return 66 - (points / 100) * 58;
  }

  protected readonly spark = computed(() => {
    const withForecast = this.records().filter((r) => r.forecast);
    const n = withForecast.length;
    const selectedIndex = this.record()?.index;
    return withForecast.map((r, i) => ({
      index: r.index,
      x: n === 1 ? 100 : 8 + (i * 184) / (n - 1),
      y: this.y(r.forecast?.points ?? 0),
      level: r.forecast ? CATEGORY_LEVEL[r.forecast.category] : 'ok',
      selected: r.index === selectedIndex,
    }));
  });
  protected readonly sparkLine = computed(() =>
    this.spark()
      .map((p) => `${p.x},${p.y}`)
      .join(' '),
  );
  protected readonly sparkCaption = computed(() => {
    const s = this.spark();
    if (s.length === 0) return '';
    return s.length === 1 ? `Record ${s[0].index}` : `Records ${s[0].index} – ${s[s.length - 1].index}`;
  });
}
