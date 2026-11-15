import { Component, input, output, signal } from '@angular/core';
import type { Measurements, Snapshot } from '../types';
import { CalibrationCard } from './calibration-card';
import { ReactionTest, type ReactionResult } from './reaction-test';
import { LogForm, type FormMessage, type RecordSubmit } from './log-form';

@Component({
  selector: 'div[appCheckInView]',
  imports: [CalibrationCard, ReactionTest, LogForm],
  host: { class: 'checkin' },
  template: `
    <article
      appCalibrationCard
      [snapshot]="snapshot()"
      [canRetry]="canRetry()"
      [busy]="busy()"
      (retry)="retry.emit()"
      (changeServer)="changeServer.emit()"
    ></article>
    <article appReactionTest (result)="onReaction($event)"></article>
    <article
      appLogForm
      [previous]="previous()"
      [reaction]="reaction()"
      [busy]="busy()"
      [message]="message()"
      [pendingRetry]="canRetry()"
      (submitRecord)="submitRecord.emit($event)"
    ></article>
  `,
})
export class CheckInView {
  readonly snapshot = input.required<Snapshot>();
  readonly previous = input<Measurements | null>(null);
  readonly busy = input(false);
  readonly canRetry = input(false);
  readonly message = input<FormMessage | null>(null);
  readonly submitRecord = output<RecordSubmit>();
  readonly retry = output<void>();
  readonly changeServer = output<void>();

  protected readonly reaction = signal<(ReactionResult & { at: number }) | null>(null);

  protected onReaction(r: ReactionResult): void {
    this.reaction.set({ ...r, at: Date.now() });
  }
}
