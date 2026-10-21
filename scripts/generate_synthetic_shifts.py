"""Синтетические смены за два года и история откликов под 40 синтетических волонтёров.

Как в жизни: координатор заводит смены в планировании (серия, роль, дата, сколько человек нужно),
приглашает людей, они подтверждают или нет, приходят или нет. Поведение людей задано скрытой
«настоящей» моделью (TRUE_*), которая НЕ совпадает с нашими ручными весами. Это нужно, чтобы
проверить: если обучать веса по истории, восстанавливается ли настоящее поведение.

    python3 scripts/generate_synthetic_volunteers.py   # база волонтёров
    python3 scripts/generate_synthetic_shifts.py       # смены и история, переписывает историю волонтёров

Пишет в materials/05-продукт/данные/:
- synthetic-shifts.json — смены (прошедшие и ближайшие 8 недель) с приглашёнными и их ответами;
- synthetic-invitations.csv — по строке на приглашение: признаки на момент приглашения и исход;
- synthetic-volunteers.json/.csv — с пересчитанной историей за 12 месяцев.
"""
import csv
import json
import math
import pathlib
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import generate_synthetic_volunteers as gv          # noqa: E402
from matching_features import blocked, features, score, FEATURES, HAND_WEIGHTS   # noqa: E402

rnd = random.Random(7)
TODAY = gv.TODAY
START = TODAY - timedelta(days=730)
HORIZON = TODAY + timedelta(days=56)
OUT = gv.OUT

NEED = {'art': 3, 'lab': 1, 'study': 2, 'life': 2, 'pack': 2, 'fair': 4, 'event': 2, 'sorochany': 5, 'residence': 8}
TIME = {'art': '14:00–18:00', 'lab': '13:30–16:00', 'study': '18:00–20:00', 'life': '12:00–15:00', 'pack': '15:00–18:00',
        'fair': '12:00–20:00', 'event': '18:00–21:00', 'sorochany': 'неделя', 'residence': 'неделя'}

# Скрытая «настоящая» модель поведения: вероятность подтвердить приглашение и прийти.
# Знакомая группа и удобное время здесь важнее, чем в наших ручных весах, район — слабее.
TRUE_CONFIRM = {'bias': -3.2, 'interest': 2.6, 'familiar': 2.2, 'time': 1.8, 'reliability': 0.0, 'response': 0.0, 'near': 0.5}
ENGAGE = {'core': 1.0, 'friend': 0.0, 'risk': 0.0, 'special': 0.4, 'newcomer': 0.3, 'reserve': -1.0}
# Сколько смен в месяц человек готов брать: больше не зовут, это видно координатору по загрузке
CAP = {'core': 5, 'friend': 2, 'risk': 3, 'special': 3, 'newcomer': 2, 'reserve': 0}
TRUE_RELIABLE = {'core': 0.94, 'friend': 0.86, 'risk': 0.66, 'special': 0.9, 'newcomer': 0.9, 'reserve': 0.8}


def occurrences(series):
    """Даты смен каждой серии: регулярные — каждую неделю, ярмарки и события — несколько раз в месяц, выезды — раз в год."""
    out = []
    d = START
    while d <= HORIZON:
        for sid, s in series.items():
            if s['weekdays'] is None:
                if d.month == s['months'][0] and d.day <= 7 and d.weekday() == 0:
                    out.append((sid, d))
            elif d.weekday() in s['weekdays']:
                if sid == 'fair' and not (d.day <= 14 and d.weekday() == 5):      # ярмарки — в первые две субботы месяца
                    continue
                if sid == 'event' and rnd.random() > 0.25:                       # выставки и праздники — около трёх в месяц
                    continue
                out.append((sid, d))
        d += timedelta(days=1)
    return out


def active_from(v):
    """С какой даты человек может получать приглашения."""
    if v['stage'] in ('regular', 'occasional') or v['segment'] == 'special':
        return max(START, date.fromisoformat(v['anketa']['submittedAt']))
    return None     # новички, резерв — истории в окне нет


def sig(x):
    return 1 / (1 + math.exp(-x))


def simulate(people, series):
    hist = {v['id']: {'by_series': {}, 'attended': 0, 'confirmed': 0, 'invited': 0, 'month': {}} for v in people}
    shifts, invites = [], []
    for sid, d in occurrences(series):
        s, iso = series[sid], d.isoformat()
        need, past = NEED[sid], d < TODAY
        cands = []
        for v in people:
            start = active_from(v)
            if not start or d < start or blocked(v, s, iso):
                continue
            h = hist[v['id']]
            if h['month'].get(iso[:7], 0) >= CAP[v['segment']]:
                continue
            f, why = features(v, sid, s, iso, h['by_series'], h['attended'], h['confirmed'], h['invited'])
            cands.append((score(f) + rnd.gauss(0, 0.12), v, f))      # координатор зовёт по своему ощущению: близко к ручной оценке, с шумом
        cands.sort(key=lambda x: -x[0])
        invited = [c for c in cands if c[0] >= 0.45 and c[2]['interest'] > 0][:need + 2]     # без общего интереса с ролью не зовут
        shift = {'id': f'{sid}@{iso}', 'series': sid, 'title': s['title'], 'role': s['role'], 'date': iso, 'time': TIME[sid],
                 'where': s['where'], 'need': need, 'responses': {}}
        filled = 0
        days_left = (d - TODAY).days
        for _, v, f in invited:
            h = hist[v['id']]
            if past:
                h['invited'] += 1
            if not past and rnd.random() > (0.7 if days_left <= 14 else 0.3):
                shift['responses'][v['id']] = 'invited'        # ещё не ответил
                continue
            logit = TRUE_CONFIRM['bias'] + ENGAGE[v['segment']] + sum(TRUE_CONFIRM[k] * f[k] for k in FEATURES) + rnd.gauss(0, 0.3)
            if filled >= need or rnd.random() > sig(logit):
                status = 'declined'
            elif not past:
                status, filled = 'confirmed', filled + 1
                h['month'][iso[:7]] = h['month'].get(iso[:7], 0) + 1
            else:
                filled += 1
                h['month'][iso[:7]] = h['month'].get(iso[:7], 0) + 1
                rel = TRUE_RELIABLE[v['segment']] - (0.08 if f['near'] < 0.5 else 0)
                if v['segment'] == 'risk' and d > TODAY - timedelta(days=90):
                    rel -= 0.2                                   # под риском: в последние месяцы пропускает чаще
                r = rnd.random()
                status = 'attended' if r < rel else ('cancelled_late' if r < rel + (1 - rel) / 2 else 'absent')
                h['confirmed'] += 1
                if status == 'attended':
                    h['attended'] += 1
                    h['by_series'][sid] = h['by_series'].get(sid, 0) + 1
            shift['responses'][v['id']] = status
            if past:
                invites.append({'shift_id': shift['id'], 'date': iso, 'series': sid, 'volunteer_id': v['id'], 'segment': v['segment'],
                                **{k: round(f[k], 3) for k in FEATURES}, 'hand_score': score(f),
                                'confirmed': int(status != 'declined'), 'attended': int(status == 'attended'), 'status': status})
        shift['confirmed'] = [k for k, x in shift['responses'].items() if x in ('confirmed', 'attended')]
        shifts.append(shift)
    return shifts, invites


def rewrite_history(people, shifts, series):
    """Переписывает историю волонтёров за последние 12 месяцев по смоделированным сменам."""
    year_ago = (TODAY - timedelta(days=365)).isoformat()
    by_v = {v['id']: [] for v in people}
    for sh in shifts:
        if sh['date'] >= TODAY.isoformat():
            continue
        for vid, st in sh['responses'].items():
            if st == 'declined':
                continue
            by_v[vid].append({'shift_id': sh['id'], 'series': sh['series'], 'date': sh['date'], 'role': sh['role'], 'status': st,
                              'hours': series[sh['series']]['hours'] if st == 'attended' else 0})
    invited = {v['id']: 0 for v in people}
    for sh in shifts:
        if year_ago <= sh['date'] < TODAY.isoformat():
            for vid in sh['responses']:
                invited[vid] += 1
    for v in people:
        if v['stage'] == 'first_shift_done':
            continue            # единственный первый выход уже записан в базе волонтёров
        recs = sorted((r for r in by_v[v['id']] if r['date'] >= year_ago), key=lambda r: r['date'])
        allrecs = by_v[v['id']]
        v['participation_12m'] = recs
        att = [r for r in recs if r['status'] == 'attended']
        v['stats'].update({
            'invited_12m': invited[v['id']], 'confirmed_12m': len(recs), 'attended_12m': len(att),
            'absent_12m': sum(r['status'] == 'absent' for r in recs),
            'late_cancel_12m': sum(r['status'] == 'cancelled_late' for r in recs),
            'hours_12m': sum(r['hours'] for r in recs),
            'last_attended': max((r['date'] for r in att), default=v['stats'].get('last_attended') if v['segment'] == 'reserve' else None),
            'series_attended': {s: sum(1 for r in att if r['series'] == s) for s in sorted({r['series'] for r in att})},
            'hours_total': max(v['stats']['hours_total'], sum(r['hours'] for r in allrecs)),
        })


def main():
    people = gv.build()
    series = gv.SERIES
    shifts, invites = simulate(people, series)
    rewrite_history(people, shifts, series)
    gv.write_volunteers(people)
    (OUT / 'synthetic-shifts.json').write_text(json.dumps({'generated_for': TODAY.isoformat(), 'need': NEED, 'shifts': shifts},
                                                          ensure_ascii=False, indent=1) + '\n')
    with open(OUT / 'synthetic-invitations.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(invites[0]))
        w.writeheader()
        w.writerows(invites)
    past = [s for s in shifts if s['date'] < TODAY.isoformat()]
    full = sum(1 for s in past if len(s['confirmed']) >= s['need'])
    print(f'смен: {len(shifts)} (прошедших {len(past)}, ближайших {len(shifts) - len(past)}), закрыто полностью: {full / len(past):.0%}')
    print(f'приглашений в истории: {len(invites)}, подтвердили: {sum(i["confirmed"] for i in invites)}, пришли: {sum(i["attended"] for i in invites)}')


if __name__ == '__main__':
    main()
