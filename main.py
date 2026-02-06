import telebot
import sqlite3
import time
import re
from threading import Lock

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAF76lTpn9L_SVHUmO_sickQIGGModV1_Ds"
DEV_USERNAME = "levil_8"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DB_NAME = "master_legend_v16.db"
db_lock = Lock()

RANK_VALUES = {"مطور": 100, "مالك اساسي": 90, "مالك": 80, "مدير": 70, "ادمن": 60, "مميز": 50, "عضو": 10}

# --- [ قاعدة البيانات ] ---
def setup_db():
    with db_lock:
        conn = sqlite3.connect(DB_NAME, check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS custom_cmds (chat_id TEXT, old_cmd TEXT, new_cmd TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS locks (chat_id TEXT, item TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_cache (user_id INTEGER PRIMARY KEY, username TEXT)")
        conn.commit()
        return conn, cursor

conn, cursor = setup_db()
user_states = {}
spam_tracker = {}

# --- [ الدوال المساعدة ] ---
def get_rank(chat_id, user_id):
    if user_id in [1358013723, 8147516847]: return "مطور"
    try:
        u = bot.get_chat_member(chat_id, user_id)
        if u.status == 'creator' or u.user.username == DEV_USERNAME: return "مطور"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def extract_user(m):
    # 1. بالرد
    if m.reply_to_message: return m.reply_to_message.from_user.id
    
    text = m.text or m.caption or ""
    parts = text.split()
    
    # 2. بالمنشن @ أو اليوزر المكتوب
    for part in parts:
        if part.startswith("@"):
            un = part.replace("@", "").lower()
            cursor.execute("SELECT user_id FROM user_cache WHERE username=?", (un,))
            res = cursor.fetchone()
            if res: return res[0]
            try: return bot.get_chat(f"@{un}").id
            except: pass
        
        # البحث عن الايدي الرقمي
        if part.isdigit() and len(part) > 7:
            return int(part)

    # 3. محاولة البحث في الكاش بالاسم المكتوب (بدون @)
    for part in parts:
        cursor.execute("SELECT user_id FROM user_cache WHERE username=?", (part.lower(),))
        res = cursor.fetchone()
        if res: return res[0]
        
    return None

def get_rank_list(chat_id, target_rank):
    cursor.execute("SELECT user_id FROM ranks WHERE chat_id=? AND rank=?", (str(chat_id), target_rank))
    users = cursor.fetchall()
    if not users: return f"<b>⌯ لا يوجد {target_rank} حالياً.</b>"
    out = f"<b>⌯ قائمة {target_rank}:\n\n</b>"
    for i, u in enumerate(users, 1):
        cursor.execute("SELECT username FROM user_cache WHERE user_id=?", (u[0],))
        name = cursor.fetchone()
        user_display = f"@{name[0]}" if name else f"<code>{u[0]}</code>"
        out += f"{i} - {user_display}\n"
    return out

# --- [ المعالج الرئيسي ] ---
@bot.message_handler(func=lambda m: True, content_types=['text','photo','sticker','video','animation','voice','video_note','document'])
def handle_all(m):
    if m.chat.type == 'private': return
    chat_id, user_id = str(m.chat.id), m.from_user.id
    
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?,?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    rank = get_rank(chat_id, user_id)
    raw_text = (m.text or m.caption or "").strip()

    # 1. الأقفال والدردشة
    cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
    active_locks = [r[0] for r in cursor.fetchall()]

    if rank == "عضو" or rank == "مميز":
        if "chat" in active_locks:
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass
        if m.content_type in active_locks or ("links" in active_locks and ("t.me" in raw_text or "http" in raw_text)):
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass

    # 2. مضاد التكرار
    if rank == "عضو":
        now = time.time()
        if chat_id not in spam_tracker: spam_tracker[chat_id] = {}
        if user_id not in spam_tracker[chat_id]: spam_tracker[chat_id][user_id] = []
        spam_tracker[chat_id][user_id] = [t for t in spam_tracker[chat_id][user_id] if now - t < 5]
        spam_tracker[chat_id][user_id].append(now)
        if len(spam_tracker[chat_id][user_id]) >= 6:
            try:
                bot.restrict_chat_member(chat_id, user_id, until_date=int(now + 21600))
                return bot.reply_to(m, "<b>⌯ تم تقييدك 6 ساعات بسبب التكرار.</b>")
            except: pass

    # 3. القوائم
    list_cmds = {"المميزين": "مميز", "الادمنيه": "ادمن", "المدراء": "مدير", "المالكين": "مالك", "المالكين الاساسيين": "مالك اساسي"}
    if raw_text in list_cmds:
        if RANK_VALUES.get(rank, 0) > RANK_VALUES.get(list_cmds[raw_text], 0):
            return bot.reply_to(m, get_rank_list(chat_id, list_cmds[raw_text]))

    # 4. الرتب
    if raw_text == "رتبتي": return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")
    if raw_text.startswith("رتبته"):
        target = extract_user(m)
        if target:
            t_rank = get_rank(chat_id, target)
            return bot.reply_to(m, f"<b>⌯ رتبته هي: {t_rank}</b>")
        return bot.reply_to(m, "<b>⌯ منشن المستخدم أو اكتب يوزره.</b>")

    # 5. قفل/فتح الدردشة
    if raw_text == "قفل الدردشه" and rank not in ["عضو", "مميز", "ادمن"]:
        cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, "chat"))
        conn.commit(); return bot.reply_to(m, "<b>⌯ تم قفل الدردشة.</b>")
    if raw_text == "فتح الدردشه" and rank not in ["عضو", "مميز", "ادمن"]:
        cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, "chat"))
        conn.commit(); return bot.reply_to(m, "<b>⌯ تم فتح الدردشة.</b>")

    # 6. الرفع والتنزيل (يدعم اليوزر)
    if raw_text.startswith(("رفع ", "تنزيل ")):
        if rank in ["عضو", "مميز"]: return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ لم أتعرف على المستخدم.</b>")
        
        for r in ["مدير", "ادمن", "مميز", "مالك", "مالك اساسي"]:
            if r in raw_text:
                if raw_text.startswith("رفع"):
                    cursor.execute("INSERT INTO ranks VALUES (?,?,?)", (chat_id, target, r))
                    msg = f"رفع {r}"
                else:
                    cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r))
                    msg = f"تنزيل {r}"
                conn.commit(); return bot.reply_to(m, f"<b>⌯ تم {msg} بنجاح.</b>")

    # 7. الردود
    if raw_text == "اضف رد" and rank != "عضو":
        user_states[user_id] = {'type': 'add_resp', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الكلمة الآن:</b>")

    if user_id in user_states:
        state = user_states[user_id]
        if raw_text == "الغاء":
            del user_states[user_id]; return bot.reply_to(m, "<b>⌯ تم الإلغاء.</b>")
        if state['type'] == 'add_resp':
            if state['step'] == 1:
                user_states[user_id].update({'trig': raw_text, 'step': 2})
                return bot.reply_to(m, "<b>⌯ ارسل الرد الآن:</b>")
            else:
                c_type = m.content_type
                f_id = raw_text if c_type == 'text' else (m.photo[-1].file_id if c_type == 'photo' else getattr(m, c_type).file_id)
                cursor.execute("INSERT INTO responses VALUES (?,?,?,?,?)", (chat_id, state['trig'], f_id, c_type, m.caption))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم حفظ الرد.</b>")

    # تشغيل الردود
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_id, raw_text))
    res = cursor.fetchone()
    if res:
        if res[1] == 'text': bot.reply_to(m, res[0])
        else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)

if __name__ == "__main__":
    bot.remove_webhook()
    print("🚀 البوت جاهز يا ليفاي! الرفع باليوزر شغال الآن.")
    bot.infinity_polling(skip_pending=True)
