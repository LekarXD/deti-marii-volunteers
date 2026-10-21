"""Синтетические волонтёры для отладки подбора волонтёров на мероприятия.

40 человек — от «ядра» фонда до новичков и «потерянных» с ковида. Поля анкеты — как в
prototype/content/form.js (v4), остальное — из плана данных docs/implementation/data-model.md
и фактуры со встречи с фондом. Люди, которые уже есть в прототипе (Светлана, Кирилл, Анна…),
сохранены с теми же именами и фактами, чтобы данные не расходились с экранами.

    python3 scripts/generate_synthetic_volunteers.py

Пишет materials/05-продукт/данные/synthetic-volunteers.json и .csv. Генерация детерминирована
(seed), поэтому повторный запуск даёт тот же набор.
"""
import csv
import json
import pathlib
import random
from datetime import date, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'materials/05-продукт/данные'
TODAY = date(2026, 10, 21)
YEAR_AGO = TODAY - timedelta(days=365)
rnd = random.Random(2026)

# Серии мероприятий фонда (по базе ВК и каталогу за год). weekdays: 0 = пн.
SERIES = {
    'art-sat':   {'title': 'Арт-суббота', 'where': 'Загородная мастерская', 'weekdays': [5], 'slot': 'день', 'hours': 5,
                  'group': 'Взрослые из соцдомов «Филимонки», «Нагатино-Садовники»', 'role': 'Ассистент педагога',
                  'skills': ['Живопись и рисунок', 'Керамика', 'Кулинария'], 'certificate': False, 'physical': True},
    'art-lab':   {'title': 'Арт-лаборатория', 'where': 'Студия в Тверском районе', 'weekdays': [1, 3], 'slot': 'день', 'hours': 3,
                  'group': 'Дети из ЦССВ «Радуга», «Сколковский»', 'role': 'Ассистент педагога',
                  'skills': ['Живопись и рисунок', 'Керамика', 'Валяние'], 'certificate': True, 'physical': False},
    'want-know': {'title': '«Хочу больше знать»', 'where': 'Студия в Тверском районе', 'weekdays': [0, 2], 'slot': 'вечер', 'hours': 2,
                  'group': 'Выпускники детских домов', 'role': 'Репетитор',
                  'skills': ['Школьные предметы', 'Английский', 'Педагогика'], 'certificate': True, 'physical': False},
    'cooking':   {'title': 'Кулинарная мастерская', 'where': 'Студия в Пресненском районе', 'weekdays': [2], 'slot': 'день', 'hours': 3,
                  'group': 'Взрослые из ПНИ № 16', 'role': 'Ассистент педагога',
                  'skills': ['Кулинария'], 'certificate': False, 'physical': False},
    'cinema':    {'title': 'Киноклуб', 'where': 'Студия в Тверском районе', 'weekdays': [6], 'slot': 'вечер', 'hours': 3,
                  'group': 'Участники и жители района', 'role': 'Ведущий беседы',
                  'skills': ['Психология', 'Педагогика'], 'certificate': False, 'physical': False},
    'games':     {'title': 'Вечер настольных игр', 'where': 'Студия в Тверском районе', 'weekdays': [4], 'slot': 'вечер', 'hours': 3,
                  'group': 'Выпускники и участники «Сообщества»', 'role': 'Ведущий игры',
                  'skills': ['Спорт и игры'], 'certificate': False, 'physical': False},
    'fair':      {'title': 'Ярмарка (Шерстяной Базар, Seasons of life)', 'where': 'Даниловский Event Hall и маркеты', 'weekdays': [5, 6], 'slot': 'день', 'hours': 8,
                  'group': 'Открытое событие, покупатели', 'role': 'Продавец на стенде',
                  'skills': ['Продажи', 'Соцсети'], 'certificate': False, 'physical': False},
    'exhibit':   {'title': 'Выставка в ИКЦ «Тверская 15»', 'where': 'ИКЦ «Тверская 15»', 'weekdays': [3, 4, 5], 'slot': 'вечер', 'hours': 4,
                  'group': 'Открытое событие, гости', 'role': 'Встречает гостей',
                  'skills': ['Фотография', 'Соцсети'], 'certificate': False, 'physical': False},
    'sorochany': {'title': 'Зимняя неделя в Сорочанах', 'where': 'Сорочаны, Подмосковье', 'weekdays': None, 'slot': 'неделя', 'hours': 40,
                  'group': 'Участники из соцучреждений', 'role': 'Сопровождающий на выезде',
                  'skills': ['Спорт и игры'], 'certificate': True, 'physical': True, 'months': [2]},
    'residence': {'title': 'Арт-резиденция на Волге (Учма)', 'where': 'Учма, Ярославская область', 'weekdays': None, 'slot': 'неделя', 'hours': 60,
                  'group': 'Дети из интерната «Надежда», школы № 1 Беслана', 'role': 'Сопровождающий на выезде',
                  'skills': ['Живопись и рисунок', 'Театр', 'Спорт и игры'], 'certificate': True, 'physical': True, 'months': [7, 8]},
}

DIRECTIONS = ['Творчество', 'Помощь на занятиях', 'Обучение', 'Психолог, логопед', 'Фото, видео, соцсети',
              'Мероприятия', 'Ярмарки', 'Юрист, IT, маркетинг', 'Пока не знаю']
AREAS = ['Центр Москвы', 'Север', 'Восток', 'Юг', 'Запад', 'Новая Москва', 'Московская область', 'Другой город']
WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

# Сегменты: доля явки, сколько раз в месяц выходит, сколько отмен в последний момент.
SEGMENTS = {
    'core':     {'label': 'Ядро: ходят регулярно', 'attend': (0.86, 0.97), 'per_month': (3, 5), 'late_cancel': (0.0, 0.06)},
    'friend':   {'label': 'Друзья фонда: приходят на отдельные события', 'attend': (0.75, 0.92), 'per_month': (0.3, 1.2), 'late_cancel': (0.03, 0.12)},
    'risk':     {'label': 'Под риском ухода', 'attend': (0.55, 0.75), 'per_month': (1, 3), 'late_cancel': (0.1, 0.25)},
    'newcomer': {'label': 'Новички в воронке', 'attend': (0.8, 1.0), 'per_month': (0, 1), 'late_cancel': (0.0, 0.1)},
    'reserve':  {'label': 'Резерв: пришли в ковид и пропали', 'attend': (0.7, 0.9), 'per_month': (0, 0), 'late_cancel': (0.0, 0.1)},
    'special':  {'label': 'Особые случаи', 'attend': (0.8, 0.95), 'per_month': (0.5, 2), 'late_cancel': (0.0, 0.08)},
}

# Люди. series — где обычно помогают; known — сколько лет с фондом; extra — особые факты.
# Первые 15 уже есть в прототипе (Volunteers, Shifts, Reserve, interview-store, Pipeline, demo.js).
PEOPLE = [
    # --- ядро ---
    dict(id='sveta', name='Светлана Ким', g='f', age=44, seg='core', since=2019, area='Север', series=['art-lab', 'art-sat'], skills=['Керамика', 'Педагогика'], dirs=['Творчество', 'Помощь на занятиях'], hours_total=168, extra={'mentor': True, 'note': 'Наставница новичков, ведёт Егора'}),
    dict(id='kirill', name='Кирилл Смирнов', g='m', age=31, seg='core', since=2020, area='Восток', series=['games', 'sorochany'], skills=['Спорт и игры'], dirs=['Мероприятия', 'Помощь на занятиях'], hours_total=140, extra={'physical_help': True}),
    dict(id='polina', name='Полина Зайцева', g='f', age=27, seg='core', since=2023, area='Центр Москвы', series=['art-lab', 'fair'], skills=['Валяние', 'Шитьё и вышивка'], dirs=['Творчество', 'Ярмарки'], hours_total=52),
    dict(id='anna', name='Анна Соколова', g='f', age=32, seg='core', since=2026, area='Центр Москвы', series=['art-sat'], skills=['Керамика', 'Живопись и рисунок'], dirs=['Творчество', 'Помощь на занятиях'], hours_total=46, extra={'note': 'С фондом 7 месяцев, справка получена 9 июня'}),
    dict(id='tatiana', name='Татьяна Воронина', g='f', age=63, seg='core', since=2018, area='Запад', series=['cooking', 'fair'], skills=['Кулинария', 'Шитьё и вышивка'], dirs=['Творчество', 'Ярмарки'], hours_total=410),
    dict(id='artem', name='Артём Белов', g='m', age=29, seg='core', since=2022, area='Юг', series=['want-know'], skills=['Школьные предметы', 'Педагогика'], dirs=['Обучение'], hours_total=190),
    dict(id='liza', name='Елизавета Громова', g='f', age=35, seg='core', since=2021, area='Центр Москвы', series=['cinema', 'art-lab'], skills=['Психология'], dirs=['Психолог, логопед', 'Помощь на занятиях'], hours_total=230),
    dict(id='sergey', name='Сергей Панов', g='m', age=41, seg='core', since=2019, area='Московская область', series=['art-sat', 'sorochany', 'residence'], skills=['Спорт и игры', 'Театр'], dirs=['Мероприятия', 'Помощь на занятиях'], hours_total=520, extra={'physical_help': True, 'car': True}),
    # --- друзья фонда ---
    dict(id='vera', name='Вера Новикова', g='f', age=26, seg='friend', since=2025, area='Север', series=['exhibit', 'fair'], skills=['Фотография'], dirs=['Фото, видео, соцсети', 'Мероприятия'], hours_total=18),
    dict(id='timur', name='Тимур Ахмедов', g='m', age=38, seg='friend', since=2022, area='Восток', series=['sorochany', 'fair'], skills=[], dirs=['Мероприятия'], hours_total=20, extra={'car': True, 'physical_help': True, 'note': 'Водитель: возит материалы и людей на выезды'}),
    dict(id='ksenia', name='Ксения Рябова', g='f', age=30, seg='friend', since=2023, area='Центр Москвы', series=['cinema'], skills=['Психология'], dirs=['Мероприятия'], hours_total=56, extra={'paused_until': '2026-12-01'}),
    dict(id='daria', name='Дарья Лисицина', g='f', age=24, seg='friend', since=2024, area='Юг', series=['fair'], skills=['Продажи', 'Соцсети'], dirs=['Ярмарки'], hours_total=64),
    dict(id='gleb', name='Глеб Соловьёв', g='m', age=34, seg='friend', since=2025, area='Запад', series=['fair', 'exhibit'], skills=['Продажи'], dirs=['Ярмарки', 'Мероприятия'], hours_total=24, extra={'corporate': 'Корпоративный волонтёр, приходит с коллегами раз в квартал'}),
    dict(id='roman', name='Роман Зуев', g='m', age=36, seg='friend', since=2024, area='Другой город', series=[], skills=['IT'], dirs=['Юрист, IT, маркетинг'], hours_total=30, extra={'online_only': True, 'note': 'Помогает с сайтом удалённо'}),
    dict(id='nastya', name='Анастасия Кравец', g='f', age=39, seg='friend', since=2023, area='Центр Москвы', series=[], skills=['Право'], dirs=['Юрист, IT, маркетинг'], hours_total=22, extra={'online_only': True, 'note': 'Консультирует выпускников по документам'}),
    dict(id='sofia', name='Софья Мартынова', g='f', age=21, seg='friend', since=2025, area='Север', series=['exhibit', 'fair'], skills=['Дизайн', 'Соцсети', 'Фотография'], dirs=['Фото, видео, соцсети'], hours_total=16, extra={'student': True}),
    # --- под риском ---
    dict(id='dima', name='Дмитрий Орлов', g='m', age=28, seg='risk', since=2024, area='Восток', series=['art-sat', 'cinema'], skills=['Театр'], dirs=['Творчество', 'Мероприятия'], hours_total=38, extra={'note': 'Два пропуска подряд'}),
    dict(id='marina', name='Марина Белова', g='f', age=33, seg='risk', since=2025, area='Юг', series=['art-lab'], skills=['Музыка и вокал'], dirs=['Творчество'], hours_total=15, extra={'note': 'Говорила координатору, что думает уйти'}),
    dict(id='nikita', name='Никита Седов', g='m', age=22, seg='risk', since=2025, area='Новая Москва', series=['games', 'want-know'], skills=['Английский', 'Спорт и игры'], dirs=['Обучение', 'Мероприятия'], hours_total=27, extra={'student': True, 'note': 'Сессия, отменяет в последний момент'}),
    # --- новички в воронке ---
    dict(id='egor', name='Егор Мельников', g='m', age=25, seg='newcomer', since=2026, area='Центр Москвы', series=['art-sat'], skills=['Живопись и рисунок'], dirs=['Помощь на занятиях'], hours_total=0, stage='meeting_booked', extra={'test_score': 10, 'meeting': '2026-10-23 12:00', 'mentor_id': 'sveta'}),
    dict(id='mila', name='Мила Орлова', g='f', age=23, seg='newcomer', since=2026, area='Север', series=[], skills=['Фотография'], dirs=['Фото, видео, соцсети'], hours_total=0, stage='onboarding', extra={'modules_done': 2}),
    dict(id='alina', name='Алина Фёдорова', g='f', age=19, seg='newcomer', since=2026, area='Запад', series=[], skills=['Живопись и рисунок'], dirs=['Творчество'], hours_total=0, stage='applied'),
    dict(id='maxim', name='Максим Ильин', g='m', age=27, seg='newcomer', since=2026, area='Юг', series=[], skills=['Спорт и игры'], dirs=['Мероприятия', 'Помощь на занятиях'], hours_total=0, stage='meeting_done', avail={'сб': ['день'], 'вс': ['день', 'вечер']}, extra={'physical_help': True}),
    dict(id='oleg', name='Олег Петров', g='m', age=45, seg='newcomer', since=2026, area='Восток', series=['art-lab'], skills=['Керамика'], dirs=['Творчество'], hours_total=0, stage='waiting_certificate', extra={'note': 'Ждём справку о несудимости'}),
    dict(id='farid', name='Фарид Гасанов', g='m', age=31, seg='newcomer', since=2026, area='Московская область', series=[], skills=[], dirs=['Пока не знаю'], hours_total=0, stage='applied'),
    dict(id='kira', name='Кира Белоусова', g='f', age=26, seg='newcomer', since=2026, area='Центр Москвы', series=[], skills=['Кулинария'], dirs=['Творчество', 'Ярмарки'], hours_total=0, stage='meeting_booked', extra={'modules_done': 0, 'note': 'Записалась на встречу, знакомство не начала'}),
    dict(id='lev', name='Лев Ермаков', g='m', age=34, seg='newcomer', since=2026, area='Север', series=[], skills=['Видео и монтаж'], dirs=['Фото, видео, соцсети'], hours_total=0, stage='dropped', extra={'note': 'Заполнил анкету месяц назад и больше не заходил'}),
    dict(id='maria_d', name='Мария Дьякова', g='f', age=29, seg='newcomer', since=2026, area='Центр Москвы', series=['cooking'], skills=['Кулинария'], dirs=['Творчество', 'Помощь на занятиях'], hours_total=3, stage='first_shift_done', extra={'note': 'Был первый выход, обсуждаем продолжение'}),
    # --- резерв ---
    dict(id='galina', name='Галина Смирнова', g='f', age=73, seg='reserve', since=2020, area='Север', series=['cooking'], skills=['Кулинария', 'Шитьё и вышивка'], dirs=['Творчество'], hours_total=85, reserve='ready', avail={'пн': ['день'], 'ср': ['день']}, extra={'note': '70+, нужен крупный шрифт; готова по будням днём'}),
    dict(id='irina', name='Ирина Ковалёва', g='f', age=38, seg='reserve', since=2020, area='Запад', series=['art-lab'], skills=['Живопись и рисунок', 'Педагогика'], dirs=['Творчество', 'Обучение'], hours_total=44, reserve='awaiting_reply'),
    dict(id='vika', name='Виктория Шевцова', g='f', age=27, seg='reserve', since=2020, area='Восток', series=['fair'], skills=['Продажи'], dirs=['Ярмарки'], hours_total=12, reserve='unverified'),
    dict(id='stas', name='Станислав Орехов', g='m', age=35, seg='reserve', since=2021, area='Юг', series=['games'], skills=['Спорт и игры'], dirs=['Мероприятия'], hours_total=9, reserve='unverified'),
    dict(id='katya_l', name='Екатерина Лапина', g='f', age=31, seg='reserve', since=2020, area='Центр Москвы', series=['art-lab'], skills=['Музыка и вокал'], dirs=['Творчество'], hours_total=31, reserve='paused', extra={'note': 'Декрет, вернётся весной'}),
    dict(id='nikolay', name='Николай Фомин', g='m', age=52, seg='reserve', since=2021, area='Московская область', series=['sorochany'], skills=[], dirs=['Мероприятия'], hours_total=48, reserve='ready', avail={'сб': ['день'], 'вс': ['день']}, extra={'car': True, 'physical_help': True}),
    dict(id='alena', name='Алёна Крылова', g='f', age=26, seg='reserve', since=2020, area='Новая Москва', series=['exhibit'], skills=['Фотография'], dirs=['Фото, видео, соцсети'], hours_total=6, reserve='no_invites'),
    dict(id='ruslan', name='Руслан Хабибуллин', g='m', age=30, seg='reserve', since=2021, area='Север', series=['want-know'], skills=['Школьные предметы'], dirs=['Обучение'], hours_total=20, reserve='unreachable'),
    # --- особые случаи ---
    dict(id='alexey', name='Алексей Ким', g='m', age=17, seg='special', since=2026, area='Центр Москвы', series=['fair', 'exhibit'], skills=['Соцсети'], dirs=['Мероприятия', 'Ярмарки'], hours_total=8, extra={'minor': True, 'note': '17 лет: только открытые события, без работы с детьми один на один'}),
    dict(id='ludmila', name='Людмила Захарова', g='f', age=72, seg='special', since=2018, area='Запад', series=['art-sat'], skills=['Валяние', 'Шитьё и вышивка'], dirs=['Творчество'], hours_total=360, extra={'low_vision': True, 'note': 'Слабое зрение, пользуется только звонками'}),
    dict(id='yan', name='Ян Ковальчук', g='m', age=44, seg='special', since=2025, area='Другой город', series=['residence'], skills=['Театр', 'Музыка и вокал'], dirs=['Мероприятия'], hours_total=60, avail={'июль–август': ['неделя']}, extra={'note': 'Живёт в Ярославле, помогает только на резиденции'}),
    dict(id='olya_f', name='Ольга Фролова', g='f', age=40, seg='special', since=2024, area='Юг', series=['art-sat'], skills=['Керамика'], dirs=['Творчество'], hours_total=70, extra={'partner': 'Волонтёр от фонда-партнёра «Лучшие друзья»'}),
]


def pick(lo_hi):
    lo, hi = lo_hi
    return round(rnd.uniform(lo, hi), 2)


def dates_for(series_id, n):
    """n дат за последний год, которые подходят серии по дням недели или сезону."""
    s = SERIES[series_id]
    out = []
    for _ in range(n * 6):
        d = YEAR_AGO + timedelta(days=rnd.randrange(365))
        if s['weekdays'] is None:
            if d.month in s['months'] and d < TODAY:
                out.append(d)
        elif d.weekday() in s['weekdays'] and d < TODAY:
            out.append(d)
        if len(out) >= n:
            break
    return sorted(set(out))


def availability(p):
    """Сетка «день недели × утро/день/вечер» из серий, где человек помогает, плюс немного шума."""
    grid = {w: [] for w in WEEK}
    for sid in p['series']:
        s = SERIES[sid]
        if s['weekdays']:
            for wd in s['weekdays']:
                if s['slot'] not in grid[WEEK[wd]]:
                    grid[WEEK[wd]].append(s['slot'])
    if p.get('avail'):
        return p['avail']
    if p['seg'] in ('core', 'friend', 'risk') and rnd.random() < 0.4:
        grid[rnd.choice(WEEK)].append(rnd.choice(['утро', 'день', 'вечер']))
    if p['seg'] == 'reserve' and p.get('reserve') != 'ready':
        return {}
    return {w: sorted(set(v)) for w, v in grid.items() if v}


def history(p, seg):
    """Записи участия за последний год: приглашён → подтвердил → пришёл / не пришёл / отменил."""
    if p.get('stage') == 'first_shift_done':
        return [{'series': p['series'][0], 'date': (TODAY - timedelta(days=9)).isoformat(), 'role': SERIES[p['series'][0]]['role'], 'status': 'attended', 'hours': 3}]
    if not p['series'] or seg['per_month'] == (0, 0) or p.get('stage') in ('applied', 'onboarding', 'meeting_booked', 'meeting_done', 'waiting_certificate', 'dropped'):
        return []
    months = 12 if p['since'] < 2026 else max(1, TODAY.month - 2)
    per_month = pick(seg['per_month'])
    if p.get('extra', {}).get('paused_until'):
        months = max(1, months - 3)
    total = max(1, round(per_month * months))
    attend, late = pick(seg['attend']), pick(seg['late_cancel'])
    recs = []
    weights = [3] + [1] * (len(p['series']) - 1)
    for _ in range(total):
        sid = rnd.choices(p['series'], weights=weights[:len(p['series'])])[0]
        ds = dates_for(sid, 1)
        if not ds:
            continue
        r = rnd.random()
        status = 'attended' if r < attend else ('cancelled_late' if r < attend + late else 'absent')
        recs.append({'series': sid, 'date': ds[0].isoformat(), 'role': SERIES[sid]['role'], 'status': status,
                     'hours': SERIES[sid]['hours'] if status == 'attended' else 0})
    # Многодневный выезд (Сорочаны, резиденция) бывает раз в год — оставляем одну запись на серию
    once, seen = [], set()
    for x in sorted(recs, key=lambda x: x['date']):
        if SERIES[x['series']]['weekdays'] is None:
            if x['series'] in seen:
                continue
            seen.add(x['series'])
        once.append(x)
    recs = once
    # Сигналы риска из прототипа: у Дмитрия два пропуска подряд
    recs.sort(key=lambda x: x['date'])
    if p['id'] == 'dima' and len(recs) >= 2:
        for x in recs[-2:]:
            x['status'], x['hours'] = 'absent', 0
    return recs


def stats(recs, p):
    confirmed = len(recs)
    attended = sum(1 for r in recs if r['status'] == 'attended')
    late = sum(1 for r in recs if r['status'] == 'cancelled_late')
    absent = sum(1 for r in recs if r['status'] == 'absent')
    invited = confirmed + rnd.randint(0, max(1, confirmed // 3))
    last = max((r['date'] for r in recs if r['status'] == 'attended'), default=None)
    days = [WEEK[date.fromisoformat(r['date']).weekday()] for r in recs if r['status'] == 'attended']
    fav = sorted({d for d in days if days.count(d) >= max(2, len(days) // 4)})
    groups = sorted({SERIES[r['series']]['group'] for r in recs if r['status'] == 'attended'})
    return {
        'invited_12m': invited, 'confirmed_12m': confirmed, 'attended_12m': attended,
        'absent_12m': absent, 'late_cancel_12m': late,
        'reliability': round(attended / confirmed, 2) if confirmed else None,
        'acceptance': round(confirmed / invited, 2) if invited else None,
        'hours_12m': sum(r['hours'] for r in recs),
        'hours_total': p['hours_total'] + (sum(r['hours'] for r in recs) if p['hours_total'] == 0 else 0),
        'last_attended': last or (f'{rnd.choice([2021, 2022])}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}' if p['seg'] == 'reserve' else None),
        'favourite_days': fav, 'groups_known': groups or ([SERIES[s]['group'] for s in p['series']] if p['seg'] == 'reserve' else []),
    }


def cabinet(p, st):
    """Действия в кабинете и боте: когда заходил, обновлял ли доступность, настроение в рефлексиях."""
    seg = p['seg']
    if seg == 'reserve':
        last_login = date(rnd.choice([2021, 2022]), rnd.randint(1, 12), rnd.randint(1, 28))
    elif p.get('stage') == 'dropped':
        last_login = TODAY - timedelta(days=31)
    else:
        last_login = TODAY - timedelta(days=rnd.randint(0, 20 if seg != 'risk' else 45))
    moods = ['great', 'good', 'ok', 'hard']
    mood_w = {'core': [5, 4, 1, 0.3], 'friend': [3, 4, 2, 0.5], 'risk': [1, 2, 3, 3], 'special': [3, 4, 2, 0.5]}.get(seg, [3, 3, 2, 1])
    refl = [{'date': (TODAY - timedelta(days=rnd.randint(3, 200))).isoformat(), 'mood': rnd.choices(moods, mood_w)[0]}
            for _ in range(min(st['attended_12m'], rnd.randint(0, 4)))]
    return {
        'last_login': last_login.isoformat(),
        'availability_updated': (last_login - timedelta(days=rnd.randint(0, 120))).isoformat() if seg != 'reserve' else None,
        'telegram_bot': bool(p.get('tg', rnd.random() < (0.85 if seg in ('core', 'newcomer') else 0.5))) and not p.get('extra', {}).get('low_vision'),
        'reflections': sorted(refl, key=lambda r: r['date']),
        'opened_invites_30d': rnd.randint(0, 6) if seg in ('core', 'friend', 'risk', 'special') else 0,
    }


def anketa(p):
    online = p.get('extra', {}).get('online_only', False) or (p['seg'] in ('friend', 'special') and rnd.random() < 0.3)
    participation = 'Каждую неделю' if p['seg'] == 'core' else ('Пока не знаю' if p.get('stage') == 'applied' and not p['skills'] else 'На отдельных событиях')
    needs_cert = any(SERIES[s]['certificate'] for s in p['series'])
    record = 'Справка уже есть' if (p['seg'] in ('core', 'special') or needs_cert) and p.get('stage') != 'waiting_certificate' else 'Получу её'
    first, last = p['name'].split(' ', 1)
    birth_year = TODAY.year - p['age']
    return {
        'firstName': first, 'lastName': last, 'birthdate': f'{birth_year}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}',
        'phone': f'+7 (9{rnd.randint(10, 99)}) {rnd.randint(100, 999)}-{rnd.randint(10, 99)}-{rnd.randint(10, 99)}',
        'email': f'{p["id"]}@example.org', 'telegram': f'@{p["id"]}_demo' if rnd.random() < 0.8 else '',
        'area': p['area'], 'directions': p['dirs'], 'skills': p['skills'], 'participation': participation,
        'online': online, 'volExp': 'Да' if p['since'] < 2026 or rnd.random() < 0.3 else 'Нет',
        'specialExp': 'Да' if p['seg'] in ('core', 'special') or p['since'] < 2024 else rnd.choice(['Да', 'Нет']),
        'record': record, 'source': rnd.choice(['ВКонтакте', 'Telegram', 'Сайт фонда', 'Добро.РФ', 'mos.ru', 'Друзья', 'Мероприятие фонда']),
        'consentPD': True, 'consentNews': rnd.random() < 0.7,
        'submittedAt': f'{p["since"]}-{rnd.randint(1, 12 if p["since"] < 2026 else 9):02d}-{rnd.randint(1, 28):02d}',
    }


def build():
    people = []
    for p in PEOPLE:
        seg = SEGMENTS[p['seg']]
        recs = history(p, seg)
        st = stats(recs, p)
        stage = p.get('stage') or {'core': 'regular', 'friend': 'occasional', 'risk': 'regular', 'special': 'regular',
                                   'reserve': 'reserve'}[p['seg']]
        extra = p.get('extra', {})
        people.append({
            'id': p['id'], 'name': p['name'], 'gender_for_text': p['g'], 'age': p['age'],
            'segment': p['seg'], 'segment_label': seg['label'], 'stage': stage,
            'with_fund_since': p['since'], 'reserve_status': p.get('reserve'),
            'anketa': anketa(p),
            'onboarding': {
                'modules_done': 4 if stage not in ('applied', 'onboarding', 'meeting_booked', 'dropped') else extra.get('modules_done', 0),
                'test_score': extra.get('test_score') if stage in ('meeting_booked', 'meeting_done', 'waiting_certificate') else (rnd.randint(7, 10) if p['since'] >= 2026 and stage not in ('applied', 'onboarding', 'dropped') else None),
            },
            # Поля, которых пока нет в модели данных: координатор отмечает их после встречи
            'abilities': {
                'physical_help': extra.get('physical_help', False),
                'car': extra.get('car', False),
                'online_only': extra.get('online_only', False),
                'minor': extra.get('minor', False),
                'low_vision': extra.get('low_vision', False),
            },
            'availability': availability(p),
            'preferred_series': p['series'],
            'participation_12m': recs,
            'stats': st,
            'cabinet': cabinet(p, st),
            'mentor': extra.get('mentor', False), 'mentor_id': extra.get('mentor_id'),
            'paused_until': extra.get('paused_until'), 'partner': extra.get('partner') or extra.get('corporate'),
            'coordinator_note': extra.get('note', ''),
        })
    return people


def main():
    people = build()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {'generated_for': TODAY.isoformat(), 'series': SERIES, 'volunteers': people}
    (OUT / 'synthetic-volunteers.json').write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')
    cols = ['id', 'name', 'age', 'segment_label', 'stage', 'with_fund_since', 'area', 'directions', 'skills', 'participation',
            'online', 'record', 'physical_help', 'car', 'availability', 'attended_12m', 'reliability', 'late_cancel_12m',
            'hours_total', 'last_attended', 'groups_known', 'last_login', 'telegram_bot', 'reserve_status', 'coordinator_note']
    with open(OUT / 'synthetic-volunteers.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for v in people:
            a, s = v['anketa'], v['stats']
            w.writerow([v['id'], v['name'], v['age'], v['segment_label'], v['stage'], v['with_fund_since'], a['area'],
                        '; '.join(a['directions']), '; '.join(a['skills']), a['participation'], a['online'], a['record'],
                        v['abilities']['physical_help'], v['abilities']['car'],
                        '; '.join(f'{d} {"/".join(sl)}' for d, sl in v['availability'].items()),
                        s['attended_12m'], s['reliability'], s['late_cancel_12m'], s['hours_total'], s['last_attended'] or '',
                        '; '.join(s['groups_known']), v['cabinet']['last_login'], v['cabinet']['telegram_bot'],
                        v['reserve_status'] or '', v['coordinator_note']])
    by_seg = {}
    for v in people:
        by_seg[v['segment_label']] = by_seg.get(v['segment_label'], 0) + 1
    print(len(people), 'волонтёров:', by_seg)


if __name__ == '__main__':
    main()
