
class DCLogic { constructor(props){ this.props = props; this.state = {}; } setState(p){ this.state = Object.assign({}, this.state, p); } }

class Component extends DCLogic {
  constructor(props) {
    super(props);
    this.state = { mode: 'week', shift: 'open', why: false, webinar: false, question: '' };
  }
  renderVals() {
    const s = this.state;
    const modeDefs = [
      { id: 'week', label: 'Обычный день' },
      { id: 'today', label: 'День смены' },
      { id: 'new', label: 'Новичок' }
    ];
    const matches = [
      { title: 'Дизайн афиши спектакля', when: 'Онлайн, до 10 ноября, около 6 часов', score: 88, art: 'art art-o', isImage: true,
        reasons: ['графический дизайн', 'можно из дома', 'театру нужно к премьере'], locked: false },
      { title: 'Мастер-класс по валянию', when: 'Сб, 1 ноября, 11:00–14:00, Дмитровка', score: 81, art: 'art art-y', isFelt: true,
        reasons: ['суббота днём', 'дети 8–12', 'не хватает трёх человек'], locked: false },
      { title: 'Наставник новичка', when: '2 месяца, встреча раз в неделю', score: 64, art: 'art art-y', isBuddy: true,
        reasons: ['опыт вожатой', 'девять недель без пропусков'], locked: true, lockReason: 'Откроется 14 декабря: наставниками становятся после полугода в фонде.' }
    ];
    return {
      isRegular: s.mode !== 'new',
      isNew: s.mode === 'new',
      isToday: s.mode === 'today',
      isWeek: s.mode === 'week',
      whenLabel: s.mode === 'today' ? 'Сегодня, 12:00–14:00' : 'Сб, 25 октября, 12:00',
      modes: modeDefs.map((m) => ({
        ...m,
        cls: m.id === s.mode ? 'is-on' : '',
        pressed: m.id === s.mode ? 'true' : 'false',
        pick: () => this.setState({ mode: m.id, shift: 'open' })
      })),
      shiftOpen: s.shift === 'open',
      shiftConfirmed: s.shift === 'yes',
      shiftCancelled: s.shift === 'no',
      confirm: () => this.setState({ shift: 'yes' }),
      cantGo: () => this.setState({ shift: 'no' }),
      reset: () => this.setState({ shift: 'open' }),
      showWhy: s.why,
      whyExpanded: s.why ? 'true' : 'false',
      whyLabel: s.why ? 'Скрыть' : 'Почему так',
      toggleWhy: () => this.setState({ why: !s.why }),
      matches: matches.map((m) => ({ ...m, isImage: !!m.isImage, isFelt: !!m.isFelt, isBuddy: !!m.isBuddy, scoreLabel: 'Совпадение ' + m.score + ' из 100' })),
      webinarOpen: !s.webinar,
      webinarJoined: s.webinar,
      joinWebinar: () => this.setState({ webinar: true }),
      question: s.question,
      typeQuestion: (e) => this.setState({ question: e.target.value }),
      prompts: [
        'ребёнок отказывается рисовать',
        'просит мой номер телефона',
        'рассказал что-то тревожное'
      ].map((t) => ({ text: t, pick: () => this.setState({ question: 'Что делать, если ' + t + '?' }) }))
    };
  }
}

const c = new Component({});
const roots = ["cantGo", "confirm", "isNew", "isRegular", "isToday", "isWeek", "joinWebinar", "matches", "modes", "prompts", "question", "reset", "shiftCancelled", "shiftConfirmed", "shiftOpen", "showWhy", "toggleWhy", "typeQuestion", "webinarJoined", "webinarOpen", "whenLabel", "whyExpanded", "whyLabel"];
const seen = new Set();
const missing = new Set();
function visit(vals, depth){
  for (const r of roots) { if (vals[r] !== undefined) seen.add(r); }
  if (depth > 3) return;
  // click every demo/mode button, then every top-level function with no args
  const lists = Object.values(vals).filter(v => Array.isArray(v));
  return lists;
}
let vals = c.renderVals();
visit(vals, 0);
// exercise demo switchers: any array whose items have 'pick'
for (const k of Object.keys(vals)) {
  const v = vals[k];
  if (Array.isArray(v)) {
    for (const it of v) {
      if (it && typeof it.pick === 'function' && /^(modes|views|demo)/.test(k)) {
        it.pick();
        const v2 = c.renderVals();
        visit(v2, 1);
        // call all zero-arg functions at top level once (except typing)
        for (const [fk, fv] of Object.entries(v2)) {
          if (typeof fv === 'function' && fv.length === 0) { try { fv(); visit(c.renderVals(), 2); } catch (e) { console.log('ERR in ' + fk + ': ' + e.message); } }
        }
      }
    }
  }
}
for (const r of roots) if (!seen.has(r)) missing.add(r);
console.log(JSON.stringify({missing: [...missing]}));
