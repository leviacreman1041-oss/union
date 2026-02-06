import telebot
import sqlite3
import time
import re

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DEV_ID = 1358013723  # ايديك يسطا

# --- [ قاعدة البيانات ] ---
conn = sqlite3.connect("bot_pro.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS locks (chat_id TEXT, item TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS cache (user_id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
conn.commit()

# --- [ ميزان القوى (الرتب) ] ---
RANK_POWER = {
    "مطور": 100,
    "مالك اساسي": 90,
    "مالك": 80,
    "مدير": 70,
    "ادمن": 60,
    "مميز": 50,
    "عضو": 10
}

def get_rank(chat_id, user_id):
    if user_id == DEV_ID: return "مطور"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.status == 'creator': return "مالك اساسي"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def extract_user_data(m):
    target_id, duration = None, 0
    text = m.text or m.caption or ""
    
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
    else:
        match = re.search(r'@(\w+)|(\d{7,})', text)
        if match:
            if match.group(1): # يوزر
                un = match.group(1).lower()
                cursor.execute("SELECT user_id FROM cache WHERE username=?", (un,))
                res = cursor.fetchone()
                if res: target_id = res[0]
                else:
                    try: target_id = bot.get_chat(f"@{un}").id
                    except: pass
            else: target_id = int(match.group(2)) # ايدي

    # استخراج وقت التقييد (مثال: كتم @user 10 دقائق)
    time_match = re.search(r'(\d+)\s*(دقيق|ساع|يوم)', text)
    if time_match:
        val, unit = int(time_match.group(1)), time_match.group(2)
        if 'دقيق' in unit: duration = val * 60
        elif 'ساع' in unit: duration = val * 3600
        elif 'يوم' in unit: duration = val * 86400
    return target_id, duration

# --- [ المعالج الرئيسي ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation'])
def handle_all(m):
    if m.chat.type == "private": return
    chat_id, user_id = str(m.chat.id), m.from_user.id
    text = (m.text or m.caption or "").strip()
    
    # حفظ بيانات المستخدم في الكاش عشان اليوزر يشتغل
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", 
                       (user_id, m.from_user.username.lower(), m.from_user.first_name))
        conn.commit()

    rank = get_rank(chat_id, user_id)
    power = RANK_POWER.get(rank, 10)

    # 1. أوامر الحماية (مدير فما فوق)
    if any(text.startswith(x) for x in ["حظر", "كتم", "تقييد", "طرد"]):
        if power < 70: return
        target, sec = extract_user_data(m)
        if not target: return bot.reply_to(m, "<b>⌯ منشن المستخدم أو اكتب يوزره ووقت التقييد.</b>")
        
        if RANK_POWER.get(get_rank(chat_id, target), 10) >= power:
            return bot.reply_to(m, "<b>⌯ لا يمكنك تنفيذ هذا الأمر على رتبة مساوية لك أو أعلى منك.</b>")

        until = int(time.time() + sec) if sec > 0 else 0
        try:
            if "حظر" in text: bot.ban_chat_member(chat_id, target, until_date=until)
            elif "طرد" in text: bot.kick_chat_member(chat_id, target); bot.unban_chat_member(chat_id, target)
            else: bot.restrict_chat_member(chat_id, target, until_date=until, can_send_messages=False)
            bot.reply_to(m, "<b>⌯ تم تنفيذ الأمر بنجاح.</b>")
        except: pass

    # 2. أوامر الرفع والتنزيل
    if text.startswith(("رفع ", "تنزيل ")):
        if power < 70: return
        target, _ = extract_user_data(m)
        if not target: return
        
        valid_ranks = ["مدير", "ادمن", "مميز", "مالك", "مالك اساسي"]
        r_name = next((r for r in valid_ranks if r in text), None)
        
        if r_name:
            if RANK_POWER.get(r_name, 10) >= power and rank != "مطور":
                return bot.reply_to(m, "<b>⌯ لا يمكنك رفع شخص لرتبة أعلى منك أو مساوية لك.</b>")
            
            if text.startswith("رفع"):
                cursor.execute("INSERT OR REPLACE INTO ranks VALUES (?, ?, ?)", (chat_id, target, r_name))
            else:
                cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r_name))
            conn.commit()
            bot.reply_to(m, "<b>⌯ تم التحديث بنجاح.</b>")

    # 3. تنزيل الكل (مطور ومالك اساسي فقط)
    if text == "تنزيل الكل" and power >= 90:
        cursor.execute("DELETE FROM ranks WHERE chat_id=?", (chat_id,))
        conn.commit()
        return bot.reply_to(m, "<b>⌯ تم مسح جميع الرتب.</b>")

    # 4. أوامر الكشف
    if text == "رتبتي": return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")
    
    if text.startswith(("رتبته", "كشف")):
        target, _ = extract_user_data(m)
        if target:
            t_rank = get_rank(chat_id, target)
            return bot.reply_to(m, f"<b>🆔 الايدي: {target}\n🎖 الرتبة: {t_rank}</b>")

    if text == "كشف المجموعه" and power >= 70:
        msg = "<b>⌯ قائمة الرتب:</b>\n"
        for r in ["مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]:
            cursor.execute("SELECT user_id FROM ranks WHERE chat_id=? AND rank=?", (chat_id, r))
            rows = cursor.fetchall()
            if rows:
                msg += f"\n━━ <b>{r}</b> ━━\n"
                for row in rows:
                    cursor.execute("SELECT username FROM cache WHERE user_id=?", (row[0],))
                    u = cursor.fetchone()
                    msg += f"— @{u[0] if u else row[0]}\n"
        return bot.reply_to(m, msg)

    # 5. الفتح والقفل (مدير فما فوق)
    locks = {"الصور": "photo", "الروابط": "links", "الفيديو": "video", "الملصقات": "sticker"}
    if text == "قفل الكل" and power >= 70:
        for v in locks.values(): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, v))
        conn.commit(); return bot.reply_to(m, "<b>⌯ تم قفل جميع الوسائط.</b>")

    if text == "فتح الكل" and power >= 70:
        cursor.execute("DELETE FROM locks WHERE chat_id=?", (chat_id,))
        conn.commit(); return bot.reply_to(m, "<b>⌯ تم فتح جميع الوسائط.</b>")

    if text.startswith(("قفل ", "فتح ")) and power >= 70:
        item = text.split(" ", 1)[1] if len(text.split()) > 1 else ""
        if item in locks:
            if "قفل" in text: cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, locks[item]))
            else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, locks[item]))
            conn.commit(); bot.reply_to(m, f"<b>⌯ تم {text[:3]} {item}.</b>")

    # نظام الحماية (تطبيق الأقفال)
    if power < 60:
        cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
        active_locks = [r[0] for r in cursor.fetchall()]
        if m.content_type in active_locks or ("links" in active_locks and ("t.me" in text or "http" in text)):
            try: bot.delete_message(chat_id, m.message_id)
            except: pass

bot.infinity_polling(skip_pending=True)
