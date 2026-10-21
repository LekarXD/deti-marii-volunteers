"""Assemble Claude Design artboards from the original kit and extension sources."""
from pathlib import Path
import json
import re
from prototype_controls import enhance_controls
from coordinator_layout import work_frame, wrap_original

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'prototype-src'
OUT = ROOT / 'prototype'
BASE = ROOT / 'materials/04-дизайн/прототип-до-фактуры/screens'
OUT.mkdir(exist_ok=True)

SCREENS = {
    'FundCatalog': ('Волонтёр: направления фонда', 'volunteer', 1270),
    'Needs': ('Фонд: возможности и подготовка к роли', 'coordinator', 1480),
    'Roles': ('Фонд: справочник ролей', 'coordinator', 1400),
    'Candidates': ('Фонд: кандидаты и анкеты', 'coordinator', 1500),
    'Interviews': ('Фонд: собеседования и доступность', 'coordinator', 1800),
    'Planning': ('Фонд: расписание и управление сменами', 'coordinator', 1290),
    'VolunteerRecord': ('Фонд: договорённости с волонтёром', 'coordinator', 1390),
    'Reserve': ('Фонд: проверка старых контактов', 'coordinator', 1140),
    'Participants': ('Фонд: участники и карточки', 'coordinator', 1230),
    'Groups': ('Фонд: состав и расписание групп', 'coordinator', 1650),
    'Group': ('Волонтёр: кто будет на занятии', 'volunteer', 1590),
    'FirstShift': ('Волонтёр: первый выход', 'volunteer', 1940),
    'Participation': ('Участие: от отклика до занятия', 'volunteer', 1320),
    # Путь кандидата: тексты в prototype/content/, общая логика в candidate-store.js
    'Apply': ('Кандидат: анкета волонтёра', 'candidate', 2600),
    'Onboarding': ('Кандидат: знакомство с фондом', 'candidate', 2400),
    'ApplicationStatus': ('Кандидат: личный кабинет', 'candidate', 1700),
}
CONTENT = ROOT / 'prototype/content'
CANDIDATE_ICONS = ['palette','book','users','heart','home','hand','shield','smile','star','camera','calendar','pin','message','mask','music','award','sparkle','eye','clock','phone','alert','check-circle']

def subnav(role, current=''):
    links = [('Interviews', 'Собеседования'), ('Needs', 'Возможности'), ('Planning', 'Расписание'), ('Roles', 'Роли'), ('Participants', 'Участники'), ('Groups', 'Группы'), ('Reserve', 'Резерв')] if role == 'coordinator' else [('FirstShift', 'Первый выход'), ('FundCatalog', 'Направления фонда'), ('Group', 'Моя группа')]
    return '<nav class="chips subnav" aria-label="' + ('Работа фонда' if role == 'coordinator' else 'Участие') + '">' + ''.join(f'<a class="chip{" is-on" if n == current else ""}" href="{n}.dc.html">{label}</a>' for n,label in links) + '</nav>'

for p in BASE.iterdir():
    if p.suffix == '.html':
        text = p.read_text()
        text = text.replace('</style>', '.subnav{margin:0 0 32px}.dm .grid-2{grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr))}\n</style>')
        # Original screens remain preserved in materials; only the working copy is linked.
        role = 'coordinator' if 'команда фонда' in text else 'volunteer'
        if role != 'coordinator' and p.stem not in ['Apply.dc', 'ApplicationStatus.dc', 'Main.dc', 'Studio.dc', 'Phone.dc']:
            text = text.replace('</header>', '</header>\n' + subnav(role), 1)
        text = text.replace('href="Opportunity.dc.html"', 'href="Participation.dc.html"') if p.name == 'Catalog.dc.html' else text
        if p.name == 'Catalog.dc.html':
            text = text.replace('>Записаться</a>', '>Откликнуться</a>')

        if p.name == 'Home.dc.html':
            text = text.replace('Пройди «Первые шаги»','Твой первый выход').replace('После обучения откроется запись на занятия','Посмотри, где тебя ждут и кто встретит').replace('Заявку одобрили','Первый выход согласован')
            text = text.replace('href="Lesson.dc.html">Продолжить обучение','href="FirstShift.dc.html">Подготовиться к выходу')
            text = text.replace('href="Lesson.dc.html" style="margin-top:28px">Продолжить обучение','href="FirstShift.dc.html" style="margin-top:28px">Подготовиться к выходу')
            text = text.replace('<div class="row" style="gap:14px;margin-top:22px;max-width:460px"><div class="bar grow"><i style="width:20%"></i></div><span class="strong num">1 из 5</span></div>','')
        if role == 'coordinator':
            text = text.replace('href="Pipeline.dc.html"', 'href="Interviews.dc.html"').replace('Заявки<span class="count">7</span>', 'Заявки')
        if role == 'coordinator':
            text = text.replace('</style>', (SRC/'extensions.css').read_text()+'\n</style>')
            text = wrap_original(text,SRC,p.stem.replace('.dc',''))
        (OUT / p.name).write_text('\n'.join(line.rstrip() for line in text.splitlines())+'\n')

helmet = (SRC/'helmet.html').read_text()
css = (SRC/'extensions.css').read_text()
for name,(title,role,height) in SCREENS.items():
    if role == 'candidate':
        if name == 'Apply':
            # анкета живёт на сайте фонда — без навигации платформы
            head = (SRC/'site-header.html').read_text()
        else:
            # личный кабинет кандидата — та же шапка платформы, «Главная» ведёт в кабинет
            head = (SRC/'volunteer-header.html').read_text().replace('{{meAvCls}}', 'avatar av-o').replace('{{meInitials}}', 'АС').replace('{{meLabel}}', 'Анна Соколова, кандидат')
            head = head.replace('class="is-active" aria-current="page" ', '').replace('<a href="Home.dc.html">', '<a class="is-active" aria-current="page" href="ApplicationStatus.dc.html">', 1)
            # Пока анкета проверяется, остальные разделы платформы закрыты
            locked = ' class="is-locked" aria-disabled="true" title="Откроется после встречи с координатором"'
            head = re.sub(r'<a href="(Catalog|Schedule|Academy|Messages|Hours)\.dc\.html">(.*?)</a>', lambda m: f'<span{locked}>' + re.sub(r'<span class="count">\d+</span>', '', m.group(2)) + '</span>', head)
            head = re.sub(r'<a class="iconbtn" href="Mentor\.dc\.html" aria-label="ИИ-наставник">(.*?)</a>', lambda m: f'<span class="iconbtn is-locked" aria-disabled="true" aria-label="ИИ-наставник откроется после встречи" title="Откроется после встречи с координатором">{m.group(1)}</span>', head)
            head = re.sub(r'<a href="Profile\.dc\.html" class="avatar av-o" aria-label="Профиль: Анна Соколова">АС</a>', '<span class="avatar av-o" aria-label="Анна Соколова">АС</span>', head)
            head = head.replace('aria-label="Уведомления, 2 новых"', 'aria-label="Уведомления"').replace('<span class="pip"></span>', '')
        body = (SRC/f'{name}.body.html').read_text().replace('<!--FIELDS-->', (SRC/'form-fields.html').read_text())
        icons = dict(re.findall(r'^([\w-]+):\s*(<svg[^\n]+)', (ROOT/'materials/04-дизайн/прототип-до-фактуры/kit/icons.html').read_text(), re.M))
        # ICONSWITCH(x) — иконка по имени из данных: x.ic_palette, x.ic_check_circle …
        def iconswitch(m):
            var = m.group(1)
            return ''.join(f'<sc-if value="{{{{{var}.ic_{k.replace("-", "_")}}}}}">{icons[k]}</sc-if>' for k in CANDIDATE_ICONS)
        body = re.sub(r'ICONSWITCH\((\w+)\)', iconswitch, body)
        body = re.sub(r'<button(?![^>]*\btype=)', '<button type="button"', body)
        body, candidate_logic = enhance_controls(body, (SRC/f'{name}.js').read_text(), SRC)
        for token,key in [('PALETTE','palette'),('CALENDAR','calendar'),('RIGHT','chevron-right'),('LEFT','chevron-left'),('CHECK','check-circle'),('SPARKLE','sparkle'),('CLOCKICO','clock'),('BOOKICO','book'),('MESSAGEICO','message'),('X','x')]:
            body = body.replace('ICON_'+token, icons[key])
        logic = (SRC/'date-utils.js').read_text() + '\n' + (SRC/'demo-store.js').read_text() + '\n' + (CONTENT/'form.js').read_text() + '\n' + (CONTENT/'onboarding.js').read_text() + '\n' + (SRC/'candidate-store.js').read_text() + '\n' + (SRC/'interview-store.js').read_text() + '\n' + candidate_logic
        h = helmet.replace('</style>', css + '\n' + (SRC/'candidate.css').read_text() + '\n</style>')
        doc = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — Опора</title><script src="./support.js"></script></head><body>
<x-dc>
{h}
<div class="dm"><div class="shell">
{head}
{body}
</div></div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":1440,"height":{height}}}}}'>
{logic}
</script></body></html>
'''
        (OUT/f'{name}.dc.html').write_text(doc)
        continue
    head = (SRC/f'{role}-header.html').read_text()
    head = head.replace('{{meAvCls}}', 'avatar av-b' if role=='coordinator' else 'avatar av-o').replace('{{meInitials}}', 'ОЛ' if role=='coordinator' else 'АС').replace('{{meLabel}}', 'Ольга Лебедева, координатор' if role=='coordinator' else 'Анна Соколова, волонтёр')
    if name == 'Interviews':
        head = head.replace('ОЛ', 'АВ').replace('Ольга Лебедева, координатор', 'Алевтина, координатор волонтёров')
    head = head.replace('class="is-active" aria-current="page" ', '')
    head = head.replace('href="Pipeline.dc.html"', 'href="Interviews.dc.html"')
    active = 'Interviews' if name == 'Interviews' else 'Shifts' if name == 'Planning' else ('Volunteers' if name in ['VolunteerRecord','Reserve'] else ('Catalog' if name in ['FundCatalog','Participation'] else 'Home'))
    head = head.replace(f'<a href="{active}.dc.html"', f'<a class="is-active" aria-current="page" href="{active}.dc.html"')
    body = re.sub(r'<button(?![^>]*\btype=)', '<button type="button"', (SRC/f'{"Interviews" if name=="Candidates" else name}.body.html').read_text())
    screen_logic=(SRC/f'{"Interviews" if name=="Candidates" else name}.js').read_text()
    if name in ['Interviews','Candidates']:screen_logic="const INTERVIEW_VIEW = "+repr('candidates' if name=='Candidates' else 'meetings')+";\n"+screen_logic
    body, screen_logic = enhance_controls(body, screen_logic, SRC)
    if 'UI_DATE_PICKER' in body:
        calendar = re.sub(r'\{\{uiDate\.([\w.]+)\}\}', lambda m: '{{'+{'open':'datePicker','key':'dateKey'}.get(m[1],m[1])+'}}', (SRC/'date-picker.html').read_text())
        body = body.replace('UI_DATE_PICKER', calendar)
    icons = dict(re.findall(r'^([\w-]+):\s*(<svg[^\n]+)', (ROOT/'materials/04-дизайн/прототип-до-фактуры/kit/icons.html').read_text(), re.M))
    for token,key in [('USERS','users'),('PALETTE','palette'),('CALENDAR','calendar'),('RIGHT','chevron-right'),('LEFT','chevron-left'),('PLUS','plus'),('X','x')]:
        body = body.replace('ICON_'+token, icons[key])
    logic = (SRC/'date-utils.js').read_text() + '\n' + (SRC/'demo-store.js').read_text() + '\nconst ROLES = demoRead("roles", ' + (SRC/'roles.json').read_text().strip() + ');\nconst PEOPLE = demoRead("people", ' + (SRC/'participants.json').read_text().strip() + ');\n' + (SRC/'role-directory.js').read_text() + '\n' + ((SRC/'Planning.controls.js').read_text() + '\n' if name=='Planning' else '') + (((CONTENT/'form.js').read_text()+'\n'+(CONTENT/'onboarding.js').read_text()+'\n'+(SRC/'candidate-store.js').read_text()+'\n'+(SRC/'interview-store.js').read_text()+'\n') if name in ['Interviews','Candidates'] else '') + screen_logic
    h = helmet.replace('</style>',css+'\n</style>')
    doc = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} — Опора</title><script src="./support.js"></script></head><body>
<x-dc>
{h}
<div class="dm"><div class="shell">
{head}
{subnav(role,name)}
{body}
</div></div>
</x-dc>
<script type="text/x-dc" data-dc-script data-props='{{"$preview":{{"width":1440,"height":{height}}}}}'>
{logic}
</script></body></html>
'''
    if role == 'coordinator':
        frame_start=doc.index('<div class="dm"><div class="shell">')
        frame_end=doc.index('</x-dc>',frame_start)
        doc=doc[:frame_start]+work_frame(SRC,name,body)+'\n'+doc[frame_end:]
    (OUT/f'{name}.dc.html').write_text(doc)

# Add a connected entry into the original map, without replacing its four role cards.
p = OUT/'Main.dc.html'
t = p.read_text()
extension = '<section class="section"><div class="section-head"><h2 class="h2">Новые сценарии</h2></div><div class="grid-3">' + ''.join(f'<a class="card" href="{name}.dc.html"><h3 class="h3">{label}</h3></a>' for name,label in [('Apply','Анкета волонтёра'),('Onboarding','Знакомство с фондом и тест'),('ApplicationStatus','Личный кабинет кандидата и встреча с координатором'),('FirstShift','Первый выход'),('Needs','Возможности и подготовка'),('Planning','Расписание'),('Candidates','Кандидаты и анкеты'),('Interviews','Собеседования и доступность'),('Roles','Роли волонтёров'),('VolunteerRecord','Договорённости с волонтёром'),('Participants','Участники фонда'),('Groups','Группы и состав')]) + '</div></section>'
t = t.replace('</div></div>\n</x-dc>', extension+'\n</div></div>\n</x-dc>')
t = t.replace('class Component extends DCLogic', (SRC/'demo-store.js').read_text() + '\nclass Component extends DCLogic')
t = t.replace('    return {\n      steps:', '    return {\n      demoReset:!!s.demoReset, resetDemo:()=>{try{localStorage.removeItem("opora-interviews-v1");}catch(_){}["roles","role-directory","people","groups","reflection","schedule-v2","schedule-responses-v2","candidate","onboarding","apply-draft"].forEach(k=>{try{sessionStorage.removeItem("opora-prototype-v1:"+k);}catch(_){}});this.setState({demoReset:true});},\n      steps:')
t = t.replace('<h2 class="h2">Новые сценарии</h2>', '<h2 class="h2">Новые сценарии</h2><button class="btn btn-ghost" onClick="{{resetDemo}}">Сбросить демо</button>')
t = t.replace('</div></div>\n</x-dc>', '<sc-if value="{{demoReset}}"><p class="hint" role="status">Демо-данные сброшены</p></sc-if></div></div>\n</x-dc>')
t=t.replace('"height":1670','"height":2450')
p.write_text(t)

# Extend reflection with voluntary questions, preserving every existing branch.
p = OUT/'Reflection.dc.html';t=p.read_text().replace('class Component extends DCLogic',(SRC/'demo-store.js').read_text()+'\nclass Component extends DCLogic')
t=t.replace("pause: false };", "pause: false, unexpected: '', help: 'later', continuation: 'discuss' };")
fields='''<details class="card" style="margin-top:24px"><summary class="h3">После первого выхода</summary><div class="field" style="margin-top:24px"><label class="label" for="unexpected">Что оказалось неожиданным?</label><textarea class="textarea" id="unexpected" value="{{unexpected}}" onChange="{{changeUnexpected}}"></textarea></div><div class="grid-2" style="margin-top:24px"><div class="field"><label class="label" for="help-choice">Нужна ли помощь?</label><select class="select" id="help-choice" value="{{helpChoice}}" onChange="{{changeHelp}}"><option value="later">Пока не знаю</option><option value="yes">Хочу поговорить</option><option value="no">Сейчас справляюсь</option></select></div><div class="field"><label class="label" for="continuation">Хочешь продолжать?</label><select class="select" id="continuation" value="{{continuation}}" onChange="{{changeContinuation}}"><option value="discuss">Сначала обсудить</option><option value="yes">Да, в этой группе</option><option value="other">Хочу другую роль</option><option value="pause">Нужна пауза</option><option value="finish">Не планирую продолжать</option></select></div></div></details>'''
t=t.replace('<textarea class="textarea"', '<textarea class="textarea"',1)
t=t.replace('<div class="row wrap" style="margin-top:20px">', '<div class="row wrap" style="margin-top:20px">',1)
anchor='<button type="button" class="btn btn-primary'
pos=t.find(anchor,t.find('Расскажи своими словами'))
if pos<0:raise ValueError('Reflection submit anchor missing')
# Insert before its action container, keeping valid markup.
pos=t.rfind('<div',0,pos)
t=t[:pos]+fields+'\n'+t[pos:]
t=t.replace('text: s.text,', "unexpected: s.unexpected, changeUnexpected: (e) => this.setState({unexpected:e.target.value}), helpChoice:s.help, changeHelp:(e)=>this.setState({help:e.target.value}), continuation:s.continuation, changeContinuation:(e)=>this.setState({continuation:e.target.value}), text: s.text,")
t=t.replace('<h2 class="h2" id="und-title">Мы поняли так</h2>', '<h2 class="h2" id="und-title">Мы поняли так</h2>')
t=t.replace('und: (undBy[flow] || undBy.done).map', "und: (undBy[flow] || undBy.done).concat(s.unexpected ? [{label:'Неожиданное',value:s.unexpected}] : []).concat([{label:'Поддержка',value:({yes:'Хочу поговорить',no:'Сейчас справляюсь',later:'Пока не знаю'})[s.help]},{label:'Продолжение',value:({discuss:'Сначала обсудить',yes:'Да, в этой группе',other:'Хочу другую роль',pause:'Нужна пауза',finish:'Не планирую продолжать'})[s.continuation]}]).map")
t = t.replace("send: () => this.setState({ sent: true, confirmed: false, voice: 'idle' }),", "send: () => {demoWrite('reflection',{unexpected:s.unexpected,help:s.help,continuation:s.continuation,text:s.text});this.setState({sent:true,confirmed:false,voice:'idle'});},")
match = re.search(r'(<script type="text/x-dc"[^>]*>)(.*?)(</script>)', t, re.S)
markup, reflection_logic = enhance_controls(t[:match.start()], match[2], SRC)
icons = dict(re.findall(r'^([\w-]+):\s*(<svg[^\n]+)', (ROOT/'materials/04-дизайн/прототип-до-фактуры/kit/icons.html').read_text(), re.M))
for token,key in [('CALENDAR','calendar'),('RIGHT','chevron-right'),('LEFT','chevron-left'),('X','x')]:
    markup = markup.replace('ICON_'+token, icons[key])
markup = markup.replace('</style>', css+'\n</style>')
p.write_text(markup + match[1] + (SRC/'date-utils.js').read_text() + reflection_logic + match[3] + t[match.end():])

c=json.loads((BASE/'canvas.json').read_text())
c['title']='Платформа волонтёров — прототип с дополнениями'
for i,(name,(title,role,height)) in enumerate(SCREENS.items()):
    c['boards'][f'{name}.dc.html']={'x':(i%5)*1520,'y':13300+(i//5)*2300,'w':1440,'h':height,'title':title,'expand':'fill','is_interactive':True}
    if f'{name}.dc.html' not in c['order']:c['order'].append(f'{name}.dc.html')
c['boards']['Main.dc.html']['h']=2450
c['boards']['Reflection.dc.html']['h']=1400
c['notes']['extensions']={'x':0,'y':13000,'text':'Новые сценарии: участие, планирование, люди и группы','kind':'title1','maxW':7520}
(OUT/'canvas.json').write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n')
(OUT/'opora.html').write_text('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=Main.dc.html"><title>Опора</title></head><body><a href="Main.dc.html">Открыть прототип</a></body></html>')
# Shared dropdown behaviour is outside the reactive template.
(OUT/'coordinator-nav.js').write_text((SRC/'coordinator-nav.js').read_text())
for page in OUT.glob('*.dc.html'):
    text=page.read_text()
    if 'class="work-app"' in text or 'class="dm work-app"' in text:
        page.write_text(text.replace('</body>', '<script src="./coordinator-nav.js"></script></body>'))
print('Built',len(c['boards']),'artboards')

# Keep historical URLs as routes into the single Opora interface.
(OUT/'legacy-redirect.js').write_text((SRC/'legacy-redirect.js').read_text())
(OUT/'index.html').write_text('<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Опора — платформа волонтёров</title></head><body><p><a href="Main.dc.html">Открыть прототип «Опора»</a></p><script src="legacy-redirect.js"></script></body></html>')
