import { Component, computed, input } from '@angular/core';
import type { DayRecord, Level, PersonalBaseline } from '../types';
import { MEASURES, deltaLabel, evaluate, formatValue, worstLevel, type Group, type MeasurementKey } from '../lib/metrics';
import { StatusTag } from './status-tag';

/** One group of related measurements: the main one big, the others as rows, plus a chart slot. */
@Component({
  selector: 'article[appMetricGroup]',
  imports: [StatusTag],
  host: { class: 'card tile', '[attr.data-level]': 'level() ?? \'none\'' },
  template: `
    <header>
      <h3>{{ group().title }}</h3>
      @if (level(); as lv) {
        <span appStatusTag [level]="lv"></span>
      }
    </header>
    <p class="big">
      <span>{{ primaryValue() }}</span>
      <small>{{ primary().unit }}</small>
    </p>
    <p class="delta">{{ primary().label }} · {{ delta() }}</p>

    @if (others().length > 0) {
      <ul class="group-rows">
        @for (row of others(); track row.key) {
          <li [attr.data-level]="row.level ?? 'none'">
            <span>{{ row.label }}</span>
            <strong>{{ row.value }} <small>{{ row.unit }}</small></strong>
          </li>
        }
      </ul>
    }

    <div class="tile-visual"><ng-content /></div>
  `,
})
export class MetricGroup {
  readonly group = input.required<Group>();
  readonly records = input.required<DayRecord[]>();
  readonly index = input.required<number>();
  readonly baseline = input<PersonalBaseline | null>(null);

  protected readonly primary = computed(() => MEASURES[this.group().primary]);
  private readonly current = computed(() => this.records()[this.index()]);
  protected readonly primaryValue = computed(() => formatValue(this.group().primary, this.current().measurements[this.group().primary]));
  protected readonly delta = computed(() =>
    deltaLabel(
      this.group().primary,
      this.records().map((r) => r.measurements[this.group().primary]),
      this.index(),
    ),
  );

  private levelOf(key: MeasurementKey): Level | null {
    return evaluate(key, this.current().measurements[key], this.baseline());
  }

  protected readonly level = computed(() => worstLevel(this.group().members.map((k) => this.levelOf(k))));

  protected readonly others = computed(() =>
    this.group()
      .members.filter((k) => k !== this.group().primary)
      .map((key) => ({
        key,
        label: MEASURES[key].label,
        unit: MEASURES[key].unit,
        value: formatValue(key, this.current().measurements[key]),
        level: this.levelOf(key),
      })),
  );
}
