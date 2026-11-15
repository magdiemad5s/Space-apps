import { Component, input, output } from '@angular/core';
import type { DayRecord } from '../types';
import { CATEGORY_LEVEL } from '../lib/metrics';

/**
 * One column of dots per record. Records with a forecast show more dots for a higher index;
 * calibration and unavailable records show one hollow dot. The selected record becomes a pill.
 */
@Component({
  selector: 'div[appFatigueTimeline]',
  host: { class: 'timeline', role: 'group', 'aria-label': 'Forecast index by record' },
  template: `
    @for (r of records(); track r.index; let i = $index) {
      @if (i === index()) {
        <span class="timeline-pill" [attr.data-level]="level(r)">
          <span>{{ pillText(r) }}</span>
          <small>Record {{ r.index }}</small>
        </span>
      } @else {
        <button
          class="timeline-col"
          [class.hollow]="!r.forecast"
          [attr.data-level]="level(r)"
          (click)="dayChange.emit(i)"
          [attr.aria-label]="'Record ' + r.index + ': ' + pillText(r)"
        >
          @for (d of dots(r); track $index) {
            <i></i>
          }
        </button>
      }
    }
  `,
})
export class FatigueTimeline {
  readonly records = input.required<DayRecord[]>();
  readonly index = input.required<number>();
  readonly dayChange = output<number>();

  protected level(r: DayRecord): string {
    return r.forecast ? CATEGORY_LEVEL[r.forecast.category] : 'none';
  }

  protected pillText(r: DayRecord): string {
    if (r.forecast) return `Index ${Math.round(r.forecast.points)}`;
    return r.status === 'collecting_baseline' ? 'Calibration' : 'No forecast';
  }

  protected dots(r: DayRecord): number[] {
    const n = r.forecast ? Math.max(1, Math.round(r.forecast.points / 20)) : 1;
    return Array.from({ length: n }, (_, k) => k);
  }
}
