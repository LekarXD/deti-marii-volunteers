"""Прототип подбора на ближайших сменах. Без ИИ и без персональных данных: только признаки.

Две стороны одного расчёта:
1. Волонтёр открывает «Возможности» → смены идут в нашем порядке. Наверху блок «Подобрано для вас»
   (как на главной «Опоры»), у него кнопка «Почему так» с причинами. Остальные смены — обычным списком.
2. Координатор открывает смену → видит, кого позвать, почему, и видел ли человек эту смену.

Расписание из профиля — рекомендация: смены в неудобные дни не прячем, а опускаем ниже.

    python3 scripts/match_demo.py
"""
import json
import pathlib
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from matching_features import blocked, features, score, plural      # noqa: E402

DATA = pathlib.Path(__file__).resolve().parents[1] / 'materials/05-продукт/данные'
VOLS = json.loads((DATA / 'synthetic-volunteers.json').read_text())
SERIES, VOL = VOLS['series'], VOLS['volunteers']
TODAY = date.fromisoformat(VOLS['generated_for'])
SHIFTS = [s for s in json.loads((DATA / 'synthetic-shifts.json').read_text())['shifts']
          if TODAY.isoformat() <= s['date'] <= (TODAY + timedelta(days=21)).isoformat()]
try:        # если веса уже обучены — берём их, иначе ручные
    from matching_features import HAND_WEIGHTS
    W = {k: v for k, v in json.loads((DATA / 'learned-weights.json').read_text())['learned_weights_share'].items()}
except FileNotFoundError:
    W = HAND_WEIGHTS


def fit_for(v, sh):
    s, st = SERIES[sh['series']], v['stats']
    seen = dict(st.get('series_attended_before') or {})          # резерв: выходы 2020–2022 из старой базы
    for k, n in st['series_attended'].items():
        seen[k] = seen.get(k, 0) + n
    f, why = features(v, sh['series'], s, sh['date'], seen, st['attended_12m'], st['confirmed_12m'], st['invited_12m'])
    if v.get('reserve_status') == 'ready':
        why.append('из резерва, готов вернуться')
    return score(f, W), f, why


def need_left(sh):
    return max(0, sh['need'] - len(sh['confirmed']))


def urgency(sh):
    days = (date.fromisoformat(sh['date']) - TODAY).days
    return need_left(sh) / sh['need'] * (1.0 if days <= 7 else 0.6 if days <= 14 else 0.3)


def feed(vid):
    """Порядок смен в «Возможностях» для одного волонтёра."""
    v = next(x for x in VOL if x['id'] == vid)
    items = []
    for sh in SHIFTS:
        if v['id'] in sh['confirmed'] or blocked(v, SERIES[sh['series']], sh['date']):
            continue
        sc, f, why = fit_for(v, sh)
        # Порядок: насколько подходит + нужны ли ещё люди. Срочность сама по себе не поднимает неподходящее
        rank = 0.7 * sc + 0.3 * urgency(sh) * (1 if sc >= 0.5 else 0) - (1 if not need_left(sh) else 0)   # заполненные — в конец
        items.append((rank, sc, sh, why))
    items.sort(key=lambda x: -x[0])
    top = [x for x in items[:2] if x[1] >= 0.55 and need_left(x[2])]
    print(f'\n### {v["name"]} — {v["segment_label"].split(":")[0].lower()}')
    if top:
        print('  Подобрано для вас                                     [Почему так]')
        for _, sc, sh, why in top:
            print(f'   ▸ {SERIES[sh["series"]]["title"]:24} {sh["date"]} {sh["time"]:12} записались {len(sh["confirmed"])} из {sh["need"]}')
            print(f'       почему: {"; ".join(why) or "подходит по направлениям"}')
    print('  Все смены')
    for _, sc, sh, why in items[len(top):len(top) + 4]:
        print(f'     {SERIES[sh["series"]]["title"]:24} {sh["date"]} {sh["time"]:12} записались {len(sh["confirmed"])} из {sh["need"]}')


def coordinator(sh):
    s = SERIES[sh['series']]
    left = need_left(sh)
    rows, out = [], {}
    for v in VOL:
        r = blocked(v, s, sh['date'])
        if r:
            out.setdefault(r, []).append(v['name'].split()[0])
            continue
        if v['id'] in sh['confirmed']:
            continue
        sc, f, why = fit_for(v, sh)
        rows.append((sc, v, why))
    rows.sort(key=lambda x: -x[0])
    days = (date.fromisoformat(sh['date']) - TODAY).days
    print(f'\n### {s["title"]}, {sh["date"]} {sh["time"]} — нужно {sh["need"]}, записались {len(sh["confirmed"])}, до смены {days} {plural(days, "день", "дня", "дней")}')
    if left and sum(1 for x in rows if x[0] >= 0.6) < left:
        print('    Хорошо подходящих меньше, чем свободных мест: можно позвать резерв или открыть смену всем')
    for sc, v, why in rows[:4]:
        resp = sh['responses'].get(v['id'])
        state = {'invited': 'приглашён, не ответил', 'declined': 'отказался'}.get(resp, 'видел в подборке' if v['activity']['feed_views_30d'] else 'не открывал подборку')
        print(f'    {sc:.2f} {v["name"]:20} [{state}{", бот" if v["activity"]["telegram_bot"] else ""}] {"; ".join(why)}')
    for r, names in sorted(out.items(), key=lambda x: -len(x[1]))[:3]:
        print(f'    ✕ {r}: {", ".join(names)}')


def main():
    print('=== «Возможности» глазами волонтёра ===')
    for vid in ['anna', 'maxim', 'nikolay', 'vera']:
        feed(vid)
    print('\n=== Смена глазами координатора ===')
    shown = set()
    for sh in sorted((s for s in SHIFTS if need_left(s)), key=lambda s: -urgency(s)):
        if sh['series'] not in shown and len(shown) < 3:
            shown.add(sh['series'])
            coordinator(sh)


if __name__ == '__main__':
    main()
