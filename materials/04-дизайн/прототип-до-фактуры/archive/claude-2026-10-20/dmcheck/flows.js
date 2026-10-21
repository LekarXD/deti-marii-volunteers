const fs = require('fs');
const path = require('path');
const DIR = path.join(__dirname, '..', 'dm-canvas', 'project');

function load(file) {
  const src = fs.readFileSync(path.join(DIR, file), 'utf8');
  const js = src.match(/<script type="text\/x-dc" data-dc-script[^>]*>([\s\S]*?)<\/script>/)[1];
  class DCLogic { constructor(p) { this.props = p; this.state = {}; } setState(p) { this.state = Object.assign({}, this.state, p); } }
  const C = new Function('DCLogic', js + '\nreturn Component;')(DCLogic);
  const c = new C({});
  return { c, v: () => c.renderVals() };
}
let fails = 0;
const ok = (cond, msg) => { if (!cond) { fails++; console.log('FAIL', msg); } else console.log('ok  ', msg); };
const ev = (value) => ({ target: { value } });

// ---------- Builder
{
  const { v } = load('Builder.dc.html');
  ok(v().blocks.length === 5 && v().lessonTitle.startsWith('Инклюзия'), 'builder: default lesson has 5 blocks');
  ok(v().hasStats && v().pubDotLabel === 'Опубликован', 'builder: stats + published');
  v().blocks[1].askDelete(); ok(v().blocks[1].confirming && !v().blocks[1].showActions, 'builder: delete asks confirm');
  v().blocks[1].doDelete(); ok(v().blocks.length === 4 && !v().blocks.some((b) => b.isVideo), 'builder: video deleted');
  v().toggleMenu(); ok(v().menuOpen && v().blockTypes.length === 10, 'builder: add menu with 10 types');
  v().blockTypes[7].add(); ok(v().blocks.length === 5 && v().blocks[4].isSim && v().blocks[4].isEmpty && !v().menuOpen, 'builder: sim block added');
  v().blocks[0].edit(); v().blocks[0].onEditText(ev('Кто приходит на занятия')); v().blocks[0].saveEdit();
  ok(v().blocks[0].title === 'Кто приходит на занятия', 'builder: edit title saved');
  v().audience[2].toggle(); ok(v().audience[2].cls === 'chip is-on' && v().audience[1].cls === 'chip is-on', 'builder: audience toggles');
  v().setDraft(); ok(v().pubDotLabel === 'Черновик', 'builder: set draft');
  v().modes[1].pick(); ok(v().isAi && v().aiIdle && v().layoutCls.includes('builder-2'), 'builder: ai mode');
  v().buildDraft(); ok(v().aiBuilt && v().plan.length === 5 && v().aiTest.length === 3 && v().sortCards[0].cards.length + v().sortCards[1].cards.length === 6, 'builder: draft 5/3/6');
  v().addToLesson(); ok(v().isEditor && v().blocks.length === 4 && v().hasNotice && !v().hasStats && v().pubDotLabel === 'Черновик', 'builder: draft added to lesson');
  v().modes[2].pick(); v().buildRec(); ok(v().recSummary.length === 5 && v().recTest.length === 5 && v().recTimes.length === 5, 'builder: rec 5/5/5');
  v().recTracks[2].pick(); v().createFromRec();
  ok(v().isEditor && v().lessonWhere === 'Ведущий, модуль 7 из 7' && v().blocks.length === 3 && v().isDraftTrack, 'builder: lesson from recording in Ведущий: ' + v().lessonWhere);
  ok(v().tracks[2].open && v().tracks[2].mods.length === 7, 'builder: track expanded with new module');
  v().tracks[2].mods[0].pick(); ok(v().noBlocks && v().cantPublish && v().pubDisabled === 'true', 'builder: empty module cannot publish');
  v().setPub(); ok(v().pubDotLabel === 'Черновик', 'builder: setPub ignored on empty');
  v().tracks[0].mods[4].pick(); ok(v().blocks[0].isTest && v().blocks[0].hasMore, 'builder: final test module');
}

// ---------- Knowledge
{
  const { v } = load('Knowledge.dc.html');
  ok(v().gaps.length === 3 && v().sources.length === 6 && v().uploadCls === 'btn btn-primary', 'kb: defaults');
  ok(v().sources[2].isError && v().sources[3].statusLabel === 'Обновляется', 'kb: one error, one updating');
  v().sources[2].retry(); ok(!v().sources[2].isError && v().sources[2].statusLabel === 'Обновляется', 'kb: retry upload');
  v().toggleLink(); v().onLink(ev('https://example.org/faq')); v().addLink(); ok(v().sources.length === 7 && v().sources[6].isLink, 'kb: link added');
  v().reviewQa(); // closed editor: should not matter
  v().gaps[2].write(); ok(v().qaOpen && v().qaQ.includes('подарки') && v().uploadCls === 'btn btn-secondary' && v().gaps[2].writing, 'kb: write answer opens editor with question');
  v().reviewQa(); ok(v().qaErr, 'kb: empty answer error');
  v().aiDraft(); ok(v().qaA.length > 20 && v().hasQaSrc && !v().qaSafety, 'kb: AI draft filled, not safety');
  v().reviewQa(); ok(v().qaReview, 'kb: review step');
  v().publishQa(); ok(v().gaps.length === 2 && v().hasFlash && v().sources[4].kind.startsWith('37') && v().sources[4].listOpen, 'kb: gift published, moved to answers');
  ok(v().sources[4].items[0].status === 'Новый', 'kb: new item marked');
  v().checkPrompts[2].pick(); v().ask(); ok(v().hasAnswer && v().fragments[0].doc === 'Ответы координаторов', 'kb: check finds new answer');
  v().gaps[0].write(); v().aiDraft(); ok(v().qaSafety, 'kb: museum is safety topic');
  v().reviewQa(); v().publishQa(); ok(v().sources[4].items[0].status === 'На проверке у психолога' && v().gaps.length === 1, 'kb: museum pending psych');
  v().togglePsych(); v().gaps[0].write(); v().aiDraft(); ok(!v().qaSafety, 'kb: psych check off');
  v().reviewQa(); v().publishQa(); ok(v().noGaps, 'kb: all gaps closed');
  v().modes[2].pick(); ok(v().hasAnswer && v().fragments.length === 3, 'kb: check demo shows phone answer with 3 fragments');
  v().onCheck(ev('Сколько стоит обед?')); v().ask(); ok(v().noAnswer, 'kb: custom question no answer');
  v().writeFromCheck(); ok(v().qaOpen && v().qaQ === 'Сколько стоит обед?' && !v().hasDraft, 'kb: write from check');
  v().modes[2].pick(); v().fixAnswer(); ok(v().qaOpen && v().qaA.startsWith('Скажи честно'), 'kb: fix answer prefilled');
  v().modes[2].pick(); v().markOk(); ok(v().verdictOk, 'kb: mark ok');
  v().modes[1].pick(); ok(v().qaOpen && v().qaQ.includes('музей'), 'kb: gaps demo opens editor with museum');
}

// ---------- Scenarios
{
  const { v } = load('Scenarios.dc.html');
  ok(v().isList && v().pending3 && v().rows.length === 6, 'sc: list');
  ok(v().rows[1].warn && v().rows[2].statusLabel === 'На проверке' && v().rows[5].statusLabel === 'Черновик' && v().rows[0].statusLabel.startsWith('Одобрен Ириной Власовой'), 'sc: statuses');
  v().open3(); ok(v().isEditor && v().hasStats && v().scTitle.includes('телефон') && v().runIdle, 'sc: editor sc3');
  ok(v().approveDisabled === 'true' && v().approveNote.includes('прогоните'), 'sc: approve needs run');
  ok(v().criteria.length === 5 && v().criteria[0].cls === 'toggle is-on' && v().critSummary.startsWith('Критических: 1'), 'sc: criteria with 1 critical');
  v().runTest(); ok(v().runDone && v().runLines.length === 3 && v().modes[2].cls === 'is-on', 'sc: test run 3 lines');
  v().setBad(); ok(v().runNote.includes('критическому'), 'sc: bad move note');
  v().rules[1].toggle(); ok(v().approveDisabled === 'true' && v().rules[1].off, 'sc: safety off blocks approval');
  v().rules[1].toggle(); ok(v().approveDisabled === 'false', 'sc: safety back on');
  v().approve(); ok(v().confirming && !v().approveIdle, 'sc: confirm step');
  v().confirmApprove(); ok(v().justApproved && v().statusLabel === 'Одобрен Ириной Власовой сегодня' && !v().showApprove, 'sc: approved today');
  v().onFirst(ev('[тихо] Придёшь?')); ok(v().runLines[0].text === '[тихо] Придёшь?', 'sc: edited first line used in run');
  v().rows[1].open(); ok(v().scWarn && v().criteria.filter((c) => c.cls === 'toggle is-on').length === 2, 'sc: sc2 warn + 2 critical');
  v().rows[5].open(); ok(v().showApprove && v().statusLabel === 'Черновик' && !v().hasStats, 'sc: sc6 draft');
  v().runTest(); v().approve(); v().confirmApprove(); ok(v().rows[5].short === 'Одобрен сегодня', 'sc: sc6 approved');
  v().modes[0].pick(); ok(v().pending3, 'sc: list reset');
}
console.log(fails ? fails + ' FAILED' : 'ALL FLOWS OK');
