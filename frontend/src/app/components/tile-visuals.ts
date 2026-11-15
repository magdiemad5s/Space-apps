import { Component, computed, input } from '@angular/core';

type Domain = [number, number];

const norm = (v: number, [d0, d1]: Domain) => Math.min(1, Math.max(0, (v - d0) / (d1 - d0)));

/** Thin vertical bars, one per day. */
@Component({
  selector: 'div[appBars]',
  host: { class: 'bars', 'aria-hidden': 'true' },
  template: `
    @for (v of values(); track $index) {
      <i [class.on]="$index === active()" [style.height.%]="14 + norm(v) * 86"></i>
    }
  `,
})
export class Bars {
  readonly values = input.required<number[]>();
  readonly domain = input.required<Domain>();
  /** Index of the selected day */
  readonly active = input.required<number>();

  protected norm(v: number): number {
    return norm(v, this.domain());
  }
}

/** Smooth line through the days, with a dot on the selected day. */
@Component({
  selector: 'app-wave',
  host: { style: 'display: contents' },
  template: `
    <svg class="wave" viewBox="0 0 200 64" aria-hidden="true">
      <path [attr.d]="path()" />
      <circle [attr.cx]="dot()[0]" [attr.cy]="dot()[1]" r="5" />
    </svg>
  `,
})
export class Wave {
  readonly values = input.required<number[]>();
  readonly domain = input.required<Domain>();
  readonly active = input.required<number>();

  private readonly points = computed(() => {
    const values = this.values();
    return values.map(
      (v, i) =>
        [(i / (values.length - 1)) * 190 + 5, 64 - 6 - norm(v, this.domain()) * 50] as const,
    );
  });

  protected readonly path = computed(() =>
    this.points().reduce((acc, [x, y], i, pts) => {
      if (i === 0) return `M${x},${y}`;
      const [px, py] = pts[i - 1];
      const mx = (px + x) / 2;
      return `${acc} C${mx},${py} ${mx},${y} ${x},${y}`;
    }, ''),
  );

  protected readonly dot = computed(() => this.points()[this.active()]);
}

/** Smartwatch with a heart that beats at the measured rate. */
@Component({
  selector: 'app-heart-watch',
  host: { style: 'display: contents' },
  template: `
    <svg class="watch" viewBox="0 0 120 120" aria-hidden="true">
      <rect x="42" y="0" width="36" height="20" rx="6" class="watch-strap" />
      <rect x="42" y="100" width="36" height="20" rx="6" class="watch-strap" />
      <rect x="28" y="12" width="64" height="96" rx="22" class="watch-body" />
      <rect x="35" y="19" width="50" height="82" rx="16" class="watch-screen" />
      <path
        class="beat"
        [style.animation-duration]="60 / bpm() + 's'"
        d="M60 74 C46 64 41 57 41 50 C41 44 45 40 50.5 40 C55 40 58.5 43 60 46.5 C61.5 43 65 40 69.5 40 C75 40 79 44 79 50 C79 57 74 64 60 74 Z"
      />
    </svg>
  `,
})
export class HeartWatch {
  readonly bpm = input.required<number>();
}
