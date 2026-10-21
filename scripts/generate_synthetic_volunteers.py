"""Синтетические волонтёры для отладки подбора на смены.

Берём только те данные, которые платформа реально собирает:
- анкета — prototype/content/form.js;
- знакомство с фондом и тест — prototype/content/onboarding.js;
- встреча с координатором — prototype-src/interview-store.js;
- профиль, который волонтёр заполняет сам (время, возраст детей, где удобно, частота) — prototype/Profile.dc.html;
- отклики и явка на смены из планирования координатора — prototype-src/Planning.js, роли — prototype-src/roles.json;
- действия в кабинете и боте.

Физическую помощь, машину и прочее, чего мы не собираем, не выдумываем.
15 человек уже есть в прототипе (Светлана, Кирилл, Анна, Егор…) — они сохранены с теми же фактами.

    python3 scripts/generate_synthetic_volunteers.py

Пишет materials/05-продукт/данные/synthetic-volunteers.json и .csv. Набор детерминирован (seed).
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
WEEK = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']

# Серии смен — как в планировании координатора (Planning.js) и справочнике ролей (roles.json).
# weekdays: 0 = пн; months — для выездов раз в год; ages — возраст участников для поля профиля «Возраст детей».
SERIES = {
    'art':       {'title': 'Арт-субботы', 'role': 'assistant', 'program': 'Творческие занятия', 'where': 'Загородная мастерская, Грибаново',
                  'zone': 'Московская область', 'weekdays': [5], 'part': 'день', 'hours': 4, 'ages': 'Взрослые', 'skills': ['Живопись и рисунок', 'Керамика', 'Кулинария']},
    'lab':       {'title': 'Арт-лаборатория', 'role': 'teacher', 'program': 'Творческие занятия', 'where': 'Студия у м. Театральная',
                  'zone': 'Центр Москвы', 'weekdays': [3], 'part': 'день', 'hours': 2.5, 'ages': '13–17 лет', 'skills': ['Живопись и рисунок', 'Керамика', 'Валяние']},
    'study':     {'title': '«Хочу больше знать»', 'role': 'tutor', 'program': 'Образовательные занятия', 'where': 'Студия у м. Театральная',
                  'zone': 'Центр Москвы', 'weekdays': [0, 2], 'part': 'вечер', 'hours': 2, 'ages': 'Выпускники', 'skills': ['Школьные предметы', 'Английский', 'Педагогика']},
    'life':      {'title': 'Кулинарная мастерская', 'role': 'life', 'program': 'Практические занятия', 'where': 'Студия фонда',
                  'zone': 'Центр Москвы', 'weekdays': [2], 'part': 'день', 'hours': 3, 'ages': 'Взрослые', 'skills': ['Кулинария']},
    'pack':      {'title': 'Подготовка продукции', 'role': 'packing', 'program': 'Магазин фонда', 'where': 'Студия фонда',
                  'zone': 'Центр Москвы', 'weekdays': [4], 'part': 'вечер', 'hours': 3, 'ages': None, 'skills': ['Шитьё и вышивка', 'Валяние']},
    'fair':      {'title': 'Ярмарки фонда', 'role': 'fair', 'program': 'Магазин фонда', 'where': 'Даниловский Event Hall и маркеты',
                  'zone': 'Юг', 'weekdays': [5, 6], 'part': 'день', 'hours': 8, 'ages': None, 'skills': ['Продажи', 'Соцсети']},
    'event':     {'title': 'Выставки и праздники', 'role': 'event', 'program': 'События фонда', 'where': 'ИКЦ «Тверская 15»',
                  'zone': 'Центр Москвы', 'weekdays': [3, 4, 5], 'part': 'вечер', 'hours': 4, 'ages': None, 'skills': ['Фотография', 'Соцсети']},
    'sorochany': {'title': 'Зимняя неделя в Сорочанах', 'role': 'escort', 'program': 'Выездные проекты', 'where': 'Сорочаны',
                  'zone': 'Московская область', 'weekdays': None, 'months': [2], 'part': 'неделя', 'hours': 40, 'ages': 'Взрослые', 'skills': ['Спорт и игры']},
    'residence': {'title': 'Арт-резиденция в Учме', 'role': 'escort', 'program': 'Выездные проекты', 'where': 'Учма, Ярославская область',
                  'zone': 'Другой город', 'weekdays': None, 'months': [7], 'part': 'неделя', 'hours': 60, 'ages': '8–12 лет', 'skills': ['Живопись и рисунок', 'Театр', 'Спорт и игры']},
}

# Сегменты: явка, сколько смен в месяц, отмены в последний момент, насколько часто заполнен профиль.
SEGMENTS = {
    'core':     {'label': 'Ядро: ходят регулярно', 'attend': (0.86, 0.97), 'per_month': (3, 5), 'late': (0.0, 0.06), 'profile': 0.95},
    'friend':   {'label': 'Друзья фонда: приходят на отдельные события', 'attend': (0.75, 0.92), 'per_month': (0.3, 1.2), 'late': (0.03, 0.12), 'profile': 0.6},
    'risk':     {'label': 'Под риском ухода', 'attend': (0.55, 0.75), 'per_month': (1, 3), 'late': (0.1, 0.25), 'profile': 0.7},
    'newcomer': {'label': 'Новички на разных этапах', 'attend': (0.8, 1.0), 'per_month': (0, 1), 'late': (0.0, 0.1), 'profile': 0.35},
    'reserve':  {'label': 'Резерв: пришли в ковид и пропали', 'attend': (0.7, 0.9), 'per_month': (0, 0), 'late': (0.0, 0.1), 'profile': 0.2},
    'special':  {'label': 'Особые случаи', 'attend': (0.8, 0.95), 'per_month': (0.5, 2), 'late': (0.0, 0.08), 'profile': 0.8},
}

# series — где человек обычно помогает. stage — этап пути (как в Interviews.js и VolunteerRecord.js).
PEOPLE = [
    # ядро
    dict(id='sveta', name='Светлана Ким', age=44, seg='core', since=2019, area='Север', series=['lab', 'art'], skills=['Керамика', 'Педагогика'], dirs=['Творчество', 'Помощь на занятиях'], hours=168, note='Наставница новичков, ведёт Егора'),
    dict(id='kirill', name='Кирилл Смирнов', age=31, seg='core', since=2020, area='Восток', series=['event', 'sorochany'], skills=['Спорт и игры'], dirs=['Мероприятия', 'Помощь на занятиях'], hours=140),
    dict(id='polina', name='Полина Зайцева', age=27, seg='core', since=2023, area='Центр Москвы', series=['pack', 'fair'], skills=['Валяние', 'Шитьё и вышивка'], dirs=['Творчество', 'Ярмарки'], hours=52),
    dict(id='anna', name='Анна Соколова', age=32, seg='core', since=2026, area='Центр Москвы', series=['art', 'fair'], skills=['Керамика', 'Живопись и рисунок'], dirs=['Творчество', 'Помощь на занятиях'], hours=46, note='С фондом 7 месяцев'),
    dict(id='tatiana', name='Татьяна Воронина', age=63, seg='core', since=2018, area='Запад', series=['life', 'pack'], skills=['Кулинария', 'Шитьё и вышивка'], dirs=['Творчество', 'Ярмарки'], hours=410),
    dict(id='artem', name='Артём Белов', age=29, seg='core', since=2022, area='Юг', series=['study'], skills=['Школьные предметы', 'Педагогика'], dirs=['Обучение'], hours=190),
    dict(id='liza', name='Елизавета Громова', age=35, seg='core', since=2021, area='Центр Москвы', series=['lab', 'event'], skills=['Психология'], dirs=['Психолог, логопед', 'Помощь на занятиях'], hours=230),
    dict(id='sergey', name='Сергей Панов', age=41, seg='core', since=2019, area='Московская область', series=['art', 'sorochany', 'residence'], skills=['Спорт и игры', 'Театр'], dirs=['Мероприятия', 'Помощь на занятиях'], hours=520),
    # друзья фонда
    dict(id='vera', name='Вера Новикова', age=26, seg='friend', since=2025, area='Север', series=['event', 'fair'], skills=['Фотография'], dirs=['Фото, видео, соцсети', 'Мероприятия'], hours=18),
    dict(id='timur', name='Тимур Ахмедов', age=38, seg='friend', since=2022, area='Восток', series=['sorochany', 'fair'], skills=[], dirs=['Мероприятия'], hours=20, note='Сам писал в анкете, что может возить материалы'),
    dict(id='ksenia', name='Ксения Рябова', age=30, seg='friend', since=2023, area='Центр Москвы', series=['event'], skills=['Психология'], dirs=['Мероприятия'], hours=56, paused='2026-12-01'),
    dict(id='daria', name='Дарья Лисицина', age=24, seg='friend', since=2024, area='Юг', series=['fair'], skills=['Продажи', 'Соцсети'], dirs=['Ярмарки'], hours=64),
    dict(id='gleb', name='Глеб Соловьёв', age=34, seg='friend', since=2025, area='Запад', series=['fair', 'event'], skills=['Продажи'], dirs=['Ярмарки', 'Мероприятия'], hours=24, note='Приходит с коллегами раз в квартал'),
    dict(id='roman', name='Роман Зуев', age=36, seg='friend', since=2024, area='Другой город', series=[], skills=['IT'], dirs=['Юрист, IT, маркетинг'], hours=30, online=True),
    dict(id='nastya', name='Анастасия Кравец', age=39, seg='friend', since=2023, area='Центр Москвы', series=[], skills=['Право'], dirs=['Юрист, IT, маркетинг'], hours=22, online=True),
    dict(id='sofia', name='Софья Мартынова', age=21, seg='friend', since=2025, area='Север', series=['event', 'fair'], skills=['Дизайн', 'Соцсети', 'Фотография'], dirs=['Фото, видео, соцсети'], hours=16),
    # под риском
    dict(id='dima', name='Дмитрий Орлов', age=28, seg='risk', since=2024, area='Восток', series=['art', 'event'], skills=['Театр'], dirs=['Творчество', 'Мероприятия'], hours=38, note='Два пропуска подряд'),
    dict(id='marina', name='Марина Белова', age=33, seg='risk', since=2025, area='Юг', series=['lab'], skills=['Музыка и вокал'], dirs=['Творчество'], hours=15, note='Говорила координатору, что думает уйти'),
    dict(id='nikita', name='Никита Седов', age=22, seg='risk', since=2025, area='Новая Москва', series=['study', 'event'], skills=['Английский', 'Спорт и игры'], dirs=['Обучение', 'Мероприятия'], hours=27, note='Сессия, отменяет в последний момент'),
    # новички
    dict(id='egor', name='Егор Мельников', age=25, seg='newcomer', since=2026, area='Центр Москвы', series=['art'], skills=['Живопись и рисунок'], dirs=['Помощь на занятиях'], hours=0, stage='meeting_booked', test=10, modules=4, note='Встреча 23 октября, наставница — Светлана'),
    dict(id='mila', name='Мила Орлова', age=23, seg='newcomer', since=2026, area='Север', series=[], skills=['Фотография'], dirs=['Фото, видео, соцсети'], hours=0, stage='onboarding', modules=2),
    dict(id='alina', name='Алина Фёдорова', age=19, seg='newcomer', since=2026, area='Запад', series=[], skills=['Живопись и рисунок'], dirs=['Творчество'], hours=0, stage='applied', modules=0),
    dict(id='maxim', name='Максим Ильин', age=27, seg='newcomer', since=2026, area='Юг', series=[], skills=['Спорт и игры'], dirs=['Мероприятия', 'Помощь на занятиях'], hours=0, stage='meeting_done', test=8, modules=4, avail={'сб': ['день'], 'вс': ['день', 'вечер']}, note='Итог встречи: подобрать первое занятие'),
    dict(id='oleg', name='Олег Петров', age=45, seg='newcomer', since=2026, area='Восток', series=[], skills=['Керамика'], dirs=['Творчество'], hours=0, stage='meeting_done', test=9, modules=4, record='Получу её', note='Ждём справку о несудимости'),
    dict(id='farid', name='Фарид Гасанов', age=31, seg='newcomer', since=2026, area='Московская область', series=[], skills=[], dirs=['Пока не знаю'], hours=0, stage='applied', modules=0),
    dict(id='kira', name='Кира Белоусова', age=26, seg='newcomer', since=2026, area='Центр Москвы', series=[], skills=['Кулинария'], dirs=['Творчество', 'Ярмарки'], hours=0, stage='meeting_booked', modules=0, note='Записалась на встречу, знакомство не начала'),
    dict(id='lev', name='Лев Ермаков', age=34, seg='newcomer', since=2026, area='Север', series=[], skills=['Видео и монтаж'], dirs=['Фото, видео, соцсети'], hours=0, stage='applied', modules=0, last_login_days=31, note='Заполнил анкету месяц назад и больше не заходил'),
    dict(id='maria_d', name='Мария Дьякова', age=29, seg='newcomer', since=2026, area='Центр Москвы', series=['life'], skills=['Кулинария'], dirs=['Творчество', 'Помощь на занятиях'], hours=3, stage='first_shift_done', test=9, modules=4, note='Был первый выход, обсуждаем продолжение'),
    # резерв
    dict(id='galina', name='Галина Смирнова', age=73, seg='reserve', since=2020, area='Север', series=['life'], skills=['Кулинария', 'Шитьё и вышивка'], dirs=['Творчество'], hours=85, reserve='ready', avail={'пн': ['день'], 'ср': ['день']}),
    dict(id='irina', name='Ирина Ковалёва', age=38, seg='reserve', since=2020, area='Запад', series=['lab'], skills=['Живопись и рисунок', 'Педагогика'], dirs=['Творчество', 'Обучение'], hours=44, reserve='awaiting_reply'),
    dict(id='vika', name='Виктория Шевцова', age=27, seg='reserve', since=2020, area='Восток', series=['fair'], skills=['Продажи'], dirs=['Ярмарки'], hours=12, reserve='unverified'),
    dict(id='stas', name='Станислав Орехов', age=35, seg='reserve', since=2021, area='Юг', series=['event'], skills=['Спорт и игры'], dirs=['Мероприятия'], hours=9, reserve='unverified'),
    dict(id='katya_l', name='Екатерина Лапина', age=31, seg='reserve', since=2020, area='Центр Москвы', series=['lab'], skills=['Музыка и вокал'], dirs=['Творчество'], hours=31, reserve='paused', note='Декрет, вернётся весной'),
    dict(id='nikolay', name='Николай Фомин', age=52, seg='reserve', since=2021, area='Московская область', series=['sorochany', 'art'], skills=['Спорт и игры'], dirs=['Мероприятия'], hours=48, reserve='ready', avail={'сб': ['день'], 'вс': ['день']}),
    dict(id='alena', name='Алёна Крылова', age=26, seg='reserve', since=2020, area='Новая Москва', series=['event'], skills=['Фотография'], dirs=['Фото, видео, соцсети'], hours=6, reserve='no_invites'),
    dict(id='ruslan', name='Руслан Хабибуллин', age=30, seg='reserve', since=2021, area='Север', series=['study'], skills=['Школьные предметы'], dirs=['Обучение'], hours=20, reserve='unreachable'),
    # особые случаи
    dict(id='alexey', name='Алексей Ким', age=17, seg='special', since=2026, area='Центр Москвы', series=['fair', 'event'], skills=['Соцсети'], dirs=['Мероприятия', 'Ярмарки'], hours=8, note='17 лет: только открытые события'),
    dict(id='ludmila', name='Людмила Захарова', age=72, seg='special', since=2018, area='Запад', series=['art', 'pack'], skills=['Валяние', 'Шитьё и вышивка'], dirs=['Творчество'], hours=360, note='Предпочитает звонок, бот не подключала'),
    dict(id='yan', name='Ян Ковальчук', age=44, seg='special', since=2025, area='Другой город', series=['residence'], skills=['Театр', 'Музыка и вокал'], dirs=['Мероприятия'], hours=60, avail={}, note='Живёт в Ярославле, помогает только на резиденции'),
    dict(id='olya_f', name='Ольга Фролова', age=40, seg='special', since=2024, area='Юг', series=['art'], skills=['Керамика'], dirs=['Творчество'], hours=70, note='Волонтёр фонда-партнёра'),
]


def u(lo_hi):
    return round(rnd.uniform(*lo_hi), 2)


def a_date(sid):
    """Дата за последний год, подходящая серии по дню недели или месяцу выезда."""
    s = SERIES[sid]
    for _ in range(400):
        d = YEAR_AGO + timedelta(days=rnd.randrange(365))
        if d >= TODAY:
            continue
        if (s['weekdays'] is None and d.month in s['months']) or (s['weekdays'] and d.weekday() in s['weekdays']):
            return d
    return None


def participation(p, seg):
    """Отклики и явка за год. Статусы — как в планировании: приглашён → подтвердил → пришёл / не пришёл / отменил."""
    if p.get('stage') == 'first_shift_done':
        return [{'series': 'life', 'date': (TODAY - timedelta(days=9)).isoformat(), 'role': 'life', 'status': 'attended', 'hours': 3}]
    if not p['series'] or seg['per_month'] == (0, 0) or p.get('stage'):
        return []
    months = 12 if p['since'] < 2026 else 7
    if p.get('paused'):
        months -= 3
    attend, late = u(seg['attend']), u(seg['late'])
    recs, trips = [], set()
    for _ in range(max(1, round(u(seg['per_month']) * months))):
        sid = rnd.choices(p['series'], weights=[3] + [1] * (len(p['series']) - 1))[0]
        if SERIES[sid]['weekdays'] is None:
            if sid in trips:      # выезд бывает раз в год
                continue
            trips.add(sid)
        d = a_date(sid)
        if not d:
            continue
        r = rnd.random()
        status = 'attended' if r < attend else ('cancelled_late' if r < attend + late else 'absent')
        recs.append({'series': sid, 'date': d.isoformat(), 'role': SERIES[sid]['role'], 'status': status,
                     'hours': SERIES[sid]['hours'] if status == 'attended' else 0})
    recs.sort(key=lambda x: x['date'])
    if p['id'] == 'dima':
        for x in recs[-2:]:
            x['status'], x['hours'] = 'absent', 0
    return recs


def profile(p, seg):
    """Профиль, который волонтёр заполняет сам. Незаполненное — None: это и есть повод для подсказки."""
    filled = rnd.random() < seg['profile']
    if 'avail' in p:
        avail = p['avail'] or None
    elif filled and p['series']:
        avail = {}
        for sid in p['series']:
            s = SERIES[sid]
            for wd in (s['weekdays'] or []):
                avail.setdefault(WEEK[wd], [])
                if s['part'] not in avail[WEEK[wd]]:
                    avail[WEEK[wd]].append(s['part'])
        avail = avail or None
    else:
        avail = None
    ages = sorted({SERIES[s]['ages'] for s in p['series'] if SERIES[s]['ages']}) if filled else None
    places = (['Онлайн'] if p.get('online') else []) + sorted({SERIES[s]['where'] for s in p['series']}) if filled else None
    freq = {'core': 'Каждую неделю', 'risk': '2–3 раза в месяц'}.get(p['seg'], 'Раз в месяц') if filled else None
    updated = (TODAY - timedelta(days=rnd.randint(5, 200))).isoformat() if avail else None
    if p['seg'] == 'reserve':
        updated = '2026-10-01' if p.get('reserve') == 'ready' else None
    return {'availability': avail, 'availability_updated': updated, 'age_groups': ages or None,
            'places': places or None, 'frequency': freq, 'paused_until': p.get('paused')}


def stats(recs, p):
    confirmed = len(recs)
    attended = sum(r['status'] == 'attended' for r in recs)
    last = max((r['date'] for r in recs if r['status'] == 'attended'), default=None)
    if not last and p['seg'] == 'reserve':
        last = f'{rnd.choice([2021, 2022])}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}'
    return {'invited_12m': confirmed + rnd.randint(0, max(1, confirmed // 3)), 'confirmed_12m': confirmed,
            'attended_12m': attended, 'absent_12m': sum(r['status'] == 'absent' for r in recs),
            'late_cancel_12m': sum(r['status'] == 'cancelled_late' for r in recs),
            'hours_12m': sum(r['hours'] for r in recs), 'hours_total': p['hours'] or sum(r['hours'] for r in recs),
            'last_attended': last,
            'series_attended': {s: sum(1 for r in recs if r['series'] == s and r['status'] == 'attended') for s in sorted({r['series'] for r in recs})},
            # Резерв ходил раньше, в 2020–2022: история из старой базы, не за последний год
            'series_attended_before': {s: rnd.randint(2, 8) for s in p['series']} if p['seg'] == 'reserve' else {}}


def activity(p):
    """Действия в кабинете и боте: заходил ли, видел ли подборку смен, открывал ли приглашения."""
    seg = p['seg']
    if seg == 'reserve':
        last = date(rnd.choice([2021, 2022]), rnd.randint(1, 12), rnd.randint(1, 28))
    else:
        last = TODAY - timedelta(days=p.get('last_login_days', rnd.randint(0, 45 if seg == 'risk' else 14)))
    bot = seg != 'reserve' and p['id'] != 'ludmila' and rnd.random() < (0.85 if seg in ('core', 'newcomer') else 0.55)
    active = seg in ('core', 'friend', 'risk', 'special') or p.get('stage') == 'first_shift_done'
    return {'last_login': last.isoformat(), 'telegram_bot': bot,
            'feed_views_30d': rnd.randint(1, 8) if active else 0,
            'invites_opened_30d': rnd.randint(0, 4) if active else 0}


def anketa(p):
    record = p.get('record') or ('Справка уже есть' if p['seg'] in ('core', 'special', 'risk') or p['since'] < 2025 or rnd.random() < 0.4 else 'Получу её')
    if p['id'] == 'alexey':
        record = 'Получу её'
    return {'area': p['area'], 'directions': p['dirs'], 'skills': p['skills'],
            'participation': 'Каждую неделю' if p['seg'] == 'core' else ('Пока не знаю' if p['dirs'] == ['Пока не знаю'] else 'На отдельных событиях'),
            'online': bool(p.get('online')) or rnd.random() < 0.25,
            'volExp': 'Да' if p['since'] < 2026 or rnd.random() < 0.3 else 'Нет',
            'specialExp': 'Да' if p['since'] < 2025 else rnd.choice(['Да', 'Нет']),
            'record': record, 'source': rnd.choice(['ВКонтакте', 'Telegram', 'Сайт фонда', 'Добро.РФ', 'mos.ru', 'Друзья', 'Мероприятие фонда']),
            'submittedAt': f'{p["since"]}-{rnd.randint(1, 9 if p["since"] == 2026 else 12):02d}-{rnd.randint(1, 28):02d}'}


def build():
    out = []
    for p in PEOPLE:
        seg = SEGMENTS[p['seg']]
        recs = participation(p, seg)
        stage = p.get('stage') or {'core': 'regular', 'friend': 'occasional', 'risk': 'regular', 'special': 'regular', 'reserve': 'reserve'}[p['seg']]
        out.append({
            # имя — только для экрана; в подбор и во внешние сервисы не передаётся
            'id': p['id'], 'name': p['name'], 'age': p['age'],
            'segment': p['seg'], 'segment_label': seg['label'], 'stage': stage, 'with_fund_since': p['since'],
            'reserve_status': p.get('reserve'),
            'anketa': anketa(p),
            'onboarding': {'modules_done': p.get('modules', 4), 'test_score': p.get('test')},
            'profile': profile(p, seg),
            'participation_12m': recs,
            'stats': stats(recs, p),
            'activity': activity(p),
            'coordinator_note': p.get('note', ''),
        })
    return out


def main():
    people = build()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'synthetic-volunteers.json').write_text(json.dumps({'generated_for': TODAY.isoformat(), 'series': SERIES, 'volunteers': people},
                                                              ensure_ascii=False, indent=1) + '\n')
    cols = ['id', 'name', 'age', 'segment_label', 'stage', 'with_fund_since', 'area', 'directions', 'skills', 'participation', 'online',
            'record', 'availability', 'age_groups', 'attended_12m', 'late_cancel_12m', 'hours_total', 'last_attended', 'last_login',
            'telegram_bot', 'reserve_status', 'coordinator_note']
    with open(OUT / 'synthetic-volunteers.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(cols)
        for v in people:
            a, pr, s, ac = v['anketa'], v['profile'], v['stats'], v['activity']
            w.writerow([v['id'], v['name'], v['age'], v['segment_label'], v['stage'], v['with_fund_since'], a['area'], '; '.join(a['directions']),
                        '; '.join(a['skills']), a['participation'], a['online'], a['record'],
                        '; '.join(f'{d} {"/".join(x)}' for d, x in (pr['availability'] or {}).items()) or 'не заполнено',
                        '; '.join(pr['age_groups'] or []) or 'не заполнено', s['attended_12m'], s['late_cancel_12m'], s['hours_total'],
                        s['last_attended'] or '', ac['last_login'], ac['telegram_bot'], v['reserve_status'] or '', v['coordinator_note']])
    counts = {}
    for v in people:
        counts[v['segment_label']] = counts.get(v['segment_label'], 0) + 1
    no_avail = sum(1 for v in people if not v['profile']['availability'])
    print(len(people), 'волонтёров:', counts, '| без заполненной доступности:', no_avail)


if __name__ == '__main__':
    main()
