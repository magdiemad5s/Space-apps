import { Component, input, output } from '@angular/core';

export type View = 'overview' | 'checkin' | 'trends' | 'guide' | 'clinicaldemo';

@Component({
  selector: 'nav[appTopNav]',
  host: { class: 'topnav' },
  template: `
    <div class="brand">
      <svg viewBox="0 0 32 32" aria-hidden="true">
        <circle cx="16" cy="16" r="6" />
        <ellipse cx="16" cy="16" rx="14" ry="5.5" transform="rotate(-25 16 16)" />
      </svg>
      <span>Crew Health</span>
    </div>

    <div class="pills" role="tablist">
      @for (v of views; track v.id) {
        <button
          role="tab"
          [attr.aria-selected]="v.id === view()"
          [class.active]="v.id === view()"
          (click)="viewChange.emit(v.id)"
        >
          {{ v.label }}
        </button>
      }
    </div>

    <div class="nav-right" aria-hidden="true"></div>
  `,
})
export class TopNav {
  readonly view = input.required<View>();
  readonly viewChange = output<View>();

  protected readonly views: { id: View; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'checkin', label: 'Check-in' },
    { id: 'trends', label: 'Trends' },
    { id: 'guide', label: 'Guide' },
    { id: 'clinicaldemo', label: 'Alert demo' },
  ];
}
