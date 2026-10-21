# Выгрузка стены ВК фонда

`posts-2018-2026.json` — все 2 340 постов группы https://vk.com/club1825701 с 29.09.2018 по 19.10.2026: id, дата и время (МСК), ссылка, типы вложений, текст.
Тексты очищены от HTML и вики-разметки ВК, в остальном как в группе. Собрано 2026-10-21 через внутренний эндпоинт стены ВК из браузера с входом.

Искать удобно так:

```bash
python3 -c "import json;[print(p['date'],p['url'],p['text'][:120]) for p in json.load(open('posts-2018-2026.json')) if 'волонт' in p['text'].lower()]"
```

## events-tagged.jsonl

1 736 постов о мероприятиях из «Анализ мероприятий ВК 2011–2026.xlsx», размеченные в поля смены из планирования: `is_fund_event`, `post_kind`, `kind`, `format`, `program`, `audience`, `institutions`, `venue`, `region`, `event_date`/`event_end`, `time_start`/`time_end`, `regular_weekday`, `multi_day`, `roles` (id из `prototype-src/roles.json` плюс `escort`, `event`), `skills` (из анкеты), `volunteers_mentioned`, `volunteers_needed`, `volunteer_tasks`, `children_contact`, `confidence`. Всё — только из текста поста; чего нет в тексте, то `null`. Вручную не проверялось: поле `confidence` показывает, насколько разметчик уверен.
