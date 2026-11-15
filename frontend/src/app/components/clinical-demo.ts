import { Component, computed, signal } from '@angular/core';

type ScenarioId = 'healthy' | 'review' | 'high' | 'urgent' | 'unknown';
interface Scenario {
  id: ScenarioId; name: string; level: string; title: string; coverage: string;
  kss: string; fatigue: string; sleep: string; symptoms: string; reason: string; action: string; rule: string;
}

// Presentation fixtures only. No rule evaluation, persisted measurements, model request or alert state.
const SCENARIOS: Scenario[] = [
  { id: 'healthy', name: 'Normal current measurements', level: '0', title: 'No concern detected',
    coverage: 'Complete example core inputs', kss: '3 / 9', fatigue: '2 / 7', sleep: '8 hours', symptoms: 'No acute symptoms',
    reason: 'No concern is indicated by the available valid inputs in this fictional example.',
    action: 'Continue routine monitoring. This status does not mean medical or task clearance.', rule: 'No rules triggered' },
  { id: 'review', name: 'Sleepiness needs review', level: '1', title: 'Review',
    coverage: 'Complete example core inputs', kss: '7 / 9', fatigue: '2 / 7', sleep: '8 hours', symptoms: 'No acute symptoms',
    reason: 'KSS 7/9 indicates current sleepiness that needs review.',
    action: 'Review sleep opportunity, workload and upcoming tasks. Repeat at the next planned check or within 1–2 hours if symptomatic.', rule: 'S2' },
  { id: 'high', name: 'Very sleepy now; low forecast tomorrow', level: '2', title: 'High concern',
    coverage: 'Complete example core inputs', kss: '9 / 9', fatigue: '3 / 7', sleep: '8 hours', symptoms: 'No acute symptoms',
    reason: 'KSS 9/9 indicates severe current sleepiness. A low next-day forecast does not cancel a current concern.',
    action: 'Notify the crew lead or medical support before a critical task. Arrange rest and reassess; no automatic clearance.', rule: 'S3' },
  { id: 'urgent', name: 'Emergency symptom; other data missing', level: '3', title: 'Urgent',
    coverage: 'Partial example core inputs; warning retained', kss: 'Not provided', fatigue: 'Not provided', sleep: 'Not provided', symptoms: 'New chest pain reported',
    reason: 'A direct report of new chest pain takes priority despite missing measurements.',
    action: 'Activate the mission emergency medical procedure and contact medical support immediately. Do not wait for a model result or repeat test.', rule: 'Urgent medical override' },
  { id: 'unknown', name: 'Missing sleepiness score', level: 'UNKNOWN', title: 'Insufficient data',
    coverage: 'Partial example core inputs; KSS missing', kss: 'Not provided', fatigue: '2 / 7', sleep: '8 hours', symptoms: 'No acute symptoms',
    reason: 'The current KSS response is missing, and no valid positive alert is present in this example.',
    action: 'Request a current sleepiness score. Missing information must not be displayed as a normal assessment.', rule: 'UNKNOWN' },
];

@Component({
  selector: 'article[appClinicalDemo]',
  host: { class: 'card clinical-demo' },
  template: `
    <header><h2>Current-alert appearance</h2><span class="demo-badge">Illustrative demo</span></header>
    <p class="demo-scope">Predefined fictional scenarios, not connected to your observations or the model.</p>
    <label for="clinical-demo-scenario">Preview scenario</label>
    <select id="clinical-demo-scenario" [value]="selected()" (change)="choose($event)">
      @for (item of scenarios; track item.id) { <option [value]="item.id">{{ item.name }}</option> }
    </select>
    <dl class="demo-measurements">
      <div><dt>Sleepiness · KSS</dt><dd>{{ scenario().kss }}</dd></div>
      <div><dt>Fatigue · Samn–Perelli</dt><dd>{{ scenario().fatigue }}</dd></div>
      <div><dt>Main sleep</dt><dd>{{ scenario().sleep }}</dd></div>
      <div><dt>Symptom response</dt><dd>{{ scenario().symptoms }}</dd></div>
    </dl>
    <section class="demo-result" aria-live="polite" aria-atomic="true" [attr.data-demo-level]="scenario().level">
      <div class="demo-heading"><span>NOW · example current assessment</span><strong>{{ scenario().level === 'UNKNOWN' ? 'UNKNOWN' : 'Level ' + scenario().level }}</strong></div>
      <h3>{{ scenario().title }}</h3>
      <p class="demo-small">{{ scenario().coverage }}</p>
      <h4>Reason</h4><p>{{ scenario().reason }}</p>
      <h4>Example recommended action</h4><p>{{ scenario().action }}</p>
      <p class="demo-small">Illustrative V2 outcome: {{ scenario().rule }}</p>
    </section>
    <section class="demo-forecast">
      <div class="demo-heading"><h3>Tomorrow’s example forecast</h3><strong>Low</strong></div>
      <p>Placeholder only; no model request. Separate from the current-alert example above.</p>
    </section>
    <p class="demo-scope">Five presentation examples, not execution of the 14 clinical acceptance cases.
      The Clinical Alert V2 engine is deferred. This preview is not clinically validated.</p>
  `,
  styles: [`
    :host { display:block; padding:24px; }
    header,.demo-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; }
    h2 { font-size:20px; margin:0; } h3 { font-size:17px; margin:12px 0 4px; }
    h4 { font-size:13px; margin:18px 0 4px; } p { font-size:13px; line-height:1.6; margin:4px 0 0; }
    .demo-badge { background:var(--lime); padding:5px 9px; border-radius:6px; font-size:11px; }
    .demo-scope { color:var(--ink-2); margin-top:12px; }
    label { display:block; font-size:13px; margin:22px 0 8px; }
    select { width:100%; min-width:0; min-height:44px; border:1px solid var(--hair); border-radius:9px; padding:10px; background:var(--bg); color:var(--ink); font:inherit; font-size:14px; }
    .demo-measurements { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:18px; margin:20px 0; }
    dt { font-size:12px; color:var(--ink-2); } dd { margin:5px 0 0; font-size:15px; }
    .demo-result,.demo-forecast { border:1px solid var(--hair); border-radius:12px; padding:18px; margin-top:14px; }
    .demo-heading { font-size:12px; } .demo-heading h3 { font-size:14px; margin:0; }
    .demo-small { color:var(--ink-2); font-size:12px; margin-top:10px; }
    .demo-result[data-demo-level="1"] h3 { color:var(--warning-ink); }
    .demo-result[data-demo-level="2"] h3,.demo-result[data-demo-level="3"] h3 { color:var(--critical-ink); }
    @media(max-width:600px) { :host{padding:18px;} .demo-heading{align-items:flex-start;} }
  `],
})
export class ClinicalDemo {
  protected readonly scenarios = SCENARIOS;
  protected readonly selected = signal<ScenarioId>('high');
  protected readonly scenario = computed(() => SCENARIOS.find(item => item.id === this.selected())!);
  protected choose(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    if (SCENARIOS.some(item => item.id === value)) this.selected.set(value as ScenarioId);
  }
}
