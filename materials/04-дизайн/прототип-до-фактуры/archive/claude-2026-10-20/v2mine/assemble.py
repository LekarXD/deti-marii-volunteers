import sys, os
ROOT = '/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas'
PARTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'parts')
NAV = [
 ('Home.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/></svg>Главная'),
 ('Catalog.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>Возможности'),
 ('Schedule.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>Мои смены'),
 ('Academy.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 9 12 4l10 5-10 5z"/><path d="M6 11v5c3 2.5 9 2.5 12 0v-5M22 9v6"/></svg>Академия'),
 ('Messages.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12z"/></svg>Сообщения<span class="count">3</span>'),
 ('Hours.dc.html','<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="9" r="6"/><path d="M8.5 14 7 21l5-2.5 5 2.5-1.5-7"/></svg>Мой путь'),
]
def header(active):
    links = []
    for href, inner in NAV:
        if href == active:
            links.append('    <a class="is-active" aria-current="page" href="%s">%s</a>' % (href, inner))
        else:
            links.append('    <a href="%s">%s</a>' % (href, inner))
    return '''<header class="top">
  <a class="brand" href="Main.dc.html"><span class="mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span><b>Опора</b><small>волонтёры «Дети Марии»</small></span></a>
  <nav class="nav" aria-label="Разделы">
''' + '\n'.join(links) + '''
  </nav>
  <div class="top-end">
    <a class="role" href="CoordHome.dc.html"><svg class="ic ic-sm" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9a8 8 0 0 1 14-3l2 2M20 4v4h-4M20 15a8 8 0 0 1-14 3l-2-2M4 20v-4h4"/></svg>Вид координатора</a>
    <div class="pillbox">
      <a class="iconbtn" href="Mentor.dc.html" aria-label="ИИ-наставник"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c.6 3.8 2.2 5.4 6 6-3.8.6-5.4 2.2-6 6-.6-3.8-2.2-5.4-6-6 3.8-.6 5.4-2.2 6-6z"/><path d="M19 15c.3 1.6 1 2.3 2.5 2.5-1.5.3-2.2 1-2.5 2.5-.3-1.5-1-2.2-2.5-2.5 1.5-.2 2.2-.9 2.5-2.5z"/></svg></a>
      <button class="iconbtn" type="button" aria-label="Уведомления, 2 новых"><svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 21a2 2 0 0 0 4 0"/></svg><span class="pip"></span></button>
      <a href="Profile.dc.html" class="avatar av-o" aria-label="Профиль: Анна Соколова">АС</a>
    </div>
  </div>
</header>
'''
def build(name, title, active, height):
    kit = open(os.path.join(ROOT, 'kit', 'helmet.html'), encoding='utf-8').read().rstrip('\n')
    css = open(os.path.join(PARTS, name + '.css'), encoding='utf-8').read().strip('\n')
    body = open(os.path.join(PARTS, name + '.body.html'), encoding='utf-8').read().strip('\n')
    js = open(os.path.join(PARTS, name + '.js'), encoding='utf-8').read().strip('\n')
    i = kit.rindex('</style>')
    helmet = kit[:i] + css + '\n' + kit[i:]
    out = ('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           '<title>' + title + '</title>\n<script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n'
           + helmet + '\n<div class="dm"><div class="shell">\n\n' + header(active) + '\n' + body + '\n\n</div></div>\n</x-dc>\n'
           '<script type="text/x-dc" data-dc-script data-props=\'{"$preview":{"width":1440,"height":' + str(height) + '}}\'>\n'
           + js + '\n</script>\n</body>\n</html>\n')
    path = os.path.join(ROOT, 'project', name + '.dc.html')
    open(path, 'w', encoding='utf-8').write(out)
    print(path, len(out))
CFG = {
 'Catalog': ('Возможности — Опора', 'Catalog.dc.html'),
 'Opportunity': ('Ассистент в мастерской живописи — Опора', 'Catalog.dc.html'),
 'Schedule': ('Мои смены — Опора', 'Schedule.dc.html'),
 'Reflection': ('Как прошло занятие — Опора', 'Schedule.dc.html'),
}
if __name__ == '__main__':
    name = sys.argv[1]; h = int(sys.argv[2])
    t, a = CFG[name]
    build(name, t, a, h)
