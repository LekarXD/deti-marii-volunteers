import re, sys, os, glob
O, N = sys.argv[1], sys.argv[2]
MON_RX = r'(январ[а-яё]*|феврал[а-яё]*|марта?|апрел[а-яё]*|мая|июн[а-яё]*|июл[а-яё]*|август[а-яё]*|сентябр[а-яё]*|октябр[а-яё]*|ноябр[а-яё]*|декабр[а-яё]*|янв|фев|мар|апр|авг|сент|сен|окт|ноя|дек)'
TOK = re.compile(r'(?<!\d)(\d{1,2})(?:\s*[–-]\s*\d{1,2})?\s+(?:по\s+\d{1,2}\s+)?' + MON_RX + r'(?![а-яё])|(?<!\d)\d{1,2}-го\b|\d{4}-\d{2}-\d{2}', re.I)
changed_tokens = 0; kept = []
for f in sorted(glob.glob(os.path.join(N, '*.dc.html'))):
    b = os.path.basename(f)
    ol = open(os.path.join(O, b), encoding='utf-8').read().split('\n')
    nl = open(f, encoding='utf-8').read().split('\n')
    assert len(ol) == len(nl), b
    nchg = 0
    for i, (a, c) in enumerate(zip(ol, nl), 1):
        ta = [m.group(0) for m in TOK.finditer(a)]
        tc = [m.group(0) for m in TOK.finditer(c)]
        if a != c:
            diff = sum(1 for x, y in zip(ta, tc) if x != y)
            nchg += diff
            for x, y in zip(ta, tc):
                if x == y: kept.append(f'{b}:{i} (line changed) «{x}»  …{c.strip()[:120]}')
        else:
            for x in ta:
                ctx = c[max(0, c.find(x) - 60): c.find(x) + len(x) + 40].strip()
                kept.append(f'{b}:{i} «{x}»  …{ctx}')
    changed_tokens += nchg
    print(f'{b:28s} date tokens changed: {nchg}')
print('TOTAL date tokens changed:', changed_tokens)
print('\nKEPT (unchanged) date tokens:')
print('\n'.join(kept))
