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

# قيم الرتب للمقارنة
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
        cursor.execute("CREATE TABLE IF NOT EXISTS muted (chat_id TEXT, user_id INTEGER, until INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS stats (chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0)")
        conn.commit()
        return conn, cursor

conn, cursor = setup_db()
user_states = {}
spam_tracker = {}

# --- [ الدوال الذكية ] ---
def get_rank(chat_id, user_id):
    try:
        u = bot.get_chat_member(chat_id, user_id)
        if u.user.username == DEV_USERNAME: return "مطور"
        if u.status == 'creator': return "مالك اساسي"
    except: pass
    cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
    res = cursor.fetchone()
    return res[0] if res else "عضو"

def translate_cmd(chat_id, text):
    if not text: return ""
    word = text.split()[0]
    cursor.execute("SELECT old_cmd FROM custom_cmds WHERE chat_id=? AND new_cmd=?", (str(chat_id), word))
    res = cursor.fetchone()
    return text.replace(word, res[0], 1) if res else text

def extract_user(m):
    # 1. بالرد
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    
    # 2. البحث عن يوزر في الرسالة (Entities)
    if m.entities:
        for entity in m.entities:
            if entity.type == 'mention':
                username = m.text[entity.offset:entity.offset + entity.length]
                try:
                    user_info = bot.get_chat(username)
                    return user_info.id
                except: return None
            if entity.type == 'text_mention':
                return entity.user.id
    
    # 3. البحث عن آيدي رقمي في النص
    p = m.text.split()
    for word in p:
        if word.isdigit() and len(word) > 7:
            return int(word)
            
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
    rank = get_rank(chat_id, user_id)
    raw_text = m.text or m.caption or ""
    text = translate_cmd(chat_id, raw_text)

    # --- [ نظام مضاد التكرار ] ---
    if rank == "عضو":
        now = time.time()
        if chat_id not in spam_tracker: spam_tracker[chat_id] = {}
        if user_id not in spam_tracker[chat_id]: spam_tracker[chat_id][user_id] = []
        spam_tracker[chat_id][user_id] = [t for t in spam_tracker[chat_id][user_id] if now - t < 5]
        spam_tracker[chat_id][user_id].append(now)
        if len(spam_tracker[chat_id][user_id]) >= 6:
            try:
                bot.restrict_chat_member(chat_id, user_id, until_date=int(now + 21600), can_send_messages=False)
                bot.reply_to(m, "<b>⌯ تم تقييدك تلقائياً لمدة 6 ساعات بسبب التكرار (Flood).</b>")
                spam_tracker[chat_id][user_id] = [] 
                return
            except: pass

    # تحديث الإحصائيات
    cursor.execute("INSERT OR IGNORE INTO stats (chat_id, user_id, msgs) VALUES (?,?,0)", (chat_id, user_id))
    cursor.execute("UPDATE stats SET msgs = msgs + 1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()

    # نظام الحالات
    if user_id in user_states:
        if raw_text == "الغاء":
            del user_states[user_id]
            return bot.reply_to(m, "<b>⌯ تم إلغاء العملية بنجاح.</b>")
        state = user_states[user_id]
        if state['type'] == 'change_cmd':
            if state['step'] == 1:
                user_states[user_id].update({'old': raw_text, 'step': 2})
                return bot.reply_to(m, f"<b>⌯ تم اختيار: ({raw_text})\n⌯ ارسل الكلمة البديلة الآن:</b>")
            else:
                cursor.execute("INSERT OR REPLACE INTO custom_cmds VALUES (?,?,?)", (chat_id, state['old'], raw_text))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم حفظ التغيير بنجاح.</b>")
        elif state['type'] == 'add_resp':
            if state['step'] == 1:
                user_states[user_id].update({'trig': raw_text, 'step': 2})
                return bot.reply_to(m, "<b>⌯ ارسل الرد الآن (نص، صورة، ملصق.. إلخ):</b>")
            else:
                c_type = m.content_type
                f_id = raw_text if c_type == 'text' else (m.photo[-1].file_id if c_type == 'photo' else getattr(m, c_type).file_id)
                cursor.execute("INSERT INTO responses VALUES (?,?,?,?,?)", (chat_id, state['trig'], f_id, c_type, m.caption))
                conn.commit(); del user_states[user_id]
                return bot.reply_to(m, "<b>⌯ تم حفظ الرد بنجاح.</b>")

    # --- [ أوامر الرفع والتنزيل ] ---
    if text.startswith(("رفع ", "تنزيل ")):
        if rank == "عضو" or rank == "مميز": return
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ عذراً، يجب استخدام الرد أو المعرف @ بشكل صحيح.</b>")
        
        target_rank = get_rank(chat_id, target)
        if RANK_VALUES.get(rank, 0) <= RANK_VALUES.get(target_rank, 0) and user_id != target:
             return bot.reply_to(m, "<b>⌯ لا يمكنك التحكم برتبة شخص مساوٍ لك أو أعلى منك.</b>")

        if text == "تنزيل الكل":
            cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=?", (chat_id, target))
            conn.commit(); return bot.reply_to(m, "<b>⌯ تم تنزيل الشخص من جميع الرتب.</b>")
        
        r_list = ["مشرف", "مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]
        for r in r_list:
            if r in text:
                if rank == "ادمن" and r != "مميز":
                    return bot.reply_to(m, "<b>⌯ كـ (ادمن) يمكنك رفع رتبة (مميز) فقط.</b>")
                if text.startswith("رفع"): cursor.execute("INSERT INTO ranks VALUES (?,?,?)", (chat_id, target, r))
                else: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r))
                conn.commit(); return bot.reply_to(m, f"<b>⌯ تم {text.split()[0]} {r}</b>")

    if text == "تنزيل الكل" and not m.reply_to_message and "@" not in text:
        if rank in ["مطور", "مالك اساسي"]:
            cursor.execute("DELETE FROM ranks WHERE chat_id=?", (chat_id,))
            conn.commit(); return bot.reply_to(m, "<b>⌯ تم تصفير جميع رتب المجموعة.</b>")

    # --- [ الإدارة والتقييد ] ---
    admin_cmds = ["حظر", "كتم", "تقيد", "تقييد"]
    first_word = text.split()[0] if text else ""
    
    if first_word in admin_cmds and rank not in ["عضو", "مميز"]:
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ ايدي/معرف/بالرد.</b>")
        
        target_rank = get_rank(chat_id, target)
        if RANK_VALUES.get(rank, 0) <= RANK_VALUES.get(target_rank, 0) and user_id != target:
            return bot.reply_to(m, "<b>⌯ لا يمكنك تقييد شخص رتبته مساوية لك أو أعلى منك.</b>")

        sec = parse_time(text)
        until = int(time.time() + sec) if sec > 0 else 0
        try:
            if "حظر" in first_word: bot.ban_chat_member(chat_id, target, until_date=until)
            else: bot.restrict_chat_member(chat_id, target, until_date=until, can_send_messages=False)
            time_str = f" لمدة {sec//60} دقيقة" if sec > 0 else " بشكل دائم"
            bot.reply_to(m, f"<b>⌯ تم {first_word} المستخدم {time_str}.</b>")
        except: bot.reply_to(m, "<b>⌯ فشل الإجراء:</b> تأكد من صلاحيات البوت.")

    # --- [ ميزة رفع القيود ] ---
    if text.startswith("رفع القيود") and rank not in ["عضو", "مميز"]:
        target = extract_user(m)
        if not target: return bot.reply_to(m, "<b>⌯ ايدي/معرف/بالرد.</b>")
        try:
            bot.restrict_chat_member(chat_id, target, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True, can_send_polls=True, can_invite_users=True, can_pin_messages=True, can_change_info=True)
            bot.unban_chat_member(chat_id, target, only_if_banned=True)
            bot.reply_to(m, "<b>⌯ تم رفع كافة القيود بنجاح.</b>")
        except: bot.reply_to(m, "⌯ فشل التنفيذ.")

    # --- [ القفل والفتح ] ---
    l_map = {"الصور":"photo", "الفيديو":"video", "الروابط":"links", "الدردشه":"chat", "الملصقات":"sticker", "المتحركات":"animation"}
    if text in ["قفل الكل", "فتح الكل"] and rank in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        if text == "قفل الكل":
            for item in l_map.values(): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, item))
            conn.commit(); return bot.reply_to(m, "<b>⌯ تم قفل الكل.</b>")
        else:
            cursor.execute("DELETE FROM locks WHERE chat_id=?", (chat_id,))
            conn.commit(); return bot.reply_to(m, "<b>⌯ تم فتح الكل.</b>")

    if text.startswith(("قفل ", "فتح ")) and rank not in ["عضو"]:
        if rank == "مميز" and "الدردشه" not in text: return 
        parts = text.split()
        if len(parts) > 1:
            item_name = parts[1]
            if item_name in l_map:
                item_db = l_map[item_name]
                if text.startswith("قفل"): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?,?)", (chat_id, item_db))
                else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, item_db))
                conn.commit(); bot.reply_to(m, f"<b>⌯ تم {text.split()[0]} {item_name}</b>")

    # --- [ الردود ] ---
    if text == "الردود" and rank in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        cursor.execute("SELECT trigger FROM responses WHERE chat_id=?", (chat_id,))
        res = cursor.fetchall()
        if not res: return bot.reply_to(m, "<b>⌯ لا توجد ردود.</b>")
        list_msg = "<b>⌯ قائمة الردود:</b>\n" + "\n".join([f"• {r[0]}" for r in res])
        return bot.reply_to(m, list_msg)

    if text == "مسح الردود" and rank in ["مطور", "مالك اساسي", "مالك"]:
        cursor.execute("DELETE FROM responses WHERE chat_id=?", (chat_id,))
        conn.commit(); return bot.reply_to(m, "<b>⌯ تم مسح جميع الردود.</b>")

    if text.startswith("مسح رد ") and rank in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        trigger_to_del = text.replace("مسح رد ", "").strip()
        cursor.execute("DELETE FROM responses WHERE chat_id=? AND trigger=?", (chat_id, trigger_to_del))
        conn.commit(); return bot.reply_to(m, f"<b>⌯ تم مسح الرد ({trigger_to_del}).</b>")

    # --- [ نظام الكشف ] ---
    if text.startswith("كشف") and len(text.split()) <= 2 and text != "كشف المجموعه":
        target_id = extract_user(m)
        if not target_id: return bot.reply_to(m, "<b>⌯ ايدي/معرف/بالرد.</b>")
        try:
            u_info = bot.get_chat(target_id)
            name = (u_info.first_name or "") + (f" {u_info.last_name}" if u_info.last_name else "")
            user_n = f"@{u_info.username}" if u_info.username else "لا يوجد"
            bio = u_info.bio if hasattr(u_info, 'bio') and u_info.bio else "لا يوجد"
        except: name, user_n, bio = "مستخدم غير معروف", "غير معروف", "غير معروف"
        
        t_rank = get_rank(chat_id, target_id)
        cursor.execute("SELECT msgs FROM stats WHERE chat_id=? AND user_id=?", (chat_id, target_id))
        st = cursor.fetchone()
        msgs_count = st[0] if st else 0
        
        caption = (f"<b>👤 معلومات المستخدم:</b>\n\n"
                   f"<b>• الاسم:</b> {name}\n"
                   f"<b>• الايدي:</b> <code>{target_id}</code>\n"
                   f"<b>• اليوزر:</b> {user_n}\n"
                   f"<b>• الرتبة:</b> {t_rank}\n"
                   f"<b>• الرسائل:</b> {msgs_count}\n"
                   f"<b>• البايو:</b> <code>{bio}</code>")
        return bot.reply_to(m, caption)

    if text == "كشف المجموعه" and rank in ["مطور", "مالك اساسي", "مالك"]:
        cursor.execute("SELECT user_id, rank FROM ranks WHERE chat_id=?", (chat_id,))
        db_ranks = cursor.fetchall()
        if not db_ranks: return bot.reply_to(m, "<b>⌯ لا توجد رتب مضافة.</b>")
        list_msg = "<b>📊 قائمة رتب المجموعه:</b>\n\n"
        for uid, rnk in db_ranks:
            list_msg += f"<b>• {rnk} :</b> <code>{uid}</code>\n"
        return bot.reply_to(m, list_msg)

    # --- [ معلومات ] ---
    if text == "تغيير امر" and rank in ["مطور", "مالك اساسي"]:
        user_states[user_id] = {'type': 'change_cmd', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الكلمة الاصلية:\n(للالغاء ارسل 'الغاء')</b>")
    if text == "اضف رد" and rank not in ["عضو"]:
        user_states[user_id] = {'type': 'add_resp', 'step': 1}
        return bot.reply_to(m, "<b>⌯ ارسل الكلمة التي تريد الرد عليها:</b>")
    if text == "ايدي":
        cursor.execute("SELECT msgs FROM stats WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        res_stats = cursor.fetchone()
        bot.reply_to(m, f"<b>👤 الاسم: {m.from_user.first_name}\n🆔 الايدي: <code>{user_id}</code>\n🎖 الرتبة: {rank}\n💬 رسائلك: {res_stats[0] if res_stats else 0}</b>")
    if text == "رتبتي": return bot.reply_to(m, f"<b>⌯ رتبتك هي: {rank}</b>")

    # --- [ نظام الحماية ] ---
    if rank == "عضو":
        cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
        current_locks = [r[0] for r in cursor.fetchall()]
        if m.content_type in ['photo', 'animation', 'sticker'] and m.content_type in current_locks:
            if "UI" not in (m.from_user.first_name or ""):
                try: bot.delete_message(chat_id, m.message_id); return
                except: pass
        if m.content_type in current_locks:
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass
        if "links" in current_locks and re.search(r't\.me/|http', raw_text):
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass
    
    if rank in ["عضو", "مميز"]:
        cursor.execute("SELECT item FROM locks WHERE chat_id=? AND item='chat'", (chat_id,))
        if cursor.fetchone():
            try: bot.delete_message(chat_id, m.message_id); return
            except: pass

    # --- [ تشغيل الردود ] ---
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_id, raw_text))
    res = cursor.fetchone()
    if res:
        try:
            if res[1] == 'text': bot.reply_to(m, res[0])
            else: getattr(bot, f"send_{res[1]}")(chat_id, res[0], caption=res[2], reply_to_message_id=m.message_id)
        except: pass

if __name__ == "__main__":
    bot.remove_webhook()
    print("🚀 الوحش V16 الأسطوري بدأ العمل يا ليفاي!")
    bot.infinity_polling(skip_pending=True)
