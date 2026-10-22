"""Кнопки меню под сообщением бота: каждая открывает тот же раздел, что и команда или текст.

Меню и раздел не копятся в чате: раздел открывается на месте меню, под ним — кнопка «Меню» (см. screen.py).
"""
from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from . import broadcasts, coordinator, db, pcoordinator, platform, pvolunteer, testmode, ui, volunteer

router = Router(name="menu")

COORD_ITEMS = {
    "feed": lambda m, s: coordinator.feed(m, s),
    "events": lambda m, s: coordinator.events_list(m, s),
    "broadcasts": lambda m, s: broadcasts.broadcasts(m, s),
    "new_event": lambda m, s: coordinator.new_event(m, s),
    "exports": lambda m, s: coordinator.exports_menu(m, s),
    "to_vol": lambda m, s: coordinator.to_volunteer_mode(m, s),
}
VOLUNTEER_ITEMS = {
    "my": lambda m, s: volunteer.my_events(m),
    "materials": lambda m, s: volunteer.materials(m),
    "meeting": lambda m, s: volunteer.meeting(m),
    "ask": lambda m, s: volunteer.ask(m, s),
    "settings": lambda m, s: volunteer.settings(m),
    "to_coord": lambda m, s: volunteer.to_coord_mode(m, s),
    "login": lambda m, s: volunteer.login_button(m, s),
    "reset": lambda m, s: testmode.ask_reset(m),
}


@router.callback_query(ui.MenuCB.filter())
async def open_item(cb: CallbackQuery, callback_data: ui.MenuCB, state: FSMContext):
    u = db.ensure_user(cb.message.chat.id, cb.from_user.username)
    item = callback_data.item
    await cb.answer()
    if item == "home":  # «Меню»: убираем текущий экран (и сообщение с кнопкой) и показываем меню
        await state.clear()
        try:
            await cb.message.delete()
        except TelegramAPIError:  # старше 48 часов Telegram удалить не даст — просто снимаем кнопки
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except TelegramAPIError:
                pass
        await ui.send_menu(cb.message, u)
        return
    on_site = platform.enabled()  # подключены к платформе — разделы берут данные с сайта
    if item in COORD_ITEMS:
        if not u["is_coordinator"]:
            return
        handler = pcoordinator.ITEMS.get(item, COORD_ITEMS[item]) if on_site else COORD_ITEMS[item]
    elif item in VOLUNTEER_ITEMS:
        if item == "reset" and not testmode.TEST_MODE:
            return
        handler = pvolunteer.ITEMS.get(item, VOLUNTEER_ITEMS[item]) if on_site else VOLUNTEER_ITEMS[item]
    else:
        return
    await handler(cb.message, state)  # смену экрана (меню → раздел, кнопка «Меню») делает screen.py
