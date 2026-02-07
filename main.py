import telebot import sqlite3 import time import threading import re import os from gtts import gTTS

---------------- CONFIG ----------------

TOKEN = "8509756465:AAHWRF5n_sAcWsmo14hfvKwoUPltb5C6kHo"  # استبدل لو محتاج DEV_ID = 8147516847  # ايدي المطور DEV_USERNAME = "levil_8" bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

---------------- DATABASE ----------------

DB_FILE = "bot_system.db" conn = sqlite3.connect(DB_FILE, check_same_thread=False) cursor = conn.cursor()

جداول

cursor.execute("""CREATE TABLE IF NOT EXISTS ranks( chat_id TEXT, user_id INTEGER, rank TEXT )""") cursor.execute("""CREATE TABLE IF NOT EXISTS punish( chat_id TEXT, user_id INTEGER, until INTEGER, ptype TEXT )""") cursor.execute("""CREATE TABLE IF NOT EXISTS stats( chat_id TEXT, user_id INTEGER, msgs INTEGER DEFAULT 0 )""") cursor.execute("""CREATE TABLE IF NOT EXISTS custom_cmds( chat_id TEXT, old_cmd TEXT, new_cmd TEXT )""") cursor.execute("""CREATE TABLE IF NOT EXISTS responses( chat_id TEXT, trigger TEXT, reply_data TEXT, type TEXT, caption TEXT )""") cursor.execute("""CREATE TABLE IF NOT EXISTS locks( chat_id TEXT, item TEXT )""") cursor.execute("""CREATE TABLE IF NOT EXISTS rank_names( chat_id TEXT, rank_key TEXT, display TEXT )""") conn.commit()

---------------- CONSTANTS ----------------

POWER = { "مطور": 100, "مالك اساسي": 90, "مالك": 80, "مدير": 70, "ادمن": 60, "مميز": 40, "عضو": 10 }

DEFAULT_COMMANDS = { 'ban': 'حظر', 'mute': 'كتم', 'restrict': 'تقييد' }

حالة إضافة الردود و تغيير الأوامر

change_state = {}    # user_id -> {'step':1,'old':...} add_resp_state = {}  # user_id -> {'step':1/'2','trigger':...}

---------------- Helpers ----------------

def get_rank(chat_id, uid): # check developer try: if uid == DEV_ID: return 'مطور' member = bot.get_chat_member(chat_id, uid) if member.status == 'creator': return 'مالك اساسي' except Exception: pass cursor.execute("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (str(chat_id), uid)) r = cursor.fetchone() return r[0] if r else 'عضو'

def rank_display(chat_id, rank_key): # return customized display name if exists cursor.execute("SELECT display FROM rank_names WHERE chat_id=? AND rank_key=?", (str(chat_id), rank_key)) r = cursor.fetchone() return r[0] if r else rank_key

def can_act(src_rank_key, target_rank_key): return POWER.get(src_rank_key, 0) > POWER.get(target_rank_key, 0)

def extract_target(m): # returns user object or None if m.reply_to_message: return m.reply_to_message.from_user parts = (m.text or '').split() # look for last arg that is @username or digits for p in parts[1:]: if p.startswith('@'): try: return bot.get_chat(p) except Exception: return None if p.isdigit(): try: return bot.get_chat(int(p)) except Exception: return None return None

def parse_time(text): # supports: '10 دقيقه' '1 د' '2 ساعه' '3 يوم' '5 دقائق' if not text: return None m = re.search(r"(\d+)\s*(دقيقة|دقائق|د|ساعه|ساعة|س|يوم|ايام|ي)", text) if not m: return None n = int(m.group(1)) unit = m.group(2) if unit.startswith('د'): return n * 60 if unit.startswith('س'): return n * 3600 if unit.startswith('ي'): return n * 86400 return None

---------------- Auto-unpunish thread ----------------

def auto_unpunish(): while True: try: now = int(time.time()) cursor.execute("SELECT chat_id, user_id, until, ptype FROM punish WHERE until<=?", (now,)) rows = cursor.fetchall() for c, u, until, ptype in rows: try: if ptype == 'mute' or ptype == 'restrict': bot.restrict_chat_member(int(c), u, can_send_messages=True) elif ptype == 'ban': bot.unban_chat_member(int(c), u) except Exception: pass cursor.execute("DELETE FROM punish WHERE chat_id=? AND user_id=?", (c, u)) conn.commit() except Exception: pass time.sleep(5)

threading.Thread(target=auto_unpunish, daemon=True).start()

---------------- Small utilities ----------------

def save_tts(text, lang='ar'): fname = f"tts_{int(time.time()*1000)}.mp3" tts = gTTS(text=text, lang=lang) tts.save(fname) return fname

---------------- Command handlers inside message handler ----------------

@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'sticker', 'video', 'animation', 'voice', 'audio', 'document', 'video_note']) def main_handler(m): try: if m.chat.type not in ['group', 'supergroup']: return except Exception: return

chat_id = m.chat.id
chat_key = str(chat_id)
user = m.from_user
uid = user.id
text = m.text or m.caption or ''
text = text.strip()

# update stats
try:
    cursor.execute("INSERT OR IGNORE INTO stats (chat_id, user_id, msgs) VALUES (?, ?, 0)", (chat_key, uid))
    cursor.execute("UPDATE stats SET msgs = msgs + 1 WHERE chat_id = ? AND user_id = ?", (chat_key, uid))
    conn.commit()
except Exception:
    pass

my_rank = get_rank(chat_id, uid)

# enforce locks for ordinary members
try:
    if my_rank not in ['مطور', 'مالك اساسي', 'مالك', 'مدير', 'ادمن']:
        # if chat locked entirely
        cursor.execute("SELECT 1 FROM locks WHERE chat_id=? AND item=?", (chat_key, 'chat'))
        if cursor.fetchone():
            try:
                bot.delete_message(chat_id, m.message_id)
            except Exception:
                pass
            return
        # check type-specific lock
        ctype = m.content_type
        # map telebot types to our lock keys
        mapping = {
            'photo': 'الصور', 'video': 'الفيديو', 'sticker': 'الملصقات', 'animation': 'المتحركات',
            'voice': 'الفويسات', 'audio': 'الملفات', 'document': 'الملفات', 'video_note': 'انطقي'
        }
        if ctype in mapping:
            lock_key = mapping[ctype]
            if is_locked(chat_key, lock_key):
                try:
                    bot.delete_message(chat_id, m.message_id)
                except Exception:
                    pass
                return
        # if message contains link and links locked
        if 'http://' in text or 'https://' in text or 't.me/' in text:
            if is_locked(chat_key, 'الروابط'):
                try:
                    bot.delete_message(chat_id, m.message_id)
                except Exception:
                    pass
                return
except Exception:
    pass

# --- interactive: change command flow ---
if uid in change_state:
    state = change_state[uid]
    if state.get('step') == 1:
        state['old'] = text
        state['step'] = 2
        change_state[uid] = state
        bot.reply_to(m, f"⌯ أمر قديم: <b>{text}</b> الآن ارسل الامر البديل الجديد.")
        return
    elif state.get('step') == 2:
        old = state.get('old')
        new = text
        cursor.execute("DELETE FROM custom_cmds WHERE chat_id=? AND old_cmd=?", (chat_key, old))
        cursor.execute("INSERT INTO custom_cmds VALUES (?, ?, ?)", (chat_key, old, new))
        conn.commit()
        del change_state[uid]
        bot.reply_to(m, f"⌯ تم تغيير الأمر <b>{old}</b> إلى <b>{new}</b>.")
        return

# --- interactive: add response flow ---
if uid in add_resp_state:
    state = add_resp_state[uid]
    if text == 'الغاء':
        del add_resp_state[uid]
        bot.reply_to(m, '⌯ تم إلغاء إضافة الرد.')
        return
    if state['step'] == 1:
        state['trigger'] = text
        state['step'] = 2
        add_resp_state[uid] = state
        bot.reply_to(m, f"⌯ الكلمة المفتاحية: <b>{text}</b>. الآن أرسل الرد (نص، صورة، فيديو، ستيكر...).")
        return
    elif state['step'] == 2:
        trigger = state['trigger']
        ctype = m.content_type
        f_id = None
        cap = None
        try:
            if ctype == 'text':
                f_id = text
            else:
                media_attrs = ['photo', 'sticker', 'animation', 'video', 'voice', 'video_note', 'document', 'audio']
                for attr in media_attrs:
                    val = getattr(m, attr)
                    if val:
                        if attr == 'photo':
                            f_id = val[-1].file_id
                        else:
                            f_id = val.file_id
                        break
                cap = m.caption if hasattr(m, 'caption') else None
        except Exception:
            pass
        cursor.execute("DELETE FROM responses WHERE chat_id=? AND trigger=?", (chat_key, trigger))
        cursor.execute("INSERT INTO responses VALUES (?, ?, ?, ?, ?)", (chat_key, trigger, f_id, ctype, cap))
        conn.commit()
        del add_resp_state[uid]
        bot.reply_to(m, f"⌯ تم حفظ الرد لكلمة: <b>{trigger}</b>.")
        return

# --- command mapping ---
ban_c = get_cmd(chat_key, DEFAULT_COMMANDS['ban'])
mute_c = get_cmd(chat_key, DEFAULT_COMMANDS['mute'])
rest_c = get_cmd(chat_key, DEFAULT_COMMANDS['restrict'])

# --- ADMIN ACTIONS (reply-based) ---
if m.reply_to_message:
    t = m.reply_to_message.from_user
    t_id = t.id
    t_rank = get_rank(chat_id, t_id)

    # BAN
    if text.startswith(ban_c) and my_rank not in ['عضو']:
        if not can_act(my_rank, t_rank):
            bot.reply_to(m, '❌ لازم تكون رتبتك أعلى من الشخص.')
            return
        # parse optional duration
        secs = parse_time(text) or None
        try:
            bot.ban_chat_member(chat_id, t_id)
            if secs:
                until = int(time.time()) + secs
                cursor.execute("INSERT INTO punish VALUES (?, ?, ?, ?)", (chat_key, t_id, until, 'ban'))
                conn.commit()
                bot.reply_to(m, f"⛔ تم حظره لمدة {secs//60} دقيقة.")
            else:
                bot.reply_to(m, f"⛔ تم حظره نهائياً.")
            return
        except Exception as e:
            bot.reply_to(m, '❌ فشل تنفيذ الحظر: تأكد أن البوت مشرف ويملك صلاحيات.')
            return

    # MUTE
    if text.startswith(mute_c) and my_rank not in ['عضو']:
        if not can_act(my_rank, t_rank):
            bot.reply_to(m, '❌ لازم تكون رتبتك أعلى من الشخص.')
            return
        secs = parse_time(text) or None
        try:
            bot.restrict_chat_member(chat_id, t_id, can_send_messages=False)
            if secs:
                until = int(time.time()) + secs
                cursor.execute("INSERT INTO punish VALUES (?, ?, ?, ?)", (chat_key, t_id, until, 'mute'))
                conn.commit()
                bot.reply_to(m, f"🔇 تم كتمه لمدة {secs//60} دقيقة.")
            else:
                cursor.execute("INSERT OR IGNORE INTO punish VALUES (?, ?, ?, ?)", (chat_key, t_id, 9999999999, 'mute'))
                conn.commit()
                bot.reply_to(m, "🔇 تم كتمه.")
            return
        except Exception:
            bot.reply_to(m, '❌ فشل تنفيذ الكتم: تأكد أن البوت مشرف.')
            return

    # RESTRICT (full restrict send media/links)
    if text.startswith(rest_c) and my_rank not in ['عضو']:
        if not can_act(my_rank, t_rank):
            bot.reply_to(m, '❌ لازم تكون رتبتك أعلى من الشخص.')
            return
        secs = parse_time(text) or None
        try:
            bot.restrict_chat_member(chat_id, t_id, can_send_messages=False)
            if secs:
                until = int(time.time()) + secs
                cursor.execute("INSERT INTO punish VALUES (?, ?, ?, ?)", (chat_key, t_id, until, 'restrict'))
                conn.commit()
                bot.reply_to(m, f"⛔ تم تقييده لمدة {secs//60} دقيقة.")
            else:
                bot.reply_to(m, f"⛔ تم تقييده.")
            return
        except Exception:
            bot.reply_to(m, '❌ فشل تنفيذ التقييد: تأكد أن البوت مشرف.')
            return

# --- UNDO / CANCEL actions by text commands (not reply) ---
if text.startswith('الغاء'):
    # ممكن تكون: الغاء الكتم، الغاء الحظر، الغاء التقييد
    # نحاول استخراج نوع
    if 'كتم' in text:
        t = extract_target(m)
        if not t:
            bot.reply_to(m, '❌ استخدم بالرد أو اذكر اليوزر/الايدي.')
            return
        try:
            bot.restrict_chat_member(chat_id, t.id, can_send_messages=True)
        except Exception:
            pass
        cursor.execute("DELETE FROM punish WHERE chat_id=? AND user_id=? AND ptype IN ('mute')", (chat_key, t.id))
        conn.commit()
        bot.reply_to(m, '✅ تم فك الكتم.')
        return
    if 'حظر' in text or 'الغاء الحظر' in text:
        t = extract_target(m)
        if not t:
            bot.reply_to(m, '❌ استخدم بالرد أو اذكر اليوزر/الايدي.')
            return
        try:
            bot.unban_chat_member(chat_id, t.id)
        except Exception:
            pass
        cursor.execute("DELETE FROM punish WHERE chat_id=? AND user_id=? AND ptype IN ('ban')", (chat_key, t.id))
        conn.commit()
        bot.reply_to(m, '✅ تم فك الحظر.')
        return
    if 'تقييد' in text or 'الغاء التقييد' in text:
        t = extract_target(m)
        if not t:
            bot.reply_to(m, '❌ استخدم بالرد أو اذكر اليوزر/الايدي.')
            return
        try:
            bot.restrict_chat_member(chat_id, t.id, can_send_messages=True)
        except Exception:
            pass
        cursor.execute("DELETE FROM punish WHERE chat_id=? AND user_id=? AND ptype IN ('restrict')", (chat_key, t.id))
        conn.commit()
        bot.reply_to(m, '✅ تم فك التقييد.')
        return

# --- ID and rank commands ---
if text in ['ايدي', 'id']:
    t = extract_target(m) or user
    r = get_rank(chat_id, t.id)
    rdisp = rank_display(chat_key, r)
    cursor.execute("SELECT msgs FROM stats WHERE chat_id=? AND user_id=?", (chat_key, t.id))
    res = cursor.fetchone()
    msgs = res[0] if res else 0
    info = f"👤 الاسم: {t.first_name}\n🆔 الايدي: <code>{t.id}</code>\n🎖 الرتبة: {rdisp}\n💬 الرسائل: {msgs}\n🔗 اليوزر: @{t.username if getattr(t, 'username', None) else 'لا يوجد'}"
    try:
        photos = bot.get_user_profile_photos(t.id, limit=1)
        bot.send_photo(chat_id, photos.photos[0][-1].file_id, caption=info)
    except Exception:
        bot.reply_to(m, info)
    return

if text == 'رتبتي':
    bot.reply_to(m, f"🎖 رتبتك: <b>{rank_display(chat_key, my_rank)}</b>")
    return

if text.startswith('رتبته'):
    t = extract_target(m)
    if not t:
        bot.reply_to(m, '❌ الصيغة الصح: رتبته @username أو بالرد')
        return
    bot.reply_to(m, f"🎖 رتبته: <b>{rank_display(chat_key, get_rank(chat_id, t.id))}</b>")
    return

# --- add response command starter ---
if text == 'اضف رد' and my_rank not in ['عضو']:
    add_resp_state[uid] = {'step': 1}
    bot.reply_to(m, '⌯ أرسل الآن الكلمة المفتاحية (التي سيكتبها الأعضاء).')
    return

# list responses
if text == 'الردود':
    cursor.execute("SELECT trigger FROM responses WHERE chat_id=?", (chat_key,))
    rows = cursor.fetchall()
    if not rows:
        bot.reply_to(m, '⌯ لا توجد ردود مضافة.')
    else:
        bot.reply_to(m, '<b>⌯ قائمة الردود:</b>\n' + '\n'.join([f'• {r[0]}' for r in rows]))
    return

# delete response commands
if text.startswith('مسح رد ') and my_rank not in ['عضو']:
    trigger = text.replace('مسح رد ', '').strip()
    cursor.execute("DELETE FROM responses WHERE chat_id=? AND trigger=?", (chat_key, trigger))
    conn.commit()
    bot.reply_to(m, f'⌯ تم مسح الرد على ({trigger}).')
    return
if text == 'مسح الردود' and my_rank not in ['عضو']:
    cursor.execute("DELETE FROM responses WHERE chat_id=?", (chat_key,))
    conn.commit()
    bot.reply_to(m, '⌯ تم مسح جميع الردود.')
    return

# run auto-responses
try:
    cursor.execute("SELECT reply_data, type, caption FROM responses WHERE chat_id=? AND trigger=?", (chat_key, text))
    row = cursor.fetchone()
    if row:
        r_val, r_type, r_cap = row
        try:
            if r_type == 'text':
                bot.reply_to(m, r_val)
            elif r_type == 'photo':
                bot.send_photo(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'video':
                bot.send_video(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'animation':
                bot.send_animation(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'document':
                bot.send_document(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'voice':
                bot.send_voice(chat_id, r_val, caption=r_cap, reply_to_message_id=m.message_id)
            elif r_type == 'sticker':
                bot.send_sticker(chat_id, r_val, reply_to_message_id=m.message_id)
            elif r_type == 'video_note':
                bot.send_video_note(chat_id, r_val, reply_to_message_id=m.message_id)
        except Exception:
            pass
        return
except Exception:
    pass

# --- Locks (قفل/فتح) ---
locks_map = {"الصور": "الصور", "الفيديو": "الفيديو", "الملصقات": "الملصقات", "المتحركات": "المتحركات", "الفويسات": "الفويسات", "الملفات": "الملفات", "الروابط": "الروابط", "الدردشه": "chat", "انطقي":"انطقي"}
if (text.startswith('قفل ') or text.startswith('فتح ')) and my_rank not in ['عضو']:
    is_lock = text.startswith('قفل ')
    item_raw = text.split(' ', 1)[1].strip()
    if item_raw in locks_map:
        item_db = item_raw
        if is_lock:
            cursor.execute("INSERT OR IGNORE INTO locks VALUES (?, ?)", (chat_key, item_db))
        else:
            cursor.execute("DELETE FROM locks WHERE chat_id=? AND item=?", (chat_key, item_db))
        conn.commit()
        bot.reply_to(m, f"⌯ تم {'قفل' if is_lock else 'فتح'} {item_raw} بنجاح.")
        return

# --- تغيير أمر (interactive) ---
if text == 'تغيير امر' and my_rank not in ['عضو']:
    change_state[uid] = {'step': 1}
    bot.reply_to(m, '⌯ أرسل اسم الأمر القديم (مثال: حظر)')
    return

# --- تغيير اسم رتبه للعرض ---
if text.startswith('تغيير رتبه') and my_rank not in ['عضو']:
    # صيغة: تغيير رتبه مدير: الزعيم
    m2 = re.match(r'تغيير رتبه\s+(\S+)\s*:\s*(.+)', text)
    if not m2:
        bot.reply_to(m, '❌ الصيغة: تغيير رتبه <الرتبه> : <الاسم الجديد>')
        return
    rank_key = m2.group(1).strip()
    new_name = m2.group(2).strip()
    cursor.execute("DELETE FROM rank_names WHERE chat_id=? AND rank_key=?", (chat_key, rank_key))
    cursor.execute("INSERT INTO rank_names VALUES (?, ?, ?)", (chat_key, rank_key, new_name))
    conn.commit()
    bot.reply_to(m, f'✅ تم تغيير اسم الرتبة <{rank_key}> إلى <{new_name}>')
    return

# --- TTS ---
if text.startswith('انطقي'):
    rest = text.replace('انطقي', '').strip()
    if not rest:
        bot.reply_to(m, '❌ اكتب: انطقي <النص>')
        return
    try:
        fname = save_tts(rest)
        with open(fname, 'rb') as f:
            bot.send_voice(chat_id, f)
        os.remove(fname)
    except Exception:
        bot.reply_to(m, '❌ فشل تحويل النص لصوت.')
    return

# --- رسائلي ---
if text == 'رسائلي':
    cursor.execute("SELECT msgs FROM stats WHERE chat_id=? AND user_id=?", (chat_key, uid))
    r = cursor.fetchone()
    bot.reply_to(m, f"💬 رسائلك: {r[0] if r else 0}")
    return

# fallback: ignore

except Exception: try: bot.reply_to(m, '⚠️ حصل خطأ داخلي.') except Exception: pass

---------------- START ----------------

if name == 'main': print('Bot is starting...') bot.infinity_polling()
