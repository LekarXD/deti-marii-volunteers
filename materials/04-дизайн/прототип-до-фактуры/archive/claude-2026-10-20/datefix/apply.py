import re, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from spec import E
D = sys.argv[1]
write = '--write' in sys.argv

def pat(old):
    p = re.escape(old)
    if old[0].isdigit(): p = r'(?<!\d)' + p
    if old[-1].isdigit(): p = p + r'(?!\d)'
    elif old[-1].isalpha(): p = p + r'(?![а-яёА-ЯЁa-zA-Z])'
    return re.compile(p)

total = 0; errors = 0
for name, edits in E.items():
    path = os.path.join(D, name + '.dc.html')
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    lines = text.split('\n')
    n = 0
    for e in edits:
        ln, old, new = e[0], e[1], e[2]
        cnt = e[3] if len(e) > 3 else 1
        rx = pat(old)
        line = lines[ln - 1]
        found = len(rx.findall(line))
        if found != cnt:
            print(f'ERROR {name}:{ln}: expected {cnt} of {old!r}, found {found}\n   line: {line.strip()[:200]}')
            errors += 1
            continue
        lines[ln - 1] = rx.sub(lambda m: new, line)
        n += cnt
    total += n
    print(f'{name}: {n} replacements in {len(edits)} edits')
    if write and not errors:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
print('TOTAL', total, 'ERRORS', errors, 'WRITTEN' if write and not errors else 'DRY-RUN')
