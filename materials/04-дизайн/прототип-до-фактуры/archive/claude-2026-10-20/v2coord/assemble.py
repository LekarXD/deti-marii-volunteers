"""Assemble a v2 .dc.html from parts: <name>.css, <name>.body.html, <name>.js; kit helmet verbatim + css appended."""
import sys, os, json
S = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(S, '..', 'dm-canvas')
KIT = open(os.path.join(ROOT, 'kit', 'helmet.html'), encoding='utf-8').read().rstrip('\n')
TITLES = {'CoordHome': 'Обзор фонда', 'Pipeline': 'Заявки', 'Volunteers': 'Волонтёры', 'Shifts': 'Смены'}
def build(name, height):
    css = open(os.path.join(S, name + '.css'), encoding='utf-8').read().strip('\n')
    body = open(os.path.join(S, name + '.body.html'), encoding='utf-8').read().strip('\n')
    js = open(os.path.join(S, name + '.js'), encoding='utf-8').read().strip('\n')
    assert KIT.count('</style>') == 1
    helmet = KIT.replace('</style>', css + '\n</style>')
    props = json.dumps({"$preview": {"width": 1440, "height": int(height)}}, separators=(',', ':'))
    out = ('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           '<title>' + TITLES[name] + ' — Опора</title>\n<script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n'
           + helmet + '\n' + body + '\n</x-dc>\n'
           "<script type=\"text/x-dc\" data-dc-script data-props='" + props + "'>\n" + js + '\n</script>\n</body>\n</html>\n')
    dest = os.path.join(ROOT, 'project', name + '.dc.html')
    open(dest, 'w', encoding='utf-8').write(out)
    print(dest, len(out))
build(sys.argv[1], sys.argv[2])
