/*
 * Crew Health dashboard (Angular + Ionic). Code written with SI assistance (Claude, Anthropic) and
 * reviewed by the team; see README "Use of SI".
 */
import { Component, computed, signal } from '@angular/core';
import { IonApp, IonContent } from '@ionic/angular';
import type { Measurements, Snapshot } from './types';
import { apiBase, buildBody, getSnapshot, setApiBase, setDemoMode, retryBodyFor, submitRecord, type AssessBody, type SubmitResult } from './data/source';
import { GROUPS, MEASURES, type MeasurementKey } from './lib/metrics';
import { buildRecommendations } from './lib/insights';
import { TopNav, type View } from './components/top-nav';
import { BodyMap, type GuideTarget } from './components/body-map';
import { DayStrip } from './components/day-strip';
import { FatigueTimeline } from './components/fatigue-timeline';
import { OverviewStatus } from './components/overview-status';
import { MetricGroup } from './components/metric-group';
import { Bars, HeartWatch, Wave } from './components/tile-visuals';
import { FatigueCard } from './components/fatigue-card';
import { TrendChart } from './components/trend-chart';
import { CheckInView } from './components/check-in-view';
import type { FormMessage, RecordSubmit } from './components/log-form';
import { GuideView } from './components/guide-view';
import { ClinicalDemo } from './components/clinical-demo';
import { InsightsPanel } from './components/insights-panel';
import { RecommendationCards } from './components/recommendation-cards';
import { ProgressGauge } from './components/progress-gauge';

@Component({
  selector: 'app-root',
  imports: [
    IonApp,
    IonContent,
    TopNav,
    BodyMap,
    DayStrip,
    FatigueTimeline,
    OverviewStatus,
    MetricGroup,
    Bars,
    Wave,
    HeartWatch,
    FatigueCard,
    TrendChart,
    CheckInView,
    GuideView,
    ClinicalDemo,
    InsightsPanel,
    RecommendationCards,
    ProgressGauge,
  ],
  template: `
    <ion-app>
      <ion-content>
        @if (snapshot(); as snap) {
          <div class="shell">
            <section class="light">
              <nav appTopNav [view]="view()" (viewChange)="view.set($event)"></nav>

              <div class="light-grid">
                <div class="figure-col">
                  <div class="intro">
                    <h1>Crew Health</h1>
                    <p>Astronaut {{ snap.astronautId }}</p>
                    <p class="env">
                      <svg viewBox="0 0 16 16" aria-hidden="true">
                        <circle cx="8" cy="8" r="2.6" />
                        <ellipse cx="8" cy="8" rx="6.5" ry="2.6" transform="rotate(-25 8 8)" />
                      </svg>
                      {{ snap.source === 'backend' ? 'Records from the backend' : 'Simulated example records (demo mode)' }}
                    </p>
                    <div class="connection-controls">
                      <button type="button" class="link-btn" [disabled]="loading() || busy()" (click)="load()">Refresh data</button>
                      <button type="button" class="link-btn" [disabled]="loading() || busy()" (click)="chooseDemo(snap.source !== 'demo')">
                        {{ snap.source === 'demo' ? 'Connect to backend' : 'Preview demo data' }}
                      </button>
                    </div>
                    @if (connectionError()) {
                      <p class="connection-error" role="alert">{{ connectionError() }}</p>
                    }
                  </div>
                  <div appBodyMap [record]="record()" [baseline]="selectedBaseline()" (guide)="openGuide($event)"></div>
                </div>

                <div class="main-col">
                  @if ((view() === 'overview' || view() === 'trends') && snap.records.length > 0) {
                    <div class="main-top">
                      <div appDayStrip [records]="snap.records" [index]="index()" (dayChange)="selectRecord($event)"></div>
                      <div appOverviewStatus [record]="record()" [snapshot]="snap" (openCheckIn)="view.set('checkin')"></div>
                    </div>
                    <div appFatigueTimeline [records]="snap.records" [index]="index()" (dayChange)="selectRecord($event)"></div>
                  }

                  @switch (view()) {
                    @case ('overview') {
                      @if (record(); as rec) {
                        <div class="tiles">
                          <article
                            appFatigueCard
                            [record]="rec"
                            [records]="snap.records"
                            [required]="snap.calibrationRequired"
                            (openCheckIn)="view.set('checkin')"
                          ></article>
                          <article appMetricGroup class="tile-sleep" [group]="groups[0]" [records]="snap.records" [index]="index()" [baseline]="selectedBaseline()">
                            <div appBars [values]="series('sleep_duration_hours')" [domain]="domain('sleep_duration_hours')" [active]="index()"></div>
                          </article>
                          <article appMetricGroup class="tile-heart" [group]="groups[1]" [records]="snap.records" [index]="index()" [baseline]="selectedBaseline()">
                            <app-heart-watch [bpm]="rec.measurements.resting_heart_rate_bpm" />
                          </article>
                          <article appMetricGroup class="tile-cognition" [group]="groups[2]" [records]="snap.records" [index]="index()" [baseline]="selectedBaseline()">
                            <app-wave [values]="series('reaction_time_median_ms')" [domain]="domain('reaction_time_median_ms')" [active]="index()" />
                          </article>
                          <article appMetricGroup class="tile-self" [group]="groups[3]" [records]="snap.records" [index]="index()" [baseline]="selectedBaseline()">
                            <div appBars [values]="series('self_report_fatigue_score')" [domain]="domain('self_report_fatigue_score')" [active]="index()"></div>
                          </article>
                          <article appMetricGroup class="tile-load" [group]="groups[4]" [records]="snap.records" [index]="index()" [baseline]="selectedBaseline()">
                            <div appBars [values]="series('workload_hours')" [domain]="domain('workload_hours')" [active]="index()"></div>
                          </article>
                        </div>
                      } @else {
                        <article class="card empty-card">
                          <h3>No records yet</h3>
                          <p>
                            The first 7 daily records build your personal baseline. Add the first one in the Check-in tab.
                          </p>
                          <button class="btn btn-primary" (click)="view.set('checkin')">Open Check-in</button>
                        </article>
                      }
                    }
                    @case ('trends') {
                      <article
                        appTrendChart
                        [records]="snap.records"
                        [selected]="index()"
                        [baseline]="selectedBaseline()"
                        [required]="snap.calibrationRequired"
                      ></article>
                    }
                    @case ('checkin') {
                      <div
                        appCheckInView
                        [snapshot]="snap"
                        [previous]="previous()"
                        [busy]="busy() || loading() || !!connectionError()"
                        [canRetry]="canRetry()"
                        [message]="message()"
                        (submitRecord)="save($event)"
                        (retry)="retry()"
                        (changeServer)="configureServer()"
                      ></div>
                    }
                    @case ('clinicaldemo') {
                      <article appClinicalDemo></article>
                    }
                    @case ('guide') {
                      <div appGuideView [record]="record()" [baseline]="selectedBaseline()" [target]="guideTarget()"></div>
                    }
                  }
                </div>
              </div>
            </section>

            <section id="action-panel" class="dark" [class.collapsed]="!panelOpen()">
              <button
                class="seam"
                [attr.aria-expanded]="panelOpen()"
                aria-controls="action-panel"
                [attr.aria-label]="panelOpen() ? 'Collapse the forecast reasons and recommendations' : 'Expand the forecast reasons and recommendations'"
                (click)="panelOpen.set(!panelOpen())"
              >
                <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 10l4-4 4 4" /></svg>
              </button>
              <button class="dark-summary" (click)="panelOpen.set(true)">
                <span><strong>{{ snap.records.length }}</strong> records</span>
                <span><strong>{{ recommendations().length }}</strong> recommendations</span>
                <span>{{ record()?.forecast ? 'Forecast: ' + record()?.forecast?.category : 'No forecast for this record' }}</span>
              </button>
              <section
                appInsightsPanel
                [record]="record()"
                [baseline]="selectedBaseline()"
                [required]="snap.calibrationRequired"
                [note]="recordNote()"
              ></section>
              @for (key of [resetKey()]; track key) {
                <section appRecommendationCards [items]="recommendations()" [resetKey]="key"></section>
              }
              <section appProgressGauge [count]="snap.records.length" [required]="snap.calibrationRequired"></section>
              <p class="disclaimer">
                Decision support only, not a medical diagnosis. All model training data is synthetic. Contact the flight
                surgeon for any medical concern. Built with SI assistance: code and illustrations. Sources are listed in
                the Guide.
              </p>
            </section>
          </div>
        } @else if (connectionError()) {
          <section class="card connection-failure" role="alert">
            <h1>Backend connection unavailable</h1>
            <p>{{ connectionError() }}</p>
            <p>Start the three services, then retry. Demo mode is a separate, explicitly simulated preview.</p>
            <div class="connection-controls">
              <button type="button" class="btn btn-primary" [disabled]="loading()" (click)="load()">Retry connection</button>
              <button type="button" class="btn" (click)="configureServer()">Change backend address</button>
              <button type="button" class="btn" (click)="chooseDemo(true)">Open simulated demo</button>
            </div>
          </section>
        } @else {
          <p class="loading">Loading crew data…</p>
        }
      </ion-content>
    </ion-app>
  `,
})
export class App {
  protected readonly groups = GROUPS;
  protected readonly snapshot = signal<Snapshot | null>(null);
  protected readonly view = signal<View>('overview');
  /** null = latest record */
  private readonly recordIndex = signal<number | null>(null);
  protected readonly panelOpen = signal(true);
  protected readonly guideTarget = signal<{ key: GuideTarget; at: number } | null>(null);
  protected readonly busy = signal(false);
  protected readonly loading = signal(false);
  protected readonly connectionError = signal<string | null>(null);
  protected readonly message = signal<FormMessage | null>(null);
  private readonly retryBody = signal<AssessBody | null>(null);

  protected readonly index = computed(() => {
    const n = this.snapshot()?.records.length ?? 0;
    const i = this.recordIndex();
    return i === null ? Math.max(0, n - 1) : Math.min(Math.max(0, i), Math.max(0, n - 1));
  });
  protected readonly record = computed(() => this.snapshot()?.records[this.index()] ?? null);
  protected readonly selectedBaseline = computed(() => {
    const snap = this.snapshot(), record = this.record();
    return snap && record && record.index >= snap.calibrationRequired ? snap.baseline : null;
  });
  protected readonly previous = computed<Measurements | null>(() => {
    const records = this.snapshot()?.records ?? [];
    return records.length > 0 ? records[records.length - 1].measurements : null;
  });
  /** The latest record was saved without a prediction, so it can be sent again unchanged. */
  protected readonly canRetry = computed(() => {
    const snap = this.snapshot();
    const records = snap?.records ?? [];
    return snap?.source === 'backend' && records[records.length - 1]?.status === 'model_unavailable';
  });
  protected readonly recommendations = computed(() => buildRecommendations(this.record() ?? undefined, this.selectedBaseline()));
  protected readonly resetKey = computed(() => `${this.snapshot()?.astronautId}-${this.record()?.index ?? 0}`);
  protected readonly recordNote = computed(() => {
    const snap = this.snapshot();
    const r = this.record();
    if (!snap || !r || r.index === snap.records.length) return undefined;
    return `You are viewing record ${r.index} of ${snap.records.length}.`;
  });

  constructor() {
    this.load();
  }

  protected async load(): Promise<void> {
    if (this.loading()) return;
    this.loading.set(true);
    this.connectionError.set(null);
    try { this.snapshot.set(await getSnapshot()); }
    catch (error) {
      this.connectionError.set(error instanceof Error ? error.message : 'Could not load backend records.');
    } finally { this.loading.set(false); }
  }

  protected chooseDemo(enabled: boolean): void {
    setDemoMode(enabled);
    this.snapshot.set(null);
    this.retryBody.set(null);
    this.recordIndex.set(null);
    this.message.set(null);
    void this.load();
  }

  protected series(key: MeasurementKey): number[] {
    return this.snapshot()?.records.map((r) => r.measurements[key]) ?? [];
  }

  protected domain(key: MeasurementKey): [number, number] {
    return MEASURES[key].domain;
  }

  protected selectRecord(i: number): void {
    const n = this.snapshot()?.records.length ?? 0;
    this.recordIndex.set(Math.min(n - 1, Math.max(0, i)));
  }

  /** Lets the user point the app at another backend (for example the computer's address on the phone's Wi-Fi). */
  protected configureServer(): void {
    if (this.busy() || this.loading()) return;
    const next = window.prompt(
      'Backend address, for example http://192.168.1.10:3000/api/v1\nLeave empty to use the default.',
      apiBase(),
    );
    if (next === null) return;
    setApiBase(next);
    setDemoMode(false);
    location.reload();
  }

  protected openGuide(key: GuideTarget): void {
    this.view.set('guide');
    this.guideTarget.set({ key, at: Date.now() });
  }

  protected async save(e: RecordSubmit): Promise<void> {
    const snap = this.snapshot();
    if (!snap || this.busy() || this.loading() || this.connectionError()) return;
    await this.send(snap, buildBody(snap, e.measurements, e.journalText));
  }

  protected async retry(): Promise<void> {
    const snap = this.snapshot();
    const last = snap?.records[snap.records.length - 1];
    if (!snap || !last || this.busy()) return;
    // Same measurements and same timestamp: the backend updates this record instead of adding a day.
    const body: AssessBody = this.retryBody() ?? retryBodyFor(snap.astronautId, last);
    await this.send(snap, body);
  }

  private async send(snap: Snapshot, body: AssessBody): Promise<void> {
    this.busy.set(true);
    this.message.set(null);
    try {
      this.handle(await submitRecord(snap, body));
    } catch (error) {
      this.message.set({ tone: 'critical', text: error instanceof Error ? error.message : 'The request could not be completed.' });
    } finally {
      this.busy.set(false);
    }
  }

  private handle(result: SubmitResult): void {
    if (result.kind === 'saved') {
      this.snapshot.set(result.snapshot);
      this.connectionError.set(result.refreshWarning ?? null);
      this.recordIndex.set(null);
      const n = result.snapshot.records.length;
      if (result.status === 'completed' && !result.snapshot.records.at(-1)?.forecast) {
        this.retryBody.set(null);
        this.message.set({ tone: 'warning', text: `Record ${n} saved; its incompatible forecast is withheld. Refresh data before continuing.` });
      } else if (result.status === 'model_unavailable') {
        this.retryBody.set(result.body);
        // httpStatus 0 = kept locally (no backend), where there is nothing to retry.
        const retryText = result.httpStatus === 0 ? '' : ' You can retry it.';
        this.message.set({ tone: 'warning', text: `Record ${n} saved without a prediction. ${result.modelError ?? ''}${retryText}` });
      } else {
        this.retryBody.set(null);
        this.message.set({
          tone: 'ok',
          text:
            result.status === 'completed'
              ? `Record ${n} saved. The next-day forecast is ready in the Overview.`
              : `Record ${n} saved. Calibration ${Math.min(n, result.snapshot.calibrationRequired)} of ${result.snapshot.calibrationRequired}.`,
        });
      }
      return;
    }
    if (result.kind === 'rejected') {
      this.message.set({
        tone: 'critical',
        text:
          result.httpStatus === 409
            ? `Not saved (duplicate, out-of-order or gapped record): ${result.message}`
            : `Not saved: ${result.message}`,
      });
      return;
    }
    this.message.set({ tone: 'critical', text: result.message });
  }
}
