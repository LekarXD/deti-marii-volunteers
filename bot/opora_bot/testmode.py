"""Тестовый режим (TEST_MODE=on): кнопка и команда /reset сбрасывают диалог, чтобы пройти путь волонтёра заново.

Подключается первым роутером, поэтому срабатывает в любом состоянии (например, посреди ввода кода).
На рабочем сервере TEST_MODE не включаем — кнопки не будет.
"""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, ui
from .config import TEST_MODE

router = Router(name="testmode")


def reset_user(uid: int) -> None:
    """Стирает всё о человеке в боте. Вход координатора остаётся, чтобы уведомления продолжали приходить."""
    u = db.user(uid)
    coordinator = u["is_coordinator"] if u else 0
    for sql in ("DELETE FROM invites WHERE user_id=?", "DELETE FROM meetings WHERE user_id=?",
                "DELETE FROM questions WHERE user_id=?", "DELETE FROM auth_codes WHERE chat_id=?",
                "DELETE FROM outbox WHERE chat_id=?", "DELETE FROM users WHERE id=?"):
        db.run(sql, uid)
    db.run("DELETE FROM sent WHERE key LIKE ?", f"%:{uid}")  # отметки отправленных напоминаний этому человеку
    # после сброса координатор видит путь нового волонтёра; вернуться — кнопкой «Режим координатора»
    prefs = '{"inline_menu": true, "mode": "vol"}' if coordinator else '{"inline_menu": true}'
    db.run("INSERT INTO users (id, is_coordinator, prefs, created_at) VALUES (?,?,?,?)", uid, coordinator, prefs, db.stamp())


@router.message(F.text == ui.BTN_RESET, lambda _: TEST_MODE)
@router.message(Command("reset"), lambda _: TEST_MODE)
async def ask_reset(msg: Message):
    b = InlineKeyboardBuilder()
    b.button(text="Да, сбросить", callback_data=ui.StepCB(name="reset_yes"))
    b.button(text="Отмена", callback_data=ui.StepCB(name="reset_no"))
    await msg.answer("🧪 <b>Тест: сбросить диалог?</b>\nБот забудет ваш вход, собеседования, приглашения, часы и вопросы "
                     "и начнёт с приветствия, как для нового человека. Вход координатора сохранится.",
                     reply_markup=b.as_markup())


@router.callback_query(ui.StepCB.filter(F.name.in_({"reset_yes", "reset_no"})), lambda _: TEST_MODE)
async def do_reset(cb: CallbackQuery, callback_data: ui.StepCB, state: FSMContext):
    if callback_data.name == "reset_no":
        await cb.message.edit_text("Сброс отменён.")
        await cb.answer()
        return
    await state.clear()
    reset_user(cb.message.chat.id)
    await cb.message.edit_text("Диалог сброшен. ──────────")
    await cb.answer()
    from .volunteer import welcome  # noqa: PLC0415 — избегаем циклического импорта
    await welcome(cb.message, db.ensure_user(cb.message.chat.id, cb.from_user.username))
