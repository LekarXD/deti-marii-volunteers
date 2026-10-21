
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'answer', q: '', cite: '', fb: '', sent: false, passed: false, reported: false, draft: '', asked: [] };
  }
  renderVals() {
    const s = this.state;
    const DEFQ = {
      answer: 'Ребёнок попросил мой номер телефона. Что ответить?',
      none: 'Можно ли взять детей из группы в музей в выходной?',
      urgent: 'Девочка после занятия сказала, что один взрослый делает ей плохо, и попросила никому не говорить. Что делать?'
    };
    const clean = { cite: '', fb: '', sent: false, passed: false, reported: false };
    const route = (t) => {
      if (/насил|обижа|бьёт|бьет|наказыва|трога|делает .*плохо|никому не говорить/i.test(t)) return 'urgent';
      if (/телефон|номер|соцсет|друзья|переписк|контакт/i.test(t)) return 'answer';
      return 'none';
    };
    const modeDefs = [
      { id: 'answer', label: 'Ответ с источниками' },
      { id: 'none', label: 'Нет ответа в базе' },
      { id: 'urgent', label: 'Срочная ситуация' }
    ];
    const ANS = [
      { id: 'code', label: 'Кодекс волонтёра, п. 4.2', title: 'Кодекс волонтёра, пункт 4.2',
        text: 'Волонтёр не даёт детям личные номера телефонов, адреса и ссылки на свои страницы в соцсетях и не переписывается с ними лично. Связь с ребёнком вне занятий — только через координатора.' },
      { id: 'memo', label: 'Памятка «Границы»', title: 'Памятка «Границы», раздел «Личные контакты»',
        text: 'Если ребёнок просит твой номер: признай, что ему важно не потерять связь, объясни, что правило одно для всех взрослых, и предложи открытку через координатора.' },
      { id: 'lesson', label: 'Урок «Правила безопасности»', title: 'Урок «Правила безопасности и границы», модуль 2 «Первых шагов»',
        text: 'Любое общение с ребёнком должно быть на виду у других взрослых. Никаких контактов один на один — в том числе в переписке.', href: 'Lesson.dc.html', link: 'Открыть урок' }
    ];
    const URG = [
      { id: 'nspcc', label: 'NSPCC: как реагировать на раскрытие', title: 'NSPCC, «Recognising and responding to abuse» (перевод фонда)',
        text: 'Слушать, не перебивая. Сказать, что ребёнок правильно сделал, что рассказал, и что это не его вина. Не обещать сохранить тайну. Дословно записать слова ребёнка и как можно скорее действовать по процедурам организации.' },
      { id: 'reg', label: 'Регламент фонда: сигнал о ребёнке', title: 'Регламент фонда «Сигнал о ребёнке», пункт 2',
        text: 'Волонтёр сообщает психологу или координатору в тот же день. Сам не выясняет обстоятельства, не обсуждает услышанное с тем, на кого указал ребёнок, и не расспрашивает других детей. Дальнейшие шаги определяет психолог фонда.' }
    ];
    const citeDefs = s.mode === 'urgent' ? URG : ANS;
    const open = citeDefs.find((c) => c.id === s.cite);
    const defaults = [
      { q: 'Ребёнок попросил мой номер телефона', when: 'Сегодня', mode: 'answer', custom: false },
      { q: 'Можно ли взять детей в музей в выходной?', when: 'Сегодня', mode: 'none', custom: false },
      { q: 'Девочка просит никому не говорить, что её обижают', when: 'Вчера', mode: 'urgent', custom: false }
    ];
    const history = s.asked.map((a) => ({ q: a.q, when: 'Только что', mode: a.mode, custom: true })).concat(defaults).map((h) => {
      const on = h.custom ? s.q === h.q : (!s.q && s.mode === h.mode);
      return {
        q: h.q,
        when: h.when,
        cls: on ? 'hq is-on' : 'hq',
        pressed: on ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ mode: h.mode, q: h.custom ? h.q : '' }, clean))
      };
    });
    return {
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState(Object.assign({ mode: m.id, q: '' }, clean))
      })),
      isAnswer: s.mode === 'answer',
      isNone: s.mode === 'none',
      isUrgent: s.mode === 'urgent',
      question: s.q || DEFQ[s.mode],
      history,
      prompts: ['Ребёнок просит добавить его в друзья в соцсетях', 'Можно ли угостить группу сладким?', 'Ребёнок сказал, что дома его наказывают'].map((t) => ({
        text: t,
        pick: () => this.setState({ draft: t })
      })),
      cites: citeDefs.map((c) => ({
        label: c.label,
        cls: s.cite === c.id ? 'cite is-on' : 'cite',
        expanded: s.cite === c.id ? 'true' : 'false',
        toggle: () => this.setState({ cite: s.cite === c.id ? '' : c.id })
      })),
      citeOpen: !!open,
      citeTitle: open ? open.title : '',
      citeText: open ? open.text : '',
      citeHasLink: !!(open && open.href),
      citeHref: open && open.href ? open.href : '',
      citeLinkLabel: open && open.link ? open.link : '',
      fbIdle: !s.fb,
      fbWasYes: s.fb === 'yes',
      fbWasNo: s.fb === 'no',
      fbYes: () => this.setState({ fb: 'yes' }),
      fbNo: () => this.setState({ fb: 'no' }),
      notSent: !s.sent,
      sent: s.sent,
      sendCoord: () => this.setState({ sent: true }),
      notPassed: !s.passed,
      passed: s.passed,
      passQ: () => this.setState({ passed: true }),
      notReported: !s.reported,
      reported: s.reported,
      report: () => this.setState({ reported: true }),
      draft: s.draft,
      typeDraft: (e) => this.setState({ draft: e.target.value }),
      ask: () => {
        const t = (s.draft || '').trim();
        if (!t) return;
        const m = route(t);
        this.setState(Object.assign({ mode: m, q: t, draft: '', asked: [{ q: t, mode: m }].concat(s.asked).slice(0, 3) }, clean));
      }
    };
  }
}

const c = new Component({});
const roots = ["ask", "citeHasLink", "citeHref", "citeLinkLabel", "citeOpen", "citeText", "citeTitle", "cites", "draft", "fbIdle", "fbNo", "fbWasNo", "fbWasYes", "fbYes", "history", "isAnswer", "isNone", "isUrgent", "modes", "notPassed", "notReported", "notSent", "passQ", "passed", "prompts", "question", "report", "reported", "sendCoord", "sent", "typeDraft"];
const seen = new Set();
function mark(vals){ for (const r of roots) { if (vals[r] !== undefined) seen.add(r); } }
function fire(vals, label){
  for (const [fk, fv] of Object.entries(vals)) {
    if (typeof fv === 'function') {
      try { fv({ target: { value: 'тест' } }); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + ': ' + e.message); }
    }
    if (Array.isArray(fv)) {
      for (const it of fv) {
        if (it && typeof it === 'object') {
          for (const [ik, iv] of Object.entries(it)) {
            if (typeof iv === 'function') {
              try { iv(); mark(c.renderVals()); } catch (e) { console.log('ERR ' + label + '.' + fk + '[].' + ik + ': ' + e.message); }
            }
          }
        }
      }
    }
  }
}
let v0 = c.renderVals();
mark(v0);
const modeKey = Object.keys(v0).find(k => /^(modes|views|demo)$/.test(k));
const modes = modeKey ? v0[modeKey] : [null];
for (let i = 0; i < modes.length; i++) {
  const cur = c.renderVals();
  if (modeKey) { cur[modeKey][i].pick(); }
  const v = c.renderVals();
  mark(v);
  fire(v, 'mode' + i);
  mark(c.renderVals());
}
console.log(JSON.stringify({ missing: roots.filter(r => !seen.has(r)) }));
