import telebot
import sqlite3
import time
import re
import os
from threading import Lock

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAF76lTpn9L_SVHUmO_sickQIGGModV1_Ds"
DEV_USERNAME = "levil_8"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_NAME = "master_legend_v16.db"
db_lock = Lock()

# ترتيب الرتب وقيمتها
RANK_VALUES = {
    "مطور": 100,
    "مالك اساسي": 90,
    "مالك": 80,
    "مدير": 70,
    "ادمن": 60,
    "مميز": 50,
    "عضو": 10
}

# --- [ إعداد قاعدة البيانات ] ---
def setup_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS custom_cmds (chat_id TEXT, old_cmd TEXT, new_cmd TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS locks (chat_id TEXT, item TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS stats (chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_cache (user_id INTEGER PRIMARY KEY, username TEXT)")
        conn.commit()
        return conn, cursor

conn, cursor = setup_db()
user_states = {} # لتخزين خطوات "اضف رد" و "تغيير امر"

# --- [ الدوال الذكية ] ---
def get_rank(chat_id, user_id):
    try:
        if user_id in [1358013723, 8147516847]: return "مطور"
        u = bot.get_chat_member(chat_id, user_id)
        if u.user.username == DEV_USERNAME: return "مطور"
        if u.status == 'creator': return "مالك اساسي"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def extract_user(m):
    if m.reply_to_message: return m.reply_to_message.from_user.id
    if m.entities:
        for ent in m.entities:
            if ent.type == "text_mention": return ent.user.id
            if ent.type == "mention":
                un = m.text[ent.offset:ent.offset+ent.length].replace("@", "")
                cursor.execute("SELECT user_id FROM user_cache WHERE username=?", (un.lower(),))
                res = cursor.fetchone()
                if res: return res[0]
                try: return bot.get_chat(f"@{un}").id
                except: pass
    p = m.text.split()
    for word in p:
        if word.isdigit() and len(word) > 7: return int(word)
    return None

def parse_time(text):
    match = re.search(r'(\d+)\s*(دقيقه|دقيقة|ساعه|ساعة|يوم|ايام)', text)
    if not match: return 0
    val, unit = int(match.group(1)), match.group(2)
    if 'دقيق' in unit: return val * 60
    if 'ساع' in unit: return val * 3600
    return val * 86400 if 'يوم' in unit or 'ايام' in unit else 0

# --- [ المعالج الرئيسي ] ---
@bot.message_handler(func=lambda m: True, content_types=['text','photo','sticker','video','animation','voice','video_note','document'])
def handle_all(m):
    if m.chat.type == 'private': return
    chat_id, user_id = str(m.chat.id), m.from_user.id
    
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?,?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    rank = get_rank(chat_id, user_id)
    raw_text = m.text or m.caption or ""

    # 1. نظام الحالات (إكمال الأوامر)
    if user_id in user_states:
        state = user_states[user_id]
        if raw_text == "الغاء":
            del user_states[user_id]
            return bot.reply_to(m, "<b>⌯ تم إلغاء العملية.</b>")

        if state['type'] == 'add_resp':
            if state['step'] == 1:
                user_states[user_id].update({'trig': raw_text, 'step': 2})
                return bot.reply_to(m, "<b>⌯ ارسل الرد الآن (نص، صورة، ملصق، فيديو):</b>")
            else:
                c_type = m.content_type
                f_id = raw_text if c_type == 'text' else (m.photo[-1].file_id if c_type == 'photo' else getattr(m, c_type).file_id)
                cursor.execute("INSERT INTO responses VALUES (?,?,?,?,?)", (chat_id, state['trig'], f_id, c_type, m.caption))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم حفظ الرد بنجاح.</b>")

        if state['type'] == 'change_cmd':
            if state['step'] == 1:
                user_states[user_id].update({'old': raw_text, 'step': 2})
                return bot.reply_to(m, f"<b>⌯ تم اختيار ({raw_text})، ارسل الكلمة البديلة:</b>")
            else:
                cursor.execute("INSERT OR REPLACE INTO custom_cmds VALUES (?,?,?)", (chat_id, state['old'], raw_text))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم تغيير الأمر بنجاح.</b>")

    # 2. الأوامر الأساسية
    if raw_text == "رتبتي":
        return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")

    if raw_text == "اضف رد" and rank != "عضو":
        user_states[user_id] = {'type': 'add_resp', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الكلمة التي تريد الرد عليها:</b>")

    if raw_text == "تغيير امر" and rank in ["مطور", "مالك اساسي"]:
        user_states[user_id] = {'type': 'change_cmd', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الأمر الأصلي (مثل: حظر):</b>")

    # 3. بقية أوامر الإدارة والكشف
    cmd_parts = raw_text.split()
    if not cmd_parts: return
    action = cmd_parts[0]

    # [رفع/تنزيل]
    if action in ["رفع", "تنزيل"] and len(cmd_parts) > 1:
        if rank in ["عضو", "مميز"]: return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ منشن المستخدم أو رد عليه.</b>")
        target_rank = get_rank(chat_id, target)
        if RANK_VALUES.get(rank, 0) <= RANK_VALUES.get(target_rank, 0) and user_id != target:
            return bot.reply_to(m, "<b>⌯ رتبته أعلى منك!</b>")
        for r in ["مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]:
            if r in raw_text:
                if rank == "ادمن" and r != "مميز": continue
                if action == "رفع": cursor.execute("INSERT INTO ranks VALUES (?,?,?)", (chat_id, target, r))
                else: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r))
                conn.commit(); return bot.reply_to(m, f"<b>⌯ تم {action} {r} بنجاح.</b>")

    # [حظر/تقييد]
    if action in ["حظر", "كتم", "تقيد", "تقييد"]:
        if rank in ["عضو", "مميز", "ادمن"]: return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ لم أتعرف على المستخدم.</b>")
        sec = parse_time(raw_text)
        until = int(time.time() + sec) if sec > 0 else 0
        try:
            if action == "حظر": bot.ban_chat_member(chat_id, target, until_date=until)
            else: bot.restrict_chat_member(chat_id, target, until_date=until, can_send_messages=False)
            bot.reply_to(m, f"<b>⌯ تم {action} المستخدم {'مؤقتاً' if sec > 0 else 'دائماً'}.</b>")
        except: bot.reply_to(m, "<b>⌯ خطأ في الصلاحيات.</b>")

    if action == "كشف":
        target = extract_user(m) or user_id
        return bot.reply_to(m, f"<b>👤 الايدي:</b> <code>{target}</code>\n<b>🎖 الرتبة:</b> {get_rank(chat_id, target)}")

    if action == "رتبته":
        target = extract_user(m)
        if target: return bot.reply_to(m, f"<b>🎖 رتبته هي: {get_rank(chat_id, target)}</b>")

    if raw_text == "ايدي":
        return bot.reply_to(m, f"<b>🆔 ايديك: <code>{user_id}</code>\n🎖 رتبتك: {rank}</b>")

    # [القفل والفتح]
    if action in ["قفل", "فتح"] and rank not in ["عضو", "مميز", "ادمن"]:
        l_map = {"الصور":"photo", "الفيديو":"video", "الروابط":"links", "الدردشه":"chat", "الملصقات":"sticker"}
        for k, v in l_map.items():
            if k in raw_text:
                if action == "قفل": cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, v))
                else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, v))
                conn.commit(); return bot.reply_to(m, f"<b>⌯ تم {action} {k}.</b>")

    # [حماية الأقفال]
    if rank == "عضو":
        cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
        locks = [r[0] for r in cursor.fetchall()]
        if (m.content_type in locks) or ("links" in locks and re.search(r't\.me/|http', raw_text)) or ("chat" in locks):
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass
    elif rank == "مميز":
        cursor.execute("SELECT 1 FROM locks WHERE chat_id=? AND item='chat'", (chat_id,))
        if cursor.fetchone():
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass

    # [تشغيل الردود]
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_id, raw_text))
    res = cursor.fetchone()
    if res:
        try:
            if res[1] == 'text': bot.reply_to(m, res[0])
            else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)
        except: pass

if __name__ == "__main__":
    bot.remove_webhook()
    print("🚀 تم تفعيل أوامر الحالات والرتب بنجاح!")
    bot.infinity_polling(skip_pending=True)
