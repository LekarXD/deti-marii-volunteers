"""Рассылки координатора: кому → тип → текст → предпросмотр с числом получателей → отправка. История рассылок."""
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, platform, ui
from .coordinator import IsCoordinator
from .notify import is_quiet, send
from .schedule import WEEKDAYS
from .seed import ROLES

router = Router(name="broadcasts")
router.message.filter(IsCoordinator())
router.callback_query.filter(IsCoordinator())
# С платформой разделы координатора — в pcoordinator; старые кнопки из истории чата сюда не попадают.
router.message.filter(lambda _: not platform.enabled())
router.callback_query.filter(lambda _: not platform.enabled())

IDLE_DAYS = 60
KINDS = {"news": "Новость фонда", "important": "Важное"}


class Bc(StatesGroup):
    text = State()


def audience_label(aud: str) -> str:
    if aud == "active":
        return "все допущенные"
    if aud == "candidates":
        return "кандидаты"
    if aud == "idle":
        return f"допущенные, кто не выходил {IDLE_DAYS}+ дней"
    if aud.startswith("role."):
        return f"роль «{ROLES.get(aud[5:], aud[5:])}»"
    if aud.startswith("day."):
        return f"свободны в {WEEKDAYS[int(aud[4:])].lower()}"
    return aud


def recipients(aud: str, kind: str):
    """Люди из аудитории. Новость — только тем, кто не отключил «Новости фонда»; важное — всем."""
    if aud == "candidates":
        rows = db.all_("SELECT * FROM users WHERE status='candidate' AND blocked=0")
    else:
        rows = db.all_("SELECT * FROM users WHERE status='active' AND blocked=0")
    since = (db.now().date() - timedelta(days=IDLE_DAYS)).isoformat()
    out = []
    for u in rows:
        if aud.startswith("role.") and aud[5:] not in (u["roles"] or "").split(","):
            continue
        if aud.startswith("day.") and aud[4:] not in (u["days"] or "").split(","):
            continue
        if aud == "idle" and db.one("SELECT 1 FROM invites WHERE user_id=? AND status='attended' AND date>=?", u["id"], since):
            continue
        if kind == "news" and not db.prefs(u)["news"]:
            continue
        out.append(u)
    return out


@router.message(F.text == ui.BTN_BROADCASTS)
async def broadcasts(msg: Message, state: FSMContext):
    await state.clear()
    history = db.all_("SELECT * FROM broadcasts ORDER BY id DESC LIMIT 5")
    lines = ["📣 <b>Рассылки</b>", "Новость уходит только тем, кто не отключил новости в настройках. "
             "«Важное» — всем выбранным: для изменений и того, что нельзя пропустить. Ночью сообщения ждут до 9:00."]
    if history:
        lines.append("\n<b>Последние</b>")
        for h in history:
            pic = " · с картинкой" if h["photo"] else ""
            lines.append(f"• {datetime.fromisoformat(h['at']):%d.%m %H:%M} · {KINDS.get(h['kind'], h['kind'])}{pic} · "
                         f"{escape(h['audience'])} · {h['recipients']} чел.\n  <i>{escape(h['text'][:80])}</i>")
    b = InlineKeyboardBuilder()
    b.button(text="Новая рассылка", callback_data=ui.BcCB(step="new"))
    await msg.answer("\n".join(lines), reply_markup=b.as_markup())


def audience_kb():
    b = InlineKeyboardBuilder()
    for aud in ("active", "candidates", "idle"):
        b.button(text=f"{audience_label(aud).capitalize()} · {len(recipients(aud, 'important'))}",
                 callback_data=ui.BcCB(step="aud", val=aud))
    b.button(text="По роли…", callback_data=ui.BcCB(step="role"))
    b.button(text="По свободному дню…", callback_data=ui.BcCB(step="day"))
    b.button(text="Отмена", callback_data=ui.BcCB(step="cancel"))
    b.adjust(1)
    return b.as_markup()


@router.callback_query(ui.BcCB.filter())
async def flow(cb: CallbackQuery, callback_data: ui.BcCB, state: FSMContext, bot: Bot):
    step, val = callback_data.step, callback_data.val
    if step == "new":
        await state.clear()
        await cb.message.answer("Кому отправить? Рядом — сколько человек.", reply_markup=audience_kb())
    elif step == "role":
        b = InlineKeyboardBuilder()
        for key, title in ROLES.items():
            b.button(text=f"{title} · {len(recipients('role.' + key, 'important'))}", callback_data=ui.BcCB(step="aud", val="role." + key))
        b.adjust(1)
        await cb.message.edit_text("Какая роль?", reply_markup=b.as_markup())
    elif step == "day":
        b = InlineKeyboardBuilder()
        for i, name in enumerate(WEEKDAYS):
            b.button(text=f"{name} · {len(recipients(f'day.{i}', 'important'))}", callback_data=ui.BcCB(step="aud", val=f"day.{i}"))
        b.adjust(4)
        await cb.message.edit_text("Кто свободен в какой день?", reply_markup=b.as_markup())
    elif step == "aud":
        await state.update_data(bc_aud=val)
        b = InlineKeyboardBuilder()
        b.button(text=f"Новость фонда · {len(recipients(val, 'news'))}", callback_data=ui.BcCB(step="kind", val="news"))
        b.button(text=f"Важное · {len(recipients(val, 'important'))}", callback_data=ui.BcCB(step="kind", val="important"))
        b.adjust(1)
        await cb.message.edit_text(f"Кому: {audience_label(val)}. Что это за сообщение?", reply_markup=b.as_markup())
    elif step == "kind":
        await state.update_data(bc_kind=val)
        await state.set_state(Bc.text)
        await cb.message.edit_text("Напишите текст одним сообщением или пришлите картинку — с подписью или без. "
                                   "Без рекламы и просьб о пожертвованиях.", reply_markup=ui.cancel_kb())
    elif step == "send":
        data = await state.get_data()
        await state.clear()
        if not data.get("bc_text") and not data.get("bc_photo"):
            await cb.answer("Рассылка уже отправлена или отменена.")
            return
        people = recipients(data["bc_aud"], data["bc_kind"])
        body = message_text(data)
        for u in people:
            await send(bot, u["id"], body, photo=data.get("bc_photo"))
        db.run("INSERT INTO broadcasts (at, audience, kind, text, recipients, photo) VALUES (?,?,?,?,?,?)",
               db.stamp(), audience_label(data["bc_aud"]), data["bc_kind"], data["bc_text"], len(people), data.get("bc_photo"))
        later = " Сейчас ночь — сообщения уйдут в 9:00." if is_quiet() else ""
        done = f"✅ Рассылка отправлена: {len(people)} чел.{later}"
        if cb.message.photo:
            await cb.message.edit_caption(caption=done)
        else:
            await cb.message.edit_text(done)
    elif step == "cancel":
        await state.clear()
        if cb.message.photo:
            await cb.message.edit_caption(caption="Рассылка отменена.")
        else:
            await cb.message.edit_text("Рассылка отменена.")
    await cb.answer()


CAPTION_LIMIT = 1024


def message_text(data) -> str:
    title = "📰 <b>Новости фонда</b>" if data["bc_kind"] == "news" else "❗️ <b>Важное от фонда</b>"
    return f"{title}\n{escape(data['bc_text'])}" if data.get("bc_text") else title


@router.message(Bc.text, F.photo | F.text)
async def preview(msg: Message, state: FSMContext):
    photo = msg.photo[-1].file_id if msg.photo else None
    text = (msg.caption if photo else msg.text) or ""
    if photo and len(text) > CAPTION_LIMIT - 40:
        await msg.answer(f"Подпись к картинке длинновата — Telegram берёт до {CAPTION_LIMIT} символов. "
                         "Сократите подпись или пришлите текст отдельной рассылкой.", reply_markup=ui.cancel_kb())
        return
    await state.update_data(bc_text=text[:3500], bc_photo=photo)
    data = await state.get_data()
    n = len(recipients(data["bc_aud"], data["bc_kind"]))
    b = InlineKeyboardBuilder()
    if n:
        b.button(text=f"Отправить · {n} чел.", callback_data=ui.BcCB(step="send"))
    b.button(text="Отмена", callback_data=ui.BcCB(step="cancel"))
    b.adjust(1)
    await state.set_state(None)
    head = (f"<b>Проверьте</b> · кому: {audience_label(data['bc_aud'])} · {KINDS[data['bc_kind']]} · {n} чел."
            + ("" if n else "\nНекому отправить — выберите другую аудиторию."))
    if photo:
        await msg.answer(head)
        await msg.answer_photo(photo, caption=message_text(data), reply_markup=b.as_markup())
    else:
        await msg.answer(f"{head}\n\n{message_text(data)}", reply_markup=b.as_markup())
