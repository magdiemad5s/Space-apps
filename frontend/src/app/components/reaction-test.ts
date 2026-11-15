import { Component, DestroyRef, computed, inject, output, signal } from '@angular/core';

/** Prototype scoring cutoff shared with the synthetic 60-response model data. */
const LAPSE_MS = 500;
/** Faster than this is an anticipation, not a reaction */
const FALSE_START_MS = 100;

type Mode = 'full' | 'quick';
type Phase = 'idle' | 'waiting' | 'go' | 'early' | 'done' | 'interrupted';

const MODES: Record<Mode, { trials: number; minWait: number; maxWait: number; label: string; duration: string }> = {
  full: { trials: 60, minWait: 2000, maxWait: 6000, label: 'Full demo · 60 taps', duration: '2–6 second random waits; duration varies' },
  quick: { trials: 10, minWait: 1200, maxWait: 3000, label: 'Quick demo · 10 taps', duration: '1.2–3 second random waits; duration varies' },
};

export interface ReactionResult {
  medianMs: number;
  lapses: number;
  trials: number;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** PVT-like test: tap as soon as the pad turns green. Gives the median response time and the lapse count. */
@Component({
  selector: 'article[appReactionTest]',
  host: { class: 'card test-card' },
  template: `
    <header>
      <h3>Reaction test</h3>
      @if (phase() === 'idle' || phase() === 'done' || phase() === 'interrupted') {
        <div class="segmented" role="group" aria-label="Test length">
          @for (m of modeList; track m.id) {
            <button type="button" [attr.aria-pressed]="m.id === mode()" (click)="selectMode(m.id)">{{ m.label }}</button>
          }
        </div>
      }
    </header>

    <button
      type="button"
      class="pad"
      [attr.data-phase]="phase()"
      aria-live="polite"
      (pointerdown)="onPointer($event)"
      (keydown)="onKey($event)"
    >
      <strong>{{ text()[0] }}</strong>
      @if (text()[1]) {
        <small>{{ text()[1] }}</small>
      }
    </button>

    <div class="trial-progress" aria-hidden="true">
      <i [style.width.%]="progress()"></i>
    </div>

    @if (phase() === 'done' || phase() === 'interrupted') {
      <div class="test-actions">
        <button type="button" class="btn btn-primary" [disabled]="!canApply()" (click)="useResult()">
          {{ saved() ? 'Added to the form' : 'Use these results' }}
        </button>
        <button type="button" class="btn" (click)="start()">Retake</button>
      </div>
    }

    @if (config().trials < 60) {
      <p class="test-note warn">
        The quick demo uses {{ config().trials }} taps for practice only. Its results cannot be added to the
        model input form; a 10-response lapse count is not a 60-response lapse count.
      </p>
    }
    <p class="test-note">
      <strong>{{ mode() === 'full' ? 'Custom 60-response PVT-inspired reaction-time test' : 'Custom 10-response practice demo' }}</strong>:
      median response time and responses of {{ lapseMs }} ms or more.
      This is a fixed-count task, not a timed five-minute or standard PVT protocol. Keep this tab visible and the
      window focused. Matching 60 responses does not establish clinical validity or model accuracy on human data.
    </p>
  `,
})
export class ReactionTest {
  readonly result = output<ReactionResult>();

  protected readonly modeList = (Object.keys(MODES) as Mode[]).map((id) => ({ id, label: MODES[id].label }));
  protected readonly lapseMs = LAPSE_MS;
  protected readonly mode = signal<Mode>('full');
  protected readonly config = computed(() => MODES[this.mode()]);
  protected readonly phase = signal<Phase>('idle');
  protected readonly times = signal<number[]>([]);
  protected readonly falseStarts = signal(0);
  protected readonly saved = signal(false);

  private timer: number | undefined;
  private goAt = 0;

  constructor() {
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') this.interrupt();
    };
    const onBlur = () => this.interrupt();
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    inject(DestroyRef).onDestroy(() => {
      window.clearTimeout(this.timer);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
    });
  }

  protected readonly progress = computed(() => (this.times().length / this.config().trials) * 100);
  protected readonly canApply = computed(() =>
    this.phase() === 'done' && this.mode() === 'full' && this.times().length === 60 && !this.saved(),
  );

  private readonly summary = computed<ReactionResult>(() => {
    const t = this.times();
    return {
      medianMs: t.length ? Math.round(median(t) * 10) / 10 : 0,
      lapses: t.filter((x) => x >= LAPSE_MS).length,
      trials: t.length,
    };
  });

  protected readonly text = computed<[string, string]>(() => {
    const n = this.times().length;
    const { trials, duration } = this.config();
    switch (this.phase()) {
      case 'idle':
        return ['Tap to start', `${trials} taps · ${duration}`];
      case 'waiting':
        return ['Wait for green…', `Tap ${n + 1} of ${trials}`];
      case 'go':
        return ['Tap!', ''];
      case 'early':
        return ['Too soon', 'Wait for the pad to turn green'];
      case 'interrupted':
        return ['Session interrupted', 'Window focus or visibility changed. Retake the full session.'];
      case 'done': {
        const s = this.summary();
        return [`${s.medianMs} ms`, `${plural(s.lapses, 'lapse')} · ${plural(this.falseStarts(), 'false start')}`];
      }
    }
  });

  private arm(): void {
    if (document.visibilityState !== 'visible') {
      this.phase.set('interrupted');
      return;
    }
    this.phase.set('waiting');
    const { minWait, maxWait } = this.config();
    this.timer = window.setTimeout(
      () => {
        if (document.visibilityState !== 'visible') return this.interrupt();
        this.goAt = performance.now();
        this.phase.set('go');
      },
      minWait + Math.random() * (maxWait - minWait),
    );
  }

  private interrupt(): void {
    if (!['waiting', 'go', 'early'].includes(this.phase())) return;
    window.clearTimeout(this.timer);
    this.saved.set(false);
    this.phase.set('interrupted');
  }

  protected selectMode(mode: Mode): void {
    if (!['idle', 'done', 'interrupted'].includes(this.phase())) return;
    window.clearTimeout(this.timer);
    this.mode.set(mode);
    this.times.set([]);
    this.falseStarts.set(0);
    this.saved.set(false);
    this.phase.set('idle');
  }

  protected start(): void {
    window.clearTimeout(this.timer);
    this.times.set([]);
    this.falseStarts.set(0);
    this.saved.set(false);
    this.arm();
  }

  protected onPointer(e: PointerEvent): void {
    e.preventDefault();
    this.press();
  }

  protected onKey(e: KeyboardEvent): void {
    if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
      e.preventDefault();
      this.press();
    }
  }

  private press(): void {
    if (document.visibilityState !== 'visible') return this.interrupt();
    const phase = this.phase();
    if (phase === 'idle' || phase === 'done') return phase === 'idle' ? this.start() : undefined;
    if (phase === 'waiting') {
      window.clearTimeout(this.timer);
      this.falseStarts.update((n) => n + 1);
      this.phase.set('early');
      this.timer = window.setTimeout(() => this.arm(), 1000);
      return;
    }
    if (phase !== 'go') return;

    const rt = performance.now() - this.goAt;
    if (rt < FALSE_START_MS) {
      this.falseStarts.update((n) => n + 1);
      this.arm();
      return;
    }
    const next = [...this.times(), Math.round(rt * 10) / 10];
    this.times.set(next);
    if (next.length >= this.config().trials) this.phase.set('done');
    else this.arm();
  }

  protected useResult(): void {
    // Enforce this at the event boundary too, not only through a disabled button.
    if (!this.canApply()) return;
    this.result.emit(this.summary());
    this.saved.set(true);
  }
}
