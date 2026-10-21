"""Source controlled permission catalog; roles for volunteer activities are unrelated."""
LABELS={
 'staff.manage':'Команда и права доступа','messaging.manage':'Сообщения кандидатов','notifications.manage':'Настройки уведомлений','notifications.send':'Отправка уведомлений','integrations.manage':'Интеграции','assets.manage':'Файлы фонда',
 'candidates.read':'Просмотр кандидатов','candidates.review':'Рассмотрение анкет','candidates.notes':'Внутренние заметки кандидатов','interviews.manage':'Проведение собеседований','roles.manage':'Задачи волонтёров','opportunities.manage':'Волонтёрские возможности','schedule.read':'Просмотр расписания','schedule.manage':'Редактирование расписания','assignments.manage':'Назначения волонтёров',
 'crm.read':'Просмотр базы волонтёров','crm.write':'Работа с базой волонтёров','contacts.review':'Проверка контактов','studio.manage':'Онлайн-занятия и студия','studio.host':'Ведение своего онлайн-занятия',
 'followups.read':'Просмотр сопровождения','followups.manage':'Работа с сопровождением','followups.private_notes':'Закрытые заметки сопровождения','signals.restricted':'Закрытые обращения',
 'knowledge.read':'Просмотр базы знаний','knowledge.write':'Редактирование базы знаний','knowledge.publish':'Публикация базы знаний','knowledge.manage':'Управление базой знаний','ai.manage':'Настройки ИИ','simulator.manage':'Управление тренажёром','simulator.review':'Разбор результатов тренажёра','hours.review':'Проверка часов','profile.requests.review':'Запросы по персональным данным','recognition.manage':'Благодарности и признание',
 'participants.read':'Просмотр участников фонда','participants.write':'Карточки участников фонда','participants.private_notes':'Закрытые заметки участников','groups.read':'Просмотр групп','groups.write':'Редактирование групп',
 'learning.read':'Просмотр обучения','learning.write':'Редактирование обучения','learning.publish':'Публикация обучения','reports.read':'Отчёты фонда',
}
def scopes(permission):
    if permission.startswith(('participants.','groups.','followups.')):return ['foundation','group']
    if permission=='studio.host':return ['webinar']
    return ['foundation']
def permission_catalog():return {'items':[{'permission':name,'label':label,'description':('Весь фонд или конкретная группа.' if 'group' in scopes(name) else 'Только назначенное онлайн-занятие.' if name=='studio.host' else 'Доступ в пределах текущего фонда. Закрытые данные требуют отдельных прав.'),'scope_types':scopes(name)} for name,label in LABELS.items()]}
