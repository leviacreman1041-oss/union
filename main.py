import telebot
import sqlite3
import time
import re

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"
bot = telebot.TeleBot(TOKEN)
DEV_USERNAME = "levil_8" 

# --- [ قاعدة البيانات ] ---
conn = sqlite3.connect("bot_system.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_cache (user_id INTEGER PRIMARY KEY, username TEXT)")
conn.commit()

# الحالات لتخزين من يضيف رد حالياً
add_resp_state = {}

# --- [ الدوال المساعدة ] ---
def get_user_rank(chat_id, user_id):
    if user_id in [1358013723, 8147516847]: return "مطور"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.user.username == DEV_USERNAME: return "مطور"
        if member.status == 'creator': return "مالك اساسي"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def extract_user(m):
    # الأولوية للرد
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    # المنشن أو اليوزر
    text = m.text or m.caption or ""
    match = re.search(r'@(\w+)', text)
    if match:
        un = match.group(1).lower()
        cursor.execute("SELECT user_id FROM user_cache WHERE username=?", (un,))
        res = cursor.fetchone()
        if res: return res[0]
        try: return bot.get_chat(f"@{un}").id
        except: pass
    return None

# --- [ المعالج الرئيسي ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'document'])
def main_controller(m):
    chat_id, user_id = str(m.chat.id), m.from_user.id
    text = m.text or m.caption or ""
    user_rank = get_user_rank(chat_id, user_id)

    # حفظ اليوزرات
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?, ?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    # --- [ معالجة إضافة رد - المرحلة الثانية ] ---
    if user_id in add_resp_state:
        state = add_resp_state[user_id]
        if text == "الغاء":
            del add_resp_state[user_id]
            return bot.reply_to(m, "⌯ تم الإلغاء.")
        
        if state['step'] == 1:
            add_resp_state[user_id].update({'trigger': text, 'step': 2})
            return bot.reply_to(m, f"⌯ تمام، أرسل الآن (الرد) الذي تريده لـ كلمة: {text}")
        else:
            trigger = state['trigger']
            c_type = m.content_type
            f_id = m.text if c_type == 'text' else None
            if not f_id:
                for a in ['photo','sticker','animation','video','voice','document']:
                    val = getattr(m, a)
                    if val: f_id = val[-1].file_id if a=='photo' else val.file_id; break
            
            cursor.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)", (chat_id, trigger, f_id, c_type, m.caption))
            conn.commit()
            del add_resp_state[user_id]
            return bot.reply_to(m, f"⌯ تم حفظ الرد على ({trigger}) بنجاح.")

    # --- [ أوامر الرفع والتنزيل ] ---
    if text.startswith(("رفع ", "تنزيل ")):
        if user_rank not in ["مالك اساسي", "مالك", "مطور", "مدير"]: return
        target_id = extract_user(m)
        if not target_id:
            return bot.reply_to(m, "⌯ رد على الشخص أو منشنه للرفع/التنزيل.")
        
        valid_ranks = ["مدير", "ادمن", "مميز", "مالك", "مالك اساسي"]
        rank_name = next((r for r in valid_ranks if r in text), None)
        if rank_name:
            if text.startswith("رفع"):
                cursor.execute("INSERT OR REPLACE INTO ranks VALUES (?, ?, ?)", (chat_id, target_id, rank_name))
                msg = f"تم رفع {rank_name}"
            else:
                cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target_id, rank_name))
                msg = f"تم تنزيل {rank_name}"
            conn.commit()
            return bot.reply_to(m, f"⌯ {msg} بنجاح.")

    # --- [ أمر إضافة رد ] ---
    if text == "اضف رد" and user_rank != "عضو":
        add_resp_state[user_id] = {'step': 1}
        return bot.reply_to(m, "⌯ أرسل الكلمة التي تريد الرد عليها الآن:")

    # --- [ رتبتي ] ---
    if text == "رتبتي":
        return bot.reply_to(m, f"⌯ رتبتك هي: {user_rank}")

    # --- [ تشغيل الردود المخزنة ] ---
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, text))
    res = cursor.fetchone()
    if res:
        try:
            if res[1] == 'text': bot.reply_to(m, res[0])
            else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)
        except: pass

bot.infinity_polling()
