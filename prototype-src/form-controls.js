// Shared select/date behavior. Screen handlers remain the source of form values.
class FormControls extends DCLogic {
  uiPatch(patch) {
    this.setState({_ui: {...(this.state._ui || {}), ...patch}});
  }
  uiFocus(id) {
    if (typeof document !== 'undefined') document.getElementById(id)?.focus();
  }
  uiDispatch(field, value) {
    const values = this.screenVals();
    const handler = field.change.split('.').reduce((value, key) => value?.[key], values);
    handler({target: {value}});
  }
  uiSelectKey(event, field) {
    const box = event.currentTarget;
    const options = Array.from(box.querySelectorAll('[role=option]'));
    const key = event.key;
    if (key === 'Escape') {
      event.preventDefault(); event.stopPropagation();
      this.uiPatch({choice: ''}); this.uiFocus(field.id);
      return;
    }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(key)) return;
    event.preventDefault();
    if (!options.length) {
      this.uiPatch({choice: field.id});
      if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => {
        const items = Array.from(box.querySelectorAll('[role=option]'));
        const selected = items.find(o => o.getAttribute('aria-selected') === 'true');
        (selected || items[key === 'ArrowUp' || key === 'End' ? items.length - 1 : 0])?.focus();
      });
      return;
    }
    const i = options.indexOf(event.target);
    const next = key === 'Home' ? 0 : key === 'End' ? options.length - 1 : i < 0 ? (key === 'ArrowDown' ? 0 : options.length - 1) : (i + (key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
    options[next].focus();
  }
  uiOpenDate(field, value) {
    const date = scheduleValid(value) ? value : '2026-10-21';
    this.uiPatch({date: field.id, month: date.slice(0, 7) + '-01', year: date.slice(0, 4), months: false, error: '', choice: ''});
  }
  uiChooseDate(value) {
    const ui = this.state._ui || {};
    if (ui.error) return;
    const field = UI_FIELDS.find(f => f.id === ui.date);
    this.uiDispatch(field, value);
    this.uiPatch({date: ''});
    this.uiFocus(field.id);
  }
  uiDateValues(values) {
    const ui = this.state._ui || {};
    const field = UI_FIELDS.find(f => f.id === ui.date);
    if (!field) return {open: false};
    const current = field ? field.value.split('.').reduce((v, k) => v?.[k], values) : '';
    const date = scheduleValid(ui.month) ? ui.month : '2026-10-01';
    const month = scheduleDate(date), from = scheduleMonday(date);
    const close = () => {this.uiPatch({date: ''}); if (field) this.uiFocus(field.id);};
    const move = delta => () => {
      const next = scheduleISO(new Date(Date.UTC(month.getUTCFullYear(), month.getUTCMonth() + delta, 1, 12)));
      this.uiPatch({month: next, year: next.slice(0, 4), error: ''});
    };
    return {
      open: !!field, pickerTitle: field?.label || '', pickerLabel: scheduleLabel(date, {month: 'long'}), pickerYear: ui.year ?? '2026',
      pickerDayView: !ui.months, pickerMonthView: !!ui.months, pickerPrevious: move(-1), pickerNext: move(1), pickerMonths: () => this.uiPatch({months: !ui.months}),
      changePickerYear: event => {
        const text = event.target.value, year = Number(text);
        const valid = /^\d{4}$/.test(text) && year >= 1900 && year <= 9999;
        this.uiPatch({year: text, ...(valid ? {month: text + date.slice(4)} : {}), error: valid ? '' : 'Год: от 1900 до 9999.'});
      },
      pickerWeekdays: ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map(label => ({label})),
      pickerDays: Array.from({length: 42}, (_, i) => {
        const value = scheduleAdd(from, i);
        return {label: scheduleDate(value).getUTCDate(), aria: scheduleLabel(value, {day:'numeric',month:'long',year:'numeric'}), cls: 'c-date' + (value === current ? ' is-on' : '') + (value.slice(0,7) !== date.slice(0,7) ? ' is-outside' : '') + (value === '2026-10-21' ? ' is-today' : ''), pressed: value === current ? 'true' : 'false', pick: () => this.uiChooseDate(value)};
      }),
      pickerMonthOptions: Array.from({length: 12}, (_, i) => {
        const value = scheduleISO(new Date(Date.UTC(month.getUTCFullYear(), i, 1, 12)));
        return {label: scheduleLabel(value, {month:'short'}).replace('.',''), cls: 'c-month' + (i === month.getUTCMonth() ? ' is-on' : ''), pick: () => this.uiPatch({month: value, months: false})};
      }),
      pickerError: ui.error || '', closeDatePicker: close, clearDateAllowed: false, clearDate: () => this.uiChooseDate(''), pickerToday: () => this.uiChooseDate('2026-10-21'),
      key: event => {
        if (event.key === 'Escape') {event.preventDefault(); event.stopPropagation(); close(); return;}
        if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key) && event.target.classList.contains('c-date')) {
          const days = Array.from(event.currentTarget.querySelectorAll('.c-date')), i = days.indexOf(event.target), step = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key];
          event.preventDefault(); days[Math.max(0,Math.min(days.length-1,i+step))].focus();
        }
        if (event.key === 'Tab') {
          const items = Array.from(event.currentTarget.querySelectorAll('button,input')).filter(x => !x.disabled && x.getClientRects().length);
          if (event.shiftKey && event.target === items[0]) {event.preventDefault(); items[items.length-1].focus();}
          else if (!event.shiftKey && event.target === items[items.length-1]) {event.preventDefault(); items[0].focus();}
        }
      }
    };
  }
  renderVals() {
    const values = this.screenVals(), ui = this.state._ui || {};
    for (const field of UI_FIELDS) {
      const value = field.value.split('.').reduce((v, k) => v?.[k], values);
      if (field.kind === 'date') {
        values[field.key] = {title: scheduleValid(value) ? scheduleLabel(value, {day:'numeric',month:'long',year:'numeric'}) : 'Выбрать дату', open: () => this.uiOpenDate(field, value)};
        continue;
      }
      values[field.key] = {
        title: field.options.find(o => String(o.id) === String(value))?.title || 'Выбрать', open: ui.choice === field.id, expanded: ui.choice === field.id ? 'true' : 'false',
        toggle: () => this.uiPatch({choice: ui.choice === field.id ? '' : field.id}), key: event => this.uiSelectKey(event, field),
        blur: event => {if (!event.currentTarget.contains(event.relatedTarget)) this.uiPatch({choice: ''});},
        options: field.options.map(o => ({...o, cls:'c-option' + (String(o.id) === String(value) ? ' is-on' : ''), selected: String(o.id) === String(value) ? 'true' : 'false', pick: () => {this.uiDispatch(field,o.id); this.uiPatch({choice:''}); this.uiFocus(field.id);}}))
      };
    }
    values.uiDate = this.uiDateValues(values);
    return values;
  }
}
