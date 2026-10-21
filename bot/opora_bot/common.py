"""Общая отмена: кнопка «Отмена» под вопросами и слово «отмена» текстом выходят из любого пошагового ввода."""
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state
from aiogram.types import CallbackQuery, Message

from . import db, ui

router = Router(name="common")
CANCEL_WORDS = {"отмена", "отменить", "стоп", "/cancel", "cancel"}


@router.message(~StateFilter(default_state), F.text.func(lambda t: bool(t) and t.strip().lower().rstrip(".!") in CANCEL_WORDS))
async def cancel_text(msg: Message, state: FSMContext):
    await state.clear()
    await ui.send_menu(msg, db.ensure_user(msg.chat.id, msg.from_user.username), "Отменено.")


@router.callback_query(ui.StepCB.filter(F.name == "cancel_fsm"))
async def cancel_button(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("Отменено.")
    await ui.send_menu(cb.message, db.ensure_user(cb.message.chat.id, cb.from_user.username))
    await cb.answer()
