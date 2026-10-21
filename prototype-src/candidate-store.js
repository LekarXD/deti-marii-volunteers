// Общая логика кандидата: анкета, маски ввода, проверки, прогресс онбординга.
// Тексты анкеты и онбординга — в prototype/content/form.js и onboarding.js (FORM, ONBOARDING).
const FORM = window.FORM, ONB = window.ONBOARDING;
const arr = v => Array.isArray(v) ? v : (v ? [v] : []);
// Вариант ответа — строка или { label, icon }
const optLabel = o => typeof o === 'string' ? o : o.label;
const cap = w => w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w;
const ageOf = d => { const b = new Date(d); if (isNaN(b)) return null; const n = new Date(); let a = n.getFullYear() - b.getFullYear(); if (n < new Date(n.getFullYear(), b.getMonth(), b.getDate())) a--; return a; };
const fullName = c => (c && (c.name || [c.firstName, c.lastName].filter(Boolean).join(' '))) || '';
const firstName = c => fullName(c).split(/\s+/)[0] || '';
const allFields = () => FORM.steps.flatMap(s => s.fields).concat(FORM.matching.fields);

const birthdateDisplay = value => /^\d{4}-\d{2}-\d{2}$/.test(value||'') ? value.slice(8,10)+'.'+value.slice(5,7)+'.'+value.slice(0,4) : (value||'');
const birthdateInput = raw => {if(/^\d{4}-\d{2}-\d{2}$/.test(raw))return raw;const digits=raw.replace(/\D/g,'').slice(0,8);if(digits.length===8)return digits.slice(4)+'-'+digits.slice(2,4)+'-'+digits.slice(0,2);return [digits.slice(0,2),digits.slice(2,4),digits.slice(4)].filter(Boolean).join('.');};
const MASK = {
  name: v => v.replace(/[^A-Za-zА-Яа-яЁё\- ']/g, '').replace(/\s+/g, ' ').replace(/^[\s-]+/, '').replace(/(^|[\s-])([a-zа-яё])/g, (m, a, b) => a + b.toUpperCase()),
  phone: v => {
    let d = v.replace(/\D/g, '');
    if (d[0] === '8') d = '7' + d.slice(1);
    if (d[0] !== '7') d = '7' + d;
    if (d.length > 11 && d[1] === '8') d = d[0] + d.slice(2); // набрали 8… после подставленного +7
    const p = d.slice(1, 11);
    let out = '+7';
    if (p.length) out += ' (' + p.slice(0, 3);
    if (p.length > 3) out += ') ' + p.slice(3, 6);
    if (p.length > 6) out += '-' + p.slice(6, 8);
    if (p.length > 8) out += '-' + p.slice(8, 10);
    return out;
  },
  telegram: v => '@' + v.trim().replace(/^@+/, '').replace(/^(https?:\/\/)?(www\.)?(t\.me|telegram\.me)\//i, '').replace(/[^A-Za-z0-9_]/g, '').slice(0, 32)
};
const FINAL = {
  name: v => MASK.name(v).trim().replace(/-+$/, '').split(/([\s-])/).map(w => /[\s-]/.test(w) ? w : cap(w)).join(''),
  phone: v => v.replace(/\D/g, '').length <= 1 ? '' : MASK.phone(v),
  telegram: v => v === '@' ? '' : MASK.telegram(v)
};
const shortHint = (f, v) => {
  if (f.id !== 'firstName') return '';
  const full = (FORM.shortNames || {})[cap(String(v || '').trim())];
  return full ? `Это полное имя? Например, ${full}. Так координатору будет проще найти вас в документах.` : '';
};
const visibleFor = (f, data) => {
  if (!f.showIf) return true;
  const v = arr(data[f.showIf.field]), want = arr(f.showIf.value);
  return want.some(w => v.includes(w));
};
// «Нет, не подходит» и «Пока не знаю» нельзя выбрать вместе с остальными вариантами
const withExclusive = (f, list, changed, added) => {
  const ex = (f.exclusive || []).concat(f.unsure ? [f.unsure] : []);
  if (!added || !ex.length) return list;
  return ex.includes(changed) ? [changed] : list.filter(v => !ex.includes(v));
};
const roleGroups = roles => {
  const f = FORM.steps.flatMap(s => s.fields).find(x => x.type === 'roles');
  return f ? f.groups.filter(g => g.roles.some(r => arr(roles).includes(r))).map(g => g.title) : [];
};
function validateFields(fields, data) {
  const errs = {};
  fields.filter(f => visibleFor(f, data)).forEach(f => {
    if (f.groups && f.type === 'checkbox') data[f.id] = arr(data[f.id]).filter(o => f.groups.some(g => visibleFor(g, data) && g.options.includes(o)));
    if (f.groups && f.type === 'chips') data[f.id] = arr(data[f.id]).filter(o => f.groups.some(g => visibleFor(g, data) && g.options.map(optLabel).includes(o)));
    const v = data[f.id];
    const empty = v == null || v === '' || v === false || (Array.isArray(v) && v.length === 0);
    if (f.required && empty) errs[f.id] = f.type === 'consent' ? 'Без согласия мы не сможем обработать заявку' : f.type === 'roles' ? 'Выберите хотя бы одну роль или «Пока не знаю»' : 'Заполните, пожалуйста';
    else if (!empty && f.type === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) errs[f.id] = 'Проверьте адрес почты';
    else if (!empty && f.mask === 'phone' && String(v).replace(/\D/g, '').length !== 11) errs[f.id] = 'Номер должен быть из 10 цифр после +7';
    else if (!empty && f.mask === 'telegram' && !/^@[A-Za-z0-9_]{5,32}$/.test(v)) errs[f.id] = 'Ник — от 5 символов: латиница, цифры и _';
    else if (!empty && f.mask === 'name' && !/^[А-ЯЁA-Z][а-яёa-z']+([\s-][А-ЯЁA-Z][а-яёa-z']+)*$/.test(v)) errs[f.id] = 'Проверьте написание: только буквы, без сокращений';
    else if (!empty && f.id === 'birthdate' && !scheduleValid(v)) errs[f.id] = 'Введите дату в формате ДД.ММ.ГГГГ';
    else if (!empty && f.id === 'birthdate') { const a = ageOf(v); if (a == null || a < 16) errs[f.id] = 'Волонтёром можно стать с 16 лет'; else if (a > 110) errs[f.id] = 'Проверьте дату'; }
  });
  return errs;
}

// Поля формы → данные для шаблона. update(id, value) меняет ответ; ui — раскрытые группы ролей.
function fieldViews(fields, data, errs, update, ui, setUi) {
  let sec = 0;
  return fields.filter(f => visibleFor(f, data)).map(f => {
    const v = data[f.id];
    const t = f.type;
    const isInput = ['text', 'email', 'tel', 'date'].includes(t);
    const toggleIn = (o) => () => {
      const set = new Set(arr(data[f.id]));
      const on = !set.has(o);
      on ? set.add(o) : set.delete(o);
      update(f.id, withExclusive(f, [...set], o, on));
    };
    const optView = opt => { const o = optLabel(opt), icon = typeof opt === 'string' ? '' : opt.icon || '', on = (t === 'radio' || t === 'select') ? v === o : arr(v).includes(o); return { label: o, ...icoFlags(icon), hasIcon: !!icon, checked: on, pressed: on, cls: on ? 'chip is-on' : 'chip', lineCls: on ? 'a-line is-on' : 'a-line', tileCls: on ? 'a-tile is-on' : 'a-tile', toggle: (t === 'radio' || t === 'select') ? () => update(f.id, o) : toggleIn(o) }; };
    const warn = shortHint(f, v);
    return {
      id: f.id, label: f.label || f.title, req: !!f.required,
      isSection: t === 'section', note: f.note || '', hasNote: !!f.note, ...icoFlags(f.icon || ''), showLabel: !['consent', 'section', 'tiles'].includes(t) && !f.hideLabel,
      isTiles: t === 'tiles', opt: !!f.optional, why: f.why || '', hasWhy: !!f.why,
      cls: (t === 'section' ? 'a-sec a-sec-' + (sec++ % 4) : 'field a-field') + (f.half ? ' a-half' : '') + (errs[f.id] ? ' a-bad' : ''),
      err: errs[f.id] || '', hasErr: !!errs[f.id], warn, hasWarn: !!warn,
      isConsent: t === 'consent', notConsent: t !== 'consent',
      isInput, inputType: t === 'date' ? 'text' : t, inputMode: t === 'date' ? 'numeric' : t === 'email' ? 'email' : t === 'tel' ? 'tel' : 'text', value: t === 'date' ? birthdateDisplay(v) : v == null ? '' : v, placeholder: t === 'date' ? 'ДД.ММ.ГГГГ' : f.placeholder || '', autocomplete: f.autocomplete || 'off',
      change: e => { const raw = e.target.value; update(f.id, t === 'date' ? birthdateInput(raw) : f.mask ? MASK[f.mask](raw) : raw); },
      focus: () => { if (f.mask === 'phone' && !data[f.id]) update(f.id, '+7 ('); if (f.mask === 'telegram' && !data[f.id]) update(f.id, '@'); },
      blur: () => { if (f.mask) update(f.id, FINAL[f.mask](String(data[f.id] || ''))); },
      isTextarea: t === 'textarea', isSelect: t === 'select',
      isChoice: (t === 'radio' || t === 'checkbox') && !f.groups, choiceType: t, options: (f.options || []).map(optView),
      isGroups: t === 'checkbox' && !!f.groups,
      groups: (t === 'checkbox' && f.groups ? f.groups : []).filter(g => visibleFor(g, data)).map(g => ({ title: g.title, note: g.note || '', hasNote: !!g.note, hasOptions: g.options.length > 0, options: g.options.map(optView) })),
      isChips: t === 'chips' && !f.groups, isChipGroups: t === 'chips' && !!f.groups,
      chipGroups: (t === 'chips' && f.groups ? f.groups : []).filter(g => visibleFor(g, data)).map(g => ({ title: g.title, options: g.options.map(optView) })),
      hasOther: !!f.allowOther, other: data[f.id + 'Other'] || '', changeOther: e => update(f.id + 'Other', e.target.value),
      isGrid: t === 'grid', cols: f.cols || [],
      rows: (f.rows || []).map(r => ({ label: r, cells: (f.cols || []).map(c => { const k = r + '·' + c, on = arr(v).includes(k); return { cls: on ? 'a-cell is-on' : 'a-cell', pressed: on, aria: r + ', ' + c, toggle: toggleIn(k) }; }) })),
      isRoles: t === 'roles',
      rgroups: (t === 'roles' ? f.groups : []).map((g, gi) => {
        const n = g.roles.filter(r => arr(v).includes(r)).length, key = f.id + gi, open = n > 0 || !!ui[key];
        return { title: g.title, hint: g.hint || '', hasHint: !!g.hint, open, cls: open ? 'a-rgroup is-open' : 'a-rgroup', badge: n ? `выбрано: ${n}` : (open ? 'свернуть' : 'открыть'), badgeCls: n ? 'tag t-orange' : 'tag', toggle: () => setUi(key), roles: g.roles.map(optView) };
      }),
      unsure: f.unsure || '', unsureOn: arr(v).includes(f.unsure), unsureToggle: toggleIn(f.unsure),
      checked: !!v, toggle: () => update(f.id, !data[f.id])
    };
  });
}

const freshProgress = () => ({ done: {}, testDone: false, score: null, road: false, tg: false });
const loadCandidate = () => demoRead('candidate', null);
const loadProgress = () => Object.assign(freshProgress(), demoRead('onboarding', {}));
const DEMO_CANDIDATE = { firstName: 'Анна', lastName: 'Соколова', name: 'Анна Соколова', birthdate: '1994-05-12', phone: '+7 (916) 123-45-67', email: 'anna@example.com', channels: ['Telegram'], telegram: '@anna_sokolova', area: 'Центр Москвы', directions: ['Творческие занятия и мастер-классы', 'Помогать на занятиях'], skills: ['Керамика', 'Живопись и рисунок'], sphere: 'Дизайн, фото, медиа', volExp: 'Нет', specialExp: 'Нет, но готов(а) попробовать', participation: 'Каждую неделю', online: true, source: 'ВКонтакте', record: 'Да', consentPD: true, submittedAt: new Date().toISOString() };

// Все поля анкеты по id (без заголовков блоков) — для вариантов 2 и 3
const fieldById = id => FORM.steps.flatMap(s => s.fields).find(f => f.id === id && f.type !== 'section');
const quickField = q => typeof q === 'string' ? fieldById(q) : q.type === 'section' ? q : { ...fieldById(q.id), ...(q.override || {}) };
// Сохранить анкету и перейти в кабинет
const submitCandidate = (data, extra) => { const me = { ...data, ...(extra || {}), name: [data.firstName, data.lastName].filter(Boolean).join(' '), submittedAt: new Date().toISOString() }; demoWrite('candidate', me); demoWrite('onboarding', freshProgress()); location.href = 'ApplicationStatus.dc.html'; };

// Иконки по имени из контента (сборщик подставляет svg через ICONSWITCH)
const ICON_KEYS = ['palette','book','users','user','heart','home','hand','shield','smile','star','camera','calendar','pin','message','mask','music','award','sparkle','eye','clock','phone','alert','check-circle','academy','pen','scissors','flame','globe','dice','film','image','file','chart','screen','database','send','inbox','settings','search','edit'];
const icoFlags = name => { const o = {}; ICON_KEYS.forEach(k => { o['ic_' + k.replace('-', '_')] = k === name; }); return o; };
// В прототипе без анкеты показываем всё на демо-кандидате, чтобы ничего не заполнять руками
const ensureCandidate = () => { const me = loadCandidate(); if (me) return me; demoWrite('candidate', DEMO_CANDIDATE); return DEMO_CANDIDATE; };
