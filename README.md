# Lid yig'uvchi Telegram bot

**Bot nima qiladi:**
- Admin botga `/post` yozadi va video/rasm/matn yuboradi → bot uni kanalga joylaydi va tagiga **"📝 Ro'yxatdan o'tish"** knopkasini qo'yadi. Har bir post uchun alohida link yaratiladi (`?start=post_123`), shuning uchun har bir lid qaysi videodan kelgani ko'rinib turadi.
- Foydalanuvchi knopkani bosadi → bot ism, familiya, telefon raqam (knopka orqali yoki yozib) va ingliz tili darajasini so'raydi.
- Tayyor ariza **guruhga** yuboriladi va (agar sozlangan bo'lsa) **Fieldy CRM ga** yuboriladi.

Hosting: **Render.com** (bepul, karta so'ramaydi) + **UptimeRobot** (bepul, botni uxlatmaydi).

---

## 1-qadam. Botni yaratish (2 daqiqa)

1. Telegramda [@BotFather](https://t.me/BotFather) ga kiring → `/newbot` → nom va username bering.
2. U bergan **token**ni saqlab qo'ying (masalan `7123456789:AAH...`). Bu `BOT_TOKEN`.

## 2-qadam. Kanal va guruhga botni admin qilish

1. **Kanal**: Kanal sozlamalari → Administratorlar → botni qo'shing. "Xabar joylash" va "Xabarlarni tahrirlash" huquqlari yoqilgan bo'lsin.
   - Kanal ochiq bo'lsa, `CHANNEL_ID` = `@kanal_username`.
2. **Guruh**: botni guruhga qo'shing va admin qiling.
3. **O'zingizning ID'ingiz**: [@userinfobot](https://t.me/userinfobot) ga yozing — u bergan raqam `ADMIN_IDS`. Bir nechta admin bo'lsa vergul bilan: `111,222`.
4. **Guruh ID**: bot ishga tushgandan keyin guruhda `/id` yozing — bot `-100...` ko'rinishidagi raqamni beradi. Bu `GROUP_ID`.
   (Yopiq kanal bo'lsa ham shu usul: kanalga `/id` yozib bo'lmaydi, shuning uchun kanaldan postni [@userinfobot](https://t.me/userinfobot) ga forward qiling.)

## 3-qadam. Kodni GitHub ga yuklash

1. [github.com](https://github.com) da ro'yxatdan o'ting (bepul).
2. **New repository** → nom bering (masalan `lead-bot`) → **Create**.
3. **"uploading an existing file"** linkini bosing → shu papkadagi `bot.py`, `requirements.txt` fayllarini sudrab tashlang → **Commit changes**.

## 4-qadam. Render.com ga joylash (5 daqiqa)

1. [render.com](https://render.com) → **Sign up with GitHub**.
2. **New +** → **Web Service** → GitHub repongizni tanlang.
3. Sozlamalar:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Instance Type**: **Free**
4. **Environment Variables** bo'limiga qo'shing:

   | Key | Value |
   |---|---|
   | `BOT_TOKEN` | BotFather bergan token |
   | `CHANNEL_ID` | `@kanal_username` |
   | `GROUP_ID` | `-100...` (hozircha bilmasangiz `0` yozing, keyin almashtirasiz) |
   | `ADMIN_IDS` | sizning ID |
   | `CONTACT_PHONES` | ariza qabul qilingach mijozga ko'rsatiladigan raqamlar, masalan `+998 90 123 45 67, +998 91 765 43 21` |
   | `FIELDY_API_URL`, `FIELDY_API_KEY`, `FIELDY_PIPELINE_ID`, `FIELDY_STAGE_ID` | ixtiyoriy, pastga qarang |

5. **Create Web Service**. 1-2 daqiqada "Live" bo'ladi. Webhook avtomatik o'rnatiladi.
6. Guruhda `/id` yozing → `GROUP_ID` ni Render'da yangilang (Environment → Save, bot o'zi qayta ishga tushadi).

## 5-qadam. Botni uxlatmaslik (UptimeRobot)

Render bepul serveri 15 daqiqa jim tursa uxlab qoladi va birinchi javob ~30 soniya kechikadi. Buning oldini olish:

1. [uptimerobot.com](https://uptimerobot.com) → bepul ro'yxatdan o'ting.
2. **Add New Monitor** → turi **HTTP(s)** → URL: Render bergan manzil (masalan `https://lead-bot-xxxx.onrender.com`) → interval **5 minut** → Save.

## Fieldy CRM ga ulash

Render **Environment** (yoki kompyuterda `.env`) ga qo'shing:

| Nomi | Qiymati |
|---|---|
| `FIELDY_API_URL` | Fieldy bergan kontakt yaratish manzili |
| `FIELDY_API_KEY` | Fieldy API kaliti (`Authorization: Bearer ...` bilan yuboriladi) |
| `FIELDY_PIPELINE_ID` | `78` |
| `FIELDY_STAGE_ID` | `725` |

Bot Fieldy'ga shunday yuboradi:

| Fieldy maydoni | Botdan |
|---|---|
| `firstName`, `lastName` | ism, familiya |
| `phone` | telefon |
| `secondaryPhone`, `region`, `city`, `district`, `address`, `email`, `instagram` | ixtiyoriy savollar (o'tkazib yuborilsa yuborilmaydi) |
| `source` | `TELEGRAM` |
| `sourceDetail` | qaysi post: `post_123` (to'g'ridan-to'g'ri kelsa — `to'g'ridan-to'g'ri`) |
| `telegram` | @username (bo'lsa) |
| `notes` | ingliz tili darajasi, izoh, post linki, Telegram ID |
| `pipelineId`, `stageId` | 78, 725 |

Fieldy xato qaytarsa, adminlarga ⚠️ xabar keladi (lid guruhda baribir bo'ladi).

## Foydalanish

- Kanalga post: botga `/post` → video yuboring (izoh bilan) → **"✅ Kanalga joylash"** ni bosing. Bot sizga ro'yxat linkini ham qaytaradi (Instagram, reklama uchun ham ishlatsa bo'ladi).
- Keyinroq joylash: **"⏰ Keyinroq"** ni bosing va vaqtni yozing: `18:30` (bugun, o'tgan bo'lsa ertaga) yoki `25.11 18:30`. Vaqt — Toshkent vaqti. Botdagi asl xabarni o'chirmang.
- Rejalashtirilgan postlarni ko'rish va bekor qilish: `/rejalar`.
- ⚠️ Rejalar `scheduled.json` faylida saqlanadi. Kompyuterda bot qayta ishga tushsa ham saqlanib qoladi, lekin Render'da **qayta deploy qilinganda o'chadi** — deploydan keyin `/rejalar` ni tekshiring.
- Ariza guruhga yuborilmasa, bot sababini va arizaning o'zini adminlarga yuboradi.
- Bekor qilish: `/cancel`.

## Lokal sinash (ixtiyoriy)

Sozlamalarni `.env` fayliga bir marta yozing (Bloknotda oching), keyin har safar faqat:
```powershell
python bot.py
```
`.env` faylini GitHub'ga **yuklamang** — Render'da sozlamalar Environment bo'limiga yoziladi.
Lokal ishga tushganda webhook o'chadi — keyin Render'dagi botni **Manual Deploy → Restart** qiling.
