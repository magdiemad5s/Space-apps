import { Component, computed, input, signal } from '@angular/core';
import type { DayRecord, Level, PersonalBaseline } from '../types';
import { CATEGORY_LEVEL, MEASURES, MEASURE_ORDER, evaluate, formatValue, type MeasurementKey } from '../lib/metrics';

const W = 640;
const H = 250;
const PAD = { l: 46, r: 18, t: 18, b: 30 };

type SeriesKey = MeasurementKey | 'forecast';

@Component({
  selector: 'article[appTrendChart]',
  host: { class: 'card trend-card' },
  template: `
    <header>
      <h3>Trend by record</h3>
      <label class="series-pick">
        <span class="sr-only">Series</span>
        <select (change)="series.set(pick($event))" [value]="series()">
          <option value="forecast">Forecast index</option>
          @for (m of measureList; track m.key) {
            <option [value]="m.key">{{ m.label }}</option>
          }
        </select>
      </label>
    </header>

    @if (!hasData()) {
      <p class="chart-empty">No forecast yet. The forecast index appears from record 8, after calibration.</p>
    }

    <svg
      class="trend"
      [attr.viewBox]="'0 0 ' + W + ' ' + H"
      (mousemove)="onMove($event)"
      (mouseleave)="hover.set(null)"
    >
      <defs>
        <linearGradient id="trend-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" [attr.stop-color]="color()" stop-opacity="0.28" />
          <stop offset="100%" [attr.stop-color]="color()" stop-opacity="0" />
        </linearGradient>
      </defs>

      @for (t of ticks(); track t) {
        <g>
          <line [attr.x1]="PAD.l" [attr.x2]="W - PAD.r" [attr.y1]="y(t)" [attr.y2]="y(t)" class="grid-line" />
          <text [attr.x]="PAD.l - 8" [attr.y]="y(t) + 4" text-anchor="end" class="axis-text">{{ tickLabel(t) }}</text>
        </g>
      }

      @for (th of thresholds(); track th.level) {
        <g>
          <line
            [attr.x1]="PAD.l"
            [attr.x2]="W - PAD.r"
            [attr.y1]="y(th.value)"
            [attr.y2]="y(th.value)"
            [attr.stroke]="'var(--' + th.level + ')'"
            class="threshold-line"
          />
          <text [attr.x]="W - PAD.r" [attr.y]="y(th.value) - 5" text-anchor="end" class="threshold-text" [attr.fill]="'var(--' + th.level + ')'">
            {{ th.level === 'warning' ? 'watch' : 'action' }}
          </text>
        </g>
      }

      @if (baselineValue(); as b) {
        <g>
          <line [attr.x1]="x(required() - 1)" [attr.x2]="W - PAD.r" [attr.y1]="y(b)" [attr.y2]="y(b)" class="baseline-line" />
          <text [attr.x]="W - PAD.r" [attr.y]="y(b) - 5" text-anchor="end" class="axis-text">baseline from record 7</text>
        </g>
      }

      @if (dividerX(); as dx) {
        <g>
          <line [attr.x1]="dx" [attr.x2]="dx" [attr.y1]="PAD.t" [attr.y2]="PAD.t + innerH" class="divider-line" />
          <text [attr.x]="dx + 5" [attr.y]="PAD.t + 10" class="axis-text">forecasts start</text>
        </g>
      }

      @for (s of segments(); track $index) {
        <path [attr.d]="s.area" fill="url(#trend-fill)" />
        <path [attr.d]="s.line" fill="none" [attr.stroke]="color()" stroke-width="2.4" stroke-linejoin="round" />
      }
      @for (p of points(); track p.i) {
        <circle [attr.cx]="p.x" [attr.cy]="p.y" r="3" [attr.fill]="color()" />
      }
      @if (selectedPoint(); as sp) {
        <circle [attr.cx]="sp.x" [attr.cy]="sp.y" r="5" class="selected-dot" />
      }

      @for (r of records(); track r.index; let i = $index) {
        @if (i === 0 || (i + 1) % labelStep() === 0) {
          <text [attr.x]="x(i)" [attr.y]="H - 8" text-anchor="middle" class="axis-text">{{ r.index }}</text>
        }
      }

      @if (hoverPoint(); as hp) {
        <g>
          <line [attr.x1]="hp.x" [attr.x2]="hp.x" [attr.y1]="PAD.t" [attr.y2]="PAD.t + innerH" class="hover-line" />
          @if (hp.y !== null) {
            <circle [attr.cx]="hp.x" [attr.cy]="hp.y" r="5" fill="var(--bg)" [attr.stroke]="color()" stroke-width="2.4" />
          }
          <g [attr.transform]="'translate(' + hp.boxX + ',' + hp.boxY + ')'">
            <rect width="124" height="34" rx="6" class="tooltip-box" />
            <text x="10" y="14" class="tooltip-day">Record {{ hp.index }}</text>
            <text x="10" y="28" class="tooltip-value">{{ hp.text }}</text>
          </g>
        </g>
      }
    </svg>
  `,
})
export class TrendChart {
  readonly records = input.required<DayRecord[]>();
  /** Index of the selected record, marked on the line */
  readonly selected = input.required<number>();
  readonly baseline = input<PersonalBaseline | null>(null);
  readonly required = input(7);

  protected readonly W = W;
  protected readonly H = H;
  protected readonly PAD = PAD;
  protected readonly innerH = H - PAD.t - PAD.b;
  protected readonly measureList = MEASURE_ORDER.map((key) => ({ key, label: MEASURES[key].label }));
  protected readonly series = signal<SeriesKey>('forecast');
  protected readonly hover = signal<number | null>(null);

  protected readonly values = computed<(number | null)[]>(() => {
    const key = this.series();
    return this.records().map((r) => (key === 'forecast' ? (r.forecast?.points ?? null) : r.measurements[key]));
  });
  protected readonly hasData = computed(() => this.values().some((v) => v !== null));

  private readonly unit = computed(() => (this.series() === 'forecast' ? '/ 100' : MEASURES[this.series() as MeasurementKey].unit));

  private readonly domain = computed<[number, number]>(() => {
    const key = this.series();
    const base: [number, number] = key === 'forecast' ? [0, 100] : MEASURES[key].domain;
    const present = this.values().filter((v): v is number => v !== null);
    if (present.length === 0) return base;
    return [Math.min(base[0], Math.floor(Math.min(...present))), Math.max(base[1], Math.ceil(Math.max(...present)))];
  });

  protected readonly level = computed<Level | null>(() => {
    const key = this.series();
    const records = this.records();
    for (let i = records.length - 1; i >= 0; i--) {
      if (key === 'forecast') {
        const f = records[i].forecast;
        if (f) return CATEGORY_LEVEL[f.category];
      } else {
        return evaluate(key, records[i].measurements[key], this.baseline());
      }
    }
    return null;
  });
  protected readonly color = computed(() => (this.level() ? `var(--${this.level()})` : 'var(--ink-2)'));

  protected readonly points = computed(() =>
    this.values()
      .map((v, i) => (v === null ? null : { i, x: this.x(i), y: this.y(v) }))
      .filter((p): p is { i: number; x: number; y: number } => p !== null),
  );

  protected readonly segments = computed(() => {
    const bottom = PAD.t + this.innerH;
    const result: { line: string; area: string }[] = [];
    let current: { x: number; y: number }[] = [];
    const flush = () => {
      if (current.length > 0) {
        const line = current.map((p, k) => `${k === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
        const area = `${line} L${current[current.length - 1].x},${bottom} L${current[0].x},${bottom} Z`;
        result.push({ line, area });
      }
      current = [];
    };
    this.values().forEach((v, i) => {
      if (v === null) flush();
      else current.push({ x: this.x(i), y: this.y(v) });
    });
    flush();
    return result;
  });

  protected readonly selectedPoint = computed(() => {
    const v = this.values()[this.selected()];
    return v === null || v === undefined ? null : { x: this.x(this.selected()), y: this.y(v) };
  });

  protected readonly ticks = computed(() => {
    const [d0, d1] = this.domain();
    return [0, 1, 2, 3].map((k) => d0 + ((d1 - d0) * k) / 3);
  });

  protected readonly thresholds = computed(() => {
    const key = this.series();
    if (key === 'forecast') return [];
    const rule = MEASURES[key].rule;
    if (!rule || rule.kind !== 'absolute') return [];
    const [d0, d1] = this.domain();
    return (
      [
        { level: 'warning' as const, value: rule.warning },
        { level: 'critical' as const, value: rule.critical },
      ] satisfies { level: 'warning' | 'critical'; value: number }[]
    ).filter((th) => th.value >= d0 && th.value <= d1);
  });

  protected readonly baselineValue = computed(() => {
    const key = this.series();
    if (key === 'forecast') return null;
    const bk = MEASURES[key].baselineKey;
    const v = bk ? this.baseline()?.[bk] : undefined;
    const [d0, d1] = this.domain();
    return v !== undefined && v >= d0 && v <= d1 ? v : null;
  });

  protected readonly dividerX = computed(() => {
    const n = this.records().length;
    const req = this.required();
    return n > req ? (this.x(req - 1) + this.x(req)) / 2 : null;
  });

  protected readonly labelStep = computed(() => Math.max(1, Math.ceil(this.records().length / 8)));

  protected readonly hoverPoint = computed(() => {
    const i = this.hover();
    if (i === null) return null;
    const r = this.records()[i];
    const v = this.values()[i];
    const x = this.x(i);
    const y = v === null ? null : this.y(v);
    const key = this.series();
    const text =
      v === null
        ? 'no value'
        : `${key === 'forecast' ? String(Math.round(v * 10) / 10) : formatValue(key, v)} ${this.unit()}`;
    return {
      x,
      y,
      index: r.index,
      text,
      boxX: Math.min(x + 10, W - 140),
      boxY: Math.max((y ?? PAD.t + 40) - 38, PAD.t),
    };
  });

  protected x(i: number): number {
    const n = this.records().length;
    const inner = W - PAD.l - PAD.r;
    return PAD.l + (n <= 1 ? inner / 2 : (i * inner) / (n - 1));
  }

  protected y(v: number): number {
    const [d0, d1] = this.domain();
    return PAD.t + (1 - (v - d0) / (d1 - d0 || 1)) * this.innerH;
  }

  protected tickLabel(t: number): number {
    return Math.round(t * 10) / 10;
  }

  protected pick(e: Event): SeriesKey {
    return (e.target as HTMLSelectElement).value as SeriesKey;
  }

  protected onMove(e: MouseEvent): void {
    const svg = e.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const n = this.records().length;
    if (n === 0) return;
    const idx = n === 1 ? 0 : Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    this.hover.set(Math.min(n - 1, Math.max(0, idx)));
  }
}
