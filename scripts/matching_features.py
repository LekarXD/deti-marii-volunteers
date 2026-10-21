"""Признаки «волонтёр × смена» для подбора. Общие для симуляции смен, подбора и обучения весов.

Все признаки от 0 до 1 и считаются только из того, что платформа хранит: анкета, профиль,
история смен. Персональные данные (имя, телефон, почта) сюда не попадают.
"""
from datetime import date

WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

# Какие направления из анкеты подходят роли (роли — prototype-src/roles.json и планирование)
ROLE_DIRS = {'assistant': {'Помощь на занятиях', 'Творчество'}, 'teacher': {'Творчество'}, 'tutor': {'Обучение'},
             'life': {'Помощь на занятиях', 'Творчество'}, 'packing': {'Творчество', 'Ярмарки'}, 'fair': {'Ярмарки', 'Мероприятия'},
             'event': {'Мероприятия', 'Фото, видео, соцсети'}, 'escort': {'Мероприятия', 'Помощь на занятиях'}}
CERTIFICATE = {'assistant', 'teacher', 'tutor', 'life', 'escort'}

# Ручные веса — то, с чего начинаем, пока нет истории. Обучение (train_weights.py) их уточняет.
HAND_WEIGHTS = {'interest': 0.25, 'familiar': 0.25, 'time': 0.20, 'reliability': 0.10, 'response': 0.10, 'near': 0.10}
FEATURES = list(HAND_WEIGHTS)


def blocked(v, series, day_iso):
    """Жёсткие фильтры. Расписание из профиля сюда НЕ входит: это рекомендация, а не запрет."""
    a, p = v['anketa'], v['profile']
    if v['stage'] not in ('regular', 'occasional', 'first_shift_done', 'meeting_done', 'reserve'):
        return 'ещё не прошёл знакомство и встречу'
    if v.get('reserve_status') and v['reserve_status'] != 'ready':
        return 'в резерве, актуальность не подтверждена'
    if p.get('paused_until') and day_iso < p['paused_until']:
        return 'на паузе'
    if series['role'] in CERTIFICATE and a['record'] != 'Справка уже есть':
        return 'нужна справка о несудимости'
    if v['age'] < 18 and series.get('ages') and series['ages'] != 'Взрослые':
        return 'младше 18 — не на занятия с детьми'
    if a['area'] == 'Другой город' and series['zone'] != 'Другой город':
        return 'живёт в другом городе'
    return None


def features(v, sid, series, day_iso, attended_by_series, attended_total, confirmed_total, invited_total=0):
    """Признаки и причины. attended_by_series — сколько раз человек уже был на этой серии к этой дате."""
    a, p = v['anketa'], v['profile']
    why = []
    skills = set(a['skills']) & set(series['skills'])
    interest = min(1.0, 0.5 * len(skills) + (0.5 if ROLE_DIRS[series['role']] & set(a['directions']) else 0))
    if skills:
        why.append('умеет: ' + ', '.join(sorted(skills)))
    n = attended_by_series.get(sid, 0)
    familiar = min(1.0, n / 5)
    if n:
        title = series['title'] if series['title'].startswith('«') else f'«{series["title"]}»'
        why.append(f'был на {title} {n} {plural(n, "раз", "раза", "раз")}')
    day = WEEK[date.fromisoformat(day_iso).weekday()]
    avail = p.get('availability')
    if series['part'] == 'неделя':
        time = 0.6
    elif avail:
        time = 1.0 if series['part'] in avail.get(day, []) else 0.6 if day in avail else 0.2
        if time == 1.0:
            why.append(f'обычно свободен: {day}, {series["part"]}')
    else:
        time = 0.5
    reliability = (attended_total + 3) / (confirmed_total + 4)     # новичок без истории — осторожные 0,75
    if confirmed_total >= 5 and attended_total / confirmed_total >= 0.9:
        why.append(f'приходит, когда обещал ({attended_total} из {confirmed_total})')
    # Отклик: какую долю приглашений человек принимает. Без истории — нейтральные 0,5
    response = (confirmed_total + 1) / (invited_total + 2)
    near = 1.0 if a['area'] == series['zone'] else 0.7 if 'Москв' in a['area'] + series['zone'] else 0.3
    return {'interest': interest, 'familiar': familiar, 'time': time, 'reliability': reliability, 'response': response, 'near': near}, why


def score(f, weights=HAND_WEIGHTS):
    return round(sum(weights[k] * f[k] for k in FEATURES), 3)


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many
