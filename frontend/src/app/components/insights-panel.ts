import { Component, computed, input } from '@angular/core';
import type { DayRecord, Level, PersonalBaseline } from '../types';
import {
  CATEGORY_LEVEL,
  LEVEL_LABEL,
  MEASURES,
  MEASURE_ORDER,
  compareLevels,
  evaluate,
  featureLabel,
  formatValue,
} from '../lib/metrics';
import { GUIDE } from '../lib/guide';

interface Row {
  id: string;
  level: Level | 'none';
  title: string;
  message: string;
  side: string;
}

/**
 * Alerts for measurements outside their range, then why the forecast looks the way it does (SHAP reasons),
 * or what is happening instead when the record has no forecast.
 */
@Component({
  selector: 'section[appInsightsPanel]',
  host: { class: 'dark-block alerts' },
  template: `
    <header>
      <h2>Demo measurement guidance</h2>
      <span class="count">{{ alerts().length }}</span>
    </header>
    <p class="dark-note">Prototype display thresholds; not the Clinical Alert V2 engine or a medical assessment.</p>
    @if (note()) {
      <p class="dark-note">{{ note() }}</p>
    }

    @if (!record()) {
      <p class="dark-empty">No records yet. Submit the first daily record in the Check-in tab.</p>
    } @else {
      @if (alerts().length === 0) {
        <p class="dark-empty">No measurement with a level is outside its range in this record.</p>
      } @else {
        <ul>
          @for (a of alerts(); track a.id) {
            <li [attr.data-level]="a.level">
              <i class="dot" aria-hidden="true"></i>
              <div>
                <div class="alert-row">
                  <strong>{{ a.title }}</strong>
                </div>
                <p>{{ a.message }}</p>
              </div>
            </li>
          }
        </ul>
      }

      <h3 class="dark-sub">{{ record()?.forecast ? 'Why this forecast' : 'Forecast status' }}</h3>
      <ul>
        @for (a of reasons(); track a.id) {
          <li [attr.data-level]="a.level">
            <i class="dot" aria-hidden="true"></i>
            <div>
              <div class="alert-row">
                <strong>{{ a.title }}</strong>
                <time>{{ a.side }}</time>
              </div>
              <p>{{ a.message }}</p>
            </div>
          </li>
        }
      </ul>

      @if (record()?.forecast) {
        <p class="dark-foot">
          These are SHAP attributions for the model's output. They are not medical causes or instructions.
        </p>
      }
    }
  `,
})
export class InsightsPanel {
  readonly record = input<DayRecord | null>(null);
  readonly baseline = input<PersonalBaseline | null>(null);
  readonly required = input(7);
  /** Shown when the user is looking at an earlier record */
  readonly note = input<string | undefined>(undefined);

  /** Measurements of this record that are in their watch or action range. */
  protected readonly alerts = computed<Row[]>(() => {
    const r = this.record();
    if (!r) return [];
    const rows: (Row & { level: Level })[] = [];
    for (const key of MEASURE_ORDER) {
      const value = r.measurements[key];
      const level = evaluate(key, value, this.baseline());
      if (!level || level === 'ok') continue;
      const range = GUIDE[key].levels?.[level];
      rows.push({
        id: key,
        level,
        title: `${MEASURES[key].label}: ${formatValue(key, value)} ${MEASURES[key].unit}`,
        message: `${LEVEL_LABEL[level]}${range ? ` range (${range})` : ''}. The Guide says how to measure it again and when to escalate.`,
        side: '',
      });
    }
    return rows.sort((a, b) => compareLevels(a.level, b.level));
  });

  protected readonly reasons = computed<Row[]>(() => {
    const r = this.record();
    if (!r) return [];
    const f = r.forecast;

    if (!f) {
      return [
        r.status === 'collecting_baseline'
          ? {
              id: 'calibration',
              level: 'none',
              title: `Calibration record ${r.index} of ${this.required()}`,
              message: `No forecast is made during calibration. It starts with record ${this.required() + 1}, using your fixed baseline and the last 3 days.`,
              side: '',
            }
          : {
              id: 'unavailable',
              level: 'warning',
              title: 'Model unavailable',
              message: 'The daily record is saved without a prediction. Retry it from the Check-in tab once the model service is back.',
              side: '',
            },
      ];
    }

    const forecastLevel = CATEGORY_LEVEL[f.category];
    const rows: Row[] = f.reasons.map((reason, i) => {
      const supports = reason.direction === 'supports_prediction';
      const neutral = reason.direction === 'neutral';
      return {
        id: `reason-${i}`,
        level: neutral ? 'none' : supports ? forecastLevel : 'ok',
        title: featureLabel(reason.feature),
        message: `Value ${Math.round(reason.value * 100) / 100}. ${
          neutral ? `No directional contribution to ${f.category}.` : supports ? `Pushes the forecast toward ${f.category}.` : `Pushes the forecast away from ${f.category}.`
        }`,
        side: `${reason.shapValue >= 0 ? '+' : ''}${reason.shapValue.toFixed(3)}`,
      };
    });

    if (f.outOfRangeFeatures.length > 0) {
      rows.push({
        id: 'range',
        level: 'warning',
        title: 'Inputs outside the training range',
        message: `${f.outOfRangeFeatures.map(featureLabel).join(', ')}. The model saw few or no examples like this, so treat the forecast with extra care.`,
        side: '',
      });
    }
    if (f.physiologyOutlier) {
      rows.push({
        id: 'outlier',
        level: 'warning',
        title: 'Unusual heart rate and HRV',
        message: "Today's heart rate and HRV look unusual compared with the training data. This is a statistical flag, not a diagnosis.",
        side: '',
      });
    }
    return rows;
  });
}
