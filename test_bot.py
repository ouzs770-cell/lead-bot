import os

os.environ.setdefault("BOT_TOKEN", "1:test")
os.environ.setdefault("CHANNEL_ID", "@kanal")
os.environ.setdefault("GROUP_ID", "-1001")

from datetime import datetime

from bot import fieldy_payload, TZ, clean_email, clean_instagram, clean_phone, parse_time, post_link

now = datetime(2026, 11, 24, 20, 0, tzinfo=TZ)
assert parse_time("21:30", now) == datetime(2026, 11, 24, 21, 30, tzinfo=TZ)
assert parse_time("08:00", now) == datetime(2026, 11, 25, 8, 0, tzinfo=TZ)  # o'tgan vaqt -> ertaga
assert parse_time("25.11 18:30", now) == datetime(2026, 11, 25, 18, 30, tzinfo=TZ)
assert parse_time("01.01 10:00", now) == datetime(2027, 1, 1, 10, 0, tzinfo=TZ)
assert parse_time("31.02 10:00", now) is None
assert parse_time("25:99", now) is None
assert parse_time("ertaga", now) is None

assert clean_phone("+998 90 123-45-67") == "+998901234567"
assert clean_phone("901234567") == "+998901234567"
assert clean_phone("12345") is None
assert clean_phone("salom") is None
assert post_link("42") == "https://t.me/kanal/42"
assert post_link("to'g'ridan-to'g'ri") is None
lead = {"first_name": "Ali", "last_name": "Valiyev", "phone": "+998901234567",
        "english_level": "Intermediate (B1)", "comment": "", "source_post": "42",
        "source_link": "https://t.me/kanal/42", "telegram_id": 5, "telegram_username": None}
p = fieldy_payload(lead)
assert (p["source"], p["sourceDetail"], p["pipelineId"], p["stageId"]) == ("TELEGRAM", "post_42", 78, 725)
assert "telegram" not in p and "Izoh" not in p["notes"] and "B1" in p["notes"]
lead.update(comment="Kechqurun", telegram_username="ali", source_post="to'g'ridan-to'g'ri", source_link=None)
p = fieldy_payload(lead)
assert p["telegram"] == "@ali" and "Izoh: Kechqurun" in p["notes"] and p["sourceDetail"] == "to'g'ridan-to'g'ri"
assert "email" not in p and "secondaryPhone" not in p  # o'tkazib yuborilganlar yuborilmaydi
lead.update(secondary_phone="+998911112233", region="Andijon", city="Andijon", district="", address="",
            email="ali@gmail.com", instagram="@ali_v")
p = fieldy_payload(lead)
assert (p["secondaryPhone"], p["region"], p["email"], p["instagram"]) == ("+998911112233", "Andijon", "ali@gmail.com", "@ali_v")
assert "district" not in p

assert clean_email("Ali@Gmail.com") == "ali@gmail.com" and clean_email("ali@gmail") is None
assert clean_instagram("@ali_v") == "@ali_v"
assert clean_instagram("https://www.instagram.com/ali_v/?hl=en") == "@ali_v"
assert clean_instagram("ali v") is None
print("OK")
