/*
  Демо-данные для экрана координатора: вымышленные кандидаты на разных этапах.
  Анкета, которую вы заполните сами, добавится к ним сверху.
*/
window.DEMO_CANDIDATES = [
  {
    id: "demo-1", name: "Ирина Ковалёва", birthdate: "1988-04-12", phone: "+7 916 000-11-22", email: "irina@example.com",
    channels: ["Telegram"], telegram: "@irina_k", area: "Центр Москвы",
    directions: ["Проводить творческие занятия и мастер-классы"], skills: ["Керамика", "Живопись и рисунок"],
    profession: "Художник-керамист", volExp: "Да", specialExp: "Нет, но готов(а) попробовать", audience: ["Подростки", "Взрослые"],
    format: "Очно", regularity: "Каждую неделю", horizon: "От полугода", slots: ["Выходные·Утро", "Выходные·День"],
    places: ["Студия в центре (м. Театральная)", "Загородная мастерская (Арт-субботы, на машине или электричке)"], physical: [], comfort: [],
    source: "ВКонтакте", record: "Да", consentPD: true, submittedAt: "2026-10-19T10:20:00",
    progress: { modules: 6, test: 13, meeting: "Сб, 25 октября, 11:00" }
  },
  {
    id: "demo-2", name: "Дмитрий Орлов", birthdate: "1995-09-03", phone: "+7 925 000-33-44", email: "d.orlov@example.com",
    channels: ["WhatsApp", "Телефонный звонок"], area: "Юг / Юго-Запад",
    directions: ["Мероприятия: встреча гостей, навигация, монтаж", "Магазин и ярмарки: упаковка, продажи на маркетах"], skills: ["Спорт и подвижные игры", "Продажи"],
    profession: "Менеджер по продажам", volExp: "Нет", specialExp: "Нет, но готов(а) попробовать", audience: ["Не важно"],
    format: "Очно", regularity: "Пару раз в месяц", horizon: "3–6 месяцев", slots: ["Выходные·День", "Будни·Вечер"],
    places: ["Ярмарки и события по Москве"], physical: ["Помочь человеку на коляске", "Перенести или собрать оборудование"], comfort: [],
    source: "Добро.РФ", record: "Хочу сначала обсудить", consentPD: true, submittedAt: "2026-10-20T18:05:00",
    progress: { modules: 6, test: 12, meeting: null }
  },
  {
    id: "demo-3", name: "Галина Петровна Смирнова", birthdate: "1953-02-21", phone: "+7 903 000-55-66", email: "g.smirnova@example.com",
    channels: ["Телефонный звонок", "SMS"], area: "Север / Северо-Восток",
    directions: ["Обучение: репетиторство, бытовые и жизненные навыки"], skills: ["Школьные предметы", "Кулинария", "Шитьё и вышивка"],
    profession: "Учитель математики на пенсии", volExp: "Да", specialExp: "Да", audience: ["Дети 7–12 лет", "Взрослые"],
    format: "Очно", regularity: "Каждую неделю", horizon: "От полугода", slots: ["Будни·Утро", "Будни·День"],
    places: ["Студия в центре (м. Театральная)"], physical: ["Нет, физическая помощь мне не подходит"], comfort: ["Крупный шрифт на сайте", "Звонок вместо переписки"],
    source: "Друзья или знакомые", record: "Справка уже есть", consentPD: true, submittedAt: "2026-10-18T09:40:00",
    progress: { modules: 3, test: null, meeting: null }
  },
  {
    id: "demo-4", name: "Алексей Ким", birthdate: "2002-11-30", phone: "+7 977 000-77-88", email: "kim.a@example.com",
    channels: ["Telegram"], telegram: "@alexkim", area: "Восток / Юго-Восток",
    directions: ["Фото, видео, монтаж"], skills: ["Фотография", "Видео и монтаж"],
    profession: "Студент, снимаю свадьбы", volExp: "Нет", specialExp: "Нет, хочу сначала обсудить на встрече", audience: ["Не важно"],
    format: "И очно, и онлайн", regularity: "Только на отдельных событиях", horizon: "Пока не знаю", slots: ["Выходные·День", "Выходные·Вечер"],
    places: [], physical: [], comfort: [],
    source: "Telegram", record: "Да", consentPD: true, submittedAt: "2026-10-21T08:15:00",
    progress: { modules: 0, test: null, meeting: null }
  }
];
