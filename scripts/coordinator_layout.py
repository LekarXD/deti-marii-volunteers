"""Shared top navigation for coordinator screens, using the original Opora kit."""
import re


def work_frame(src, name, body):
    icons = dict(re.findall(r'^([\w-]+):\s*(<svg[^\n]+)', (src.parent/'materials/04-дизайн/прототип-до-фактуры/kit/icons.html').read_text(), re.M))
    current = {'VolunteerRecord':'Volunteers','Shifts':'Planning','Pipeline':'Candidates'}.get(name,name)
    groups = [
        ('Волонтёры','users', [('Candidates','Кандидаты'),('Interviews','Собеседования'),('Volunteers','Волонтёры'),('Reserve','Проверка контактов')]),
        ('Занятия','calendar',[('Planning','Расписание'),('Needs','Возможности'),('Roles','Роли')]),
        ('Подопечные','heart',[('Participants','Участники'),('Groups','Группы')]),
        ('Ещё','settings',[('Builder','Обучение'),('Knowledge','База знаний'),('Signals','Сигналы'),('Reports','Отчёты'),('Admin','Настройки'),('Main','Карта прототипа')])]
    def link(screen, title, icon=''):
        active = screen == current
        return f'<a class="work-link{" is-current" if active else ""}" href="{screen}.dc.html"'+(' aria-current="page"' if active else '')+f'>{icons.get(icon, "")}{title}</a>'
    nav = link('CoordHome','Обзор','chart')
    mobile=link('CoordHome','Обзор')
    group_label='Фонд'
    page_label='Разделы'
    for title,icon,items in groups:
        active = any(n==current for n,_ in items)
        if active:
            group_label=title
            page_label=next(t for n,t in items if n==current)
        links=''.join(link(n,t) for n,t in items)
        nav+='<details class="work-dropdown'+(' is-current' if active else '')+'" name="coord-navigation"><summary>'+icons[icon]+'<span>'+title+'</span>'+icons['chevron-down']+'</summary><div class="work-dropdown-panel" aria-label="'+title+'">'+links+'</div></details>'
        mobile+='<section class="work-nav-group"><h2>'+title+'</h2>'+links+'</section>'
    brand='<a class="brand" href="CoordHome.dc.html"><span class="mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span><b>Опора</b><small>команда фонда</small></span></a>'
    header='<header class="work-header">'+brand+'<div class="work-header-end"><a class="btn btn-ghost btn-sm work-view" href="ApplicationStatus.dc.html">Вид волонтёра</a><details class="work-mobile-menu" name="coord-navigation"><summary>'+page_label+' '+icons['chevron-down']+'</summary><nav class="work-mobile-links" aria-label="Разделы фонда">'+mobile+'</nav></details></div><nav class="work-topnav" aria-label="Разделы фонда">'+nav+'</nav></header>'
    return '<div class="dm work-app">'+header+'<main class="work-content"><p class="work-context">'+group_label+'</p>'+body+'</main></div>'


def wrap_original(doc, src, name):
    start=doc.find('<div class="dm"><div class="shell">')
    end=doc.rfind('</div></div>',0,doc.index('</x-dc>'))
    if start<0 or end<0:
        raise ValueError('Cannot locate coordinator frame: '+name)
    inner=doc[start+len('<div class="dm"><div class="shell">'):end]
    inner=re.sub(r'<header class="top".*?</header>','',inner,count=1,flags=re.S)
    return doc[:start]+work_frame(src,name,inner)+doc[end+len('</div></div>'):]
