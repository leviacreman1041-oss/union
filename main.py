import telebot, sqlite3, time, re, os, random
from gtts import gTTS

# --- [ الإعدادات ] ---
TOKEN = "8486555369:AAGa6z2L1KKA-ajRdacAK21FAtzH9ZCbm4U"
DEV_ID = 8147516847 
DEV_USERNAME = "levil_8"
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# --- [ قاعدة البيانات ] ---
conn = sqlite3.connect("master.db", check_same_thread=False)
cursor = conn.cursor()
tables = [
    "ranks (chat_id TEXT, user_id INTEGER, rank TEXT)",
    "responses (chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT)",
    "custom_cmds (chat_id TEXT, old_cmd TEXT, new_cmd TEXT)",
    "custom_ranks (chat_id TEXT, old_rank TEXT, new_rank TEXT)",
    "locks (chat_id TEXT, item TEXT)",
    "muted (chat_id TEXT, user_id INTEGER)",
    "stats (chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0)",
    "cache (user_id INTEGER PRIMARY KEY, username TEXT, name TEXT)"
]
for t in tables: cursor.execute(f"CREATE TABLE IF NOT EXISTS {t}")
conn.commit()

RANK_POWER = {"مطور": 100, "مالك اساسي": 90, "مالك": 80, "مدير": 70, "ادمن": 60, "مميز": 50, "عضو": 10}

# --- [ الدوال ] ---
def get_rank(chat_id, user_id):
    if user_id == DEV_ID: return "مطور"
    cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), user_id))
    res = cursor.fetchone()
    if res: return res[0]
    try:
        u = bot.get_chat_member(chat_id, user_id)
        if u.status == 'creator': return "مالك اساسي"
        if u.status == 'administrator': return "مدير"
    except: pass
    return "عضو"

def get_custom_rank(chat_id, rank_name):
    cursor.execute("SELECT new_rank FROM custom_ranks WHERE chat_id=? AND old_rank=?", (str(chat_id), rank_name))
    res = cursor.fetchone()
    return res[0] if res else rank_name

def extract_target(m):
    target_id, sec = None, 0
    text = (m.text or m.caption or "")
    if m.reply_to_message: target_id = m.reply_to_message.from_user.id
    else:
        match = re.search(r'@(\w+)|(\d{7,})', text)
        if match:
            if match.group(1):
                cursor.execute("SELECT user_id FROM cache WHERE username=?", (match.group(1).lower(),))
                res = cursor.fetchone(); target_id = res[0] if res else None
            else: target_id = int(match.group(2))
    t_match = re.search(r'(\d+)\s*(دقيق|ساع|يوم)', text)
    if t_match:
        v, unit = int(t_match.group(1)), t_match.group(2)
        if 'دقيق' in unit: sec = v * 60
        elif 'ساع' in unit: sec = v * 3600
        elif 'يوم' in unit: sec = v * 86400
    return target_id, sec

states = {}

@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'document'])
def main_handler(m):
    chat_id, user_id = str(m.chat.id), m.from_user.id
    text = (m.text or m.caption or "").strip()
    
    actual_rank = get_rank(chat_id, user_id)
    pwr = RANK_POWER.get(actual_rank, 10)
    display_rank = get_custom_rank(chat_id, actual_rank)

    # تحديث الكاش والرسائل
    if m.from_user.username: cursor.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (user_id, m.from_user.username.lower(), m.from_user.first_name))
    cursor.execute("INSERT OR IGNORE INTO stats VALUES (?, ?, 0)", (chat_id, user_id))
    cursor.execute("UPDATE stats SET msgs = msgs + 1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    conn.commit()

    # 1. نظام الأقفال (المميز فما فوق محمي)
    cursor.execute("SELECT item FROM locks WHERE chat_id=?", (chat_id,))
    active_locks = [r[0] for r in cursor.fetchall()]
    if pwr < 60:
        if "chat" in active_locks: bot.delete_message(chat_id, m.message_id); return
        if pwr < 50: # الأعضاء فقط
            if m.content_type in active_locks: bot.delete_message(chat_id, m.message_id); return
            if "links" in active_locks and ("t.me" in text or "http" in text): bot.delete_message(chat_id, m.message_id); return

    # 2. أوامر الإدارة (حظر، كتم، تقييد)
    if any(cmd in text for cmd in ["حظر", "كتم", "طرد", "تقيد"]) and pwr >= 70:
        target, sec = extract_target(m)
        if target:
            if pwr <= RANK_POWER.get(get_rank(chat_id, target), 10) and actual_rank != "مطور":
                return bot.reply_to(m, "<b>⌯ لا يمكنك التحكم برتبة مساوية أو أعلى منك!</b>")
            until = int(time.time() + sec) if sec > 0 else 0
            if "حظر" in text: bot.ban_chat_member(chat_id, target, until_date=until)
            elif "كتم" in text: cursor.execute("INSERT OR IGNORE INTO muted VALUES (?, ?)", (chat_id, target))
            elif "طرد" in text: bot.kick_chat_member(chat_id, target)
            elif "تقيد" in text: bot.restrict_chat_member(chat_id, target, until_date=until, can_send_messages=False)
            bot.reply_to(m, "<b>⌯ تم التنفيذ بنجاح.</b>")
            conn.commit(); return

    # 3. أوامر الرفع والتنزيل
    if text.startswith(("رفع ", "تنزيل ")) and pwr >= 70:
        target, _ = extract_target(m)
        r_name = next((r for r in ["مدير", "ادمن", "مميز", "مالك اساسي", "مالك"] if r in text), None)
        if target and r_name:
            if pwr <= RANK_POWER.get(get_rank(chat_id, target), 10) and actual_rank != "مطور": return
            if "رفع" in text: cursor.execute("INSERT OR REPLACE INTO ranks VALUES (?, ?, ?)", (chat_id, target, r_name))
            else: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND user_id=? AND rank=?", (chat_id, target, r_name))
            bot.reply_to(m, f"<b>⌯ تم {text[:3]} {r_name}.</b>")
            conn.commit(); return

    # 4. أوامر القفل والفتح (الشاملة)
    locks_map = {"الصور": "photo", "الفيديو": "video", "الروابط": "links", "الدردشه": "chat", "الملصقات": "sticker", "المتحركات": "animation", "الفويسات": "voice", "الكل": "all"}
    if text.startswith(("قفل ", "فتح ")) and pwr >= 70:
        item = text.split(" ", 1)[1]
        if item in locks_map:
            db_item = locks_map[item]
            if text.startswith("قفل"):
                if db_item == "all":
                    for v in locks_map.values(): cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, v))
                else: cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_id, db_item))
            else:
                if db_item == "all": cursor.execute("DELETE FROM locks WHERE chat_id=?", (chat_id,))
                else: cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_id, db_item))
            bot.reply_to(m, f"<b>⌯ تم {text[:3]} {item}.</b>")
            conn.commit(); return

    # 5. أوامر المسح
    if text.startswith("مسح ") and pwr >= 70:
        if "الردود" in text: cursor.execute("DELETE FROM responses WHERE chat_id=?", (chat_id,))
        if "المدراء" in text and pwr >= 80: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND rank='مدير'", (chat_id,))
        if "المميزين" in text: cursor.execute("DELETE FROM ranks WHERE chat_id=? AND rank='مميز'", (chat_id,))
        bot.reply_to(m, "<b>⌯ تم المسح بنجاح.</b>")
        conn.commit(); return

    # 6. نظام الردود والتغيير (States)
    if text == "اضف رد" and pwr >= 70:
        states[user_id] = {'a': 'add_res', 's': 1}; return bot.reply_to(m, "<b>أرسل الكلمة:</b>")
    if text == "تغيير امر" and pwr >= 90:
        states[user_id] = {'a': 'ch_cmd', 's': 1}; return bot.reply_to(m, "<b>الأمر القديم:</b>")
    if text == "تغيير رتبه" and pwr >= 90:
        states[user_id] = {'a': 'ch_rank', 's': 1}; return bot.reply_to(m, "<b>الرتبة الأصلية:</b>")

    if user_id in states:
        s = states[user_id]
        if s['a'] == 'add_res' and s['s'] == 1:
            states[user_id].update({'t': text, 's': 2}); return bot.reply_to(m, "<b>أرسل الرد:</b>")
        elif s['a'] == 'add_res' and s['s'] == 2:
            f_id = m.text if m.content_type == 'text' else getattr(m, m.content_type).file_id if m.content_type != 'photo' else m.photo[-1].file_id
            cursor.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (chat_id, s['t'], f_id, m.content_type, m.caption))
            conn.commit(); del states[user_id]; return bot.reply_to(m, "<b>تم الحفظ.</b>")
        # (يمكن إضافة منطق تغيير الرتبة والأمر هنا بنفس الطريقة)

    # 7. أوامر عامة
    if text == "ايدي":
        bot.reply_to(m, f"<b>👤 اسمك: {m.from_user.first_name}\n🆔 ايديك: {user_id}\n🎖 رتبتك: {display_rank}</b>")
    
    if text.startswith("انطقي ") and pwr >= 50:
        word = text.replace("انطقي ", "")
        tts = gTTS(word, lang='ar')
        tts.save("voice.ogg")
        with open("voice.ogg", "rb") as v: bot.send_voice(chat_id, v, reply_to_message_id=m.message_id)
        os.remove("voice.ogg")

    # تشغيل الردود
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_id, text))
    r = cursor.fetchone()
    if r:
        try:
            if r[1] == 'text': bot.reply_to(m, r[0])
            else: getattr(bot, f"send_{r[1]}")(chat_id, r[0], caption=r[2], reply_to_message_id=m.message_id)
        except: pass

bot.infinity_polling()
