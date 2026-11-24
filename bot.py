import asyncio
import hashlib
import html
import logging
import os
import re
import json
from datetime import datetime, timedelta, timezone

from aiohttp import ClientSession, ClientTimeout, web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

logging.basicConfig(level=logging.INFO)

# .env faylidan sozlamalarni o'qish (kompyuterda). Render'da sozlamalar Environment bo'limidan olinadi
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE, encoding="utf-8-sig") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]  # @kanal_nomi yoki -100...
GROUP_ID = os.environ["GROUP_ID"]  # -100...
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").replace(" ", "").split(",") if x}
# Fieldy CRM: kontakt yaratish manzili va API kaliti (bo'sh bo'lsa CRM ga yuborilmaydi)
FIELDY_API_URL = os.environ.get("FIELDY_API_URL") or os.environ.get("CRM_WEBHOOK_URL")
FIELDY_API_KEY = os.environ.get("FIELDY_API_KEY", "")
FIELDY_PIPELINE_ID = int(os.environ.get("FIELDY_PIPELINE_ID", "78"))
FIELDY_STAGE_ID = int(os.environ.get("FIELDY_STAGE_ID", "725"))
BUTTON_TEXT = os.environ.get("BUTTON_TEXT", "📝 Ro'yxatdan o'tish")
CONTACT_PHONES = os.environ.get("CONTACT_PHONES", "")  # masalan: +998 90 123 45 67, +998 91 765 43 21
SKIP = "➡️ O'tkazib yuborish"
# Render bu o'zgaruvchini o'zi beradi; bo'lmasa bot lokal polling rejimida ishlaydi
BASE_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")
SECRET = hashlib.sha256(TOKEN.encode()).hexdigest()[:32]

LEVELS = ["Beginner (A0)", "Elementary (A1)", "Pre-Intermediate (A2)",
          "Intermediate (B1)", "Upper-Intermediate (B2)", "Advanced (C1+)"]

REGIONS = ["Toshkent shahri", "Toshkent viloyati", "Andijon", "Buxoro", "Farg'ona", "Jizzax", "Xorazm",
           "Namangan", "Navoiy", "Qashqadaryo", "Qoraqalpog'iston", "Samarqand", "Sirdaryo", "Surxondaryo"]


def clean_phone(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    if len(digits) == 9:  # 901234567 -> O'zbekiston raqami
        digits = "998" + digits
    return "+" + digits if 10 <= len(digits) <= 15 else None


def clean_text(text: str) -> str:
    return text[:200]


def clean_email(text: str) -> str | None:
    return text.lower() if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", text) else None


def clean_instagram(text: str) -> str | None:
    name = re.sub(r"^(https?://)?(www\.)?instagram\.com/", "", text).split("?")[0].strip("@/ ")
    return "@" + name if re.fullmatch(r"[A-Za-z0-9._]{1,30}", name) else None


# Telefondan keyin so'raladigan ixtiyoriy savollar: (kalit, savol, tekshiruvchi, xato matni).
# Kalit — lead dagi nom; FIELDY_KEYS orqali Fieldy maydoniga o'tadi.
EXTRA = [
    ("secondary_phone", "Qo'shimcha telefon raqamingiz bo'lsa yozing.", clean_phone,
     "Raqam noto'g'ri. Masalan: +998 90 123 45 67"),
    ("region", "Viloyatingiz?", clean_text, ""),
    ("city", "Shahringiz?", clean_text, ""),
    ("district", "Tumaningiz?", clean_text, ""),
    ("address", "Manzilingiz (ko'cha, uy)?", clean_text, ""),
    ("email", "Email manzilingiz?", clean_email, "Email noto'g'ri. Masalan: ali@gmail.com"),
    ("instagram", "Instagram sahifangiz?", clean_instagram, "Instagram nomi noto'g'ri. Masalan: @ali_valiyev"),
]

FIELDY_KEYS = {"secondary_phone": "secondaryPhone", "region": "region", "city": "city", "district": "district",
               "address": "address", "email": "email", "instagram": "instagram"}
EXTRA_LABELS = {"secondary_phone": "📞", "region": "🗺", "city": "🏙", "district": "🏘", "address": "🏠",
                "email": "✉️", "instagram": "📸"}

dp = Dispatcher()


class Reg(StatesGroup):
    first_name = State()
    last_name = State()
    phone = State()
    extra = State()  # EXTRA ro'yxatidagi ixtiyoriy savollar
    level = State()
    comment = State()


class Post(StatesGroup):
    waiting = State()
    confirm = State()
    when = State()


TZ = timezone(timedelta(hours=5))  # Toshkent, yozgi vaqt yo'q
JOBS_FILE = os.environ.get("JOBS_FILE", "scheduled.json")
# shortcut: fayl Render bepul serverida qayta deploy qilinganda o'chadi; doimiy saqlash kerak bo'lsa bazaga o'tkazing
JOBS: list[dict] = json.load(open(JOBS_FILE, encoding="utf-8")) if os.path.exists(JOBS_FILE) else []


def save_jobs():
    with open(JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(JOBS, f)


def parse_time(text: str, now: datetime) -> datetime | None:
    m = re.fullmatch(r"\s*(?:(\d{1,2})\.(\d{1,2})\s+)?(\d{1,2})[:.](\d{2})\s*", text)
    if not m:
        return None
    day, month, hour, minute = m.groups()
    try:
        at = now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
        if day:
            at = at.replace(month=int(month), day=int(day))
            if at <= now:
                at = at.replace(year=at.year + 1)
        elif at <= now:
            at += timedelta(days=1)
    except ValueError:
        return None
    return at


def post_link(post_id: str) -> str | None:
    if CHANNEL_ID.startswith("@") and post_id.isdigit():
        return f"https://t.me/{CHANNEL_ID[1:]}/{post_id}"
    return None


# ---------- Umumiy ----------

@dp.message(Command("id"))
async def show_id(message: Message):
    await message.answer(f"Chat ID: <code>{message.chat.id}</code>\nSizning ID: <code>{message.from_user.id}</code>")


@dp.message(Command("cancel"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=ReplyKeyboardRemove())


# ---------- Admin: kanalga post ----------

@dp.message(Command("post"), F.chat.type == "private")
async def post_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(Post.waiting)
    await message.answer("Kanalga joylanadigan postni yuboring (video, rasm yoki matn).\nBekor qilish: /cancel")


@dp.message(Post.waiting)
async def post_preview(message: Message, state: FSMContext):
    await state.update_data(src_chat=message.chat.id, src_msg=message.message_id)
    await state.set_state(Post.confirm)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Hozir joylash", callback_data="post_ok"),
         InlineKeyboardButton(text="⏰ Keyinroq", callback_data="post_later")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="post_no")],
    ])
    await message.reply("Shu postni kanalga joylaymi?", reply_markup=kb)


async def publish(bot: Bot, src_chat: int, src_msg: int) -> tuple[int, str]:
    sent = await bot.copy_message(CHANNEL_ID, src_chat, src_msg)
    me = await bot.me()
    link = f"https://t.me/{me.username}?start=post_{sent.message_id}"
    # Har bir post uchun alohida link: post ID knopkaning ichida, lid qaysi postdan kelganini shu bildiradi
    await bot.edit_message_reply_markup(
        chat_id=CHANNEL_ID, message_id=sent.message_id,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=BUTTON_TEXT, url=link)]]),
    )
    return sent.message_id, link


@dp.callback_query(Post.confirm, F.data.in_({"post_ok", "post_no", "post_later"}))
async def post_decide(call: CallbackQuery, state: FSMContext, bot: Bot):
    await call.answer()
    if call.data == "post_later":
        await state.set_state(Post.when)
        await call.message.edit_text("Qachon joylansin? (Toshkent vaqti)\n"
                                     "Masalan: <code>18:30</code> yoki <code>25.11 18:30</code>\nBekor qilish: /cancel")
        return
    data = await state.get_data()
    await state.clear()  # ikki marta bosilsa ikki marta joylanmasin
    if call.data == "post_no":
        await call.message.edit_text("❌ Bekor qilindi.")
        return
    mid, link = await publish(bot, data["src_chat"], data["src_msg"])
    await call.message.edit_text(f"✅ Joylandi. Post #{mid}\nRo'yxat linki: {link}")


@dp.message(Post.when, F.text)
async def post_schedule(message: Message, state: FSMContext):
    at = parse_time(message.text, datetime.now(TZ))
    if not at:
        await message.answer("Vaqt tushunarsiz yoki o'tib ketgan. Masalan: <code>18:30</code> yoki <code>25.11 18:30</code>")
        return
    data = await state.get_data()
    await state.clear()
    JOBS.append({"id": max((j["id"] for j in JOBS), default=0) + 1, "at": at.isoformat(),
                 "src_chat": data["src_chat"], "src_msg": data["src_msg"]})
    save_jobs()
    await message.answer(f"⏰ Post {at:%d.%m %H:%M} da joylanadi.\n"
                         f"Botdagi asl xabarni o'chirmang. Rejalar ro'yxati: /rejalar")


@dp.message(Command("rejalar"), F.chat.type == "private")
async def list_jobs(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not JOBS:
        await message.answer("Rejalashtirilgan postlar yo'q.")
        return
    for j in sorted(JOBS, key=lambda j: j["at"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"unsched:{j['id']}")]])
        try:
            await message.bot.copy_message(message.chat.id, j["src_chat"], j["src_msg"])
        except Exception:
            await message.answer("⚠️ Asl xabar topilmadi (o'chirilgan) — bu post joylanmaydi.")
        await message.answer(f"⏰ {datetime.fromisoformat(j['at']):%d.%m %H:%M} da joylanadi", reply_markup=kb)


@dp.callback_query(F.data.startswith("unsched:"))
async def unschedule(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    job_id = int(call.data.split(":")[1])
    JOBS[:] = [j for j in JOBS if j["id"] != job_id]
    save_jobs()
    await call.answer()
    await call.message.edit_text("❌ Reja bekor qilindi.")


async def scheduler(bot: Bot):
    while True:
        now = datetime.now(TZ)
        for job in [j for j in JOBS if datetime.fromisoformat(j["at"]) <= now]:
            JOBS.remove(job)
            save_jobs()  # avval o'chiramiz: xato bo'lsa ham post ikki marta chiqmasin
            try:
                mid, link = await publish(bot, job["src_chat"], job["src_msg"])
                await bot.send_message(job["src_chat"], f"✅ Rejalashtirilgan post joylandi. Post #{mid}\nRo'yxat linki: {link}")
            except Exception as err:
                logging.exception("Rejalashtirilgan post joylanmadi: %s", job)
                try:
                    await bot.send_message(job["src_chat"], f"⚠️ Rejalashtirilgan post joylanmadi: <code>{html.escape(str(err))}</code>")
                except Exception:
                    logging.exception("Adminga yuborib bo'lmadi")
        await asyncio.sleep(30)


@dp.startup()
async def start_scheduler(bot: Bot, dispatcher: Dispatcher):
    dispatcher["scheduler"] = asyncio.create_task(scheduler(bot))  # havola saqlanadi, aks holda task yo'qolishi mumkin


# ---------- Foydalanuvchi: ro'yxatdan o'tish ----------

@dp.message(CommandStart(), F.chat.type == "private")
async def start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    source = (command.args or "").removeprefix("post_") or "to'g'ridan-to'g'ri"
    await state.update_data(source=source)
    await state.set_state(Reg.first_name)
    await message.answer("Assalomu alaykum! Ro'yxatdan o'tish uchun bir nechta savol.\n\nIsmingiz?",
                         reply_markup=ReplyKeyboardRemove())


@dp.message(Reg.first_name, F.text)
async def got_first_name(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip()[:64])
    await state.set_state(Reg.last_name)
    await message.answer("Familiyangiz?")


@dp.message(Reg.last_name, F.text)
async def got_last_name(message: Message, state: FSMContext):
    await state.update_data(last_name=message.text.strip()[:64])
    await state.set_state(Reg.phone)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)]],
                             resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Telefon raqamingizni yuboring (knopkani bosing yoki yozing: +998 90 123 45 67).",
                         reply_markup=kb)


@dp.message(Reg.phone)
async def got_phone(message: Message, state: FSMContext):
    raw = message.contact.phone_number if message.contact else (message.text or "")
    phone = clean_phone(raw)
    if not phone:
        await message.answer("Raqam noto'g'ri. Masalan: +998 90 123 45 67")
        return
    await state.update_data(phone=phone, step=0)
    await state.set_state(Reg.extra)
    await ask_extra(message, 0)


async def ask_extra(message: Message, i: int):
    key, question, _, _ = EXTRA[i]
    buttons = [KeyboardButton(text=r) for r in REGIONS] if key == "region" else []
    rows = [buttons[j:j + 2] for j in range(0, len(buttons), 2)] + [[KeyboardButton(text=SKIP)]]
    await message.answer(question, reply_markup=ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True))


@dp.message(Reg.extra, F.text)
async def got_extra(message: Message, state: FSMContext):
    i = (await state.get_data())["step"]
    key, _, check, error = EXTRA[i]
    text = message.text.strip()
    value = "" if text == SKIP else check(text)
    if value is None:
        await message.answer(error)
        return
    await state.update_data({key: value, "step": i + 1})
    if i + 1 < len(EXTRA):
        await ask_extra(message, i + 1)
        return
    await state.set_state(Reg.level)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=lv)] for lv in LEVELS],
                             resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Ingliz tili darajangiz?", reply_markup=kb)


@dp.message(Reg.extra)
async def wrong_extra(message: Message):
    await message.answer(f"Iltimos, javobni yozing yoki «{SKIP}» ni bosing.")


@dp.message(Reg.level, F.text.in_(LEVELS))
async def got_level(message: Message, state: FSMContext):
    await state.update_data(level=message.text)
    await state.set_state(Reg.comment)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=SKIP)]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Qo'shimcha fikr yoki savolingiz bo'lsa yozing (masalan, qulay vaqt, maqsadingiz).\n"
                         "Bo'lmasa, pastdagi knopkani bosing.", reply_markup=kb)


@dp.message(Reg.level)
async def wrong_level(message: Message):
    await message.answer("Iltimos, pastdagi knopkalardan birini tanlang.")


@dp.message(Reg.comment, F.text)
async def got_comment(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    u = message.from_user
    comment = "" if message.text == SKIP else message.text.strip()[:1000]
    lead = {
        "first_name": data["first_name"],
        "last_name": data["last_name"],
        "phone": data["phone"],
        "english_level": data["level"],
        "comment": comment,
        "source_post": data["source"],
        "source_link": post_link(data["source"]),
        "telegram_id": u.id,
        "telegram_username": u.username,
        "created_at": datetime.now(timezone.utc).isoformat(),
        **{key: data.get(key, "") for key, *_ in EXTRA},
    }
    e = html.escape
    thanks = "✅ Rahmat! Arizangiz qabul qilindi, tez orada siz bilan bog'lanamiz."
    if CONTACT_PHONES:
        thanks += f"\n\nO'zingiz bog'lanmoqchi bo'lsangiz, bizga qo'ng'iroq qiling:\n📞 {e(CONTACT_PHONES)}"
    await message.answer(thanks, reply_markup=ReplyKeyboardRemove())

    src = lead["source_link"] or f"#{lead['source_post']}"
    text = (f"🆕 <b>Yangi lid</b>\n\n"
            f"👤 {e(lead['first_name'])} {e(lead['last_name'])}\n"
            f"📱 {lead['phone']}\n"
            + "".join(f"{EXTRA_LABELS[k]} {e(lead[k])}\n" for k, *_ in EXTRA if lead[k])
            + f"🇬🇧 {e(lead['english_level'])}\n"
            + (f"📝 {e(comment)}\n" if comment else "")
            + f"📌 Post: {e(src)}\n"
            f"💬 {'@' + u.username if u.username else ''} <a href=\"tg://user?id={u.id}\">profil</a>")
    try:
        await bot.send_message(GROUP_ID, text)
    except Exception as err:
        logging.exception("Guruhga yuborib bo'lmadi: %s", lead)
        # lid yo'qolmasin va admin sababini ko'rsin
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, f"⚠️ Guruhga yuborilmadi: <code>{e(str(err))}</code>\n"
                                              f"GROUP_ID={e(str(GROUP_ID))} ni tekshiring.\n\n{text}")
            except Exception:
                logging.exception("Adminga yuborib bo'lmadi")

    if FIELDY_API_URL:
        headers = {"Authorization": f"Bearer {FIELDY_API_KEY}"} if FIELDY_API_KEY else {}
        try:
            async with ClientSession(timeout=ClientTimeout(total=15)) as s:
                async with s.post(FIELDY_API_URL, json=fieldy_payload(lead), headers=headers) as r:
                    error = None if r.status < 300 else f"HTTP {r.status}: {(await r.text())[:200]}"
        except Exception as err:
            error = f"ulanib bo'lmadi ({type(err).__name__})"
        if error:
            logging.error("Fieldy ga yuborib bo'lmadi: %s | %s", error, lead)
            for admin in ADMIN_IDS:
                try:
                    await bot.send_message(admin, f"⚠️ Fieldy CRM ga yuborilmadi: <code>{e(error)}</code>\n"
                                                  f"Lid: {e(lead['first_name'])} {lead['phone']}")
                except Exception:
                    logging.exception("Adminga yuborib bo'lmadi")


def fieldy_payload(lead):
    """Fieldy kontakt formati. Fieldy'da maydoni yo'q narsalar notes ga yoziladi."""
    notes = [f"Ingliz tili darajasi: {lead['english_level']}"]
    if lead["comment"]:
        notes.append(f"Izoh: {lead['comment']}")
    notes.append(f"Post: {lead['source_link'] or lead['source_post']}")
    notes.append(f"Telegram ID: {lead['telegram_id']}")
    payload = {
        "firstName": lead["first_name"],
        "lastName": lead["last_name"],
        "phone": lead["phone"],
        "source": "TELEGRAM",
        "sourceDetail": f"post_{lead['source_post']}" if lead["source_post"].isdigit() else lead["source_post"],
        "telegram": f"@{lead['telegram_username']}" if lead["telegram_username"] else "",
        "notes": "\n".join(notes),
        "pipelineId": FIELDY_PIPELINE_ID,
        "stageId": FIELDY_STAGE_ID,
        **{FIELDY_KEYS[k]: lead.get(k, "") for k in FIELDY_KEYS},
    }
    return {k: v for k, v in payload.items() if v}


# ---------- Ishga tushirish ----------

def main():
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    if not BASE_URL:
        async def run():
            await bot.delete_webhook()
            await dp.start_polling(bot)
        asyncio.run(run())
        return

    async def on_startup(bot: Bot):
        await bot.set_webhook(f"{BASE_URL}/webhook", secret_token=SECRET)

    dp.startup.register(on_startup)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="ok"))  # UptimeRobot shu manzilni ping qiladi
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=SECRET).register(app, path="/webhook")
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


if __name__ == "__main__":
    main()
