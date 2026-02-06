import telebot
import sqlite3
import time
import re

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DEV_USERNAME = "levil_8" 

# --- [ قاعدة البيانات ] ---
def get_db():
    conn = sqlite3.connect("bot_system.db", check_same_thread=False)
    return conn

conn = get_db()
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_cache (user_id INTEGER PRIMARY KEY, username TEXT)")
conn.commit()

# قاموس لتخزين الحالات
user_steps = {}

# --- [ الدوال المساعدة ] ---
def get_rank(chat_id, user_id):
    if user_id in [1358013723, 8147516847]: return "مطور"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.user.username == DEV_USERNAME: return "مطور"
        if member.status == 'creator': return "مالك اساسي"
    except: pass
    
    cursor.execute("SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

# --- [ معالج إضافة رد ] ---
@bot.message_handler(func=lambda m: m.from_user.id in user_steps)
def handle_steps(m):
    uid = m.from_user.id
    chat_id = str(m.chat.id)
    step = user_steps[uid].get('step')
    text = m.text or m.caption or ""

    if text == "الغاء":
        del user_steps[uid]
        return bot.reply_to(m, "<b>⌯ تم إلغاء العملية.</b>")

    if step == 1:
        user_steps[uid]['trigger'] = text
        user_steps[uid]['step'] = 2
        bot.reply_to(m, f"<b>⌯ تمام، أرسل الآن الرد (نص، صورة، ملصق، إلخ) لـ: {text}</b>")
    
    elif step == 2:
        trigger = user_steps[uid]['trigger']
        content_type = m.content_type
        
        # جلب ملف الميديا
        file_id = m.text if content_type == 'text' else None
        if not file_id:
            if content_type == 'photo': file_id = m.photo[-1].file_id
            else: file_id = getattr(m, content_type).file_id
        
        cursor.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)", 
                       (chat_id, trigger, file_id, content_type, m.caption))
        conn.commit()
        del user_steps[uid]
        bot.reply_to(m, f"<b>⌯ تم حفظ الرد على ({trigger}) بنجاح!</b>")

# --- [ المعالج الرئيسي ] ---
@bot.message_handler(content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'document'])
def main(m):
    if m.chat.type == "private": return
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = (m.text or m.caption or "").strip()
    rank = get_rank(chat_id, user_id)

    # حفظ اليوزر
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?, ?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    # --- 1. أوامر الرفع والتنزيل (بالرد) ---
    if text.startswith(("رفع ", "تنزيل ")) and m.reply_to_message:
        if rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]: return
        target_id = m.reply_to_message.from_user.id
        valid_ranks = ["مدير", "ادمن", "مميز", "مالك", "مالك اساسي"]
        
        selected_rank = next((r for r in valid_ranks if r in text), None)
        if selected_rank:
            if text.startswith("رفع"):
                cursor.execute("INSERT OR REPLACE INTO ranks VALUES (?, ?, ?)", (chat_id, target_id, selected_rank))
                bot.reply_to(m, f"<b>⌯ تم رفع الشخص {selected_rank}</b>")
            else:
                cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target_id, selected_rank))
                bot.reply_to(m, f"<b>⌯ تم تنزيل الشخص من {selected_rank}</b>")
            conn.commit()
            return

    # --- 2. أمر إضافة رد ---
    if text == "اضف رد":
        if rank == "عضو": return
        user_steps[user_id] = {'step': 1}
        return bot.reply_to(m, "<b>⌯ أرسل الآن الكلمة التي تريد الرد عليها:</b>")

    # --- 3. أوامر المعلومات ---
    if text == "رتبتي":
        return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")

    if text == "رتبته" and m.reply_to_message:
        t_rank = get_rank(chat_id, m.reply_to_message.from_user.id)
        return bot.reply_to(m, f"<b>⌯ رتبته هي: {t_rank}</b>")

    # --- 4. تشغيل الردود ---
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, text))
    res = cursor.fetchone()
    if res:
        try:
            r_val, r_type, r_cap = res[0], res[1], res[2]
            if r_type == 'text': bot.reply_to(m, r_val)
            else: getattr(bot, f"send_{r_type}")(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
        except: pass

print("🚀 البوت شغال يا ليفاي.. جرب الرفع بالرد دلوقتي!")
bot.infinity_polling(skip_pending=True)
