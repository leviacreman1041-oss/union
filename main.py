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
    if m.reply_to_message: return m.reply_to_message.from_user.id
    text = m.text or m.caption or ""
    # البحث عن معرف @
    match = re.search(r'@(\w+)', text)
    if match:
        un = match.group(1).lower()
        cursor.execute("SELECT user_id FROM user_cache WHERE username=?", (un,))
        res = cursor.fetchone()
        if res: return res[0]
        try: return bot.get_chat(f"@{un}").id
        except: return None
    # البحث عن ايدي رقمي
    nums = re.findall(r'\d{7,}', text)
    if nums: return int(nums[0])
    return None

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

    # 1. نظام الـ Anti-Spam
    if rank == "عضو":
        now = time.time()
        if chat_id not in spam_tracker: spam_tracker[chat_id] = {}
        if user_id not in spam_tracker[chat_id]: spam_tracker[chat_id][user_id] = []
        spam_tracker[chat_id][user_id] = [t for t in spam_tracker[chat_id][user_id] if now - t < 5]
        spam_tracker[chat_id][user_id].append(now)
        if len(spam_tracker[chat_id][user_id]) >= 6:
            bot.restrict_chat_member(chat_id, user_id, until_date=int(now + 21600))
            return bot.reply_to(m, "<b>⌯ تم تقييدك 6 ساعات (تكرار).</b>")

    # 2. استبدال الأوامر المخصصة (تغيير أمر)
    cursor.execute("SELECT old_cmd FROM custom_cmds WHERE chat_id=? AND new_cmd=?", (chat_id, raw_text))
    custom = cursor.fetchone()
    if custom: raw_text = custom[0]

    # 3. نظام الحالات (إضافة رد / تغيير أمر)
    if user_id in user_states:
        state = user_states[user_id]
        if raw_text == "الغاء":
            del user_states[user_id]; return bot.reply_to(m, "<b>⌯ تم الإلغاء.</b>")
        
        if state['type'] == 'add_resp':
            if state['step'] == 1:
                user_states[user_id].update({'trig': raw_text, 'step': 2})
                return bot.reply_to(m, "<b>⌯ ارسل الرد الآن (نص/صورة/ملصق..):</b>")
            else:
                c_type = m.content_type
                f_id = raw_text if c_type == 'text' else (m.photo[-1].file_id if c_type == 'photo' else getattr(m, c_type).file_id)
                cursor.execute("INSERT INTO responses VALUES (?,?,?,?,?)", (chat_id, state['trig'], f_id, c_type, m.caption))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم حفظ الرد.</b>")
        
        if state['type'] == 'change_cmd':
            if state['step'] == 1:
                user_states[user_id].update({'old': raw_text, 'step': 2})
                return bot.reply_to(m, f"<b>⌯ ارسل الكلمة البديلة لـ ({raw_text}):</b>")
            else:
                cursor.execute("INSERT OR REPLACE INTO custom_cmds VALUES (?,?,?)", (chat_id, state['old'], raw_text))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم تغيير الأمر بنجاح.</b>")

    # 4. الأوامر الإدارية
    # [رفع / تنزيل]
    if raw_text.startswith(("رفع ", "تنزيل ")):
        if rank == "عضو": return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ منشن المستخدم أو رد عليه.</b>")
        for r in ["مدير", "ادمن", "مميز", "مالك"]:
            if r in raw_text:
                if raw_text.startswith("رفع"):
                    cursor.execute("INSERT INTO ranks VALUES (?,?,?)", (chat_id, target, r))
                    msg = f"رفع {r}"
                else:
                    cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r))
                    msg = f"تنزيل {r}"
                conn.commit()
                return bot.reply_to(m, f"<b>⌯ تم {msg} بنجاح.</b>")

    # [قفل / فتح]
    if raw_text.startswith(("قفل ", "فتح ")):
        if rank in ["عضو", "مميز"]: return
        l_map = {"الصور":"photo", "الفيديو":"video", "الروابط":"links", "الملصقات":"sticker", "الكل":"all"}
        for k, v in l_map.items():
            if k in raw_text:
                if v == "all":
                    for item in ["photo", "video", "links", "sticker"]:
                        if raw_text.startswith("قفل"): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, item))
                        else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, item))
                else:
                    if raw_text.startswith("قفل"): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, v))
                    else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, v))
                conn.commit()
                return bot.reply_to(m, f"<b>⌯ تم {raw_text.split()[0]} {k} بنجاح.</b>")

    # [رفع القيود]
    if raw_text.startswith("رفع القيود") and rank != "عضو":
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ ارسل المعرف أو رد عليه.</b>")
        bot.unban_chat_member(chat_id, target, only_if_banned=True)
        bot.restrict_chat_member(chat_id, target, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
        return bot.reply_to(m, "<b>⌯ تم رفع كافة قيود المستخدم.</b>")

    # [إدارة الردود]
    if raw_text == "اضف رد" and rank != "عضو":
        user_states[user_id] = {'type': 'add_resp', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل كلمة الرد:</b>")
    
    if raw_text.startswith("مسح رد ") and rank != "عضو":
        trig = raw_text.replace("مسح رد ", "").strip()
        cursor.execute("DELETE FROM responses WHERE chat_id=? AND trigger=?", (chat_id, trig))
        conn.commit()
        return bot.reply_to(m, f"<b>⌯ تم حذف الرد ({trig}).</b>")

    if raw_text == "الردود" and rank != "عضو":
        cursor.execute("SELECT trigger FROM responses WHERE chat_id=?", (chat_id,))
        res = cursor.fetchall()
        out = "<b>⌯ قائمة الردود:\n</b>" + "\n".join([f"- {r[0]}" for r in res])
        return bot.reply_to(m, out if res else "<b>⌯ لا توجد ردود.</b>")

    if raw_text == "تغيير امر" and rank == "مطور":
        user_states[user_id] = {'type': 'change_cmd', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الأمر الأصلي (مثل: قفل الصور):</b>")

    if raw_text == "رتبتي": return bot.reply_to(m, f"<b>⌯ رتبتك: {rank}</b>")

    # 5. تشغيل الردود والأقفال
    cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
    active_locks = [r[0] for r in cursor.fetchall()]
    if rank == "عضو" and (m.content_type in active_locks or ("links" in active_locks and "t.me" in raw_text)):
        try: bot.delete_message(chat_id, m.message_id); return
        except: pass

    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_id, raw_text))
    res = cursor.fetchone()
    if res:
        if res[1] == 'text': bot.reply_to(m, res[0])
        else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)

if __name__ == "__main__":
    bot.remove_webhook()
    print("🚀 ليفاي، البوت الآن جاهز 100% وبكامل الصلاحيات!")
    bot.infinity_polling(skip_pending=True)
