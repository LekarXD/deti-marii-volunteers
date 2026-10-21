# deti-marii-volunteers

Веб-платформа волонтёров фонда «Дети Марии» (хакатон, кейс 3).

Единое цифровое пространство: профиль волонтёра, обучение, каталог возможностей, подбор, учёт участия, коммуникация, мотивация и рабочее пространство для команды фонда.

Материалы и постановка задачи — в [`materials/`](materials/README.md).

**Путь кандидата** «анкета → знакомство с фондом → тест → встреча с координатором» — в прототипе «Опора»: `prototype/Apply.dc.html`, `Onboarding.dc.html`, `ApplicationStatus.dc.html`. Тексты правятся в `prototype/content/`, после правки — `python3 scripts/build_prototype.py`. Первая версия на простом HTML (`prototype/index.html`) оставлена как черновик, подробнее — [prototype/README.md](prototype/README.md).

Прототип «Опора» и все сохранённые артефакты его подготовки — в [`materials/04-дизайн/прототип-до-фактуры/`](materials/04-дизайн/прототип-до-фактуры/README.md). [Интерактивный холст Claude Design](https://claude.ai/artifact/KeurJ9hsWHTx9g8ovz512u).

**Расширенный прототип «Опора»**: [расписание, роли, участники и группы](prototype/README-opora.md). Открывается через `prototype/Main.dc.html`; исходники в `prototype-src/`. Анкета и онбординг — экраны `Apply`, `Onboarding`, `ApplicationStatus`.
