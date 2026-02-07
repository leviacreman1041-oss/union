import telebot
import sqlite3
import time
import threading
import re
from telebot import types

# ================== الإعدادات ==================
TOKEN = "8486555369:AAGa6z2L1KKA-ajRdacAK21FAtzH9ZCbm4U"
DEV_USERNAME = "levil_8"

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
    try:
        m = bot.get_chat_member(chat_id, user_id)
        if m.user.username == DEV_USERNAME:
            return "مطور"
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

def can_act(actor_rank, target_rank):
    return POWER.get(actor_rank, 0) > POWER.get(target_rank, 0)

def extract_target(m):
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    parts = m.text.split()
    if len(parts) > 1:
        x = parts[1]
        if x.isdigit():
            return int(x)
        if x.startswith("@"):
            try:
                return bot.get_chat(x).id
            except:
                return None
    return None

def parse_duration(text):
    # 10 دقيقه / 2 ساعه / 1 يوم
    m = re.search(r"(\d+)\s*(د|دقيق|س|ساع|ي|يوم)", text)
    if not m:
        return None
    num = int(m.group(1))
    unit = m.group(2)

    if unit.startswith("د"):
        return num * 60
    if unit.startswith("س"):
        return num * 3600
    if unit.startswith("ي"):
        return num * 86400
    return None

# ================== فك العقوبات تلقائي ==================
def auto_unpunish():
    while True:
        time.sleep(5)
        cur.execute("SELECT chat_id, user_id, type FROM punishments WHERE until <= ?", (now(),))
        rows = cur.fetchall()
        for chat_id, user_id, ptype in rows:
            try:
                if ptype == "كتم":
                    bot.restrict_chat_member(chat_id, user_id, can_send_messages=True)
                elif ptype == "تقييد":
                    bot.restrict_chat_member(chat_id, user_id,
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True
                    )
                elif ptype == "حظر":
                    bot.unban_chat_member(chat_id, user_id)
            except:
                pass
            cur.execute(
                "DELETE FROM punishments WHERE chat_id=? AND user_id=? AND type=?",
                (chat_id, user_id, ptype)
            )
            conn.commit()

threading.Thread(target=auto_unpunish, daemon=True).start()

# ================== المعالج ==================
@bot.message_handler(func=lambda m: m.chat.type in ["group", "supergroup"])
def handler(m):
    text = m.text or ""
    chat_id = m.chat.id
    uid = m.from_user.id

    actor_rank = get_rank(chat_id, uid)

    # ---------- تقييد / كتم / حظر بالمدة ----------
    if any(cmd in text for cmd in ["تقييد", "كتم", "حظر"]):
        if actor_rank not in POWER:
            return

        target = extract_target(m)
        if not target:
            return

        target_rank = get_rank(chat_id, target)
        if not can_act(actor_rank, target_rank):
            return

        duration = parse_duration(text)
        until = now() + duration if duration else None

        try:
            if "كتم" in text:
                bot.restrict_chat_member(chat_id, target, can_send_messages=False)
                ptype = "كتم"

            elif "تقييد" in text:
                bot.restrict_chat_member(
                    chat_id, target,
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False
                )
                ptype = "تقييد"

            elif "حظر" in text:
                bot.ban_chat_member(chat_id, target)
                ptype = "حظر"

            if until:
                cur.execute(
                    "INSERT INTO punishments VALUES (?,?,?,?)",
                    (str(chat_id), target, ptype, until)
                )
                conn.commit()

        except:
            pass

    # ---------- إلغاء ----------
    if text.startswith("الغاء"):
        target = extract_target(m)
        if not target:
            return
        target_rank = get_rank(chat_id, target)
        if not can_act(actor_rank, target_rank):
            return
        try:
            bot.restrict_chat_member(chat_id, target, can_send_messages=True)
            bot.unban_chat_member(chat_id, target)
            cur.execute(
                "DELETE FROM punishments WHERE chat_id=? AND user_id=?",
                (str(chat_id), target)
            )
            conn.commit()
        except:
            pass

# ================== تشغيل ==================
bot.infinity_polling()
