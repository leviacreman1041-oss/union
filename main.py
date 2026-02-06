import telebot
import sqlite3
import os
import time
import re # أضفنا مكتبة re للبحث المتقدم

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"
bot = telebot.TeleBot(TOKEN)
DEV_USERNAME = "levil_8" 

# --- [ قاعدة البيانات الشاملة ] ---
conn = sqlite3.connect("bot_system.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS ranks (chat_id TEXT, user_id INTEGER, rank TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS muted (chat_id TEXT, user_id INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS stats (chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS custom_cmds (chat_id TEXT, old_cmd TEXT, new_cmd TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS locks (chat_id TEXT, item TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS user_cache (user_id INTEGER PRIMARY KEY, username TEXT)") # جدول جديد لحفظ اليوزرات
conn.commit()

change_state = {}     
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
    # البحث عن ايدي
    parts = text.split()
    for part in parts:
        if part.isdigit() and len(part) > 6: return int(part)
    return None

def get_cmd(chat_id, default):
    cursor.execute("SELECT new_cmd FROM custom_cmds WHERE chat_id = ? AND old_cmd = ?", (str(chat_id), default))
    res = cursor.fetchone()
    return res[0] if res else default

def is_locked(chat_id, item):
    cursor.execute("SELECT 1 FROM locks WHERE chat_id = ? AND item = ?", (str(chat_id), item))
    return cursor.fetchone() is not None

def show_full_list(m, rank_title):
    cursor.execute("SELECT user_id FROM ranks WHERE chat_id = ? AND rank = ?", (str(m.chat.id), rank_title))
    rows = cursor.fetchall()
    if not rows:
        return bot.reply_to(m, f"<b>⌯ لا يوجد {rank_title} حالياً.</b>", parse_mode="HTML")
    msg = f"<b>⌯ قائمة {rank_title}:</b>\n"
    for row in rows:
        uid = row[0]
        cursor.execute("SELECT username FROM user_cache WHERE user_id=?", (uid,))
        cached = cursor.fetchone()
        user_link = f"@{cached[0]}" if cached else f"<code>{uid}</code>"
        msg += f"• {user_link}\n"
    bot.reply_to(m, msg, parse_mode="HTML")

# --- [ معالج الرسائل الرئيسي ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'audio', 'document', 'video_note'])
def main_controller(m):
    if not m.chat.type in ['group', 'supergroup']: return
    chat_id, user_id = str(m.chat.id), m.from_user.id
    text = m.text if m.text else m.caption if m.caption else ""
    user_rank = get_user_rank(chat_id, user_id)

    # حفظ اليوزر في الداتا
    if m.from_user.username:
        cursor.execute("INSERT OR REPLACE INTO user_cache VALUES (?, ?)", (user_id, m.from_user.username.lower()))
        conn.commit()

    # --- [ تحديث الإحصائيات ] ---
    cursor.execute("INSERT OR IGNORE INTO stats (chat_id, user_id, msgs) VALUES (?, ?, 0)", (chat_id, user_id))
    cursor.execute("UPDATE stats SET msgs = msgs + 1 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()

    # --- [ فحص الأقفال وقفل الدردشة ] ---
    if user_rank == "عضو":
        if is_locked(chat_id, "chat") or is_locked(chat_id, m.content_type) or (is_locked(chat_id, "links") and ("t.me" in text or "http" in text)):
            try: bot.delete_message(chat_id, m.message_id)
            except: pass
            return

    # --- [ فحص الكتم ] ---
    cursor.execute("SELECT 1 FROM muted WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    if cursor.fetchone() and user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير", "ادمن"]:
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass
        return

    # --- [ رتبتي ورتبته ] ---
    if text == "رتبتي":
        return bot.reply_to(m, f"<b>⌯ رتبتك هي: {user_rank}</b>", parse_mode="HTML")
    
    if text.startswith("رتبته"):
        t_id = extract_user(m)
        if t_id:
            t_rank = get_user_rank(chat_id, t_id)
            return bot.reply_to(m, f"<b>⌯ رتبته هي: {t_rank}</b>", parse_mode="HTML")

    # --- [ أنظمة الإدخال ] ---
    if user_id in change_state:
        # (نفس منطق كودك تماماً)
        if text == "الغاء": del change_state[user_id]; return bot.reply_to(m, "⌯ تم الإلغاء.")
        if change_state[user_id]['step'] == 1:
            change_state[user_id].update({'old': text, 'step': 2})
            return bot.reply_to(m, f"<b>⌯ تم اختيار: ({text})\n⌯ أرسل البديلة:</b>", parse_mode="HTML")
        else:
            cursor.execute("INSERT OR REPLACE INTO custom_cmds VALUES (?, ?, ?)", (chat_id, change_state[user_id]['old'], text))
            conn.commit(); del change_state[user_id]
            return bot.reply_to(m, "<b>⌯ تم التغيير بنجاح.</b>", parse_mode="HTML")

    if user_id in add_resp_state:
        # (نفس منطق كودك لزيادة الميديا)
        if text == "الغاء": del add_resp_state[user_id]; return bot.reply_to(m, "<b>⌯ تم الإلغاء.</b>", parse_mode="HTML")
        if add_resp_state[user_id]['step'] == 1:
            add_resp_state[user_id].update({'trigger': text, 'step': 2})
            return bot.reply_to(m, f"<b>⌯ أرسل الرد لـ ({text}):</b>", parse_mode="HTML")
        else:
            trigger = add_resp_state[user_id]['trigger']
            c_type = m.content_type
            f_id = m.text if c_type == 'text' else None
            if not f_id:
                for a in ['photo','sticker','animation','video','voice','video_note','document','audio']:
                    val = getattr(m, a)
                    if val: f_id = val[-1].file_id if a=='photo' else val.file_id; break
            cursor.execute("INSERT OR REPLACE INTO responses VALUES (?, ?, ?, ?, ?)", (chat_id, trigger, f_id, c_type, m.caption))
            conn.commit(); del add_resp_state[user_id]
            return bot.reply_to(m, "<b>⌯ تم حفظ الرد.</b>", parse_mode="HTML")

    # --- [ أوامر الإدارة ] ---
    ban_c = get_cmd(chat_id, "حظر")
    mute_c = get_cmd(chat_id, "كتم")
    rest_c = get_cmd(chat_id, "تقييد")

    if any(text.startswith(c) for c in [ban_c, mute_c, rest_c, "طرد", "رفع القيود", "الغاء الحظر", "الغاء الكتم"]):
        if user_rank == "عضو": return
        target_id = extract_user(m)
        if not target_id: return
        try:
            if any(x in text for x in ["رفع القيود", "الغاء الحظر", "الغاء الكتم"]):
                bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
                bot.restrict_chat_member(chat_id, target_id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True)
                cursor.execute("DELETE FROM muted WHERE chat_id = ? AND user_id = ?", (chat_id, target_id))
                conn.commit(); bot.reply_to(m, "⌯ تم رفع القيود.")
            elif text.startswith(ban_c):
                bot.ban_chat_member(chat_id, target_id); bot.reply_to(m, "⌯ تم الحظر.")
            elif text.startswith(mute_c):
                cursor.execute("INSERT OR IGNORE INTO muted VALUES (?, ?)", (chat_id, target_id))
                conn.commit(); bot.reply_to(m, "⌯ تم الكتم.")
            elif text.startswith(rest_c) or "تقييد" in text:
                # تطوير منطق الوقت
                match = re.search(r'(\d+)\s*(دقيق|ساع|يوم)', text)
                until = None; d_txt = "للأبد"
                if match:
                    amt = int(match.group(1))
                    unit = match.group(2)
                    now = int(time.time())
                    if "دقيق" in unit: until = now + (amt*60); d_txt = f"{amt} دقيقة"
                    elif "ساع" in unit: until = now + (amt*3600); d_txt = f"{amt} ساعة"
                    elif "يوم" in unit: until = now + (amt*86400); d_txt = f"{amt} يوم"
                bot.restrict_chat_member(chat_id, target_id, until_date=until, can_send_messages=False)
                bot.reply_to(m, f"⌯ تم التقييد لـ {d_txt}.")
        except: bot.reply_to(m, "⌯ فشل التنفيذ.")
        return

    # --- [ أوامر الرفع والتنزيل ] ---
    if text.startswith(("رفع ", "تنزيل ")):
        if user_rank not in ["مالك اساسي", "مالك", "مطور"]: return
        target_id = extract_user(m)
        if not target_id: return
        valid_ranks = ["مدير", "ادمن", "مميز", "مالك", "مالك اساسي"]
        rank_name = next((r for r in valid_ranks if r in text), None)
        if rank_name:
            if text.startswith("رفع"): cursor.execute("INSERT INTO ranks VALUES (?, ?, ?)", (chat_id, target_id, rank_name))
            else: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target_id, rank_name))
            conn.commit(); bot.reply_to(m, f"⌯ تم {text.split()[0]} {rank_name}")
            return

    # --- [ المعلومات والقوائم ] ---
    if text in ["ايدي", "id", "الايدي"]:
        target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
        cursor.execute("SELECT msgs FROM stats WHERE chat_id = ? AND user_id = ?", (chat_id, target.id))
        msgs = cursor.fetchone()[0] if cursor.fetchone() else 0
        caption = f"👤 الاسم: {target.first_name}\n🆔 الايدي: {target.id}\n🎖 الرتبة: {get_user_rank(chat_id, target.id)}\n💬 رسائلك: {msgs}"
        bot.reply_to(m, caption)
        return

    if text == "تغيير امر" and user_rank != "عضو":
        change_state[user_id] = {'step': 1}; return bot.reply_to(m, "⌯ أرسل الأمر القديم:")
    
    lists = {"المدراء": "مدير", "الادمنيه": "ادمن", "المالكيين": "مالك", "المميزين": "مميز"}
    if text in lists: show_full_list(m, lists[text])

    if text == "المطورين": bot.reply_to(m, f"⌯ المطور: @{DEV_USERNAME}")

    # --- [ الردود ] ---
    if text == "اضف رد" and user_rank != "عضو":
        add_resp_state[user_id] = {'step': 1}; return bot.reply_to(m, "⌯ أرسل الكلمة:")
    
    if text.startswith("فتح ") or text.startswith("قفل "):
        # (نفس منطق كودك تماماً للأقفال)
        parts = text.split(" ", 1)
        if len(parts) > 1 and parts[1] in locks_map:
            db_item = locks_map[parts[1]]
            if text.startswith("قفل"): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, db_item))
            else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, db_item))
            conn.commit(); bot.reply_to(m, f"⌯ تم {text[:3]} {parts[1]}")

    # تشغيل الردود
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, text))
    res = cursor.fetchone()
    if res:
        try:
            if res[1] == 'text': bot.reply_to(m, res[0])
            else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)
        except: pass

bot.infinity_polling()
