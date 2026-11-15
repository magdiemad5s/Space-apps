import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import type { Recommendation } from '../types';

/** Pixels the mouse must move before a press counts as a drag (so clicks on cards still work) */
const DRAG_THRESHOLD = 5;
/** Space between cards, must match `.rec-row` gap in styles.css */
const CARD_GAP = 14;

/** Recommendation cards the astronaut can tick off; ticks reset when `resetKey` changes. */
@Component({
  selector: 'section[appRecommendationCards]',
  host: { class: 'dark-block recs' },
  template: `
    <header>
      <h2>Demo suggestions</h2>
      <div class="rec-tools">
        <span class="count">{{ done().size }} / {{ items().length }} done</span>
        @if (edges().prev || edges().next) {
          <div class="rec-arrows">
            <button class="rec-arrow" [disabled]="!edges().prev" aria-label="Previous recommendations" (click)="scrollByCard(-1)">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3 5 8l5 5" /></svg>
            </button>
            <button class="rec-arrow" [disabled]="!edges().next" aria-label="Next recommendations" (click)="scrollByCard(1)">
              <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3l5 5-5 5" /></svg>
            </button>
          </div>
        }
      </div>
    </header>

    <div
      #row
      class="rec-row"
      (pointerdown)="onPointerDown($event)"
      (pointermove)="onPointerMove($event)"
      (pointerup)="endDrag()"
      (pointercancel)="endDrag()"
    >
      @for (r of items(); track r.id; let i = $index) {
        <article class="rec" [class.done]="done().has(r.id)" [attr.data-level]="r.priority">
          <button
            class="rec-check"
            [attr.aria-pressed]="done().has(r.id)"
            [attr.aria-label]="
              done().has(r.id) ? 'Mark &quot;' + r.action + '&quot; as not done' : 'Mark &quot;' + r.action + '&quot; as done'
            "
            (click)="toggle(r.id)"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5 6.5 11.5 12.5 4.5" /></svg>
          </button>
          <p class="rec-index">{{ pad(i + 1) }} / {{ pad(items().length) }}</p>
          <h3>{{ r.action }}</h3>
          <p class="rec-reason">{{ r.reason }}</p>
          <span class="rec-glow" aria-hidden="true"></span>
        </article>
      }
    </div>
  `,
})
export class RecommendationCards {
  readonly items = input.required<Recommendation[]>();
  readonly resetKey = input<string>('');

  protected readonly done = signal<Set<string>>(new Set());
  protected readonly edges = signal({ prev: false, next: false });
  private readonly row = viewChild.required<ElementRef<HTMLDivElement>>('row');
  private drag = { active: false, moved: false, startX: 0, startScroll: 0 };

  constructor() {
    effect(() => {
      this.resetKey();
      untracked(() => this.done.set(new Set()));
    });

    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      const row = this.row().nativeElement;
      const update = () =>
        this.edges.set({
          prev: row.scrollLeft > 4,
          next: row.scrollLeft < row.scrollWidth - row.clientWidth - 4,
        });
      update();
      row.addEventListener('scroll', update, { passive: true });
      const observer = new ResizeObserver(update);
      observer.observe(row);
      destroyRef.onDestroy(() => {
        row.removeEventListener('scroll', update);
        observer.disconnect();
      });
    });

    // The card count can change without the row resizing, so re-check after items change.
    effect(() => {
      this.items();
      setTimeout(() => {
        const row = this.row().nativeElement;
        this.edges.set({
          prev: row.scrollLeft > 4,
          next: row.scrollLeft < row.scrollWidth - row.clientWidth - 4,
        });
      }, 0);
    });
  }

  protected pad(n: number): string {
    return String(n).padStart(2, '0');
  }

  protected toggle(id: string): void {
    this.done.update((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  protected scrollByCard(direction: 1 | -1): void {
    const row = this.row().nativeElement;
    const card = row.firstElementChild;
    if (!card) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    row.scrollBy({
      left: direction * (card.getBoundingClientRect().width + CARD_GAP),
      behavior: reduce ? 'auto' : 'smooth',
    });
  }

  /** Lets a mouse drag the row sideways, since its scrollbar is hidden. Touch and trackpad scroll natively. */
  protected onPointerDown(e: PointerEvent): void {
    if (e.pointerType !== 'mouse' || e.button !== 0) return;
    this.drag = { active: true, moved: false, startX: e.clientX, startScroll: this.row().nativeElement.scrollLeft };
  }

  protected onPointerMove(e: PointerEvent): void {
    const row = this.row().nativeElement;
    const d = this.drag;
    if (!d.active) return;
    const dx = e.clientX - d.startX;
    if (!d.moved && Math.abs(dx) < DRAG_THRESHOLD) return;
    if (!d.moved) {
      d.moved = true;
      row.classList.add('dragging');
      row.setPointerCapture(e.pointerId);
    }
    row.scrollLeft = d.startScroll - dx;
  }

  protected endDrag(): void {
    this.drag.active = false;
    this.row().nativeElement.classList.remove('dragging');
  }
}
