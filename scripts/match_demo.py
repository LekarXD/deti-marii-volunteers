"""Прототип подбора волонтёров на мероприятие: жёсткие фильтры + взвешенная оценка + причины.

Работает на синтетических волонтёрах (scripts/generate_synthetic_volunteers.py) и нескольких
реальных мероприятиях из базы ВК. Без ИИ: каждое решение можно объяснить строкой «почему».

    python3 scripts/match_demo.py
"""
import json
import pathlib
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / 'materials/05-продукт/данные/synthetic-volunteers.json').read_text())
VOL, SERIES = DATA['volunteers'], DATA['series']
WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

# Мероприятия из каталога за год (посты ВК указаны). need — сколько нужно, roles — что делать.
EVENTS = [
    dict(id='bazar', title='Шерстяной Базар, зимний', series='fair', date='2026-12-12', slot='день', zone='Юг',
         need=4, skills=['Продажи', 'Соцсети'], certificate=False, physical=False, children=False, src='7507'),
    dict(id='art-sat', title='Арт-суббота, 24 октября', series='art-sat', date='2026-10-24', slot='день', zone='Московская область',
         need=3, skills=['Живопись и рисунок', 'Керамика'], certificate=False, physical=True, children=False, src='7495',
         note='В группе Павел на коляске — нужен хотя бы один, кто может помочь физически'),
    dict(id='art-lab', title='Арт-лаборатория, 27 октября', series='art-lab', date='2026-10-27', slot='день', zone='Центр Москвы',
         need=2, skills=['Живопись и рисунок', 'Керамика', 'Валяние'], certificate=True, physical=False, children=True, src='7348'),
    dict(id='sorochany', title='Зимняя неделя в Сорочанах', series='sorochany', date='2027-02-01', slot='неделя', zone='Московская область',
         need=5, skills=['Спорт и игры'], certificate=True, physical=True, children=True, src='7357'),
]

# Насколько далеко ехать: одна и та же зона — 1, соседние — 0.6, остальное — 0.3
NEAR = {('Центр Москвы', x): 0.8 for x in ['Север', 'Восток', 'Юг', 'Запад']}
WEIGHTS = {'skills': 0.30, 'group': 0.25, 'reliability': 0.20, 'time': 0.15, 'distance': 0.10}
READY = {'regular', 'occasional', 'first_shift_done', 'meeting_done', 'reserve'}


def distance(area, zone):
    if area == zone:
        return 1.0
    if zone == 'Московская область' and area in ('Московская область', 'Новая Москва'):
        return 0.9
    return NEAR.get((zone, area)) or NEAR.get((area, zone)) or 0.3


def times_word(n):
    return 'раза' if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else 'раз'


def check(v, e):
    """Жёсткие фильтры: если хоть один не пройден — человека не предлагаем, но пишем почему."""
    a, ab = v['anketa'], v['abilities']
    d = date.fromisoformat(e['date'])
    if v['stage'] not in READY:
        return 'ещё не прошёл знакомство и встречу'
    if v['reserve_status'] in ('unverified', 'awaiting_reply', 'paused', 'no_invites', 'unreachable'):
        return 'в резерве: ' + {'unverified': 'актуальность не проверена', 'awaiting_reply': 'ждём ответа', 'paused': 'на паузе',
                                'no_invites': 'не хочет приглашений', 'unreachable': 'не дозвонились'}[v['reserve_status']]
    if v['paused_until'] and e['date'] < v['paused_until']:
        return 'на паузе до ' + v['paused_until']
    if ab['online_only']:
        return 'помогает только онлайн'
    if e['certificate'] and a['record'] != 'Справка уже есть':
        return 'нет справки о несудимости'
    if e['children'] and ab['minor']:
        return 'младше 18 — не работает с детьми'
    av = v['availability']
    # На многодневный выезд день недели не важен: смотрим, ездил ли человек на такие выезды раньше
    if e['slot'] != 'неделя' and av and WEEK[d.weekday()] not in av:
        return 'в этот день недели не может'
    return None


def score(v, e):
    a, s, ab = v['anketa'], v['stats'], v['abilities']
    d = date.fromisoformat(e['date'])
    why = []
    sk = len(set(a['skills']) & set(e['skills'])) / max(1, len(e['skills']))
    sk = min(1.0, sk * 2)
    if sk:
        why.append('умеет: ' + ', '.join(sorted(set(a['skills']) & set(e['skills']))))
    group = SERIES[e['series']]['group']
    times = sum(1 for r in v['participation_12m'] if r['series'] == e['series'] and r['status'] == 'attended')
    gr = 1.0 if times >= 3 else 0.7 if times else (0.5 if group in s['groups_known'] else 0.0)
    if times:
        why.append(f'был на «{SERIES[e["series"]]["title"]}» {times} {times_word(times)} за год')
    elif group in s['groups_known']:
        why.append('знает эту группу')
    # Надёжность со «сглаживанием»: у новичка без истории не ноль, а осторожные 0.75
    rel = (s['attended_12m'] + 3) / (s['confirmed_12m'] + 4)
    if s['confirmed_12m'] >= 5 and s['reliability'] and s['reliability'] >= 0.9:
        why.append(f'приходит, когда обещал ({s["attended_12m"]} из {s["confirmed_12m"]})')
    if s['late_cancel_12m'] >= 3:
        why.append(f'{s["late_cancel_12m"]} отмены в последний момент')
    av = v['availability']
    day = WEEK[d.weekday()] if e['slot'] != 'неделя' else None
    if e['slot'] == 'неделя':
        tm = 1.0 if e['series'] in v['preferred_series'] else 0.3
    else:
        tm = 0.5 if not av else (1.0 if day and e['slot'] in av.get(day, []) else 0.7)
    if day and e['slot'] in av.get(day, []):
        why.append(f'обычно свободен: {day}, {e["slot"]}')
    dist = distance(a['area'], e['zone'])
    total = (WEIGHTS['skills'] * sk + WEIGHTS['group'] * gr + WEIGHTS['reliability'] * rel
             + WEIGHTS['time'] * tm + WEIGHTS['distance'] * dist)
    if e['physical'] and ab['physical_help']:
        why.append('может помочь физически')
    if ab['car'] and e['zone'] == 'Московская область':
        why.append('на машине')
    if v['stage'] == 'first_shift_done':
        why.append('новичок: второй выход, позвать вместе с наставником')
    return round(total, 2), why


def pick(e):
    """Топ по оценке, но так, чтобы закрыть обязательные потребности (физическая помощь) и не позвать двух новичков сразу."""
    ok, out = [], []
    for v in VOL:
        reason = check(v, e)
        if reason:
            out.append((v, reason))
        else:
            ok.append((v, *score(v, e)))
    ok.sort(key=lambda x: -x[1])
    chosen = []
    if e['physical']:
        strong = [x for x in ok if x[0]['abilities']['physical_help']]
        if strong:
            chosen.append(strong[0])
    for x in ok:
        if len(chosen) >= e['need']:
            break
        if x in chosen:
            continue
        if x[0]['stage'] == 'first_shift_done' and any(c[0]['stage'] == 'first_shift_done' for c in chosen):
            continue
        chosen.append(x)
    reserve = [x for x in ok if x not in chosen][:3]
    return chosen, reserve, ok, out


def main():
    for e in EVENTS:
        chosen, reserve, ok, out = pick(e)
        print(f'\n### {e["title"]} — нужно {e["need"]} (пост {e["src"]})')
        if e.get('note'):
            print('   ', e['note'])
        good = sum(1 for x in ok if x[1] >= 0.6)
        print(f'    Подходят по фильтрам: {len(ok)} из {len(VOL)}, хорошо подходят (≥ 0.6): {good}')
        if good < e['need']:
            print(f'    ⚠ Хорошо подходящих меньше, чем нужно: позвать резерв или открыть набор')
        for v, sc, why in chosen:
            print(f'    ✓ {v["name"]:22} {sc:.2f}  {"; ".join(why)}')
        for v, sc, why in reserve:
            print(f'    · запас: {v["name"]:15} {sc:.2f}  {"; ".join(why[:2])}')
        reasons = {}
        for v, r in out:
            reasons.setdefault(r, []).append(v['name'].split()[0])
        for r, names in sorted(reasons.items(), key=lambda x: -len(x[1]))[:5]:
            print(f'    ✕ {r}: {", ".join(names)}')


if __name__ == '__main__':
    main()
