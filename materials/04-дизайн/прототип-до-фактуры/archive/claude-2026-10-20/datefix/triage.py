import re, sys, glob, os
D = sys.argv[1]
files = sys.argv[2:] or sorted(glob.glob(os.path.join(D, '*.dc.html')))
MON = r'(январ|феврал|март|апрел|мая|июн|июл|август|сентябр|октябр|ноябр|декабр|янв|фев|мар|апр|авг|сен|окт|ноя|дек)'
WD = r'\b(пн|вт|ср|чт|пт|сб|вс|понедельник|вторник|сред[аеуы]|четверг|пятниц|суббот|воскресень)'
KW = r'(сегодня|завтра|вчера|через \d|дн[еяй]|недел|day|date|Date|cal|heat|week|month|deadline|срок|2025|2026)'
pat = re.compile('|'.join([MON, WD, KW]), re.I)
for f in files:
    lines = open(f, encoding='utf-8').read().split('\n')
    se = next(i for i,l in enumerate(lines) if '</style>' in l)
    out = []
    for i,l in enumerate(lines[se+1:], start=se+2):
        if pat.search(l) and re.search(r'\d', l):
            out.append(f'{i}: {l.strip()[:400]}')
    print(f'===== {os.path.basename(f)} ({len(out)})')
    print('\n'.join(out))
