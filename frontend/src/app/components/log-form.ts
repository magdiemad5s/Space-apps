import { Component, computed, effect, input, output, signal, untracked } from '@angular/core';
import type { Measurements, MeasurementKey } from '../types';
import { MEASUREMENT_KEYS } from '../types';
import { GROUPS, MEASURES } from '../lib/metrics';
import { DEMO_RECORDS } from '../data/demo-data';
import type { ReactionResult } from './reaction-test';

export interface RecordSubmit {
  measurements: Measurements;
  journalText: string;
}

export interface FormMessage {
  tone: 'ok' | 'warning' | 'critical';
  text: string;
}

type Values = Record<MeasurementKey, string>;

function emptyValues(): Values {
  const out = {} as Values;
  for (const key of MEASUREMENT_KEYS) out[key] = '';
  return out;
}

function toStrings(m: Measurements): Values {
  const out = {} as Values;
  for (const key of MEASUREMENT_KEYS) out[key] = String(m[key]);
  return out;
}

/** Error text for one field, or null when it is valid. */
function fieldError(key: MeasurementKey, text: string): string | null {
  const measure = MEASURES[key];
  if (text.trim() === '') return 'Required.';
  const n = Number(text);
  if (!Number.isFinite(n)) return 'Enter a number.';
  if (measure.integer && !Number.isInteger(n)) return 'Enter a whole number.';
  if (n < measure.min || n > measure.max) return `Enter a value from ${measure.min} to ${measure.max}.`;
  return null;
}

@Component({
  selector: 'article[appLogForm]',
  host: { class: 'card log-card' },
  template: `
    <header>
      <h3>Today's record</h3>
      @if (allowExample()) {
        <button type="button" class="link-btn" [disabled]="busy()" (click)="fillExample()">Fill example values (simulated)</button>
      }
    </header>
    <p class="lead">
      Enter fresh measurements for this daily record before the cutoff. All 15 measurements are required;
      previous values are not copied into today's fields. Leave an unmeasured value blank until it is available.
    </p>

    <form class="log-form" (submit)="submit($event)" novalidate>
      @for (g of groups; track g.id) {
        <fieldset class="log-group">
          <legend>{{ g.title }}</legend>
          <div class="log-grid">
            @for (key of g.members; track key) {
              <div class="field">
                <label [for]="'f-' + key">
                  {{ measures[key].label }}
                  <span class="unit">{{ measures[key].unit }}</span>
                </label>
                <input
                  [id]="'f-' + key"
                  type="number"
                  inputmode="decimal"
                  [attr.min]="measures[key].min"
                  [attr.max]="measures[key].max"
                  [attr.step]="measures[key].integer ? 1 : 'any'"
                  [value]="values()[key]"
                  (input)="setValue(key, val($event))"
                  [attr.aria-invalid]="showErrors() && !!error(key)"
                />
                <small [class.error]="showErrors() && !!error(key)">
                  {{ showErrors() && error(key) ? error(key) : measures[key].hint }}
                </small>
                @if (key === 'attention_accuracy_pct') {
                  <button type="button" class="link-btn" [disabled]="busy()" (click)="markAttentionNotMeasured()">Not measured</button>
                  @if (attentionNotMeasured()) {
                    <small class="attention-missing" role="status">
                      Attention was not measured. This record cannot be saved or sent for a forecast until an externally measured value is supplied.
                    </small>
                  }
                }
              </div>
            }
          </div>
        </fieldset>
      }

      <div class="field field-wide">
        <label for="log-journal">Note for today (optional)</label>
        <textarea
          id="log-journal"
          rows="2"
          maxlength="400"
          placeholder="e.g. I woke up several times and feel tired today."
          [value]="journal()"
          (input)="journal.set(val($event))"
        ></textarea>
      </div>

      @if (pendingRetry()) {
        <p class="retry-hint">
          The latest record has no prediction yet. Retry it first (button in the card above): once a new day is saved,
          the older record can no longer be retried.
        </p>
      }

      <div class="form-actions">
        <button type="submit" class="btn btn-primary" [disabled]="busy()">
          {{ busy() ? 'Saving…' : 'Save daily record' }}
        </button>
        @if (showErrors() && invalidCount() > 0) {
          <span class="saved-note bad">{{ invalidCount() }} field(s) need attention.</span>
        }
        @if (message(); as m) {
          <span class="saved-note" [attr.data-level]="m.tone">{{ m.text }}</span>
        }
      </div>
    </form>
  `,
})
export class LogForm {
  /** Previous-record identity is a reset signal only; its measurements are never copied. */
  readonly previous = input<Measurements | null>(null);
  /** Example values are permitted only in the explicitly selected offline demo. */
  readonly allowExample = input(false);
  /** Result of the reaction test; `at` changes with every new result */
  readonly reaction = input<(ReactionResult & { at: number }) | null>(null);
  readonly busy = input(false);
  readonly message = input<FormMessage | null>(null);
  /** True when the latest record was saved without a prediction and can still be retried */
  readonly pendingRetry = input(false);
  readonly submitRecord = output<RecordSubmit>();

  protected readonly groups = GROUPS;
  protected readonly measures = MEASURES;
  protected readonly values = signal<Values>(emptyValues());
  protected readonly journal = signal('');
  protected readonly showErrors = signal(false);
  protected readonly attentionNotMeasured = signal(false);

  protected readonly invalidCount = computed(
    () => MEASUREMENT_KEYS.filter((k) => fieldError(k, this.values()[k]) !== null).length,
  );

  constructor() {
    effect(() => {
      this.previous();
      this.allowExample();
      untracked(() => {
        this.values.set(emptyValues());
        this.journal.set('');
        this.showErrors.set(false);
        this.attentionNotMeasured.set(false);
      });
    });
    effect(() => {
      const r = this.reaction();
      if (!r) return;
      untracked(() => {
        this.values.update((v) => ({
          ...v,
          reaction_time_median_ms: String(r.medianMs),
          reaction_time_lapses_count: String(r.lapses),
        }));
      });
    });
  }

  protected error(key: MeasurementKey): string | null {
    return fieldError(key, this.values()[key]);
  }

  protected val(e: Event): string {
    return (e.target as HTMLInputElement | HTMLTextAreaElement).value;
  }

  protected setValue(key: MeasurementKey, text: string): void {
    this.values.update((v) => ({ ...v, [key]: text }));
    if (key === 'attention_accuracy_pct' && text.trim() !== '') this.attentionNotMeasured.set(false);
  }

  protected markAttentionNotMeasured(): void {
    this.values.update((v) => ({ ...v, attention_accuracy_pct: '' }));
    this.attentionNotMeasured.set(true);
  }

  protected fillExample(): void {
    if (!this.allowExample() || this.busy()) return;
    this.values.set(toStrings(DEMO_RECORDS[0].measurements as Measurements));
    this.showErrors.set(false);
    this.attentionNotMeasured.set(false);
  }

  protected submit(e: Event): void {
    e.preventDefault();
    this.showErrors.set(true);
    if (this.invalidCount() > 0) return;
    const measurements = {} as Measurements;
    for (const key of MEASUREMENT_KEYS) measurements[key] = Number(this.values()[key]);
    this.submitRecord.emit({ measurements, journalText: this.journal() });
  }
}
