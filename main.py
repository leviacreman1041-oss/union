import telebot
import sqlite3
import json
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import time

# --- [ الإعدادات ] ---
TOKEN = "8486555369:AAGa6z2L1KKA-ajRdacAK21FAtzH9ZCbm4U"
bot = telebot.TeleBot(TOKEN)
DEV_USERNAME = "levil_8"

# --- [ قاعدة البيانات ] ---
conn = sqlite3.connect("bot_system.db", check_same_thread=False)
cursor = conn.cursor()

# إنشاء الجداول
cursor.execute("""
CREATE TABLE IF NOT EXISTS ranks (
    chat_id TEXT,
    user_id INTEGER,
    rank TEXT,
    PRIMARY KEY (chat_id, user_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS punishments (
    chat_id TEXT,
    user_id INTEGER,
    type TEXT,
    until TIMESTAMP,
    PRIMARY KEY (chat_id, user_id, type)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS locks (
    chat_id TEXT,
    item TEXT,
    PRIMARY KEY (chat_id, item)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    trigger TEXT,
    reply_type TEXT,
    reply_data TEXT,
    caption TEXT,
    file_id TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS custom_commands (
    chat_id TEXT,
    old_cmd TEXT,
    new_cmd TEXT,
    PRIMARY KEY (chat_id, old_cmd)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS custom_ranks (
    chat_id TEXT,
    rank_key TEXT,
    rank_name TEXT,
    PRIMARY KEY (chat_id, rank_key)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    chat_id TEXT,
    user_id INTEGER,
    msgs INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)
""")

conn.commit()

# --- [ دوال المساعدة ] ---
def time_to_seconds(time_str):
    """تحويل النص الزمني إلى ثواني"""
    units = {
        'ثانية': 1,
        'ثواني': 1,
        'دقيقة': 60,
        'دقائق': 60,
        'ساعة': 3600,
        'ساعات': 3600,
        'يوم': 86400,
        'ايام': 86400,
        'اسبوع': 604800,
        'اسابيع': 604800,
        'شهر': 2592000,
        'اشهر': 2592000
    }
    
    parts = time_str.split()
    total_seconds = 0
    
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            try:
                num = int(parts[i])
                unit = parts[i+1]
                if unit in units:
                    total_seconds += num * units[unit]
            except:
                pass
    
    return total_seconds if total_seconds > 0 else 3600  # افتراضي ساعة

def is_punished(chat_id, user_id, punishment_type):
    """فحص إذا كان المستخدم معاقب"""
    cursor.execute(
        "SELECT until FROM punishments WHERE chat_id = ? AND user_id = ? AND type = ?",
        (str(chat_id), user_id, punishment_type)
    )
    result = cursor.fetchone()
    
    if result:
        until_time = datetime.fromisoformat(result[0])
        if datetime.now() < until_time:
            return True
        else:
            # انتهت المدة، حذف العقوبة
            cursor.execute(
                "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = ?",
                (str(chat_id), user_id, punishment_type)
            )
            conn.commit()
    return False

def get_user_rank(chat_id, user_id):
    """الحصول على رتبة المستخدم"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.user.username == DEV_USERNAME:
            return "مطور"
        if member.status == 'creator':
            return "مالك اساسي"
    except:
        pass
    
    cursor.execute(
        "SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?",
        (str(chat_id), user_id)
    )
    result = cursor.fetchone()
    
    if result:
        return result[0]
    return "عضو"

def get_custom_rank_name(chat_id, rank_key):
    """الحصول على اسم الرتبة المخصص"""
    cursor.execute(
        "SELECT rank_name FROM custom_ranks WHERE chat_id = ? AND rank_key = ?",
        (str(chat_id), rank_key)
    )
    result = cursor.fetchone()
    return result[0] if result else rank_key

def get_custom_command(chat_id, default_cmd):
    """الحصول على الأمر المخصص"""
    cursor.execute(
        "SELECT new_cmd FROM custom_commands WHERE chat_id = ? AND old_cmd = ?",
        (str(chat_id), default_cmd)
    )
    result = cursor.fetchone()
    return result[0] if result else default_cmd

def extract_user_id(m):
    """استخراج ID المستخدم من الرسالة"""
    if m.reply_to_message:
        return m.reply_to_message.from_user.id
    
    parts = m.text.split()
    if len(parts) > 1:
        arg = parts[1]
        if arg.isdigit():
            return int(arg)
        if arg.startswith("@"):
            try:
                user = bot.get_chat(arg)
                return user.id
            except:
                return None
    return None

def can_punish(chat_id, punisher_id, target_id):
    """فحص إذا كان يمكن للمعاقب معاقبة الهدف"""
    punisher_rank = get_user_rank(chat_id, punisher_id)
    target_rank = get_user_rank(chat_id, target_id)
    
    rank_hierarchy = {
        "مطور": 10,
        "مالك اساسي": 9,
        "مالك": 8,
        "مدير": 7,
        "ادمن": 6,
        "مميز": 5,
        "عضو": 1
    }
    
    punisher_level = rank_hierarchy.get(punisher_rank, 1)
    target_level = rank_hierarchy.get(target_rank, 1)
    
    return punisher_level > target_level

def get_rank_level(rank):
    """الحصول على مستوى الرتبة"""
    rank_hierarchy = {
        "مطور": 10,
        "مالك اساسي": 9,
        "مالك": 8,
        "مدير": 7,
        "ادمن": 6,
        "مميز": 5,
        "عضو": 1
    }
    return rank_hierarchy.get(rank, 1)

# --- [ معالجة الرسائل ] ---
add_response_state = {}
change_command_state = {}
change_rank_state = {}

@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def handle_message(m):
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = m.text if m.text else ""
    
    # تحديث الإحصائيات
    cursor.execute(
        "INSERT OR IGNORE INTO stats (chat_id, user_id, msgs) VALUES (?, ?, 0)",
        (chat_id, user_id)
    )
    cursor.execute(
        "UPDATE stats SET msgs = msgs + 1 WHERE chat_id = ? AND user_id = ?",
        (chat_id, user_id)
    )
    conn.commit()
    
    # فحص الكتم
    if is_punished(chat_id, user_id, "mute"):
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except:
            pass
        return
    
    # الحصول على الأوامر المخصصة
    ban_cmd = get_custom_command(chat_id, "حظر")
    mute_cmd = get_custom_command(chat_id, "كتم")
    restrict_cmd = get_custom_command(chat_id, "تقييد")
    kick_cmd = get_custom_command(chat_id, "طرد")
    
    # --- [ نظام الردود الذكية ] ---
    if user_id in add_response_state:
        handle_add_response(m)
        return
    
    # --- [ نظام تغيير الأوامر ] ---
    if user_id in change_command_state:
        handle_change_command(m)
        return
    
    # --- [ نظام تغيير الرتب ] ---
    if user_id in change_rank_state:
        handle_change_rank(m)
        return
    
    # --- [ أوامر الإدارة ] ---
    user_rank = get_user_rank(chat_id, user_id)
    
    # أوامر الرفع والتنزيل
    if text.startswith(("رفع ", "تنزيل ")):
        handle_promotion(m, user_rank)
    
    # أوامر العقوبات بالمدة
    elif any(cmd in text for cmd in [ban_cmd, mute_cmd, restrict_cmd, kick_cmd, "الغاء"]):
        handle_punishments(m, user_rank)
    
    # أوامر القفل والفتح
    elif text.startswith(("قفل ", "فتح ")):
        handle_locks(m, user_rank)
    
    # أوامر الردود
    elif text in ["الردود", "اضف رد", "مسح الردود"] or text.startswith("مسح رد "):
        handle_responses(m, user_rank)
    
    # أوامر التخصيص
    elif text in ["تغيير امر", "تغيير رتبه"]:
        handle_customization(m, user_rank)
    
    # أوامر المعلومات
    elif text in ["ايدي", "id", "رتبتي", "رتبته"]:
        handle_info(m)
    
    # أوامر المسح
    elif text.startswith("مسح"):
        handle_cleanup(m, user_rank)
    
    # أوامر القوائم
    elif text in ["المطورين", "المالكيين الاساسيين", "المالكيين", "المدراء", "الادمنيه", "المميزين", "المشرفين"]:
        handle_lists(m, user_rank)
    
    # فحص الأقفال قبل معالجة الرسالة العادية
    if not check_locks(m, user_rank):
        return
    
    # فحص الردود الذكية
    check_auto_responses(m, chat_id)

def handle_add_response(m):
    """معالجة إضافة رد جديد - مصحح"""
    user_id = m.from_user.id
    chat_id = str(m.chat.id)
    
    state = add_response_state[user_id]
    
    # إلغاء العملية
    if m.text and m.text == "الغاء":
        del add_response_state[user_id]
        bot.reply_to(m, "⌯ تم إلغاء إضافة الرد.")
        return
    
    if state['step'] == 1:  # انتظار الكلمة المفتاحية
        if not m.text:
            bot.reply_to(m, "⌯ يجب إرسال كلمة نصية ككلمة مفتاحية!")
            return
        
        add_response_state[user_id] = {
            'step': 2,
            'trigger': m.text,
            'chat_id': chat_id
        }
        bot.reply_to(m, f"⌯ الكلمة المفتاحية: {m.text}\n⌯ الآن أرسل الرد (نص، صورة، فيديو، ملصق، ملف...):")
    
    elif state['step'] == 2:  # انتظار الرد
        trigger = state['trigger']
        
        # تحديد نوع المحتوى
        content_type = m.content_type
        reply_data = None
        caption = None
        file_id = None
        
        if content_type == 'text':
            reply_data = m.text
        elif content_type == 'photo':
            reply_data = json.dumps({'photo': m.photo[-1].file_id})
            file_id = m.photo[-1].file_id
            caption = m.caption
        elif content_type == 'video':
            reply_data = json.dumps({'video': m.video.file_id})
            file_id = m.video.file_id
            caption = m.caption
        elif content_type == 'sticker':
            reply_data = json.dumps({'sticker': m.sticker.file_id})
            file_id = m.sticker.file_id
        elif content_type == 'animation':
            reply_data = json.dumps({'animation': m.animation.file_id})
            file_id = m.animation.file_id
            caption = m.caption
        elif content_type == 'voice':
            reply_data = json.dumps({'voice': m.voice.file_id})
            file_id = m.voice.file_id
            caption = m.caption
        elif content_type == 'document':
            reply_data = json.dumps({'document': m.document.file_id})
            file_id = m.document.file_id
            caption = m.caption
        elif content_type == 'audio':
            reply_data = json.dumps({'audio': m.audio.file_id})
            file_id = m.audio.file_id
            caption = m.caption
        elif content_type == 'video_note':
            reply_data = json.dumps({'video_note': m.video_note.file_id})
            file_id = m.video_note.file_id
        
        if reply_data:
            # حذف أي رد موجود لنفس الكلمة
            cursor.execute(
                "DELETE FROM responses WHERE chat_id = ? AND trigger = ?",
                (chat_id, trigger)
            )
            
            # إضافة الرد الجديد
            cursor.execute(
                "INSERT INTO responses (chat_id, trigger, reply_type, reply_data, caption, file_id) VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, trigger, content_type, reply_data, caption, file_id)
            )
            conn.commit()
            
            # إرسال تأكيد حسب نوع المحتوى
            if content_type == 'text':
                bot.reply_to(m, f"⌯ تم حفظ الرد النصي على كلمة '{trigger}' بنجاح!\nالرد: {reply_data}")
            else:
                bot.reply_to(m, f"⌯ تم حفظ الرد ({content_type}) على كلمة '{trigger}' بنجاح!")
        else:
            bot.reply_to(m, "⌯ نوع المحتوى غير مدعوم! أرسل نصًا، صورة، فيديو، ملصق، ملف، أو صوتًا.")
        
        del add_response_state[user_id]

def handle_change_command(m):
    """معالجة تغيير الأمر"""
    user_id = m.from_user.id
    text = m.text
    
    state = change_command_state[user_id]
    
    if state['step'] == 1:  # انتظار الأمر القديم
        change_command_state[user_id] = {
            'step': 2,
            'old_cmd': text,
            'chat_id': state['chat_id']
        }
        bot.reply_to(m, f"⌯ الأمر القديم: {text}\n⌯ أرسل الآن الأمر الجديد:")
    
    elif state['step'] == 2:  # انتظار الأمر الجديد
        old_cmd = state['old_cmd']
        new_cmd = text
        
        # حفظ التغيير
        cursor.execute(
            "INSERT OR REPLACE INTO custom_commands (chat_id, old_cmd, new_cmd) VALUES (?, ?, ?)",
            (state['chat_id'], old_cmd, new_cmd)
        )
        conn.commit()
        
        bot.reply_to(m, f"⌯ تم تغيير الأمر!\n⌯ استخدم '{new_cmd}' بدلاً من '{old_cmd}'")
        del change_command_state[user_id]

def handle_change_rank(m):
    """معالجة تغيير اسم الرتبة"""
    user_id = m.from_user.id
    text = m.text
    
    state = change_rank_state[user_id]
    
    if state['step'] == 1:  # انتظار مفتاح الرتبة
        rank_keys = {
            "مطور": "مطور",
            "مالك اساسي": "مالك اساسي",
            "مالك": "مالك",
            "مدير": "مدير",
            "ادمن": "ادمن",
            "مميز": "مميز",
            "عضو": "عضو"
        }
        
        if text in rank_keys:
            change_rank_state[user_id] = {
                'step': 2,
                'rank_key': text,
                'chat_id': state['chat_id']
            }
            bot.reply_to(m, f"⌯ الرتبة: {text}\n⌯ أرسل الآن الاسم الجديد:")
        else:
            bot.reply_to(m, "⌯ رتبة غير صحيحة!\n⌯ الرتب المتاحة: " + ", ".join(rank_keys.keys()))
    
    elif state['step'] == 2:  # انتظار الاسم الجديد
        rank_key = state['rank_key']
        new_name = text
        
        # حفظ التغيير
        cursor.execute(
            "INSERT OR REPLACE INTO custom_ranks (chat_id, rank_key, rank_name) VALUES (?, ?, ?)",
            (state['chat_id'], rank_key, new_name)
        )
        conn.commit()
        
        bot.reply_to(m, f"⌯ تم تغيير اسم الرتبة!\n⌯ '{rank_key}' أصبح '{new_name}'")
        del change_rank_state[user_id]

def handle_promotion(m, user_rank):
    """معالجة أوامر الرفع والتنزيل"""
    if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        return
    
    chat_id = str(m.chat.id)
    text = m.text
    target_id = extract_user_id(m)
    
    if not target_id:
        bot.reply_to(m, "⌯ من فضلك استخدم الرد أو المعرف أو الايدي.")
        return
    
    parts = text.split()
    action = parts[0]  # رفع أو تنزيل
    rank_name = " ".join(parts[1:])  # اسم الرتبة
    
    valid_ranks = ["مشرف", "مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]
    
    if any(rank in rank_name for rank in valid_ranks):
        target_rank = next(rank for rank in valid_ranks if rank in rank_name)
        
        if action == "رفع":
            # التحقق من الصلاحيات
            if not can_punish(chat_id, m.from_user.id, target_id):
                bot.reply_to(m, "⌯ لا يمكنك رفع شخص رتبته أعلى أو مساوية لرتبتك!")
                return
            
            cursor.execute(
                "INSERT OR REPLACE INTO ranks (chat_id, user_id, rank) VALUES (?, ?, ?)",
                (chat_id, target_id, target_rank)
            )
            bot.reply_to(m, f"⌯ تم رفعه {target_rank}")
        
        elif action == "تنزيل":
            cursor.execute(
                "DELETE FROM ranks WHERE chat_id = ? AND user_id = ? AND rank = ?",
                (chat_id, target_id, target_rank)
            )
            bot.reply_to(m, f"⌯ تم تنزيله من {target_rank}")
        
        conn.commit()

def handle_punishments(m, user_rank):
    """معالجة أوامر العقوبات"""
    if user_rank == "عضو":
        return
    
    chat_id = str(m.chat.id)
    text = m.text
    target_id = extract_user_id(m)
    
    if not target_id:
        return
    
    if target_id == bot.get_me().id:
        bot.reply_to(m, "⌯ لا يمكنني فعل ذلك بنفسي!")
        return
    
    # التحقق من الصلاحيات
    if not can_punish(chat_id, m.from_user.id, target_id):
        bot.reply_to(m, "⌯ لا يمكنك معاقبة شخص رتبته أعلى أو مساوية لرتبتك!")
        return
    
    # الحصول على الأوامر المخصصة
    ban_cmd = get_custom_command(chat_id, "حظر")
    mute_cmd = get_custom_command(chat_id, "كتم")
    restrict_cmd = get_custom_command(chat_id, "تقييد")
    kick_cmd = get_custom_command(chat_id, "طرد")
    
    try:
        # استخراج المدة من النص
        time_parts = text.split()
        duration = None
        
        # البحث عن أجزاء الوقت
        for i in range(1, len(time_parts)):
            if time_parts[i].isdigit() and i + 1 < len(time_parts):
                try:
                    num = int(time_parts[i])
                    unit = time_parts[i + 1]
                    duration = f"{num} {unit}"
                    break
                except:
                    pass
        
        until_time = None
        if duration:
            seconds = time_to_seconds(duration)
            until_time = datetime.now() + timedelta(seconds=seconds)
        
        if "الغاء" in text or "رفع القيود" in text:
            if "حظر" in text:
                try:
                    bot.unban_chat_member(chat_id, target_id)
                except:
                    pass
                cursor.execute(
                    "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'ban'",
                    (chat_id, target_id)
                )
                bot.reply_to(m, "⌯ تم الغاء الحظر.")
            
            elif "كتم" in text:
                cursor.execute(
                    "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'mute'",
                    (chat_id, target_id)
                )
                bot.reply_to(m, "⌯ تم الغاء الكتم.")
            
            elif "تقييد" in text:
                try:
                    bot.restrict_chat_member(
                        chat_id,
                        target_id,
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True
                    )
                except:
                    pass
                cursor.execute(
                    "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'restrict'",
                    (chat_id, target_id)
                )
                bot.reply_to(m, "⌯ تم الغاء التقييد.")
        
        elif ban_cmd in text:
            if until_time:
                try:
                    bot.ban_chat_member(chat_id, target_id, until_date=until_time)
                    cursor.execute(
                        "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                        (chat_id, target_id, 'ban', until_time.isoformat())
                    )
                    bot.reply_to(m, f"⌯ تم حظره لمدة {duration}")
                except:
                    bot.reply_to(m, "⌯ فشل في حظر العضو. تأكد أن البوت لديه صلاحيات.")
            else:
                try:
                    bot.ban_chat_member(chat_id, target_id)
                    bot.reply_to(m, "⌯ تم حظره بنجاح.")
                except:
                    bot.reply_to(m, "⌯ فشل في حظر العضو. تأكد أن البوت لديه صلاحيات.")
        
        elif mute_cmd in text:
            if until_time:
                cursor.execute(
                    "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                    (chat_id, target_id, 'mute', until_time.isoformat())
                )
                bot.reply_to(m, f"⌯ تم كتمه لمدة {duration}")
            else:
                cursor.execute(
                    "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                    (chat_id, target_id, 'mute', (datetime.now() + timedelta(days=365)).isoformat())
                )
                bot.reply_to(m, "⌯ تم كتمه بنجاح.")
        
        elif restrict_cmd in text:
            if until_time:
                try:
                    bot.restrict_chat_member(chat_id, target_id, until_date=until_time, can_send_messages=False)
                    cursor.execute(
                        "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                        (chat_id, target_id, 'restrict', until_time.isoformat())
                    )
                    bot.reply_to(m, f"⌯ تم تقييده لمدة {duration}")
                except:
                    bot.reply_to(m, "⌯ فشل في تقييد العضو. تأكد أن البوت لديه صلاحيات.")
            else:
                try:
                    bot.restrict_chat_member(chat_id, target_id, can_send_messages=False)
                    bot.reply_to(m, "⌯ تم تقييده بنجاح.")
                except:
                    bot.reply_to(m, "⌯ فشل في تقييد العضو. تأكد أن البوت لديه صلاحيات.")
        
        elif kick_cmd in text:
            try:
                bot.kick_chat_member(chat_id, target_id)
                bot.unban_chat_member(chat_id, target_id)
                bot.reply_to(m, "⌯ تم طرده بنجاح.")
            except:
                bot.reply_to(m, "⌯ فشل في طرد العضو. تأكد أن البوت لديه صلاحيات.")
        
        conn.commit()
        
    except Exception as e:
        bot.reply_to(m, f"⌯ فشل التنفيذ: {str(e)}")

def handle_locks(m, user_rank):
    """معالجة أوامر القفل والفتح"""
    if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        return
    
    chat_id = str(m.chat.id)
    text = m.text
    
    parts = text.split()
    action = parts[0]  # قفل أو فتح
    lock_type = " ".join(parts[1:])  # نوع القفل
    
    lock_items = {
        "الصور": "photo",
        "الفيديو": "video",
        "الملصقات": "sticker",
        "المتحركات": "animation",
        "الفيديو ملاحظة": "video_note",
        "الملفات": "document",
        "الصوت": "audio",
        "الروابط": "links",
        "اليوزرات": "usernames",
        "الدردشه": "chat",
        "الكلام الكثير": "flood",
        "التوجيه": "forward",
        "الانلاين": "inline",
        "الكل": "all"
    }
    
    if lock_type in lock_items:
        db_type = lock_items[lock_type]
        
        if action == "قفل":
            cursor.execute(
                "INSERT OR IGNORE INTO locks (chat_id, item) VALUES (?, ?)",
                (chat_id, db_type)
            )
            bot.reply_to(m, f"⌯ تم قفل {lock_type}")
        else:  # فتح
            cursor.execute(
                "DELETE FROM locks WHERE chat_id = ? AND item = ?",
                (chat_id, db_type)
            )
            bot.reply_to(m, f"⌯ تم فتح {lock_type}")
        
        conn.commit()
    else:
        bot.reply_to(m, f"⌯ نوع القفل غير صحيح!\n⌯ الأنواع المتاحة: {', '.join(lock_items.keys())}")

def handle_responses(m, user_rank):
    """معالجة أوامر الردود"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = m.text
    
    if text == "اضف رد":
        if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            bot.reply_to(m, "⌯ ليس لديك صلاحية لإضافة ردود!")
            return
        
        add_response_state[user_id] = {
            'step': 1,
            'chat_id': chat_id
        }
        bot.reply_to(m, "⌯ أرسل الكلمة التي تريد الرد عليها:")
    
    elif text.startswith("مسح رد "):
        if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            return
        
        trigger = text.replace("مسح رد ", "").strip()
        cursor.execute(
            "DELETE FROM responses WHERE chat_id = ? AND trigger = ?",
            (chat_id, trigger)
        )
        affected = cursor.rowcount
        conn.commit()
        
        if affected > 0:
            bot.reply_to(m, f"⌯ تم مسح الرد على كلمة '{trigger}'")
        else:
            bot.reply_to(m, f"⌯ لا يوجد رد على كلمة '{trigger}'")
    
    elif text == "مسح الردود":
        if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            return
        
        cursor.execute("DELETE FROM responses WHERE chat_id = ?", (chat_id,))
        affected = cursor.rowcount
        conn.commit()
        
        if affected > 0:
            bot.reply_to(m, f"⌯ تم مسح {affected} رد")
        else:
            bot.reply_to(m, "⌯ لا توجد ردود مضافة")
    
    elif text == "الردود":
        cursor.execute(
            "SELECT trigger, reply_type FROM responses WHERE chat_id = ?",
            (chat_id,)
        )
        responses = cursor.fetchall()
        
        if not responses:
            bot.reply_to(m, "⌯ لا توجد ردود مضافة.")
        else:
            response_list = []
            for trigger, reply_type in responses:
                response_list.append(f"• {trigger} ({reply_type})")
            
            response_text = "⌯ الردود المضافة:\n" + "\n".join(response_list)
            if len(response_text) > 4000:
                response_text = response_text[:4000] + "..."
            bot.reply_to(m, response_text)

def handle_customization(m, user_rank):
    """معالجة أوامر التخصيص"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = m.text
    
    if text == "تغيير امر":
        if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            bot.reply_to(m, "⌯ ليس لديك صلاحية لتغيير الأوامر!")
            return
        
        change_command_state[user_id] = {
            'step': 1,
            'chat_id': chat_id
        }
        bot.reply_to(m, "⌯ أرسل الأمر القديم الذي تريد تغييره:")
    
    elif text == "تغيير رتبه":
        if user_rank not in ["مطور", "مالك اساسي", "مالك"]:
            bot.reply_to(m, "⌯ ليس لديك صلاحية لتغيير أسماء الرتب!")
            return
        
        change_rank_state[user_id] = {
            'step': 1,
            'chat_id': chat_id
        }
        bot.reply_to(m, "⌯ أرسل اسم الرتبة التي تريد تغييرها:\n(مطور, مالك اساسي, مالك, مدير, ادمن, مميز, عضو)")

def handle_info(m):
    """معالجة أوامر المعلومات"""
    chat_id = str(m.chat.id)
    
    if m.text in ["ايدي", "id"]:
        target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
        rank = get_user_rank(chat_id, target.id)
        
        cursor.execute(
            "SELECT msgs FROM stats WHERE chat_id = ? AND user_id = ?",
            (chat_id, target.id)
        )
        result = cursor.fetchone()
        msgs = result[0] if result else 0
        
        # الحصول على اسم الرتبة المخصص
        custom_rank = get_custom_rank_name(chat_id, rank)
        
        response = f"""
👤 الاسم: {target.first_name}
🆔 الايدي: {target.id}
🎖 الرتبة: {custom_rank}
💬 الرسائل: {msgs}
"""
        
        try:
            photos = bot.get_user_profile_photos(target.id, limit=1)
            if photos.total_count > 0:
                bot.send_photo(
                    m.chat.id,
                    photos.photos[0][-1].file_id,
                    caption=response
                )
                return
        except:
            pass
        
        bot.reply_to(m, response)
    
    elif m.text == "رتبتي":
        rank = get_user_rank(chat_id, m.from_user.id)
        custom_rank = get_custom_rank_name(chat_id, rank)
        bot.reply_to(m, f"⌯ رتبتك هي: {custom_rank}")
    
    elif m.text == "رتبته" and m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
        rank = get_user_rank(chat_id, target_id)
        custom_rank = get_custom_rank_name(chat_id, rank)
        bot.reply_to(m, f"⌯ رتبته هي: {custom_rank}")

def handle_cleanup(m, user_rank):
    """معالجة أوامر المسح"""
    if user_rank == "عضو":
        return
    
    chat_id = str(m.chat.id)
    text = m.text
    
    if text == "مسح" and m.reply_to_message:
        try:
            bot.delete_message(chat_id, m.reply_to_message.message_id)
            bot.delete_message(chat_id, m.message_id)
        except:
            pass
    
    elif any(char.isdigit() for char in text):
        try:
            num = int(''.join(filter(str.isdigit, text)))
            num = min(num, 100)  # حد أقصى 100 رسالة
            
            for i in range(num):
                try:
                    bot.delete_message(chat_id, m.message_id - i)
                except:
                    pass
        except:
            pass

def handle_lists(m, user_rank):
    """معالجة أوامر القوائم"""
    chat_id = str(m.chat.id)
    text = m.text
    
    # التحقق من الصلاحيات
    rank_hierarchy = {
        "المطورين": ["مطور"],
        "المالكيين الاساسيين": ["مطور"],
        "المالكيين": ["مطور", "مالك اساسي"],
        "المدراء": ["مطور", "مالك اساسي", "مالك"],
        "الادمنيه": ["مطور", "مالك اساسي", "مالك", "مدير"],
        "المميزين": ["مطور", "مالك اساسي", "مالك", "مدير", "ادمن"],
        "المشرفين": ["مطور", "مالك اساسي", "مالك", "مدير"]
    }
    
    if text not in rank_hierarchy or user_rank not in rank_hierarchy[text]:
        bot.reply_to(m, "⌯ ليس لديك صلاحية لعرض هذه القائمة!")
        return
    
    if text == "المطورين":
        try:
            dev_info = bot.get_chat(f"@{DEV_USERNAME}")
            response = f"""
⌯ المطور الأساسي:
• الاسم: {dev_info.first_name}
• اليوزر: @{DEV_USERNAME}
• الايدي: {dev_info.id}
"""
            bot.reply_to(m, response)
        except:
            bot.reply_to(m, f"⌯ المطور الأساسي: @{DEV_USERNAME}")
    
    elif text == "المشرفين":
        try:
            admins = bot.get_chat_administrators(chat_id)
            admin_list = []
            
            for admin in admins:
                user = admin.user
                name = user.first_name or ""
                username = f"@{user.username}" if user.username else "لا يوجد"
                admin_list.append(f"• {name} | {username} | {user.id}")
            
            if admin_list:
                response = "⌯ قائمة المشرفين:\n" + "\n".join(admin_list)
            else:
                response = "⌯ لا يوجد مشرفين في المجموعة."
            
            bot.reply_to(m, response)
        except:
            bot.reply_to(m, "⌯ فشل في جلب قائمة المشرفين.")
    
    else:
        # عرض قوائم الرتب
        rank_map = {
            "المالكيين الاساسيين": "مالك اساسي",
            "المالكيين": "مالك",
            "المدراء": "مدير",
            "الادمنيه": "ادمن",
            "المميزين": "مميز"
        }
        
        if text in rank_map:
            target_rank = rank_map[text]
            cursor.execute(
                "SELECT user_id FROM ranks WHERE chat_id = ? AND rank = ?",
                (chat_id, target_rank)
            )
            users = cursor.fetchall()
            
            if not users:
                bot.reply_to(m, f"⌯ لا يوجد {target_rank} في المجموعة.")
                return
            
            user_list = []
            for user_id in users:
                try:
                    user = bot.get_chat_member(chat_id, user_id[0]).user
                    name = user.first_name or ""
                    username = f"@{user.username}" if user.username else "لا يوجد"
                    user_list.append(f"• {name} | {username} | {user.id}")
                except:
                    user_list.append(f"• مستخدم غادر | {user_id[0]}")
            
            response = f"⌯ قائمة {target_rank}:\n" + "\n".join(user_list)
            bot.reply_to(m, response)

def check_locks(m, user_rank):
    """فحص الأقفال قبل السماح بالرسالة - مصحح"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    
    # المستويات التي تستثنى من الأقفال (عدا قفل الدردشة)
    exempt_ranks = ["مطور", "مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]
    
    # فحص قفل الدردشة - يسري على الجميع بما فيهم المميزين
    cursor.execute(
        "SELECT 1 FROM locks WHERE chat_id = ? AND item = 'chat'",
        (chat_id,)
    )
    if cursor.fetchone() and user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير", "ادمن"]:
        # المميز لا يطبق عليه قفل الدردشة؟ نعم يطبق عليه حسب طلبك
        # يمكن تعديل هذا حسب الرغبة
        try:
            bot.delete_message(chat_id, m.message_id)
        except:
            pass
        return False
    
    # الأعضاء العاديون فقط يطبق عليهم باقي الأقفال
    if user_rank not in exempt_ranks:
        # فحص قفل المحتوى
        content_map = {
            'photo': 'photo',
            'video': 'video',
            'sticker': 'sticker',
            'animation': 'animation',
            'video_note': 'video_note',
            'document': 'document',
            'audio': 'audio'
        }
        
        content_type = m.content_type
        if content_type in content_map:
            cursor.execute(
                "SELECT 1 FROM locks WHERE chat_id = ? AND item = ?",
                (chat_id, content_map[content_type])
            )
            if cursor.fetchone():
                try:
                    bot.delete_message(chat_id, m.message_id)
                except:
                    pass
                return False
        
        # فحص قفل الكل
        cursor.execute(
            "SELECT 1 FROM locks WHERE chat_id = ? AND item = 'all'",
            (chat_id,)
        )
        if cursor.fetchone():
            try:
                bot.delete_message(chat_id, m.message_id)
            except:
                pass
            return False
        
        # فحص قفل الروابط
        if m.text and ('http://' in m.text.lower() or 'https://' in m.text.lower() or 'www.' in m.text.lower()):
            cursor.execute(
                "SELECT 1 FROM locks WHERE chat_id = ? AND item = 'links'",
                (chat_id,)
            )
            if cursor.fetchone():
                try:
                    bot.delete_message(chat_id, m.message_id)
                except:
                    pass
                return False
        
        # فحص قفل اليوزرات
        if m.text and '@' in m.text:
            cursor.execute(
                "SELECT 1 FROM locks WHERE chat_id = ? AND item = 'usernames'",
                (chat_id,)
            )
            if cursor.fetchone():
                try:
                    bot.delete_message(chat_id, m.message_id)
                except:
                    pass
                return False
    
    return True

def check_auto_responses(m, chat_id):
    """فحص الردود التلقائية - مصحح"""
    if not m.text:
        return
    
    cursor.execute(
        "SELECT reply_type, reply_data, caption, file_id FROM responses WHERE chat_id = ? AND trigger = ?",
        (chat_id, m.text)
    )
    result = cursor.fetchone()
    
    if result:
        reply_type, reply_data, caption, file_id = result
        
        try:
            if reply_type == 'text':
                bot.reply_to(m, reply_data)
            
            elif reply_type == 'photo':
                photo_data = json.loads(reply_data)
                bot.send_photo(
                    m.chat.id,
                    photo_data.get('photo', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'video':
                video_data = json.loads(reply_data)
                bot.send_video(
                    m.chat.id,
                    video_data.get('video', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'sticker':
                sticker_data = json.loads(reply_data)
                bot.send_sticker(
                    m.chat.id,
                    sticker_data.get('sticker', file_id),
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'animation':
                anim_data = json.loads(reply_data)
                bot.send_animation(
                    m.chat.id,
                    anim_data.get('animation', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'voice':
                voice_data = json.loads(reply_data)
                bot.send_voice(
                    m.chat.id,
                    voice_data.get('voice', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'document':
                doc_data = json.loads(reply_data)
                bot.send_document(
                    m.chat.id,
                    doc_data.get('document', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'audio':
                audio_data = json.loads(reply_data)
                bot.send_audio(
                    m.chat.id,
                    audio_data.get('audio', file_id),
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            
            elif reply_type == 'video_note':
                vnote_data = json.loads(reply_data)
                bot.send_video_note(
                    m.chat.id,
                    vnote_data.get('video_note', file_id),
                    reply_to_message_id=m.message_id
                )
        
        except Exception as e:
            print(f"Error sending auto-response: {e}")

# --- [ أوامر البداية ] ---
@bot.message_handler(commands=['start'])
def start_command(m):
    response = """
🎯 *مرحباً بك في بوت الإدارة المتكامل!*

🛠 *المميزات المتاحة:*
1️⃣ *نظام الإدارة والعقوبات*
   - كتم/حظر/تقييد بمدة زمنية
   - الغاء العقوبات
   - هرمية الرتب

2️⃣ *نظام الأقفال*
   - قفل/فتح أنواع المحتوى
   - المميزون مستثنون من الأقفال (عدا قفل الدردشة)

3️⃣ *نظام الردود الذكية*
   - إضافة ردود بأنواع مختلفة
   - مسح وعرض الردود

4️⃣ *نظام التخصيص*
   - تغيير أسماء الأوامر
   - تغيير أسماء الرتب

📋 *الأوامر الأساسية:*
• `ايدي` - لعرض معلوماتك
• `رتبتي` - لمعرفة رتبتك
• `الردود` - لعرض الردود المضافة

⚙️ *للاستفسار:* @cEbot
"""
    bot.reply_to(m, response, parse_mode="Markdown")

# --- [ تشغيل البوت ] ---
print("✅ البوت يعمل بنجاح!")
print(f"👤 المطور: @{DEV_USERNAME}")
print("🔄 في انتظار الرسائل...")
bot.infinity_polling()
