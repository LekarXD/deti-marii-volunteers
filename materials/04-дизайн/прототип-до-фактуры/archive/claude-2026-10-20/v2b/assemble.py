import sys
from pathlib import Path
ROOT = Path(sys.argv[1])
kit = (ROOT / 'kit' / 'helmet.html').read_text(encoding='utf-8')
prefix = kit.split('</style>')[0]
for name in sys.argv[2:]:
    p = ROOT / 'project' / name
    src = p.read_text(encoding='utf-8')
    if '@@KIT@@' not in src:
        print(name, 'no marker'); continue
    src = src.replace('@@KIT@@', prefix, 1)
    p.write_text(src, encoding='utf-8')
    print(name, 'assembled')
