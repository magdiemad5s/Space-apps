import { Component, computed, input, output } from '@angular/core';
import type { DayRecord } from '../types';

const VISIBLE = 5;

@Component({
  selector: 'div[appDayStrip]',
  host: { class: 'daystrip' },
  template: `
    <span class="daystrip-cap">Record</span>
    <button
      class="round-btn"
      (click)="dayChange.emit(index() - 1)"
      [disabled]="index() <= 0"
      aria-label="Previous record"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" /></svg>
    </button>
    <ol>
      @for (item of visible(); track item.record.index) {
        <li>
          <button
            [class.active]="item.i === index()"
            [attr.aria-current]="item.i === index() ? 'date' : null"
            (click)="dayChange.emit(item.i)"
          >
            <strong>{{ item.record.index }}</strong>
            <small>{{ item.ago === 0 ? 'Latest' : '−' + item.ago + 'd' }}</small>
          </button>
        </li>
      }
    </ol>
    <button
      class="round-btn"
      (click)="dayChange.emit(index() + 1)"
      [disabled]="index() >= records().length - 1"
      aria-label="Next record"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3l5 5-5 5" /></svg>
    </button>
    <span class="daystrip-cap">of {{ records().length }}</span>
  `,
})
export class DayStrip {
  readonly records = input.required<DayRecord[]>();
  readonly index = input.required<number>();
  readonly dayChange = output<number>();

  protected readonly visible = computed(() => {
    const records = this.records();
    const n = records.length;
    const start = Math.min(Math.max(0, this.index() - 2), Math.max(0, n - VISIBLE));
    return records
      .slice(start, start + VISIBLE)
      .map((record, k) => ({ record, i: start + k, ago: n - 1 - (start + k) }));
  });
}
