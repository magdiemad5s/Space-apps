import { Component, computed, input, output } from '@angular/core';
import type { Snapshot } from '../types';
import { nextCutoff } from '../data/source';

const fmt = new Intl.DateTimeFormat('en-GB', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZone: 'UTC',
});

/** Where the astronaut stands in the 7-day calibration and what happens with the next record. */
@Component({
  selector: 'article[appCalibrationCard]',
  host: { class: 'card checks-card' },
  template: `
    <header>
      <h3>Daily record</h3>
      <span class="streak">{{ stateLabel() }}</span>
    </header>

    <div class="checks-top">
      <svg class="ring" viewBox="0 0 44 44" role="img" [attr.aria-label]="shown() + ' of ' + required() + ' calibration records'">
        <circle cx="22" cy="22" r="18" pathLength="100" class="ring-track" />
        <circle
          cx="22"
          cy="22"
          r="18"
          pathLength="100"
          class="ring-fill"
          [attr.stroke-dasharray]="(shown() / required()) * 100 + ' 100'"
          transform="rotate(-90 22 22)"
        />
        <text x="22" y="26" text-anchor="middle">{{ shown() }}/{{ required() }}</text>
      </svg>
      <p>
        {{
          inCalibration()
            ? 'Calibration: the first ' + required() + ' daily records build your fixed personal baseline. No forecast is made yet.'
            : 'Baseline ready. New daily records can receive a next-day forecast while the model is available.'
        }}
      </p>
    </div>

    <ul class="check-list">
      <li data-status="upcoming">
        <i aria-hidden="true"></i>
        <span>Next record cutoff</span>
        <em>{{ cutoff() }} UTC</em>
      </li>
      <li [attr.data-status]="snapshot().records.length > 0 ? 'done' : 'upcoming'">
        <i aria-hidden="true"></i>
        <span>Records saved</span>
        <em>{{ snapshot().records.length }}</em>
      </li>
      <li [attr.data-status]="sourceStatus()">
        <i aria-hidden="true"></i>
        <span>Data source</span>
        <em>
          {{ sourceText() }} ·
          <button type="button" class="link-btn" (click)="changeServer.emit()">change</button>
        </em>
      </li>
    </ul>
    @if (settingsError()) { <p class="saved-note bad" role="alert">{{ settingsError() }}</p> }

    @if (canRetry()) {
      <div class="retry-box">
        <p>The last record is saved, but the model gave no prediction.</p>
        <button class="btn btn-primary" [disabled]="busy()" (click)="retry.emit()">Retry the prediction</button>
      </div>
    }
  `,
})
export class CalibrationCard {
  readonly snapshot = input.required<Snapshot>();
  readonly canRetry = input(false);
  readonly busy = input(false);
  readonly settingsError = input<string | null>(null);
  readonly retry = output<void>();
  /** Let the user enter another backend address */
  readonly changeServer = output<void>();

  protected readonly sourceText = computed(() => {
    const { source, backend } = this.snapshot();
    if (source === 'demo') return 'Simulated demo (explicitly selected)';
    return backend.modelReady ? 'Live backend, model ready' : 'Live backend, model offline';
  });
  protected readonly sourceStatus = computed(() => {
    const { source, backend } = this.snapshot();
    return source === 'backend' && backend.modelReady ? 'done' : 'overdue';
  });

  protected readonly required = computed(() => this.snapshot().calibrationRequired);
  protected readonly shown = computed(() => Math.min(this.snapshot().records.length, this.required()));
  protected readonly inCalibration = computed(() => this.snapshot().records.length < this.required());
  protected readonly stateLabel = computed(() => (this.inCalibration() ? 'Calibrating' : 'Forecasting'));
  protected readonly cutoff = computed(() => fmt.format(new Date(nextCutoff(this.snapshot().records))));
}
