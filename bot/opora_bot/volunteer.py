"""Волонтёр и кандидат: вход по почте, встреча, приглашения, занятия, материалы, вопросы, настройки."""
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import auth, db, exports, site, ui, unisender
from .config import ANKETA_URL, CODE_TTL_MINUTES, TZ
from .notify import send, to_coordinators
from .schedule import WEEKDAYS, duration_hours, human, starts_at, time_range

router = Router(name="volunteer")

MEETING_PLACE = "Студия фонда на Новинском б-ре, 25 к10, подъезд 3, или онлайн — координатор уточнит"


class Login(StatesGroup):
    email = State()
    code = State()


class Ask(StatesGroup):
    text = State()


class After(StatesGroup):
    hard = State()
    hours = State()


def anketa_kb() -> InlineKeyboardMarkup:
    # TODO: ANKETA_URL сейчас ведёт на Яндекс-форму фонда — заменить на анкету на сайте.
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Заполнить анкету", url=ANKETA_URL)]])


def code_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Отправить код ещё раз", callback_data=ui.StepCB(name="resend"))
    b.button(text="Другая почта", callback_data=ui.StepCB(name="login"))
    b.adjust(1)
    return b.as_markup()


# --- старт и вход по почте ---------------------------------------------------------------

WELCOME = ("👋 Здравствуйте! Это бот фонда «Дети Марии» для волонтёров.\n\n"
           "🎨 Здесь приходят приглашения на занятия и мероприятия фонда, напоминания и материалы, "
           "а ещё можно написать координатору.\n\n"
           "Впервые у нас? Заполните анкету волонтёра — это около 10 минут. "
           "Уже заполняли — войдите по почте, которую указали в анкете.")


async def welcome(target: Message, u) -> None:
    """Первое сообщение для нового человека: кнопки «Заполнить анкету» и «Войти по почте» прямо под ним."""
    await ui.drop_old_keyboard(target, u)
    await target.answer(WELCOME, reply_markup=ui.menu(u))


@router.message(CommandStart())
async def start(msg: Message, state: FSMContext):
    await state.clear()
    u = db.ensure_user(msg.chat.id, msg.from_user.username)
    if u["status"] == "new" and not ui.coord_mode(u):
        await welcome(msg, u)
    else:
        name = escape(u["name"] or "")
        await ui.send_menu(msg, u, f"👋 С возвращением{', ' + name if name else ''}!\n\n{ui.menu_text(u)}")


@router.message(Command("menu"))
async def show_menu(msg: Message, state: FSMContext):
    await state.clear()
    await ui.send_menu(msg, db.ensure_user(msg.chat.id, msg.from_user.username))


@router.message(F.text == ui.BTN_TO_COORD)
async def to_coord_mode(msg: Message, state: FSMContext):
    import json
    u = db.user(msg.chat.id)
    if not u or not u["is_coordinator"]:
        return
    await state.clear()
    p = db.prefs(u)
    p["mode"] = "coord"
    db.update_user(u["id"], prefs=json.dumps(p))
    await ui.send_menu(msg, db.user(u["id"]))


@router.message(F.text == ui.BTN_ANKETA)
async def anketa(msg: Message):
    await msg.answer("📝 Анкета займёт около 10 минут. После неё вернитесь сюда и нажмите «Войти по почте».",
                     reply_markup=anketa_kb())


async def ask_email(target: Message, state: FSMContext):
    await state.set_state(Login.email)
    await target.answer("✉️ Напишите почту, которую вы указали в анкете на сайте. Пришлём на неё код для входа.", reply_markup=ui.cancel_kb())


@router.message(F.text == ui.BTN_LOGIN)
async def login_button(msg: Message, state: FSMContext):
    await ask_email(msg, state)


@router.callback_query(ui.StepCB.filter(F.name == "login"))
async def login_inline(cb: CallbackQuery, state: FSMContext):
    await ask_email(cb.message, state)
    await cb.answer()


async def send_code(target: Message, chat_id: int, email: str, state: FSMContext, bot: Bot, first_name: str = ""):
    """Выдаёт код и отправляет письмо через Unisender Go. Ответ — в чат."""
    blocked = auth.can_send(chat_id)
    if blocked:
        await target.answer(blocked, reply_markup=code_kb())
        return
    code = auth.issue(chat_id, email)
    me = await bot.me()
    data = await state.get_data()
    name = (data.get("profile") or {}).get("name") or first_name
    subs = {"greeting": f"Здравствуйте, {name}!" if name else "Здравствуйте!", "code": code,
            "minutes": str(CODE_TTL_MINUTES), "bot_link": f"https://t.me/{me.username}", "bot_name": f"@{me.username}"}
    res = await unisender.send_login_code(email, subs, f"login-{chat_id}-{int(db.now().timestamp())}")
    if not res.ok:
        await target.answer("Не получилось отправить письмо. Проверьте адрес или попробуйте через несколько минут. "
                            "Если не выходит — напишите координатору фонда.", reply_markup=code_kb())
        return
    await state.set_state(Login.code)
    await state.update_data(email=email)
    text = (f"📨 Отправили код на {escape(auth.mask(email))}. Введите его сюда — 6 цифр. "
            f"Код действует {CODE_TTL_MINUTES} минут. Если письма нет, проверьте «Спам».")
    if res.dry_run:
        text += (f"\n\n<i>Тестовый режим: Unisender Go ещё не подключён, письмо не отправлено.</i>\nВаш код: <b>{code}</b>")
    await target.answer(text, reply_markup=code_kb())


@router.message(Login.email, F.text)
async def login_email(msg: Message, state: FSMContext, bot: Bot):
    email = auth.valid_email(msg.text)
    if not email:
        await msg.answer("Похоже, в адресе ошибка. Напишите почту целиком, например anna@mail.ru", reply_markup=ui.cancel_kb())
        return
    try:
        profile = await site.find_by_email(email)
    except Exception:
        await msg.answer("Сайт фонда сейчас не отвечает. Попробуйте чуть позже.")
        return
    if not profile:
        await msg.answer("Не нашли анкету с этой почтой. Проверьте адрес — или заполните анкету, если ещё не заполняли.",
                         reply_markup=anketa_kb())
        return
    await state.update_data(profile=profile.__dict__)
    await send_code(msg, msg.chat.id, email, state, bot, msg.from_user.first_name or "")


@router.callback_query(ui.StepCB.filter(F.name == "resend"))
async def resend(cb: CallbackQuery, state: FSMContext, bot: Bot):
    email = (await state.get_data()).get("email")
    if not email:
        await ask_email(cb.message, state)
    else:
        await send_code(cb.message, cb.message.chat.id, email, state, bot, cb.from_user.first_name or "")
    await cb.answer()


@router.message(Login.code, F.text)
async def login_code(msg: Message, state: FSMContext, bot: Bot):
    result, email = auth.check(msg.chat.id, msg.text)
    if result == "wrong":
        await msg.answer(f"Код не подошёл. Осталось попыток: {auth.attempts_left(msg.chat.id)}.")
        return
    if result in ("expired", "locked", "none"):
        why = {"expired": "Код устарел.", "locked": "Слишком много попыток.", "none": "Код не найден."}[result]
        await msg.answer(f"{why} Запросите новый.", reply_markup=code_kb())
        return
    p = (await state.get_data()).get("profile") or {}
    await state.clear()
    uid = msg.chat.id
    # одна почта — один чат: если человек вошёл с нового телефона, старый чат отвязываем
    db.run("UPDATE users SET email=NULL, status='new' WHERE email=? AND id!=? AND is_coordinator=0", email, uid)
    u = db.user(uid)
    db.update_user(uid, email=email, site_id=p.get("site_id", ""),
                   name=p.get("name") or u["name"] or msg.from_user.full_name,
                   phone=p.get("phone") or u["phone"] or "",
                   roles=",".join(p.get("roles", [])) or u["roles"], days=",".join(map(str, p.get("days", []))) or u["days"],
                   status=p.get("status", "candidate") if u["status"] != "active" else "active")
    u = db.user(uid)
    hello = f"✅ Готово, вы вошли как {escape(u['name'])}."
    if u["status"] != "candidate":
        await ui.send_menu(msg, u, f"{hello}\n\n{ui.menu_text(u)}")
    else:
        # сначала только сообщение о входе с плашкой «Меню»; по нажатию оно исчезает и открывается меню
        m = sync_interview(uid, p)
        if m:
            await msg.answer(f"{hello}\n\n🤝 Ваше собеседование с координатором пройдёт {when_text(m)}.\n"
                             f"📍 {escape(m['place'])}\n\n🔔 За день и за 15 минут до начала пришлём напоминание.",
                             reply_markup=meeting_kb(m["id"], home=True))
        else:
            b = InlineKeyboardBuilder()
            b.button(text=ui.BTN_HOME, callback_data=ui.MenuCB(item="home"))
            await msg.answer(f"{hello}\n\nЗаписи на собеседование пока не видим. Запишитесь в личном кабинете "
                             "на сайте фонда или напишите координатору.", reply_markup=b.as_markup())
    demo = " (демо: анкету на сайте не проверяли)" if p.get("demo") else ""
    db.log("login", uid, f"{ui.person(u)} вошёл(шла) в бот, {escape(email)}{demo}")


# --- собеседование с координатором ------------------------------------------------------
# Человек записывается на собеседование на сайте. Бот берёт запись из профиля, напоминает за сутки и за 15 минут
# и даёт отметить «Не смогу прийти». Перенос — через координатора или кабинет на сайте.

def sync_interview(uid: int, profile: dict):
    """Запись с сайта → таблица meetings. Возвращает актуальную запись или None."""
    at = profile.get("interview_at")
    if not at:
        return current_meeting(uid)
    same = db.one("SELECT * FROM meetings WHERE user_id=? AND starts_at=? AND status='booked'", uid, at)
    if same:
        return same
    db.run("UPDATE meetings SET status='cancelled' WHERE user_id=? AND status='booked'", uid)
    mid = db.run("INSERT INTO meetings (user_id, starts_at, place) VALUES (?,?,?)", uid, at,
                 profile.get("interview_place") or MEETING_PLACE)
    s = datetime.fromisoformat(at)
    demo = " (демо-запись)" if profile.get("demo") else ""
    db.log("meeting", uid, f"{ui.person(db.user(uid))} записан(а) на собеседование {human(s.date())}, {s:%H:%M}{demo}",
           ref=str(mid))
    return db.one("SELECT * FROM meetings WHERE id=?", mid)


ON_WEEKDAY = ["в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу", "в воскресенье"]


def when_text(m) -> str:
    """«в четверг, 22 октября, в 18:30» — с «сегодня»/«завтра», если близко."""
    s = datetime.fromisoformat(m["starts_at"])
    gap = (s.date() - db.now().date()).days
    near = {0: "сегодня, ", 1: "завтра, "}.get(gap, "")
    return f"{near}{ON_WEEKDAY[s.weekday()]}, {human(s.date(), False)}, в {s:%H:%M}"


def meeting_kb(mid: int, home: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Не смогу прийти", callback_data=ui.MeetCB(action="cancel", mid=mid))
    if home:  # плашка «Меню» под сообщением о входе
        b.button(text=ui.BTN_HOME, callback_data=ui.MenuCB(item="home"))
    b.adjust(1)
    return b.as_markup()


def current_meeting(uid: int):
    return db.one("SELECT * FROM meetings WHERE user_id=? AND status='booked' AND starts_at>=? ORDER BY starts_at",
                  uid, db.stamp())


def meeting_text(m) -> str:
    s = datetime.fromisoformat(m["starts_at"])
    return f"🤝 <b>Собеседование с координатором</b>\n📅 {human(s.date())}, {s:%H:%M}\n📍 {escape(m['place'])}"


@router.message(F.text == ui.BTN_MEETING)
async def meeting(msg: Message):
    m = current_meeting(msg.chat.id)
    if m:
        await msg.answer(meeting_text(m) + "\n\n🔔 Напомним за день и за 15 минут до начала.",
                         reply_markup=meeting_kb(m["id"]))
    else:
        await msg.answer("Записи на собеседование сейчас нет. Запишитесь в личном кабинете на сайте фонда "
                         "или напишите координатору.")


@router.callback_query(ui.MeetCB.filter())
async def meeting_action(cb: CallbackQuery, callback_data: ui.MeetCB, bot: Bot):
    m = db.one("SELECT * FROM meetings WHERE id=? AND user_id=?", callback_data.mid, cb.message.chat.id)
    if not m or m["status"] != "booked":
        await cb.answer("Эта запись уже неактуальна.")
        return
    u = db.user(cb.message.chat.id)
    s = datetime.fromisoformat(m["starts_at"])
    if callback_data.action == "yes":
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.answer("Отлично, ждём вас!")
    elif callback_data.action == "cancel":
        db.run("UPDATE meetings SET status='cancelled' WHERE id=?", m["id"])
        await cb.message.edit_text("Спасибо, что предупредили. Координатор свяжется с вами и предложит другое время. "
                                   "Записаться заново можно и в личном кабинете на сайте фонда.")
        text = f"{ui.person(u)} не сможет прийти на собеседование {human(s.date())}, {s:%H:%M}"
        db.log("meeting", u["id"], text, ref=str(m["id"]))
        if s - db.now() < timedelta(hours=24):  # в последний момент — сразу сообщением
            await to_coordinators(bot, "⚠️ <b>Срочно:</b> " + text)
        await cb.answer()
    else:  # кнопка из старых сообщений («Нужна помощь с дорогой» убрали)
        await cb.answer("Эта кнопка больше не работает.")


# --- приглашения ---------------------------------------------------------------------

@router.callback_query(ui.InvCB.filter(F.action.in_({"yes", "no", "more", "mat"})))
async def invite_answer(cb: CallbackQuery, callback_data: ui.InvCB, bot: Bot):
    uid, day, ev = cb.message.chat.id, ui.dparse(callback_data.d), db.event(callback_data.eid)
    inv = db.invite(callback_data.eid, day.isoformat(), uid)
    if not ev or not inv:
        await cb.answer("Приглашение не найдено.")
        return
    if callback_data.action in ("more", "mat"):
        await cb.message.answer(ui.materials_text(ev, day, with_group=inv["status"] in ("confirmed", "attended")))
        await cb.answer()
        return
    if day < db.now().date():
        await cb.answer("Это событие уже прошло.")
        return
    u = db.user(uid)
    if callback_data.action == "yes":
        if inv["status"] in ("accepted", "confirmed"):
            await cb.answer("Вы уже согласились.")
            return
        db.set_invite(ev["id"], day.isoformat(), uid, "accepted")
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.message.answer("🙌 Спасибо! Координатор подтвердит участие, и сюда придут материалы.")
        db.log("accepted", uid, f"{ui.person(u)} готов(а) прийти: <b>{escape(ev['title'])}</b>, {human(day)}",
               ref=ev["id"], date=day.isoformat(), action="confirm")
    else:
        late = starts_at(ev, day) - db.now() < timedelta(hours=24)
        db.set_invite(ev["id"], day.isoformat(), uid, "declined")
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.message.answer("🤍 Спасибо, что предупредили. Позовём в другой раз.")
        db.resolve("confirm", uid, ev["id"], day.isoformat())
        text = f"{ui.person(u)} не сможет: <b>{escape(ev['title'])}</b>, {human(day)}. Сейчас {ui.coverage(ev, day)}."
        db.log("declined", uid, text, ref=ev["id"], date=day.isoformat())
        if late and inv["status"] in ("accepted", "confirmed"):  # срочно — сразу сообщением
            kb = InlineKeyboardBuilder()
            kb.button(text="Позвать других", callback_data=ui.EvCB(action="call", eid=ev["id"], d=callback_data.d))
            await to_coordinators(bot, "⚠️ <b>Срочно:</b> " + text, kb.as_markup())
    await cb.answer()


# --- мои занятия и материалы -------------------------------------------------------------

def my_upcoming(uid: int, statuses=("invited", "accepted", "confirmed")):
    today = db.now().date().isoformat()
    marks = ",".join("?" * len(statuses))
    rows = db.all_(f"SELECT * FROM invites WHERE user_id=? AND date>=? AND status IN ({marks}) ORDER BY date",
                   uid, today, *statuses)
    out = []
    for r in rows:
        ev = db.event(r["event_id"])
        if ev:
            out.append((ev, ui.dparse(r["date"].replace("-", "")), r))
    return out


@router.message(F.text == ui.BTN_MY)
async def my_events(msg: Message):
    uid = msg.chat.id
    items = my_upcoming(uid)
    done = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(hours),0) AS h FROM invites WHERE user_id=? AND status='attended'", uid)
    if not items:
        await msg.answer("📅 Ближайших занятий пока нет. Когда координатор пригласит вас, приглашение придёт сюда.\n\n"
                         f"Всего вы были на {done['n']} занятиях, {done['h']:g} ч.")
        return
    await msg.answer(f"📅 <b>Ближайшие занятия</b> · всего вы были на {done['n']} занятиях, {done['h']:g} ч.")
    for ev, day, r in items[:6]:
        b = InlineKeyboardBuilder()
        if r["status"] == "invited":
            await msg.answer(ui.event_head(ev, day) + "\n\nВас пригласили — ответьте, пожалуйста.", reply_markup=ui.invite_kb(ev, day))
            continue
        b.button(text="Материалы", callback_data=ui.InvCB(action="mat", eid=ev["id"], d=ui.dkey(day)))
        b.button(text="Не смогу", callback_data=ui.InvCB(action="no", eid=ev["id"], d=ui.dkey(day)))
        await msg.answer(ui.event_head(ev, day) + f"\n\nСтатус: {ui.STATUS_RU[r['status']]}", reply_markup=b.as_markup())
    confirmed = [(ev, day) for ev, day, r in items if r["status"] == "confirmed"]
    if confirmed:
        await msg.answer_document(BufferedInputFile(exports.ics(confirmed), filename="detimarii.ics"),
                                  caption="Подтверждённые занятия — откройте файл, чтобы добавить их в календарь телефона.")


@router.message(F.text == ui.BTN_MATERIALS)
async def materials(msg: Message):
    items = [(ev, day) for ev, day, r in my_upcoming(msg.chat.id, ("confirmed",))]
    if not items:
        await msg.answer("📎 Материалы появятся, когда координатор подтвердит ваше участие в занятии или мероприятии.")
        return
    for ev, day in items[:3]:
        await msg.answer(ui.materials_text(ev, day, with_group=True))


# --- вопрос координатору -------------------------------------------------------------

@router.message(F.text == ui.BTN_ASK)
async def ask(msg: Message, state: FSMContext):
    await state.set_state(Ask.text)
    await msg.answer("💬 Напишите вопрос одним сообщением — передадим координатору, ответ придёт сюда.", reply_markup=ui.cancel_kb())


@router.message(Ask.text, F.text)
async def ask_text(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    qid = db.run("INSERT INTO questions (user_id, text, asked_at) VALUES (?,?,?)", msg.chat.id, msg.text[:2000], db.stamp())
    kb = InlineKeyboardBuilder()
    kb.button(text="Ответить", callback_data=ui.AnswerCB(qid=qid))
    kb.button(text="Карточка волонтёра", callback_data=ui.CardCB(uid=msg.chat.id))
    who = ui.person(db.user(msg.chat.id))
    db.log("question", msg.chat.id, f"Вопрос от {who}: {escape(msg.text[:300])}", ref=str(qid), action="answer")
    await to_coordinators(bot, f"💬 <b>Вопрос от {who}</b>\n{escape(msg.text)}", kb.as_markup())  # человек ждёт ответа
    await msg.answer("✅ Передали координатору. Ответ придёт в этот чат.")


# --- после занятия ---------------------------------------------------------------------

@router.callback_query(ui.AfterCB.filter())
async def after(cb: CallbackQuery, callback_data: ui.AfterCB, state: FSMContext, bot: Bot):
    uid, day, ev = cb.message.chat.id, ui.dparse(callback_data.d), db.event(callback_data.eid)
    if not ev:
        await cb.answer()
        return
    u = db.user(uid)
    if callback_data.action == "ok":
        h = duration_hours(ev) or 2
        b = InlineKeyboardBuilder()
        b.button(text=f"Да, {h:g} ч", callback_data=ui.AfterCB(action="hours", eid=ev["id"], d=callback_data.d, h=h))
        b.button(text="Другое число", callback_data=ui.AfterCB(action="other", eid=ev["id"], d=callback_data.d))
        await cb.message.edit_text(f"🎉 Рады! Засчитать {h:g} ч за «{escape(ev['title'])}»?", reply_markup=b.as_markup())
    elif callback_data.action == "hours":
        db.set_invite(ev["id"], day.isoformat(), uid, "attended", hours=callback_data.h)
        db.log("hours", uid, f"{ui.person(u)} отметил(а) {callback_data.h:g} ч: {escape(ev['title'])}, {human(day)}", ref=ev["id"], date=day.isoformat())
        await cb.message.edit_text(f"Записали {callback_data.h:g} ч. Спасибо, что были с ребятами! 🤍")
    elif callback_data.action == "other":
        await state.set_state(After.hours)
        await state.update_data(eid=ev["id"], d=callback_data.d)
        await cb.message.edit_text("Сколько часов вы были на занятии? Напишите число, например 3.5", reply_markup=ui.cancel_kb())
    elif callback_data.action == "hard":
        await state.set_state(After.hard)
        await state.update_data(eid=ev["id"], d=callback_data.d)
        await cb.message.edit_text("Расскажите, что было сложно, — координатор прочитает и поможет.", reply_markup=ui.cancel_kb())
    elif callback_data.action == "absent":
        db.set_invite(ev["id"], day.isoformat(), uid, "absent")
        await cb.message.edit_text("Спасибо, что сказали. Надеемся увидеть вас в следующий раз.")
        db.log("absent", uid, f"{ui.person(u)} не смог(ла) прийти: <b>{escape(ev['title'])}</b>, {human(day)}",
               ref=ev["id"], date=day.isoformat())
    await cb.answer()


@router.message(After.hours, F.text)
async def after_hours(msg: Message, state: FSMContext):
    try:
        h = round(float(msg.text.replace(",", ".")), 1)
        assert 0 < h <= 24
    except (ValueError, AssertionError):
        await msg.answer("Напишите число часов, например 3 или 3.5")
        return
    data = await state.get_data()
    await state.clear()
    db.set_invite(data["eid"], ui.dparse(data["d"]).isoformat(), msg.chat.id, "attended", hours=h)
    await msg.answer(f"Записали {h:g} ч. Спасибо!")


@router.message(After.hard, F.text)
async def after_hard(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    ev, day = db.event(data["eid"]), ui.dparse(data["d"])
    db.set_invite(ev["id"], day.isoformat(), msg.chat.id, "attended", hours=duration_hours(ev) or 2, feedback=msg.text[:2000])
    db.log("feedback", msg.chat.id, f"Сложности на «{escape(ev['title'])}», {human(day)} — "
                                    f"{ui.person(db.user(msg.chat.id))}: {escape(msg.text[:500])}", ref=ev["id"], date=day.isoformat())
    await msg.answer("Спасибо, передали координатору. Часы за занятие засчитаны.")


# --- настройки -----------------------------------------------------------------------

def settings_kb(u) -> InlineKeyboardMarkup:
    p = db.prefs(u)
    b = InlineKeyboardBuilder()
    b.button(text=("✓ " if p["news"] else "") + "Новости фонда", callback_data=ui.PrefCB(key="news"))
    b.button(text=("✓ " if p["thanks"] else "") + "Итоги месяца", callback_data=ui.PrefCB(key="thanks"))
    b.button(text="Снять паузу" if p.get("paused") else "Поставить паузу", callback_data=ui.PrefCB(key="paused"))
    b.adjust(1)
    return b.as_markup()


SETTINGS_TEXT = ("⚙️ <b>Настройки</b>\nНапоминания о ваших встречах и занятиях приходят всегда. Остальное можно выключить. "
                 "Ночью, с 22:00 до 9:00, бот молчит — кроме срочных изменений на сегодня.\n\n"
                 "Пауза — координатор не будет звать вас на новые занятия.")


@router.message(F.text == ui.BTN_SETTINGS)
async def settings(msg: Message):
    await msg.answer(SETTINGS_TEXT, reply_markup=settings_kb(db.user(msg.chat.id)))


@router.callback_query(ui.PrefCB.filter())
async def toggle_pref(cb: CallbackQuery, callback_data: ui.PrefCB):
    import json
    u = db.user(cb.message.chat.id)
    p = db.prefs(u)
    p[callback_data.key] = not p.get(callback_data.key, False)
    db.update_user(u["id"], prefs=json.dumps(p))
    await cb.message.edit_reply_markup(reply_markup=settings_kb(db.user(u["id"])))
    await cb.answer()
