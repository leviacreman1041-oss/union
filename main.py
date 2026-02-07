import telebot
import sqlite3
import os
from gtts import gTTS

# --- [ الإعدادات ] ---
TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"
DEV_USERNAME = "levil_8"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- [ قاعدة البيانات ] ---
conn = sqlite3.connect("bot_system.db", check_same_thread=False)
cursor = conn.cursor()

# إنشاء الجداول لو مش موجودة
cursor.execute("""CREATE TABLE IF NOT EXISTS ranks (
    chat_id TEXT, user_id INTEGER, rank TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS muted (
    chat_id TEXT, user_id INTEGER
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS stats (
    chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS custom_cmds (
    chat_id TEXT, old_cmd TEXT, new_cmd TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS responses (
    chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS locks (
    chat_id TEXT, item TEXT
)""")
conn.commit()

# --- [ المتغيرات ] ---
change_state = {}
add_resp_state = {}

# --- [ دوال مساعدة ] ---
def get_rank(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.user.username == DEV_USERNAME: return "مطور"
        if member.status == 'creator': return "مالك اساسي"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def extract_user(m):
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    parts = m.text.split()
    if len(parts) > 1:
        arg = parts[1]
        if arg.isdigit(): return int(arg)
        if arg.startswith("@"):
            try:
                return bot.get_chat(arg).id
            except: return None
    return None

def get_cmd(chat_id, default):
    cursor.execute("SELECT new_cmd FROM custom_cmds WHERE chat_id = ? AND old_cmd = ?", (str(chat_id), default))
    res = cursor.fetchone()
    return res[0] if res else default

def is_locked(chat_id, item):
    cursor.execute("SELECT 1 FROM locks WHERE chat_id = ? AND item = ?", (str(chat_id), item))
    return cursor.fetchone() is not None

def handle_id_command(m):
    target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    rank = get_rank(m.chat.id, target.id)
    cursor.execute("SELECT msgs FROM stats WHERE chat_id = ? AND user_id = ?", (str(m.chat.id), target.id))
    res = cursor.fetchone()
    msgs = res[0] if res else 0
    caption = f"👤 الاسم: {target.first_name}\n🆔 الايدي: {target.id}\n🎖 الرتبة: {rank}\n💬 رسائلك: {msgs}"
    try:
        photos = bot.get_user_profile_photos(target.id, limit=1)
        bot.send_photo(m.chat.id, photos.photos[0][-1].file_id, caption=caption)
    except:
        bot.reply_to(m, caption)

# --- [ المعالجة الرئيسية للرسائل ] ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'audio', 'document', 'video_note'])
def main_handler(m):
    if not m.chat.type in ['group', 'supergroup']: return
    chat_id, user_id = str(m.chat.id), m.from_user.id
    text = m.text if m.text else m.caption if m.caption else ""
    rank = get_rank(chat_id, user_id)

    # تحديث الإحصائيات
    cursor.execute("INSERT OR IGNORE INTO stats (chat_id, user_id, msgs) VALUES (?, ?, 0)", (chat_id, user_id))
    cursor.execute("UPDATE stats SET msgs = msgs + 1 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()

    # فحص الكتم
    cursor.execute("SELECT 1 FROM muted WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    if cursor.fetchone():
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass
        return

    # --- [ أوامر رفع وتنزيل الرتب ] ---
    if text.startswith(("رفع ", "تنزيل ")):
        if rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]: return
        target_id = extract_user(m)
        if not target_id: return bot.reply_to(m, "⌯ استخدم الرد أو المعرف أو الايدي.")
        rank_name = text.split(None, 1)[1]
        valid_ranks = ["مشرف", "مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]
        if any(r in rank_name for r in valid_ranks):
            target_rank = next(r for r in valid_ranks if r in rank_name)
            if text.startswith("رفع"):
                cursor.execute("INSERT INTO ranks VALUES (?, ?, ?)", (chat_id, target_id, target_rank))
                bot.reply_to(m, f"⌯ تم رفعه {target_rank}")
            else:
                cursor.execute("DELETE FROM ranks WHERE chat_id = ? AND user_id = ? AND rank = ?", (chat_id, target_id, target_rank))
                bot.reply_to(m, f"⌯ تم تنزيله من {target_rank}")
            conn.commit()
        return

    # --- [ أوامر الحظر والكتم والتقييد ] ---
    ban_c = get_cmd(chat_id, "حظر")
    mute_c = get_cmd(chat_id, "كتم")
    rest_c = get_cmd(chat_id, "تقييد")

    if m.reply_to_message:
        t_id = m.reply_to_message.from_user.id
        try:
            if text.startswith(ban_c) and rank not in ["عضو"]:
                bot.ban_chat_member(chat_id, t_id)
                bot.reply_to(m, f"⌯ تم تنفيذ الحظر.")
                return
            elif text.startswith(mute_c) and rank not in ["عضو"]:
                cursor.execute("INSERT OR IGNORE INTO muted VALUES (?, ?)", (chat_id, t_id))
                conn.commit()
                bot.reply_to(m, f"⌯ تم تنفيذ الكتم.")
                return
            elif text.startswith(rest_c) and rank not in ["عضو"]:
                bot.restrict_chat_member(chat_id, t_id, can_send_messages=False)
                bot.reply_to(m, f"⌯ تم تقييده.")
                return
        except:
            bot.reply_to(m, "⌯ فشل التنفيذ: تأكد أن البوت مشرف وأن العضو ليس أدمن.")

    # --- [ أوامر المعلومات ] ---
    if text in ["ايدي", "id"]:
        handle_id_command(m)
    elif text == "رتبتي":
        bot.reply_to(m, f"⌯ رتبتك: {rank}")

    # --- [ أوامر الردود التفاعلية ] ---
    if user_id in add_resp_state:
        if text == "الغاء":
            del add_resp_state[user_id]
            return bot.reply_to(m, "<b>⌯ تم إلغاء إضافة الرد.</b>")
        state = add_resp_state[user_id]
        if state['step'] == 1:
            add_resp_state[user_id].update({'trigger': text, 'step': 2})
            return bot.reply_to(m, f"<b>⌯ الكلمة المفتاحية: ({text})\n⌯ الآن أرسل الرد:</b>")
        elif state['step'] == 2:
            trigger = state['trigger']
            f_id = text if m.content_type == 'text' else getattr(m, m.content_type)[-1].file_id
            cursor.execute("DELETE FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, trigger))
            cursor.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (chat_id, trigger, f_id, m.content_type, m.caption if m.caption else None))
            conn.commit()
            del add_resp_state[user_id]
            return bot.reply_to(m, f"<b>⌯ تم حفظ الرد على ({trigger}) بنجاح.</b>")

    if text == "اضف رد" and rank not in ["عضو"]:
        add_resp_state[user_id] = {'step': 1}
        return bot.reply_to(m, "<b>⌯ أرسل الكلمة التي تريد الرد عليها:</b>")
    elif text.startswith("مسح رد ") and rank not in ["عضو"]:
        trigger_to_del = text.replace("مسح رد ", "").strip()
        cursor.execute("DELETE FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, trigger_to_del))
        conn.commit()
        return bot.reply_to(m, f"<b>⌯ تم مسح الرد على ({trigger_to_del}).</b>")
    elif text == "مسح الردود" and rank not in ["عضو"]:
        cursor.execute("DELETE FROM responses WHERE chat_id = ?", (chat_id,))
        conn.commit()
        return bot.reply_to(m, "<b>⌯ تم مسح جميع الردود.</b>")
    elif text == "الردود":
        cursor.execute("SELECT trigger FROM responses WHERE chat_id = ?", (chat_id,))
        rows = cursor.fetchall()
        if not rows: return bot.reply_to(m, "<b>⌯ لا توجد ردود مضافة.</b>")
        msg = "<b>⌯ قائمة الردود:</b>\n" + "\n".join([f"• {r[0]}" for r in rows])
        bot.reply_to(m, msg)

    # تشغيل الردود
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id = ? AND trigger = ?", (chat_id, text))
    res = cursor.fetchone()
    if res:
        r_val, r_type, r_cap = res
        try:
            if r_type == 'text': bot.reply_to(m, r_val)
            elif r_type == 'photo': bot.send_photo(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'video': bot.send_video(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'animation': bot.send_animation(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'document': bot.send_document(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'voice': bot.send_voice(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'sticker': bot.send_sticker(chat_id, r_val, reply_to_message_id=m.message_id)
            elif r_type == 'video_note': bot.send_video_note(chat_id, r_val, reply_to_message_id=m.message_id)
        except: pass

    # --- [ الأقفال ] ---
    locks_config = {"الصور": "photo", "الفيديو": "video", "الملصقات": "sticker", "المتحركات": "animation", "الفويسات": "voice", "الملفات": "document", "الروابط": "links", "الدردشه": "chat"}
    if text.startswith(("قفل ", "فتح ")) and rank not in ["عضو"]:
        is_lock = text.startswith("قفل ")
        item_raw = text.split(" ", 1)[1]
        if item_raw in locks_config:
            item_db = locks_config[item_raw]
            if is_lock: cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, item_db))
            else: cursor.execute("DELETE FROM locks WHERE chat_id = ? AND item = ?", (chat_id, item_db))
            conn.commit()
            bot.reply_to(m, f"<b>⌯ تم {'قفل' if is_lock else 'فتح'} {item_raw} بنجاح.</b>")

bot.infinity_polling()
