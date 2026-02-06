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
user_states = {} 
spam_tracker = {} # تتبع التكرار

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
    # دعم الرد
    if m.reply_to_message: return m.reply_to_message.from_user.id
    # دعم المنشن (@user)
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
    # دعم الايدي الرقمي في النص
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
    
    # تحديث الكاش لليوزرات
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?,?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    rank = get_rank(chat_id, user_id)
    raw_text = m.text or m.caption or ""

    # --- [ نظام مضاد التكرار (Anti-Spam) ] ---
    if rank == "عضو":
        now = time.time()
        if chat_id not in spam_tracker: spam_tracker[chat_id] = {}
        if user_id not in spam_tracker[chat_id]: spam_tracker[chat_id][user_id] = []
        
        # تنظيف الرسائل القديمة (أكثر من 5 ثواني)
        spam_tracker[chat_id][user_id] = [t for t in spam_tracker[chat_id][user_id] if now - t < 5]
        spam_tracker[chat_id][user_id].append(now)
        
        if len(spam_tracker[chat_id][user_id]) >= 6:
            try:
                bot.restrict_chat_member(chat_id, user_id, until_date=int(now + 21600))
                bot.reply_to(m, "<b>⌯ تم تقييدك لمدة 6 ساعات بسبب التكرار.</b>")
                spam_tracker[chat_id][user_id] = [] 
                return
            except: pass

    # --- [ نظام الحالات ] ---
    if user_id in user_states:
        state = user_states[user_id]
        if raw_text == "الغاء":
            del user_states[user_id]; return bot.reply_to(m, "<b>⌯ تم إلغاء العملية.</b>")
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

    # --- [ الأوامر ] ---
    if raw_text == "رتبتي": return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")
    
    # قفل الكل (ماعدا الدردشة)
    if raw_text == "قفل الكل" and rank not in ["عضو", "مميز", "ادمن"]:
        all_items = ["photo", "video", "links", "sticker", "animation", "voice", "document"]
        for item in all_items:
            cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, item))
        conn.commit()
        return bot.reply_to(m, "<b>⌯ تم قفل جميع الوسائط والروابط (الدردشة مفتوحة).</b>")

    # رفع القيود (باليوزر/الرد/الايدي)
    if raw_text.startswith("رفع القيود") and rank not in ["عضو", "مميز"]:
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ ايدي/معرف/بالرد.</b>")
        try:
            bot.unban_chat_member(chat_id, target, only_if_banned=True)
            bot.restrict_chat_member(chat_id, target, 
                can_send_messages=True, can_send_media_messages=True, 
                can_send_other_messages=True, can_add_web_page_previews=True)
            return bot.reply_to(m, "<b>⌯ تم رفع كافة القيود عن المستخدم.</b>")
        except: return bot.reply_to(m, "<b>⌯ فشل الإجراء، تأكد من صلاحياتي.</b>")

    cmd_parts = raw_text.split()
    if not cmd_parts: return
    action = cmd_parts[0]

    # [رفع/تنزيل] - يدعم اليوزر
    if action in ["رفع", "تنزيل"] and len(cmd_parts) > 1:
        if rank in ["عضو", "مميز"]: return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ منشن المستخدم أو رد عليه.</b>")
        target_rank = get_rank(chat_id, target)
        if RANK_VALUES.get(rank, 0) <= RANK_VALUES.get(target_rank, 0) and user_id != target:
            return bot.reply_to(m, "<b>⌯ رتبته أعلى منك!</b>")
        for r in ["مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]:
            if r in raw_text:
                if action == "رفع": cursor.execute("INSERT INTO ranks VALUES (?,?,?)", (chat_id, target, r))
                else: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r))
                conn.commit(); return bot.reply_to(m, f"<b>⌯ تم {action} {r} بنجاح.</b>")

    # [حظر/تقييد] - يدعم اليوزر
    if action in ["حظر", "كتم", "تقيد", "تقييد"]:
        if rank in ["عضو", "مميز", "ادمن"]: return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ منشن المستخدم أو رد عليه.</b>")
        sec = parse_time(raw_text)
        until = int(time.time() + sec) if sec > 0 else 0
        try:
            if action == "حظر": bot.ban_chat_member(chat_id, target, until_date=until)
            else: bot.restrict_chat_member(chat_id, target, until_date=until, can_send_messages=False)
            bot.reply_to(m, f"<b>⌯ تم {action} المستخدم.</b>")
        except: pass

    # [حماية الأقفال]
    cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
    current_locks = [r[0] for r in cursor.fetchall()]
    
    if rank == "عضو":
        if (m.content_type in current_locks) or ("links" in current_locks and re.search(r't\.me/|http', raw_text)):
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass
    elif rank == "مميز":
        if "chat" in current_locks:
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
    print("🚀 الوحش V16 يعمل بكامل طاقته!")
    bot.infinity_polling(skip_pending=True)
