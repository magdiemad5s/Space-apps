import { Component, computed, input, output } from '@angular/core';
import type { DayRecord, Snapshot } from '../types';
import { CATEGORY_LEVEL } from '../lib/metrics';
import { nextCutoff } from '../data/source';

const fmt = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });

/** Status of the selected record and when the next daily record is due. */
@Component({
  selector: 'div[appOverviewStatus]',
  host: { class: 'overview-status' },
  template: `
    <button class="next-check" (click)="openCheckIn.emit()">
      <span>Next record</span>
      <b>{{ cutoff() }} UTC</b>
    </button>
    <span class="status-pill" [attr.data-level]="level()">
      <i aria-hidden="true"></i>
      {{ label() }}
      <small>{{ detail() }}</small>
    </span>
  `,
})
export class OverviewStatus {
  readonly record = input<DayRecord | null>(null);
  readonly snapshot = input.required<Snapshot>();
  readonly openCheckIn = output<void>();

  protected readonly cutoff = computed(() => fmt.format(new Date(nextCutoff(this.snapshot().records))));
  protected readonly level = computed(() => {
    const f = this.record()?.forecast;
    return f ? CATEGORY_LEVEL[f.category] : 'none';
  });
  protected readonly label = computed(() => {
    const r = this.record();
    if (!r) return 'No records yet';
    if (r.forecast) return `Forecast: ${r.forecast.category}`;
    return r.status === 'collecting_baseline' ? 'Calibrating' : 'No forecast';
  });
  protected readonly detail = computed(() => {
    const r = this.record();
    if (!r) return 'start with the first daily record';
    if (r.forecast) return 'next-day fatigue category';
    return r.status === 'collecting_baseline'
      ? `record ${r.index} of ${this.snapshot().calibrationRequired}`
      : 'model unavailable, record saved';
  });
}
