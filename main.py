import telebot
import sqlite3
from datetime import datetime, timedelta
import time
import re

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
CREATE TABLE IF NOT EXISTS command_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    original_command TEXT,
    alias TEXT,
    UNIQUE(chat_id, alias)
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

# --- [ متغيرات نظام الفلوود ] ---
user_message_times = {}
user_message_counts = {}

# --- [ حالة إضافة الردود ] ---
add_response_state = {}

# --- [ حالة إضافة أوامر بديلة ] ---
add_alias_state = {}

# --- [ دوال المساعدة ] ---
def time_to_seconds(time_str):
    """تحويل النص الزمني إلى ثواني"""
    units = {
        'ثانية': 1, 'ثواني': 1, 'ث': 1,
        'دقيقة': 60, 'دقائق': 60, 'د': 60,
        'ساعة': 3600, 'ساعات': 3600, 'س': 3600,
        'يوم': 86400, 'ايام': 86400, 'ي': 86400,
        'اسبوع': 604800, 'اسابيع': 604800, 'أسبوع': 604800,
        'شهر': 2592000, 'اشهر': 2592000, 'ش': 2592000,
        'سنه': 31536000, 'سنة': 31536000, 'عام': 31536000
    }
    
    time_str = time_str.replace("و", " ").strip()
    total_seconds = 0
    
    # البحث عن أنماط مختلفة
    pattern = r'(\d+)\s*([^\d\s]+)'
    matches = re.findall(pattern, time_str)
    
    for num_str, unit in matches:
        try:
            num = int(num_str)
            for unit_key, unit_value in units.items():
                if unit.startswith(unit_key) or unit_key.startswith(unit):
                    total_seconds += num * unit_value
                    break
        except:
            continue
    
    return total_seconds if total_seconds > 0 else 3600

def get_command_alias(chat_id, command):
    """الحصول على الأمر الأصلي من البديل"""
    cursor.execute(
        "SELECT original_command FROM command_aliases WHERE chat_id = ? AND alias = ?",
        (str(chat_id), command.lower())
    )
    result = cursor.fetchone()
    
    if result:
        return result[0]
    
    # إذا لم يكن هناك بديل، نرجع الأمر كما هو
    return command

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
        
        # المطور الأساسي
        if member.user.username and member.user.username.lower() == DEV_USERNAME.lower():
            return "مطور"
        
        # المالك الأساسي
        if member.status == 'creator':
            return "مالك اساسي"
        
        # المشرفين في المجموعة
        if member.status == 'administrator':
            cursor.execute(
                "SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?",
                (str(chat_id), user_id)
            )
            result = cursor.fetchone()
            
            if result:
                return result[0]
            else:
                return "مدير"
    except Exception as e:
        print(f"Error getting user rank: {e}")
    
    cursor.execute(
        "SELECT rank FROM ranks WHERE chat_id = ? AND user_id = ?",
        (str(chat_id), user_id)
    )
    result = cursor.fetchone()
    
    if result:
        return result[0]
    return "عضو"

def get_user_by_username(username):
    """الحصول على معلومات المستخدم من اليوزر"""
    try:
        # إزالة @ إذا موجود
        username = username.replace("@", "").strip()
        
        # محاولة الحصول على معلومات المستخدم
        # هذه الطريقة تعمل فقط إذا كان المستخدم قد تفاعل مع البوت سابقاً
        user = bot.get_chat(f"@{username}")
        
        if user:
            return {
                'id': user.id,
                'first_name': user.first_name or f"@{username}",
                'username': username
            }
    except Exception as e:
        print(f"Error getting user by username @{username}: {e}")
    
    return None

def extract_target_from_text(text, chat_id):
    """استخراج معلومات الهدف من النص (بدون رد)"""
    if not text:
        return None, None
    
    # البحث عن @username في النص
    username_pattern = r'@([a-zA-Z][\w]{4,31})'
    usernames = re.findall(username_pattern, text)
    
    if usernames:
        username = usernames[0]  # نأخذ أول يوزر
        user_info = get_user_by_username(username)
        
        if user_info:
            # محاولة الحصول على معلومات العضو في المجموعة
            try:
                member = bot.get_chat_member(chat_id, user_info['id'])
                name = member.user.first_name or f"@{member.user.username}" or f"@{username}"
                return user_info['id'], name
            except:
                return user_info['id'], f"@{username}"
        else:
            return None, f"@{username}"
    
    # البحث عن ID رقمي في النص
    parts = text.split()
    for part in parts:
        if part.isdigit() and len(part) > 5:
            try:
                user_id = int(part)
                if user_id == bot.get_me().id:
                    return None, "البوت نفسه"
                
                try:
                    member = bot.get_chat_member(chat_id, user_id)
                    name = member.user.first_name or f"@{member.user.username}" or f"المستخدم {user_id}"
                    return user_id, name
                except:
                    return None, f"المستخدم {part}"
            except:
                pass
    
    return None, None

def can_punish(chat_id, punisher_id, target_id):
    """فحص إذا كان يمكن للمعاقب معاقبة الهدف"""
    if punisher_id == target_id:
        return False
    
    if target_id == bot.get_me().id:
        return False
    
    try:
        target_member = bot.get_chat_member(chat_id, target_id)
        if target_member.status in ['administrator', 'creator']:
            punisher_rank = get_user_rank(chat_id, punisher_id)
            if punisher_rank != "مطور":
                return False
    except:
        pass
    
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

def check_flood(chat_id, user_id):
    """فحص التكرار وتقييد العضو إذا تجاوز الحد"""
    current_time = time.time()
    key = f"{chat_id}_{user_id}"
    
    if key not in user_message_times:
        user_message_times[key] = []
        user_message_counts[key] = 0
    
    user_message_times[key].append(current_time)
    user_message_counts[key] += 1
    
    user_message_times[key] = [t for t in user_message_times[key] if current_time - t <= 5]
    
    if len(user_message_times[key]) >= 6:
        until_time = datetime.now() + timedelta(hours=6)
        try:
            bot.restrict_chat_member(
                chat_id, 
                user_id,
                until_date=until_time,
                can_send_messages=False
            )
            
            cursor.execute(
                "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                (str(chat_id), user_id, 'restrict', until_time.isoformat())
            )
            conn.commit()
            
            try:
                user = bot.get_chat_member(chat_id, user_id).user
                user_name = user.first_name or f"@{user.username}" or f"العضو {user_id}"
                bot.send_message(
                    chat_id,
                    f"⚠️ تم تقييد {user_name} لمدة 6 ساعات بسبب التكرار المفرط."
                )
            except:
                bot.send_message(
                    chat_id,
                    f"⚠️ تم تقييد العضو لمدة 6 ساعات بسبب التكرار المفرط."
                )
            
            del user_message_times[key]
            del user_message_counts[key]
            return True
        except Exception as e:
            print(f"Error in flood control: {e}")
    
    return False

# --- [ معالجة الأوامر باليوزر ] ---
def handle_command_with_username(m, command_type):
    """معالجة الأمر باستخدام اليوزر"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    user_rank = get_user_rank(chat_id, user_id)
    text = m.text.strip()
    
    if user_rank == "عضو":
        return
    
    # استخراج الهدف من النص
    target_id, target_name = extract_target_from_text(text, m.chat.id)
    
    if not target_id:
        if target_name and "@" in target_name:
            bot.reply_to(m, f"⌯ لم أستطع العثور على المستخدم {target_name}!\n⌯ تأكد من:\n1. صحة اليوزر\n2. أن المستخدم موجود في المجموعة\n3. أو استخدم الرد على رسالته")
        else:
            bot.reply_to(m, "⌯ يجب ذكر اليوزر مع @ أو الرد على رسالة المستخدم!")
        return
    
    if target_id == user_id:
        bot.reply_to(m, "⌯ لا يمكنك فعل ذلك بنفسك!")
        return
    
    if not can_punish(chat_id, user_id, target_id):
        bot.reply_to(m, "⌯ لا يمكنك معاقبة شخص رتبته أعلى أو مساوية لرتبتك!")
        return
    
    try:
        # استخراج المدة من النص
        duration_text = None
        seconds = None
        
        # البحث عن الوقت في النص
        words = text.split()
        for i in range(len(words)):
            if words[i].isdigit() and i + 1 < len(words):
                try:
                    num = int(words[i])
                    unit = words[i + 1]
                    duration_text = f"{num} {unit}"
                    seconds = time_to_seconds(duration_text)
                    break
                except:
                    continue
        
        if not seconds and text:
            seconds = time_to_seconds(text)
        
        until_time = None
        if seconds:
            until_time = datetime.now() + timedelta(seconds=seconds)
        
        display_name = target_name if target_name else f"المستخدم {target_id}"
        
        if "الغاء" in command_type:
            if "حظر" in command_type:
                try:
                    bot.unban_chat_member(chat_id, target_id)
                except:
                    pass
                cursor.execute(
                    "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'ban'",
                    (str(chat_id), target_id)
                )
                bot.reply_to(m, f"⌯ تم إلغاء حظر {display_name}.")
            
            elif "كتم" in command_type:
                cursor.execute(
                    "DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'mute'",
                    (str(chat_id), target_id)
                )
                bot.reply_to(m, f"⌯ تم إلغاء كتم {display_name}.")
            
            elif "تقييد" in command_type:
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
                    (str(chat_id), target_id)
                )
                bot.reply_to(m, f"⌯ تم إلغاء تقييد {display_name}.")
            
            conn.commit()
            return
        
        elif "حظر" in command_type:
            if until_time:
                try:
                    bot.ban_chat_member(chat_id, target_id, until_date=until_time)
                    cursor.execute(
                        "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                        (str(chat_id), target_id, 'ban', until_time.isoformat())
                    )
                    bot.reply_to(m, f"⌯ تم حظر {display_name} لمدة {duration_text or 'غير محدد'}.")
                except Exception as e:
                    error_msg = str(e)
                    if "administrator" in error_msg:
                        bot.reply_to(m, f"⌯ لا يمكن حظر {display_name} لأنه مشرف في المجموعة!")
                    else:
                        bot.reply_to(m, f"⌯ فشل في حظر {display_name}: {error_msg}")
            else:
                try:
                    bot.ban_chat_member(chat_id, target_id)
                    bot.reply_to(m, f"⌯ تم حظر {display_name} بنجاح.")
                except Exception as e:
                    error_msg = str(e)
                    if "administrator" in error_msg:
                        bot.reply_to(m, f"⌯ لا يمكن حظر {display_name} لأنه مشرف في المجموعة!")
                    else:
                        bot.reply_to(m, f"⌯ فشل في حظر {display_name}: {error_msg}")
        
        elif "كتم" in command_type:
            if until_time:
                cursor.execute(
                    "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                    (str(chat_id), target_id, 'mute', until_time.isoformat())
                )
                bot.reply_to(m, f"⌯ تم كتم {display_name} لمدة {duration_text or 'غير محدد'}.")
            else:
                cursor.execute(
                    "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                    (str(chat_id), target_id, 'mute', (datetime.now() + timedelta(days=365)).isoformat())
                )
                bot.reply_to(m, f"⌯ تم كتم {display_name} بنجاح.")
        
        elif "تقييد" in command_type:
            if until_time:
                try:
                    bot.restrict_chat_member(chat_id, target_id, until_date=until_time, can_send_messages=False)
                    cursor.execute(
                        "INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until) VALUES (?, ?, ?, ?)",
                        (str(chat_id), target_id, 'restrict', until_time.isoformat())
                    )
                    bot.reply_to(m, f"⌯ تم تقييد {display_name} لمدة {duration_text or 'غير محدد'}.")
                except Exception as e:
                    error_msg = str(e)
                    if "administrator" in error_msg:
                        bot.reply_to(m, f"⌯ لا يمكن تقييد {display_name} لأنه مشرف في المجموعة!")
                    else:
                        bot.reply_to(m, f"⌯ فشل في تقييد {display_name}: {error_msg}")
            else:
                try:
                    bot.restrict_chat_member(chat_id, target_id, can_send_messages=False)
                    bot.reply_to(m, f"⌯ تم تقييد {display_name} بنجاح.")
                except Exception as e:
                    error_msg = str(e)
                    if "administrator" in error_msg:
                        bot.reply_to(m, f"⌯ لا يمكن تقييد {display_name} لأنه مشرف في المجموعة!")
                    else:
                        bot.reply_to(m, f"⌯ فشل في تقييد {display_name}: {error_msg}")
        
        elif "طرد" in command_type:
            try:
                bot.kick_chat_member(chat_id, target_id)
                bot.unban_chat_member(chat_id, target_id)
                bot.reply_to(m, f"⌯ تم طرد {display_name} بنجاح.")
            except Exception as e:
                error_msg = str(e)
                if "administrator" in error_msg:
                    bot.reply_to(m, f"⌯ لا يمكن طرد {display_name} لأنه مشرف في المجموعة!")
                else:
                    bot.reply_to(m, f"⌯ فشل في طرد {display_name}: {error_msg}")
        
        conn.commit()
        
    except Exception as e:
        bot.reply_to(m, f"⌯ حدث خطأ: {str(e)}")

def handle_promotion_with_username(m):
    """معالجة الرفع والتنزيل باليوزر"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    user_rank = get_user_rank(chat_id, user_id)
    text = m.text.strip()
    
    if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        return
    
    # استخراج الهدف من النص
    target_id, target_name = extract_target_from_text(text, m.chat.id)
    
    if not target_id:
        if target_name and "@" in target_name:
            bot.reply_to(m, f"⌯ لم أستطع العثور على المستخدم {target_name}!\n⌯ تأكد من صحة اليوزر أو استخدم الرد على رسالته")
        else:
            bot.reply_to(m, "⌯ يجب ذكر اليوزر مع @ أو الرد على رسالة المستخدم!")
        return
    
    if not can_punish(chat_id, user_id, target_id):
        bot.reply_to(m, "⌯ لا يمكنك رفع/تنزيل شخص رتبته أعلى أو مساوية لرتبتك!")
        return
    
    # تحديد الرتبة من النص
    valid_ranks = ["مالك اساسي", "مالك", "مدير", "ادمن", "مميز"]
    rank_name = None
    
    for rank in valid_ranks:
        if rank in text:
            rank_name = rank
            break
    
    if not rank_name:
        bot.reply_to(m, f"⌯ رتبة غير صحيحة!\n⌯ الرتب المتاحة: {', '.join(valid_ranks)}")
        return
    
    try:
        display_name = target_name if target_name else f"المستخدم {target_id}"
        
        if text.startswith("رفع"):
            cursor.execute(
                "INSERT OR REPLACE INTO ranks (chat_id, user_id, rank) VALUES (?, ?, ?)",
                (chat_id, target_id, rank_name)
            )
            bot.reply_to(m, f"⌯ تم رفع {display_name} إلى رتبة {rank_name} بنجاح!")
        
        elif text.startswith("تنزيل"):
            cursor.execute(
                "DELETE FROM ranks WHERE chat_id = ? AND user_id = ? AND rank = ?",
                (chat_id, target_id, rank_name)
            )
            bot.reply_to(m, f"⌯ تم تنزيل {display_name} من رتبة {rank_name} بنجاح!")
        
        conn.commit()
    except Exception as e:
        bot.reply_to(m, f"⌯ حدث خطأ: {str(e)}")

def handle_alias_commands(m):
    """معالجة أوامر إضافة الأوامر البديلة"""
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = m.text.strip()
    
    if user_id in add_alias_state:
        state = add_alias_state[user_id]
        
        if state['step'] == 1:  # انتظار الأمر الأصلي
            if not text:
                bot.reply_to(m, "⌯ يجب إرسال الأمر الأصلي!")
                return
            
            add_alias_state[user_id] = {
                'step': 2,
                'original_command': text,
                'chat_id': chat_id
            }
            bot.reply_to(m, f"⌯ الأمر الأصلي: {text}\n⌯ الآن أرسل الكلمة البديلة لهذا الأمر:")
        
        elif state['step'] == 2:  # انتظار البديل
            original_cmd = state['original_command']
            alias = text.lower()
            
            # حذف أي بديل موجود لنفس الكلمة
            cursor.execute(
                "DELETE FROM command_aliases WHERE chat_id = ? AND alias = ?",
                (chat_id, alias)
            )
            
            # إضافة البديل الجديد
            cursor.execute(
                "INSERT INTO command_aliases (chat_id, original_command, alias) VALUES (?, ?, ?)",
                (chat_id, original_cmd, alias)
            )
            conn.commit()
            
            bot.reply_to(m, f"⌯ تم إضافة البديل '{alias}' للأمر '{original_cmd}' بنجاح!")
            del add_alias_state[user_id]
        
        return
    
    # أوامر إدارة البدائل
    if text == "اضف امر":
        if get_user_rank(chat_id, user_id) not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            bot.reply_to(m, "⌯ ليس لديك صلاحية لإضافة أوامر بديلة!")
            return
        
        add_alias_state[user_id] = {
            'step': 1,
            'chat_id': chat_id
        }
        bot.reply_to(m, "⌯ أرسل الأمر الأصلي الذي تريد إضافة بديل له:")
    
    elif text.startswith("حذف امر "):
        if get_user_rank(chat_id, user_id) not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            return
        
        alias = text.replace("حذف امر ", "").strip().lower()
        cursor.execute(
            "DELETE FROM command_aliases WHERE chat_id = ? AND alias = ?",
            (chat_id, alias)
        )
        affected = cursor.rowcount
        conn.commit()
        
        if affected > 0:
            bot.reply_to(m, f"⌯ تم حذف الأمر البديل '{alias}'")
        else:
            bot.reply_to(m, f"⌯ لا يوجد أمر بديل باسم '{alias}'")
    
    elif text == "الاوامر":
        cursor.execute(
            "SELECT original_command, alias FROM command_aliases WHERE chat_id = ?",
            (chat_id,)
        )
        aliases = cursor.fetchall()
        
        if not aliases:
            bot.reply_to(m, "⌯ لا توجد أوامر بديلة مضافة.")
        else:
            alias_list = []
            for original, alias in aliases:
                alias_list.append(f"• {alias} ← {original}")
            
            response = "⌯ الأوامر البديلة:\n" + "\n".join(alias_list)
            bot.reply_to(m, response)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text_messages(m):
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    text = m.text.strip() if m.text else ""
    
    if not text:
        return
    
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
    
    # الحصول على رتبة المستخدم
    user_rank = get_user_rank(chat_id, user_id)
    
    # نظام الفلوود - فقط للأعضاء
    if user_rank == "عضو":
        if check_flood(chat_id, user_id):
            return
    
    # التحقق من حالة إضافة الردود أولاً
    if user_id in add_response_state:
        handle_add_response_flow(m)
        return
    
    # التحقق من حالة إضافة الأوامر البديلة
    if user_id in add_alias_state:
        handle_alias_commands(m)
        return
    
    # الحصول على الأمر الحقيقي من البديل
    command = get_command_alias(chat_id, text.split()[0] if text else "")
    
    # إذا كان الأمر يحتوي على @ فهو يستهدف مستخدم باليوزر
    if "@" in text:
        # تحديد نوع الأمر
        if command in ["حظر", "كتم", "تقييد", "طرد", "الغاء حظر", "الغاء كتم", "الغاء تقييد"]:
            handle_command_with_username(m, command)
            return
        elif command in ["رفع", "تنزيل"]:
            handle_promotion_with_username(m)
            return
    
    # معالجة الأوامر الأخرى
    handle_other_commands(m, user_rank, text)

def handle_add_response_flow(m):
    """معالجة تدفق إضافة رد جديد"""
    user_id = m.from_user.id
    text = m.text.strip() if m.text else ""
    
    state = add_response_state[user_id]
    
    if text == "الغاء":
        del add_response_state[user_id]
        bot.reply_to(m, "⌯ تم إلغاء إضافة الرد.")
        return
    
    if state['step'] == 1:
        if not text:
            bot.reply_to(m, "⌯ يجب إرسال كلمة نصية ككلمة مفتاحية!")
            return
        
        add_response_state[user_id] = {
            'step': 2,
            'trigger': text,
            'chat_id': str(m.chat.id)
        }
        bot.reply_to(m, f"⌯ الكلمة المفتاحية: {text}\n⌯ الآن أرسل الرد (نص، صورة، فيديو، ملصق، ملف...):")

@bot.message_handler(func=lambda m: True, content_types=['photo', 'video', 'document', 'audio', 'voice', 'sticker', 'animation'])
def handle_media_messages(m):
    chat_id = str(m.chat.id)
    user_id = m.from_user.id
    
    if is_punished(chat_id, user_id, "mute"):
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except:
            pass
        return
    
    user_rank = get_user_rank(chat_id, user_id)
    if not check_locks(m, user_rank):
        return
    
    if user_id in add_response_state:
        state = add_response_state[user_id]
        if state['step'] == 2:
            trigger = state['trigger']
            content_type = m.content_type
            caption = m.caption if m.caption else ""
            file_id = ""
            
            if content_type == 'photo':
                file_id = m.photo[-1].file_id
            elif content_type == 'video':
                file_id = m.video.file_id
            elif content_type == 'sticker':
                file_id = m.sticker.file_id
            elif content_type == 'animation':
                file_id = m.animation.file_id
            elif content_type == 'voice':
                file_id = m.voice.file_id
            elif content_type == 'document':
                file_id = m.document.file_id
            elif content_type == 'audio':
                file_id = m.audio.file_id
            
            cursor.execute(
                "DELETE FROM responses WHERE chat_id = ? AND trigger = ?",
                (state['chat_id'], trigger)
            )
            
            cursor.execute(
                "INSERT INTO responses (chat_id, trigger, reply_type, reply_data, caption, file_id) VALUES (?, ?, ?, ?, ?, ?)",
                (state['chat_id'], trigger, content_type, caption, caption, file_id)
            )
            conn.commit()
            
            media_type = {
                'photo': 'صورة',
                'video': 'فيديو',
                'sticker': 'ملصق',
                'animation': 'متحركة',
                'voice': 'صوت',
                'document': 'ملف',
                'audio': 'صوتي'
            }.get(content_type, content_type)
            
            if caption:
                bot.reply_to(m, f"⌯ تم حفظ الرد ({media_type}) على كلمة '{trigger}' بنجاح!")
            else:
                bot.reply_to(m, f"⌯ تم حفظ الرد ({media_type}) على كلمة '{trigger}' بنجاح!")
            
            del add_response_state[user_id]

def handle_other_commands(m, user_rank, text):
    """معالجة الأوامر الأخرى"""
    chat_id = str(m.chat.id)
    
    # أوامر المعلومات
    if text in ["ايدي", "id", "رتبتي"]:
        handle_info_command(m)
    
    elif text.startswith("رتبته"):
        if m.reply_to_message:
            target = m.reply_to_message.from_user
            rank = get_user_rank(chat_id, target.id)
            bot.reply_to(m, f"🎖 **رتبة {target.first_name}:** {rank}", parse_mode="Markdown")
        else:
            bot.reply_to(m, "⌯ يجب الرد على رسالة المستخدم لمعرفة رتبته!")
    
    # أوامر الردود
    elif text == "اضف رد":
        if user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير"]:
            bot.reply_to(m, "⌯ ليس لديك صلاحية لإضافة ردود!")
            return
        
        add_response_state[m.from_user.id] = {
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
            bot.reply_to(m, response_text)
    
    # أوامر القوائم
    elif text in ["المشرفين"] and user_rank in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        try:
            admins = bot.get_chat_administrators(chat_id)
            admin_list = []
            
            for admin in admins:
                user = admin.user
                name = user.first_name or ""
                username = f"@{user.username}" if user.username else "بدون معرف"
                status = "مالك" if admin.status == 'creator' else "مشرف"
                admin_list.append(f"• {name} | {username} | {status}")
            
            if admin_list:
                response = "⌯ **قائمة المشرفين:**\n" + "\n".join(admin_list)
            else:
                response = "⌯ لا يوجد مشرفين في المجموعة."
            
            bot.reply_to(m, response)
        except:
            bot.reply_to(m, "⌯ فشل في جلب قائمة المشرفين.")
    
    elif text in ["المدراء", "الادمنيه", "المميزين"] and user_rank in ["مطور", "مالك اساسي", "مالك", "مدير"]:
        rank_map = {
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
            for user_id_tuple in users:
                user_id = user_id_tuple[0]
                try:
                    user = bot.get_chat_member(chat_id, user_id).user
                    name = user.first_name or ""
                    username = f"@{user.username}" if user.username else "بدون معرف"
                    user_list.append(f"• {name} | {username} | {user.id}")
                except:
                    user_list.append(f"• مستخدم غادر | {user_id}")
            
            response = f"⌯ **قائمة {target_rank}:**\n" + "\n".join(user_list)
            bot.reply_to(m, response)
    
    # فحص الردود الذكية
    check_auto_responses(m, chat_id)

def handle_info_command(m):
    """معالجة أوامر المعلومات"""
    chat_id = str(m.chat.id)
    text = m.text
    
    if text in ["ايدي", "id"]:
        target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
        
        rank = get_user_rank(chat_id, target.id)
        
        cursor.execute(
            "SELECT msgs FROM stats WHERE chat_id = ? AND user_id = ?",
            (chat_id, target.id)
        )
        result = cursor.fetchone()
        msgs = result[0] if result else 0
        
        response = f"""
📊 **معلومات العضو** 📊
━━━━━━━━━━━━━━━━━━
👤 **الاسم:** {target.first_name} {target.last_name if target.last_name else ''}
🆔 **الايدي:** `{target.id}`
🔗 **المعرف:** @{target.username if target.username else 'لا يوجد'}
🎖 **الرتبة:** {rank}
💬 **الرسائل:** {msgs}
━━━━━━━━━━━━━━━━━━
"""
        
        try:
            photos = bot.get_user_profile_photos(target.id, limit=1)
            if photos.total_count > 0:
                bot.send_photo(
                    m.chat.id,
                    photos.photos[0][-1].file_id,
                    caption=response,
                    parse_mode="Markdown"
                )
                return
        except:
            pass
        
        bot.reply_to(m, response, parse_mode="Markdown")
    
    elif text == "رتبتي":
        rank = get_user_rank(chat_id, m.from_user.id)
        bot.reply_to(m, f"🎖 **رتبتك هي:** {rank}", parse_mode="Markdown")

def check_locks(m, user_rank):
    """فحص الأقفال"""
    chat_id = str(m.chat.id)
    
    cursor.execute(
        "SELECT 1 FROM locks WHERE chat_id = ? AND item = 'chat'",
        (chat_id,)
    )
    if cursor.fetchone() and user_rank not in ["مطور", "مالك اساسي", "مالك", "مدير", "ادمن"]:
        try:
            bot.delete_message(chat_id, m.message_id)
        except:
            pass
        return False
    
    if user_rank == "عضو":
        content_map = {
            'photo': 'photo',
            'video': 'video',
            'sticker': 'sticker',
            'animation': 'animation',
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
    """فحص الردود التلقائية"""
    if not m.text:
        return
    
    text = m.text.strip().lower()
    
    cursor.execute(
        "SELECT reply_type, reply_data, caption, file_id FROM responses WHERE chat_id = ? AND LOWER(trigger) = ?",
        (chat_id, text)
    )
    result = cursor.fetchone()
    
    if result:
        reply_type, reply_data, caption, file_id = result
        
        try:
            if reply_type == 'text':
                bot.reply_to(m, reply_data)
            elif reply_type == 'photo':
                bot.send_photo(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'video':
                bot.send_video(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'sticker':
                bot.send_sticker(
                    m.chat.id,
                    file_id,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'animation':
                bot.send_animation(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'voice':
                bot.send_voice(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'document':
                bot.send_document(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
            elif reply_type == 'audio':
                bot.send_audio(
                    m.chat.id,
                    file_id,
                    caption=caption,
                    reply_to_message_id=m.message_id
                )
        except Exception as e:
            print(f"Error sending auto-response: {e}")

# --- [ أمر البداية ] ---
@bot.message_handler(commands=['start', 'مساعدة'])
def start_command(m):
    response = """
🎯 **مرحباً بك في بوت الإدارة المتكامل!**

🛠 **المميزات المتاحة:**
✅ **نظام الإدارة والعقوبات باليوزر**
   - تقييد @username 3 ساعات
   - حظر @username يوم
   - كتم @username
   - رفع @username مدير
   - تنزيل @username

✅ **نظام الأوامر البديلة**
   - اضف امر ← إضافة أمر بديل
   - حذف امر ← حذف أمر بديل
   - الاوامر ← عرض الأوامر البديلة

✅ **نظام الردود الذكية**
   - اضف رد ← إضافة رد تلقائي
   - الردود ← عرض الردود
   - مسح رد ← حذف رد

✅ **نظام الفلوود التلقائي**
   - تقييد تلقائي لمدة 6 ساعات عند التكرار المفرط

📋 **أمثلة على الأوامر:**
• `تقييد 3 ساعات @username`
• `حظر @username`
• `رفع مدير @username`
• `ايدي` (بالرد أو بدون)
• `اضف رد` ← إضافة رد تلقائي

⚙️ **للاستفسار:** @cEbot
"""
    bot.reply_to(m, response, parse_mode="Markdown")

# --- [ تشغيل البوت ] ---
print("✅ البوت يعمل بنجاح!")
print(f"👤 المطور: @{DEV_USERNAME}")
print("🔄 في انتظار الرسائل...")
bot.infinity_polling()
