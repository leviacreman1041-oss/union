
import telebot
import sqlite3
import time
import threading
import re

# ================== الإعدادات ==================
TOKEN = "8486555369:AAGa6z2L1KKA-ajRdacAK21FAtzH9ZCbm4U"
DEV_ID = 8147516847  # انت كمطور
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ================== قاعدة البيانات ==================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS ranks (
    chat_id TEXT,
    user_id INTEGER,
    rank TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS punishments (
    chat_id TEXT,
    user_id INTEGER,
    type TEXT,
    until INTEGER
)
""")

conn.commit()

# ================== الهرمية ==================
POWER = {
    "مطور": 100,
    "مالك اساسي": 90,
    "مالك": 80,
    "مدير": 70,
    "ادمن": 60,
    "مميز": 30,
    "عضو": 10
}

# ================== أدوات ==================
def now():
    return int(time.time())

def get_rank(chat_id, user_id):
    if user_id == DEV_ID:
        return "مطور"
    try:
        m = bot.get_chat_member(chat_id, user_id)
        if m.status == "creator":
            return "مالك اساسي"
    except:
        pass

    cur.execute(
        "SELECT rank FROM ranks WHERE chat_id=? AND user_id=?",
        (str(chat_id), user_id)
    )
    r = cur.fetchone()
    return r[0] if r else "عضو"

def can_act(actor, target):
    return POWER.get(actor, 0) > POWER.get(target, 0)

def extract_target(m):
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    parts = m.text.split()
    if len(parts) > 1:
        x = parts[-1]
        if x.isdigit():
            return int(x)
        if x.startswith("@"):
            try:
                return bot.get_chat(x).id
            except:
                return None
    return None

def parse_duration(text):
    m = re.search(r"(\d+)\s*(د|دقيق|س|ساع|ي|يوم)", text)
    if not m:
        return None
    n = int(m.group(1))
    u = m.group(2)
    if u.startswith("د"):
        return n * 60
    if u.startswith("س"):
        return n * 3600
    if u.startswith("ي"):
        return n * 86400
    return None

# ================== فك العقوبات تلقائي ==================
def auto_unpunish():
    while True:
        time.sleep(5)
        cur.execute("SELECT chat_id, user_id FROM punishments WHERE until <= ?", (now(),))
        rows = cur.fetchall()
        for chat_id, user_id in rows:
            try:
                bot.restrict_chat_member(
                    chat_id, user_id,
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True
                )
            except:
                pass
            cur.execute(
                "DELETE FROM punishments WHERE chat_id=? AND user_id=?",
                (chat_id, user_id)
            )
            conn.commit()

threading.Thread(target=auto_unpunish, daemon=True).start()

# ================== المعالج ==================
@bot.message_handler(func=lambda m: m.chat.type in ["group", "supergroup"])
def handler(m):
    chat_id = m.chat.id
    uid = m.from_user.id
    text = m.text or ""
    my_rank = get_rank(chat_id, uid)

    # ===== رتبتي =====
    if text == "رتبتي":
        bot.reply_to(m, f"⌯ رتبتك: <b>{my_rank}</b>")
        return

    # ===== رتبته =====
    if text.startswith("رتبته"):
        target = extract_target(m)
        if not target:
            return
        r = get_rank(chat_id, target)
        bot.reply_to(m, f"⌯ رتبته: <b>{r}</b>")
        return

    # ===== ايدي =====
    if text == "ايدي":
        target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
        rank = get_rank(chat_id, target.id)

        info = (
            f"👤 الاسم: {target.first_name}\n"
            f"🆔 الايدي: <code>{target.id}</code>\n"
            f"🎖 الرتبة: {rank}\n"
            f"🔗 اليوزر: @{target.username if target.username else 'لا يوجد'}"
        )

        try:
            photos = bot.get_user_profile_photos(target.id, limit=1)
            bot.send_photo(
                chat_id,
                photos.photos[0][-1].file_id,
                caption=info,
                reply_to_message_id=m.message_id
            )
        except:
            bot.reply_to(m, info)
        return

    # ===== تقييد =====
    if text.startswith("تقييد"):
        if my_rank == "عضو":
            return

        target = extract_target(m)
        if not target:
            return

        target_rank = get_rank(chat_id, target)
        if not can_act(my_rank, target_rank):
            return

        duration = parse_duration(text)
        until = now() + duration if duration else None

        try:
            bot.restrict_chat_member(
                chat_id, target,
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False
            )
            if until:
                cur.execute(
                    "INSERT INTO punishments VALUES (?,?,?,?)",
                    (str(chat_id), target, "تقييد", until)
                )
                conn.commit()
        except:
            pass

# ================== تشغيل ==================
bot.infinity_polling()
