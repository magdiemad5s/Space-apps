import { Component, effect, input } from '@angular/core';
import type { DayRecord, Level, PersonalBaseline } from '../types';
import { LEVEL_LABEL, MEASURES, MEASURE_ORDER, evaluate, type MeasurementKey } from '../lib/metrics';
import { GUIDE, SOURCES, type SourceId } from '../lib/guide';
import { StatusTag } from './status-tag';
import type { GuideTarget } from './body-map';

@Component({
  selector: 'div[appGuideView]',
  imports: [StatusTag],
  host: { class: 'guide' },
  template: `
    <article class="card guide-intro">
      <h2>How to measure and read your health</h2>
      <p>
        First how the forecast works, then for each of the 15 daily measurements: how to take it, why it matters, what
        each color means and when to call the flight surgeon. Where a level is a team assumption rather than a
        published value, it says so. These display thresholds are prototype measurement guidance, not the
        Clinical Alert V2 engine. That engine and its 14 acceptance cases remain deferred.
      </p>
    </article>

    <article id="guide-forecast" class="card guide-card">
      <header>
        <h3>Next-day fatigue forecast</h3>
      </header>
      <div class="guide-grid">
        <section>
          <h4>What it is</h4>
          <p>
            A model trained on simulated data predicts tomorrow's fatigue category (Low, Moderate or High) from today's
            record, your fixed personal baseline (the first 7 daily records) and the average of the last 3 days. The
            first 7 records only calibrate the baseline, so no forecast is shown for them.
          </p>
        </section>
        <section>
          <h4>The index</h4>
          <p>
            The index is 50 × P(moderate) + 100 × P(high). It is a prototype severity index from 0 to 100, not a medical
            percentage and not a calibrated probability. The 0 to 10 score estimate comes from a separate model, so the
            two can disagree.
          </p>
        </section>
        <section>
          <h4>The three reasons</h4>
          <p>
            Actual SHAP attributions of the classifier: which inputs pushed the forecast toward or away from the
            predicted category. They describe the model, not the causes of fatigue, and they are not medical advice.
          </p>
        </section>
        <section>
          <h4>Limits</h4>
          <p>
            All training data is synthetic (120 virtual participants). On the team's held-out test the model scored
            Macro-F1 0.53, its accuracy was below the majority-class rate and High-fatigue recall was about 46%. It is a
            demonstration, not a validated health tool.
          </p>
        </section>
      </div>
      <p class="guide-sources">
        <span>Sources:</span>
        <a [href]="sources.astraRepo.url" target="_blank" rel="noreferrer">{{ sources.astraRepo.short }}</a>
      </p>
    </article>

    @for (key of order; track key) {
      @let g = guide[key];
      <article class="card guide-card" [id]="'guide-' + key">
        <header>
          <h3>{{ measures[key].label }}</h3>
          @if (levelOf(key); as lv) {
            <span appStatusTag [level]="lv"></span>
          }
        </header>

        <div class="guide-grid">
          <section>
            <h4>How to measure</h4>
            <p>{{ g.measure }}</p>
          </section>
          <section>
            <h4>Why it matters in space</h4>
            <p>{{ g.why }}</p>
          </section>
        </div>

        @if (g.levels; as lv) {
          <ul class="levels">
            @for (l of levelKeys; track l) {
              <li [attr.data-level]="l">
                <span>{{ levelLabel[l] }}</span>
                <strong>{{ lv[l] }}</strong>
              </li>
            }
          </ul>
        }

        <p class="guide-basis">{{ g.basis }}</p>
        @if (g.escalate) {
          <p class="guide-escalate">
            <strong>When to escalate: </strong>
            {{ g.escalate }}
          </p>
        }
        <p class="guide-sources">
          <span>Sources:</span>
          @for (id of g.sources; track id) {
            <a [href]="sources[id].url" target="_blank" rel="noreferrer">{{ sources[id].short }}</a>
          }
        </p>
      </article>
    }

    <article class="card sources-card">
      <h3>Sources</h3>
      <ol>
        @for (s of sourceList; track s.url) {
          <li>
            <a [href]="s.url" target="_blank" rel="noreferrer">{{ s.label }}</a>
          </li>
        }
      </ol>
    </article>
  `,
})
export class GuideView {
  readonly record = input<DayRecord | null>(null);
  readonly baseline = input<PersonalBaseline | null>(null);
  /** Where to scroll to; `at` changes on every request so the same target can be re-opened */
  readonly target = input<{ key: GuideTarget; at: number } | null>(null);

  protected readonly order = MEASURE_ORDER;
  protected readonly measures = MEASURES;
  protected readonly guide = GUIDE;
  protected readonly sources: Record<SourceId, { short: string; label: string; url: string }> = SOURCES;
  protected readonly sourceList = Object.values(SOURCES);
  protected readonly levelKeys: Level[] = ['ok', 'warning', 'critical'];
  protected readonly levelLabel = LEVEL_LABEL;

  constructor() {
    effect(() => {
      const t = this.target();
      if (!t) return;
      setTimeout(
        () => document.getElementById(`guide-${t.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }),
        0,
      );
    });
  }

  protected levelOf(key: MeasurementKey): Level | null {
    const r = this.record();
    return r ? evaluate(key, r.measurements[key], this.baseline()) : null;
  }
}
