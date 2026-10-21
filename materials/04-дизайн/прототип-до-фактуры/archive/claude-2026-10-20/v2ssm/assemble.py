"""Assemble a .dc.html artboard: kit helmet verbatim + own CSS, volunteer header, body, logic."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = Path('/private/tmp/claude-501/-Users-iliapetri--claude-spares-spare-GxUBpt/91fc3645-2cae-45de-9eeb-32a080bb81c1/scratchpad/dm-canvas')

name, title, height = sys.argv[1], sys.argv[2], int(sys.argv[3])
mentor_current = len(sys.argv) > 4 and sys.argv[4] == 'mentor'

kit = (ROOT / 'kit' / 'helmet.html').read_text(encoding='utf-8').rstrip('\n')
tail = '</style>\n</helmet>'
assert kit.endswith(tail), 'kit tail changed'
css = (HERE / f'{name}.css').read_text(encoding='utf-8').strip('\n')
helmet = kit[: -len(tail)] + '\n' + css + '\n' + tail

header = (HERE / 'header.html').read_text(encoding='utf-8').rstrip('\n')
if mentor_current:
    header = header.replace('<a class="iconbtn" href="Mentor.dc.html" aria-label="ИИ-наставник">',
                            '<a class="iconbtn" href="Mentor.dc.html" aria-label="ИИ-наставник" aria-current="page">')
body = (HERE / f'{name}.body.html').read_text(encoding='utf-8').strip('\n')
js = (HERE / f'{name}.js').read_text(encoding='utf-8').strip('\n')

doc = (
    '<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    f'<title>{title}</title>\n<script src="./support.js"></script>\n</head>\n<body>\n<x-dc>\n'
    f'{helmet}\n<div class="dm"><div class="shell">\n\n{header}\n\n{body}\n\n</div></div>\n</x-dc>\n'
    '<script type="text/x-dc" data-dc-script data-props=\'{"$preview":{"width":1440,"height":' + str(height) + '}}\'>\n'
    f'{js}\n</script>\n</body>\n</html>\n'
)
(ROOT / 'project' / f'{name}.dc.html').write_text(doc, encoding='utf-8')
print('wrote', name, len(doc))
