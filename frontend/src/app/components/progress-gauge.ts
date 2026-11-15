import { Component, computed, input } from '@angular/core';

// 270° arc around (100, 100), open at the bottom
const R = 76;
const START_DEG = 135;
const SWEEP_DEG = 270;
const ARC = 'M46.26 153.74 A76 76 0 1 1 153.74 153.74';

/** Calibration progress: how many daily records of the 7 needed for the personal baseline exist. */
@Component({
  selector: 'section[appProgressGauge]',
  host: { class: 'dark-block gauge-block' },
  template: `
    <svg viewBox="0 0 200 180" role="img" [attr.aria-label]="shown() + ' of ' + required() + ' calibration records'">
      <path [attr.d]="arc" pathLength="100" class="gauge-track" />
      <path [attr.d]="arc" pathLength="100" class="gauge-fill" [attr.stroke-dasharray]="pct() + ' 100'" />
      <circle [attr.cx]="marker().x" [attr.cy]="marker().y" r="6" class="gauge-marker" />
      <text x="100" y="104" text-anchor="middle" class="gauge-num">{{ count() }}</text>
      <text x="100" y="126" text-anchor="middle" class="gauge-sub">{{ count() === 1 ? 'record' : 'records' }}</text>
    </svg>
    <h2>{{ done() ? 'Baseline ready' : 'Calibration' }}</h2>
    <p>{{ done() ? 'Forecasts run on every new record' : shown() + ' of ' + required() + ' records for the baseline' }}</p>
  `,
})
export class ProgressGauge {
  readonly count = input.required<number>();
  readonly required = input(7);

  protected readonly arc = ARC;
  protected readonly shown = computed(() => Math.min(this.count(), this.required()));
  protected readonly done = computed(() => this.count() >= this.required());
  protected readonly pct = computed(() => (this.shown() / this.required()) * 100);
  protected readonly marker = computed(() => {
    const rad = ((START_DEG + (SWEEP_DEG * this.pct()) / 100) * Math.PI) / 180;
    return { x: 100 + R * Math.cos(rad), y: 100 + R * Math.sin(rad) };
  });
}
