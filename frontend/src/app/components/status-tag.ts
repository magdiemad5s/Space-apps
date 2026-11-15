import { Component, computed, input } from '@angular/core';
import type { Level } from '../types';
import { LEVEL_LABEL } from '../lib/metrics';

@Component({
  selector: 'span[appStatusTag]',
  host: { class: 'status-tag', '[attr.data-level]': 'level()' },
  template: `<i aria-hidden="true"></i>{{ label() }}`,
})
export class StatusTag {
  readonly level = input.required<Level>();
  protected readonly label = computed(() => LEVEL_LABEL[this.level()]);
}
