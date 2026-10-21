import re, sys, os, glob, json, html, subprocess, datetime as DT
D = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
YEAR = 2026
WD = [('понедельник', 'пн'), ('вторник', 'вт'), ('сред', 'ср'), ('четверг', 'чт'), ('пятниц', 'пт'), ('суббот', 'сб'), ('воскресень', 'вс')]
def wd_index(w):
    w = w.lower()
    for i, (full, ab) in enumerate(WD):
        if w == ab or w.startswith(full):
            return i
    raise ValueError(w)
MON = [('янв', 1), ('фев', 2), ('мар', 3), ('апр', 4), ('ма', 5), ('июн', 6), ('июл', 7), ('авг', 8), ('сен', 9), ('окт', 10), ('ноя', 11), ('дек', 12)]
def mon_index(m):
    m = m.lower()
    for p, i in MON:
        if m.startswith(p): return i
    raise ValueError(m)
WD_RX = r'(понедельник[а-яё]*|вторник[а-яё]*|сред[аеуы]|четверг[а-яё]*|пятниц[а-яё]*|суббот[а-яё]*|воскресень[а-яё]*|пн|вт|ср|чт|пт|сб|вс)'
MON_RX = r'(январ[а-яё]*|феврал[а-яё]*|марта?|апрел[а-яё]*|мая|май|июн[а-яё]*|июл[а-яё]*|август[а-яё]*|сентябр[а-яё]*|октябр[а-яё]*|ноябр[а-яё]*|декабр[а-яё]*|янв|фев|мар|апр|авг|сент|сен|окт|ноя|дек)\.?'
NB = r'(?<![а-яёА-ЯЁa-zA-Z])'; NA = r'(?![а-яёА-ЯЁa-zA-Z])'
P1 = re.compile(NB + WD_RX + NA + r'\.?,?\s+(\d{1,2})\s+' + MON_RX + NA + r'(?:\s+(\d{4}))?', re.I)
P2 = re.compile(r'(?<!\d)(\d{1,2})\s+' + MON_RX + NA + r'(?:\s+(\d{4}))?,?\s*\(?' + NB + WD_RX + NA, re.I)
# structural JS pairs
P_SHIFTS = re.compile(r"d:\s*'(пн|вт|ср|чт|пт|сб|вс)',\s*n:\s*'(\d{1,2}) ([а-яё]+)'")
P_SCHED = re.compile(r"key:\s*'([a-z]{3})-(\d{1,2})',[^}]*?wd:\s*'(пн|вт|ср|чт|пт|сб|вс)',\s*dn:\s*'(\d{1,2})'")
MKEY = {'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

def check(day, mon, wd, year, where, bad, ok):
    try:
        d = DT.date(year, mon, day)
    except ValueError:
        bad.append(f'{where}: invalid date {day}.{mon}.{year}'); return
    if d.weekday() != wd:
        bad.append(f'{where}: {day}.{mon}.{year} is {WD[d.weekday()][1]}, text says {WD[wd][1]}')
    else:
        ok.append(where)

def scan(text, where, bad, ok, seen):
    for m in P1.finditer(text):
        wd, day, mon, yr = m.group(1), int(m.group(2)), m.group(3), m.group(4)
        check(day, mon_index(mon), wd_index(wd), int(yr) if yr else YEAR, f'{where} «{m.group(0)}»', bad, ok); seen.append(m.group(0))
    for m in P2.finditer(text):
        day, mon, yr, wd = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        check(day, mon_index(mon), wd_index(wd), int(yr) if yr else YEAR, f'{where} «{m.group(0)}»', bad, ok); seen.append(m.group(0))

grand_bad = []; grand_ok = 0
for f in sorted(glob.glob(os.path.join(D, '*.dc.html'))):
    name = os.path.basename(f)
    raw = open(f, encoding='utf-8').read()
    body = raw[raw.index('</style>'):]
    bad, ok, seen = [], [], []
    # A. static: per line, tags -> space, entities unescaped
    for i, line in enumerate(body.split('\n')):
        ln = raw[:raw.index('</style>')].count('\n') + 1 + i
        t = html.unescape(re.sub(r'<[^>]+>', ' ', line))
        scan(t, f'{name}:{ln}', bad, ok, seen)
        for m in P_SHIFTS.finditer(line):
            check(int(m.group(2)), mon_index(m.group(3)), wd_index(m.group(1)), YEAR, f'{name}:{ln} {{d,n}} «{m.group(0)}»', bad, ok)
        for m in P_SCHED.finditer(line):
            mo, day, wd, dn = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
            if day != dn: bad.append(f'{name}:{ln} key day {day} != dn {dn}')
            check(day, MKEY[mo], wd_index(wd), YEAR, f'{name}:{ln} {{key,wd,dn}} «{mo}-{day} {wd}»', bad, ok)
    # B. runtime strings from renderVals over modes/interactions
    r = subprocess.run(['node', os.path.join(HERE, 'harness.js'), f], capture_output=True, text=True)
    if r.returncode != 0:
        bad.append(f'{name}: harness failed: {r.stderr[:300]}')
        rt = []
    else:
        rt = json.loads(r.stdout)['strings']
    rt_ok_before = len(ok)
    for s in rt:
        scan(s, f'{name}[runtime]', bad, ok, seen)
    print(f'{name:28s} static+runtime weekday-date pairs checked: {len(ok):4d} (runtime {len(ok)-rt_ok_before}), mismatches: {len(bad)}')
    for b in bad: print('   MISMATCH', b)
    grand_bad += bad; grand_ok += len(ok)

# C. calendar grids
print('\nCalendar grids:')
sch = open(os.path.join(D, 'Schedule.dc.html'), encoding='utf-8').read()
for mo, mi in (('oct', 10), ('nov', 11)):
    m = re.search(mo + r":\s*\{ label: '[^']*(\d{4})', lead: (\d+), days: (\d+)", sch)
    yr, lead, days = int(m.group(1)), int(m.group(2)), int(m.group(3))
    first = DT.date(yr, mi, 1)
    exp_days = ((DT.date(yr + (mi == 12), mi % 12 + 1, 1)) - first).days
    okk = first.weekday() == lead and days == exp_days
    print(f'  Schedule {mo} {yr}: lead={lead} (1st is {WD[first.weekday()][1]}, expected lead {first.weekday()}), days={days}/{exp_days} -> {"OK" if okk else "FAIL"}')
    if not okk: grand_bad.append(f'Schedule grid {mo}')
hrs = open(os.path.join(D, 'Hours.dc.html'), encoding='utf-8').read()
d0 = int(re.search(r'let d = (\d+);', hrs).group(1))
start = DT.date(YEAR, 4, d0)
today_idx = eval(re.search(r'const today = ([\d *+]+);', hrs).group(1))
draft = re.search(r"date: '(\d{4}-\d{2}-\d{2})'", hrs).group(1)
okh = start.weekday() == 0 and start + DT.timedelta(today_idx) == DT.date(2026, 10, 20) and draft == '2026-10-20'
print(f'  Hours heatmap: starts {start} ({WD[start.weekday()][1]}), today cell = {start + DT.timedelta(today_idx)} ({WD[(start + DT.timedelta(today_idx)).weekday()][1]}), draft default {draft} -> {"OK" if okh else "FAIL"}')
if not okh: grand_bad.append('Hours heatmap')
print(f'\nTOTAL weekday-date pairs checked: {grand_ok}, mismatches: {len(grand_bad)}')
