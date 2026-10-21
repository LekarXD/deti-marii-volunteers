/*
  Анкета волонтёра, версия 4.
  Это данные, а не код: поля, варианты и подсказки можно править прямо здесь.
  Обоснование каждого поля — materials/05-продукт/Анкета v2.md

  Типы полей: section (заголовок блока с иконкой), text, email, tel, date, textarea, select (чипы, один ответ),
  chips (чипы, несколько; варианты могут быть { label, icon }, а groups — группы с showIf), tiles (плитки с иконками), radio, checkbox, grid, roles, consent.
  required — обязательное; optional — пометка «по желанию»; why — короткое «зачем спрашиваем» под полем;
  showIf — показывать, только если в другом поле выбран один из вариантов;
  exclusive — варианты, которые нельзя выбрать вместе с остальными (например, «Нет, не подходит»);
  mask — автоформат ввода: name (заглавные буквы), phone (+7 (999) 123-45-67), telegram (@ник);
  half — поле в половину ширины (два в ряд).
*/
window.FORM = {
  title: "Анкета волонтёра",
  intro: "Мы рады, что вы хотите помогать. Три коротких шага — около 5 минут.",
  /* Путь кандидата — карточка справа от анкеты */
  path: [
    { icon: "edit", title: "Анкета", meta: "5 минут" },
    { icon: "book", title: "Знакомство с фондом", meta: "онлайн, около 20 минут" },
    { icon: "calendar", title: "Встреча с координатором", meta: "30 минут, онлайн или в студии" }
  ],
  pathNote: "После встречи откроется платформа: занятия, обучение и сообщения.",
  steps: [
    {
      id: "about",
      title: "О вас",
      fields: [
        { id: "firstName", label: "Имя", type: "text", required: true, mask: "name", half: true,
          placeholder: "Михаил", autocomplete: "given-name" },
        { id: "lastName", label: "Фамилия", type: "text", required: true, mask: "name", half: true,
          placeholder: "Михайлов", autocomplete: "family-name" },
        { id: "birthdate", label: "Дата рождения", type: "date", required: true, half: true },
        { id: "phone", label: "Телефон", type: "tel", required: true, mask: "phone", autocomplete: "tel", half: true,
          placeholder: "+7 (999) 123-45-67" },
        { id: "email", label: "Электронная почта", type: "email", required: true, autocomplete: "email", half: true,
          placeholder: "name@mail.ru" },
        { id: "telegram", label: "Ник в Telegram", type: "text", mask: "telegram", placeholder: "@username", half: true, optional: true },
        { id: "area", label: "Где вы живёте?", type: "select", required: true,
          options: ["Центр Москвы", "Север", "Восток", "Юг", "Запад", "Новая Москва", "Московская область", "Другой город"] }
      ]
    },
    {
      id: "help",
      title: "Чем хотите помогать",
      fields: [
        { id: "directions", label: "Что вам интересно?", type: "tiles", required: true,
          options: [
            { label: "Творчество", icon: "palette" },
            { label: "Помощь на занятиях", icon: "hand" },
            { label: "Обучение", icon: "academy" },
            { label: "Психолог, логопед", icon: "heart" },
            { label: "Фото, видео, соцсети", icon: "camera" },
            { label: "Мероприятия", icon: "star" },
            { label: "Ярмарки", icon: "home" },
            { label: "Как специалист", icon: "settings" },
            { label: "Пока не знаю", icon: "search" }
          ],
          exclusive: ["Пока не знаю"] },
        /* Навыки показываем только по выбранным направлениям, чтобы не смешивать шитьё и IT */
        { id: "skills", label: "Что умеете или любите делать?", type: "chips", optional: true, allowOther: true,
          showIf: { field: "directions", value: ["Творчество", "Помощь на занятиях", "Обучение", "Психолог, логопед", "Фото, видео, соцсети", "Мероприятия", "Ярмарки", "Как специалист", "Пока не знаю"] },
          groups: [
            { title: "Творчество", showIf: { field: "directions", value: ["Творчество", "Помощь на занятиях", "Мероприятия", "Ярмарки", "Пока не знаю"] },
              options: [{ label: "Керамика", icon: "palette" }, { label: "Живопись и рисунок", icon: "pen" }, { label: "Валяние", icon: "hand" }, { label: "Шитьё и вышивка", icon: "scissors" }, { label: "Кулинария", icon: "flame" }, { label: "Музыка и вокал", icon: "music" }, { label: "Театр", icon: "mask" }] },
            { title: "Обучение и игры", showIf: { field: "directions", value: ["Помощь на занятиях", "Обучение", "Психолог, логопед", "Мероприятия", "Пока не знаю"] },
              options: [{ label: "Педагогика", icon: "academy" }, { label: "Психология", icon: "heart" }, { label: "Школьные предметы", icon: "book" }, { label: "Английский", icon: "globe" }, { label: "Спорт и игры", icon: "dice" }] },
            { title: "Медиа", showIf: { field: "directions", value: ["Фото, видео, соцсети", "Как специалист", "Пока не знаю"] },
              options: [{ label: "Фотография", icon: "camera" }, { label: "Видео и монтаж", icon: "film" }, { label: "Дизайн", icon: "image" }, { label: "Соцсети", icon: "message" }] },
            { title: "Работа фонда", showIf: { field: "directions", value: ["Ярмарки", "Как специалист", "Пока не знаю"] },
              options: [{ label: "Право", icon: "file" }, { label: "Маркетинг", icon: "chart" }, { label: "IT", icon: "screen" }, { label: "Финансы", icon: "database" }, { label: "Продажи", icon: "users" }] }
          ] },
        { id: "participation", label: "Как часто хотели бы помогать?", type: "select", required: true,
          options: ["Каждую неделю", "Иногда, когда получится", "На отдельных событиях", "Пока не знаю"] },
        { id: "online", label: "Могу помогать и онлайн", type: "consent" }
      ]
    },
    {
      id: "final",
      title: "Опыт и документы",
      fields: [
        { id: "volExp", label: "Вы раньше были волонтёром?", type: "select", required: true,
          options: ["Да", "Нет"] },
        { id: "volExpText", label: "Где и что делали?", type: "textarea", optional: true,
          showIf: { field: "volExp", value: "Да" } },
        { id: "specialExp", label: "Общались ли вы с людьми с особенностями развития?", type: "select", required: true,
          options: ["Да", "Нет, но готов(а) попробовать", "Хочу обсудить на встрече"] },
        { id: "specialExpText", label: "Расскажите коротко об этом опыте", type: "textarea", optional: true,
          showIf: { field: "specialExp", value: "Да" } },
        { id: "record", label: "Для работы с детьми нужна справка о несудимости. Готовы её получить?", type: "select", required: true,
          options: ["Да", "Справка уже есть", "Хочу обсудить"],
          why: "Заказать можно бесплатно на Госуслугах — это займёт минуту." },
        { id: "source", label: "Откуда вы узнали о фонде?", type: "select", required: true,
          options: ["ВКонтакте", "Telegram", "Сайт фонда", "Добро.РФ", "mos.ru", "Друзья", "Мероприятие фонда", "Другое"] },
        { id: "consentPD", label: "Я согласен(на) на обработку персональных данных фондом «Дети Марии»", type: "consent", required: true },
        { id: "consentNews", label: "Хочу получать новости и приглашения фонда", type: "consent" }
      ]
    }
  ],

  /* Раньше здесь был шаг онбординга «Профиль для подбора». Убран: физическую помощь и график
     координатор узнает на встрече, а «Когда свободна» и «Как часто» уже есть в профиле на платформе. */
  matching: { title: "", intro: "", fields: [] },

  /* Уменьшительные имена: если человек ввёл такое, мягко просим полное. Не блокирует отправку. */
  shortNames: { "Миша": "Михаил", "Саша": "Александр или Александра", "Маша": "Мария", "Женя": "Евгений или Евгения", "Дима": "Дмитрий", "Катя": "Екатерина", "Настя": "Анастасия", "Лена": "Елена", "Таня": "Татьяна", "Оля": "Ольга", "Аня": "Анна", "Вова": "Владимир", "Петя": "Пётр", "Коля": "Николай", "Серёжа": "Сергей", "Сережа": "Сергей", "Лёша": "Алексей", "Леша": "Алексей", "Паша": "Павел", "Юля": "Юлия", "Света": "Светлана", "Наташа": "Наталья", "Ира": "Ирина", "Даша": "Дарья", "Ваня": "Иван", "Костя": "Константин", "Гриша": "Григорий", "Витя": "Виктор", "Галя": "Галина", "Люба": "Любовь", "Надя": "Надежда", "Соня": "Софья", "Ксюша": "Ксения", "Тёма": "Артём", "Тема": "Артём", "Андрюша": "Андрей", "Жора": "Георгий", "Слава": "Вячеслав или Ярослава" },

  done: {
    title: "Спасибо! Ваша анкета проверяется",
    text: "Пока она на проверке, можно записаться на встречу с координатором и познакомиться с фондом."
  }
};
