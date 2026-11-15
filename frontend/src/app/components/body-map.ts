import { Component, computed, input, output, signal } from '@angular/core';
import type { DayRecord, Level, PersonalBaseline } from '../types';
import { CATEGORY_LEVEL, LEVEL_LABEL, MEASURES, evaluate, formatValue, worstLevel, type MeasurementKey } from '../lib/metrics';
import { AstronautFigure } from './astronaut-figure';

type ZoneId = 'head' | 'mind' | 'heart' | 'core';
export type GuideTarget = MeasurementKey | 'forecast';

interface Zone {
  id: ZoneId;
  label: string;
  /** Hotspot position, % of the figure box */
  x: number;
  y: number;
  metrics: MeasurementKey[];
  about: string;
  risk: string;
}

interface Row {
  label: string;
  value: string;
  unit: string;
  level: Level | null;
}

const ZONES: Zone[] = [
  {
    id: 'head',
    label: 'Sleep & alertness',
    x: 50,
    y: 6,
    metrics: ['sleep_duration_hours', 'sleep_efficiency_pct', 'reaction_time_median_ms'],
    about:
      'Sleep restores attention and memory, and efficiency shows how much of your time in bed was real sleep. Reaction time shows how alert you are.',
    risk: 'NASA HRP risk: inadequate sleep and irregular schedules',
  },
  {
    id: 'mind',
    label: 'Mood & stress',
    x: 50,
    y: 17.5,
    metrics: ['self_report_fatigue_score', 'self_report_stress_score', 'self_report_mood_score'],
    about:
      'Isolation, confinement and distance from Earth can raise stress and lower mood, which in turn disturb sleep and teamwork.',
    risk: 'NASA HRP risk: behavioral changes and psychiatric disorders',
  },
  {
    id: 'heart',
    label: 'Heart',
    x: 58,
    y: 34.6,
    metrics: ['resting_heart_rate_bpm', 'hrv_rmssd_ms'],
    about:
      'Without gravity, fluids shift toward the head and the heart and blood vessels adapt, which can raise cardiovascular risk. HRV drops under strain.',
    risk: 'NASA HRP risk: cardiovascular adaptations',
  },
  {
    id: 'core',
    label: 'Next-day fatigue',
    x: 50,
    y: 50.4,
    metrics: [],
    about:
      'The model forecasts tomorrow\'s fatigue category from today\'s record, your fixed baseline and the last three days.',
    risk: 'Linked to sleep, behavioral health and cardiovascular risks',
  },
];

@Component({
  selector: 'div[appBodyMap]',
  imports: [AstronautFigure],
  host: { class: 'bodymap' },
  template: `
    <div class="figure-stage">
      <app-astronaut-figure />
      @for (z of zones; track z.id) {
        <button
          class="hotspot"
          [class.active]="z.id === activeId()"
          [attr.data-level]="zoneLevel(z) ?? 'none'"
          [style.left.%]="z.x"
          [style.top.%]="z.y"
          [attr.aria-pressed]="z.id === activeId()"
          [attr.aria-label]="z.label + ': ' + levelText(zoneLevel(z))"
          (click)="activeId.set(z.id)"
        >
          <i></i>
        </button>
      }
    </div>
    <p class="si-mark">SI-generated illustration</p>

    <aside class="zone-card" [attr.data-level]="zoneLevel(active()) ?? 'none'" [style.--zone-y]="active().y + '%'">
      <p class="zone-label">{{ active().label }}</p>
      <ul>
        @for (row of rows(); track row.label) {
          <li [attr.data-level]="row.level ?? 'none'">
            <span>{{ row.label }}</span>
            <strong>
              {{ row.value }}
              <small>{{ row.unit }}</small>
            </strong>
            <em>{{ levelText(row.level) }}</em>
          </li>
        }
      </ul>
      <p class="zone-about">{{ active().about }}</p>
      <p class="zone-risk">{{ active().risk }}</p>
      <button class="zone-link" (click)="guide.emit(active().id === 'core' ? 'forecast' : active().metrics[0])">
        How to read this →
      </button>
    </aside>
  `,
})
export class BodyMap {
  readonly record = input<DayRecord | null>(null);
  readonly baseline = input<PersonalBaseline | null>(null);
  /** Opens the Guide view at a measurement or the forecast */
  readonly guide = output<GuideTarget>();

  protected readonly zones = ZONES;
  protected readonly activeId = signal<ZoneId>('core');
  protected readonly active = computed(() => ZONES.find((z) => z.id === this.activeId()) ?? ZONES[0]);

  private rowsFor(zone: Zone): Row[] {
    const r = this.record();
    if (zone.id === 'core') {
      const f = r?.forecast;
      if (f) {
        return [
          { label: 'Forecast index', value: String(Math.round(f.points * 10) / 10), unit: '/ 100', level: CATEGORY_LEVEL[f.category] },
          { label: 'Category', value: f.category, unit: '', level: CATEGORY_LEVEL[f.category] },
        ];
      }
      return [
        {
          label: r ? (r.status === 'collecting_baseline' ? 'Calibrating' : 'Unavailable') : 'No record',
          value: '—',
          unit: '',
          level: null,
        },
      ];
    }
    if (!r) return [];
    return zone.metrics.map((key) => ({
      label: MEASURES[key].label,
      value: formatValue(key, r.measurements[key]),
      unit: MEASURES[key].unit,
      level: evaluate(key, r.measurements[key], this.baseline()),
    }));
  }

  protected readonly rows = computed(() => this.rowsFor(this.active()));

  protected zoneLevel(z: Zone): Level | null {
    return worstLevel(this.rowsFor(z).map((row) => row.level));
  }

  protected levelText(level: Level | null): string {
    return level ? LEVEL_LABEL[level] : 'No level';
  }
}
