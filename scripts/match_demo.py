"""Прототип подбора волонтёров на смены. Без ИИ и без персональных данных: только признаки.

Две стороны одного расчёта:
1. Координатор открывает смену → видит, кого позвать, почему, и видел ли человек эту смену в своей подборке.
2. Волонтёр открывает ленту → наверху смены, которые ему подходят и которые срочно нужно закрыть.

Смены — как их заполняет координатор в планировании (Planning.js): серия, роль, дата, время, место,
сколько человек нужно, сколько уже подтвердили. Волонтёры — scripts/generate_synthetic_volunteers.py.

    python3 scripts/match_demo.py
"""
import json
import pathlib
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'materials/05-продукт/данные/synthetic-volunteers.json').read_text())
VOL, SERIES = DATA['volunteers'], DATA['series']
ROLES = {r['id']: r for r in json.loads((ROOT / 'prototype-src/roles.json').read_text())}
TODAY = date.fromisoformat(DATA['generated_for'])
WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']
# Роли, которых нет в справочнике, но которые есть в планировании
ROLE_EXTRA = {'escort': {'title': 'Сопровождающий на выезде', 'certificate': True, 'format': 'Очно'},
              'event': {'title': 'Помощь на мероприятии', 'certificate': False, 'format': 'Очно'}}

# Ближайшие смены из планирования координатора: need — сколько нужно, confirmed — сколько уже подтвердили.
SHIFTS = [
    dict(id='art@2026-10-24', series='art', date='2026-10-24', time='14:00–18:00', need=3, confirmed=['anna']),
    dict(id='lab@2026-10-29', series='lab', date='2026-10-29', time='13:30–16:00', need=1, confirmed=[]),
    dict(id='pack@2026-10-23', series='pack', date='2026-10-23', time='15:00–18:00', need=2, confirmed=['polina']),
    dict(id='study@2026-10-26', series='study', date='2026-10-26', time='18:00–20:00', need=2, confirmed=['artem']),
    dict(id='life@2026-10-28', series='life', date='2026-10-28', time='12:00–15:00', need=2, confirmed=[]),
    dict(id='event@2026-10-26', series='event', date='2026-10-26', time='18:00–21:00', need=2, confirmed=[], title='Открытие выставки «Невидимый труд»'),
    dict(id='fair@2026-12-12', series='fair', date='2026-12-12', time='12:00–20:00', need=4, confirmed=[], title='Шерстяной Базар, зимний'),
]

# Вес признаков в оценке «насколько подходит». Настраиваются; позже — по решениям координатора.
WEIGHTS = {'interest': 0.30, 'group': 0.25, 'time': 0.20, 'reliability': 0.15, 'distance': 0.10}
READY = {'regular', 'occasional', 'first_shift_done', 'meeting_done', 'reserve'}
# Какие направления из анкеты подходят роли
ROLE_DIRS = {'assistant': {'Помощь на занятиях', 'Творчество'}, 'teacher': {'Творчество'}, 'tutor': {'Обучение'},
             'life': {'Помощь на занятиях', 'Творчество'}, 'packing': {'Творчество', 'Ярмарки'}, 'fair': {'Ярмарки', 'Мероприятия'},
             'event': {'Мероприятия', 'Фото, видео, соцсети'}, 'escort': {'Мероприятия', 'Помощь на занятиях'}}


def role(sid):
    r = SERIES[sid]['role']
    return ROLES.get(r) or ROLE_EXTRA[r]


def times(n):
    return 'раза' if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else 'раз'


def blocked(v, sh):
    """Жёсткие фильтры: кого точно нельзя звать. Возвращает причину или None."""
    s, a, p = SERIES[sh['series']], v['anketa'], v['profile']
    if v['id'] in sh['confirmed']:
        return 'уже записан'
    if v['stage'] not in READY:
        return 'ещё не прошёл знакомство и встречу'
    if v['reserve_status'] and v['reserve_status'] != 'ready':
        return 'в резерве, актуальность не подтверждена'
    if p['paused_until'] and sh['date'] < p['paused_until']:
        return 'на паузе'
    if role(sh['series']).get('certificate') and a['record'] != 'Справка уже есть':
        return 'нужна справка о несудимости'
    if v['age'] < 18 and s['ages'] and s['ages'] != 'Взрослые':
        return 'младше 18 — не на занятия с детьми'
    if a['area'] == 'Другой город' and s['zone'] != 'Другой город':
        return 'живёт в другом городе'
    day = WEEK[date.fromisoformat(sh['date']).weekday()]
    if p['availability'] and day not in p['availability']:
        return f'в {day} не может (по профилю)'
    return None


def fit(v, sh):
    """Оценка 0…1 и причины, которые увидит координатор."""
    s, a, p, st = SERIES[sh['series']], v['anketa'], v['profile'], v['stats']
    why = []
    skills = set(a['skills']) & set(s['skills'])
    interest = min(1.0, 0.5 * len(skills) + (0.5 if ROLE_DIRS[s['role']] & set(a['directions']) else 0))
    if skills:
        why.append('умеет: ' + ', '.join(sorted(skills)))
    n = st['series_attended'].get(sh['series'], 0)
    before = st.get('series_attended_before', {}).get(sh['series'], 0)
    group = 1.0 if n >= 3 else 0.7 if n else 0.5 if before else 0.0
    if n:
        why.append(f'был на «{s["title"]}» {n} {times(n)} за год')
    elif before:
        why.append(f'ходил на «{s["title"]}» раньше')
    day = WEEK[date.fromisoformat(sh['date']).weekday()]
    if p['availability']:
        tm = 1.0 if s['part'] in p['availability'].get(day, []) else 0.7
        if tm == 1.0:
            why.append(f'свободен: {day}, {s["part"]}')
    else:
        tm = 0.5
        why.append('время в профиле не указано')
    rel = (st['attended_12m'] + 3) / (st['confirmed_12m'] + 4)   # у новичка без истории — осторожные 0,75
    if st['confirmed_12m'] >= 5 and st['attended_12m'] / st['confirmed_12m'] >= 0.9:
        why.append(f'приходит, когда обещал ({st["attended_12m"]} из {st["confirmed_12m"]})')
    if st['late_cancel_12m'] >= 3:
        k = st['late_cancel_12m']
        why.append(f'{k} {"отмены" if k % 10 in (2, 3, 4) and k % 100 not in (12, 13, 14) else "отмен"} в последний момент')
    dist = 1.0 if a['area'] == s['zone'] else 0.8 if 'Москв' in a['area'] + s['zone'] else 0.4
    if v['stage'] == 'first_shift_done':
        why.append('новичок: позвать вместе с наставником')
    if v['reserve_status'] == 'ready':
        why.append('из резерва, готов вернуться')
    total = (WEIGHTS['interest'] * interest + WEIGHTS['group'] * group + WEIGHTS['time'] * tm
             + WEIGHTS['reliability'] * rel + WEIGHTS['distance'] * dist)
    return round(total, 2), why


def urgency(sh):
    """Насколько срочно закрыть смену: сколько мест пусто и сколько дней осталось."""
    gap = max(0, sh['need'] - len(sh['confirmed'])) / max(1, sh['need'])
    days = (date.fromisoformat(sh['date']) - TODAY).days
    soon = 1.0 if days <= 7 else 0.7 if days <= 14 else 0.4 if days <= 30 else 0.2
    return round(gap * soon, 2), days


def coordinator_view(sh):
    ok, out = [], {}
    for v in VOL:
        r = blocked(v, sh)
        if r:
            out.setdefault(r, []).append(v['name'].split()[0])
        else:
            ok.append((v, *fit(v, sh)))
    ok.sort(key=lambda x: -x[1])
    s = SERIES[sh['series']]
    u, days = urgency(sh)
    left = sh['need'] - len(sh['confirmed'])
    print(f'\n### {sh.get("title", s["title"])}, {sh["date"]} {sh["time"]} — {role(sh["series"])["title"]}')
    print(f'    Нужно {sh["need"]}, записались {len(sh["confirmed"])}; до смены {days} дн.; подходят {len(ok)} из {len(VOL)}')
    if sum(1 for x in ok if x[1] >= 0.6) < left:
        print('    ⚠ Хорошо подходящих меньше, чем свободных мест: позвать резерв или открыть смену всем')
    for v, sc, why in ok[:max(3, left + 2)]:
        seen = 'видел в подборке' if v['activity']['feed_views_30d'] else 'подборку не открывал'
        bot = 'бот' if v['activity']['telegram_bot'] else 'без бота'
        print(f'    {sc:.2f} {v["name"]:20} [{seen}, {bot}] {"; ".join(why)}')
    for r, names in sorted(out.items(), key=lambda x: -len(x[1]))[:4]:
        print(f'    ✕ {r}: {", ".join(names)}')


def volunteer_feed(vid):
    v = next(x for x in VOL if x['id'] == vid)
    items = []
    for sh in SHIFTS:
        if blocked(v, sh):
            continue
        f, why = fit(v, sh)
        if f < 0.45:      # срочность не повод показывать то, что человеку совсем не подходит
            continue
        u, days = urgency(sh)
        score = 0.6 * f + 0.4 * u     # порядок в ленте: подходит + срочно нужно
        left = sh['need'] - len(sh['confirmed'])
        label = (f'Срочно: нужно ещё {left}' if u >= 0.6 else
                 'Вы здесь уже были' if v['stats']['series_attended'].get(sh['series']) else
                 'Вам подходит' if f >= 0.6 else '')
        items.append((score, sh, label))
    items.sort(key=lambda x: -x[0])
    print(f'\n### Лента: {v["name"]} ({v["segment_label"].split(":")[0]})')
    if not v['profile']['availability']:
        print('    Подсказка: «Отметьте, когда вам удобно, — покажем смены в эти дни»')
    for score, sh, label in items[:4]:
        s = SERIES[sh['series']]
        print(f'    {sh.get("title", s["title"]):34} {sh["date"]} {sh["time"]:12} {label}')


def main():
    print('=== Координатор: кого позвать ===')
    for sh in SHIFTS:
        coordinator_view(sh)
    print('\n=== Волонтёр: что показать наверху ленты ===')
    for vid in ['anna', 'maxim', 'nikolay', 'vera']:
        volunteer_feed(vid)


if __name__ == '__main__':
    main()
