import asyncio, sqlite3, re, time, os
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, types, functions
from telethon.tl.types import ChatBannedRights, UserStatusOnline, UserStatusOffline

# ------------------- [ إعدادات البوت ] -------------------
API_ID = 26604893
API_HASH = 'b4dad6237531036f1a4bb2580e4985b1'
BOT_TOKEN = '8486555369:AAGa6z2L1KKA-ajRdacAK21FAtzH9ZCbm4U' 
DEV_USER = 'levil_8' 

client = TelegramClient('bot_final_session', API_ID, API_HASH)
DB_NAME = 'bot_final_v4.db'

# القائمة المحددة للأقفال المدعومة
VALID_LOCKS = ["الروابط", "اليوزرات", "الصور", "الفيديو", "الملصقات", "التوجيه", "الفويسات", "الدردشه"]

# ------------------- [ قاعدة البيانات ] -------------------
db = sqlite3.connect(DB_NAME, check_same_thread=False)
cr = db.cursor()

cr.execute('CREATE TABLE IF NOT EXISTS users (cid INTEGER, uid INTEGER, rank TEXT, UNIQUE(cid, uid))')
cr.execute('CREATE TABLE IF NOT EXISTS locks (cid INTEGER, type TEXT, UNIQUE(cid, type))')
cr.execute('CREATE TABLE IF NOT EXISTS replies (cid INTEGER, trigger TEXT, reply_id INTEGER, type TEXT, UNIQUE(cid, trigger))')
cr.execute('CREATE TABLE IF NOT EXISTS aliases (cid INTEGER, command TEXT, action TEXT, UNIQUE(cid, command))')
db.commit()

# ------------------- [ أدوات مساعدة ] -------------------
flood_cache = {}
ranks_power = {
    "مطور": 100, "مالك اساسي": 50, "مالك": 40, 
    "مدير": 30, "ادمن": 20, "مميز": 10, "عضو": 0
}

async def get_rank(cid, user_id, username=None):
    if username and username.lower() == DEV_USER.lower(): return ("مطور", 100)
    cr.execute('SELECT rank FROM users WHERE cid=? AND uid=?', (cid, user_id))
    res = cr.fetchone()
    if res:
        return (res[0], ranks_power.get(res[0], 0))
    return ("عضو", 0)

async def resolve_user(event):
    user_id = None
    user_entity = None
    args = event.text.split()
    
    if event.reply_to_msg_id:
        reply_msg = await event.get_reply_message()
        user_id = reply_msg.sender_id
        user_entity = await reply_msg.get_sender()
    else:
        for word in args:
            if word.startswith("@"):
                try:
                    user_entity = await client.get_entity(word)
                    user_id = user_entity.id
                    break
                except: pass
            elif word.isdigit() and len(word) > 7:
                try:
                    user_id = int(word)
                    user_entity = await client.get_entity(user_id)
                    break
                except: pass
    return user_id, user_entity

def parse_time(text):
    match = re.search(r'(\d+)\s*(دقيقة|دقائق|ساعة|ساعات|ساعه|يوم|ايام|أيام|اسبوع|شهر)', text)
    if not match: return None
    val = int(match.group(1))
    unit = match.group(2)
    delta = None
    if 'دقيق' in unit: delta = timedelta(minutes=val)
    elif 'ساع' in unit: delta = timedelta(hours=val)
    elif 'يوم' in unit or 'أيام' in unit or 'ايام' in unit: delta = timedelta(days=val)
    elif 'اسبوع' in unit: delta = timedelta(weeks=val)
    elif 'شهر' in unit: delta = timedelta(days=val*30)
    return datetime.now(timezone.utc) + delta if delta else None

# ------------------- [ 1. المحرك الرئيسي ] -------------------
@client.on(events.NewMessage)
async def main_watcher(e):
    if not e.is_group: return
    try:
        cid = e.chat_id
        sender = await e.get_sender()
        if not sender: return
        uid = sender.id
        rank_name, rank_score = await get_rank(cid, uid, getattr(sender, 'username', None))
        text = e.text or ""

        first_word = text.split()[0] if text else ""
        cr.execute('SELECT action FROM aliases WHERE cid=? AND command=?', (cid, first_word))
        alias = cr.fetchone()
        if alias:
            text = text.replace(first_word, alias[0], 1)

        if rank_score < 20:
            now = time.time()
            if uid not in flood_cache: flood_cache[uid] = []
            flood_cache[uid].append(now)
            flood_cache[uid] = [t for t in flood_cache[uid] if now - t < 5]
            if len(flood_cache[uid]) > 6:
                flood_cache[uid] = []
                until = datetime.now(timezone.utc) + timedelta(hours=6)
                try:
                    await client.edit_permissions(cid, uid, until_date=until, send_messages=False)
                    await e.reply("⚠️ **تم تقييدك تلقائياً** بسبب التكرار.")
                except: pass

        if rank_score < 10:
            cr.execute('SELECT type FROM locks WHERE cid=?', (cid,))
            locks = [row[0] for row in cr.fetchall()]
            should_delete = False
            if "الروابط" in locks and re.search(r't\.me|http|www', text): should_delete = True
            if "اليوزرات" in locks and "@" in text: should_delete = True
            if "الصور" in locks and e.photo: should_delete = True
            if "الفيديو" in locks and e.video: should_delete = True
            if "الفويسات" in locks and e.voice: should_delete = True
            if "الملصقات" in locks and e.sticker: should_delete = True
            if "التوجيه" in locks and e.fwd_from: should_delete = True
            if "الدردشه" in locks: should_delete = True
            
            if should_delete:
                await e.delete()
                return

        cr.execute('SELECT reply_id FROM replies WHERE cid=? AND trigger=?', (cid, text))
        rep = cr.fetchone()
        if rep:
            source_msg = await client.get_messages(cid, ids=rep[0])
            if source_msg:
                await client.send_message(cid, source_msg)
                return

    except Exception as error:
        print(f"Error in watcher: {error}")

# ------------------- [ 2. معالج الأوامر ] -------------------
@client.on(events.NewMessage)
async def admin_commands(e):
    if not e.is_group or not e.text: return
    try:
        text = e.text
        cid = e.chat_id
        sender = await e.get_sender()
        uid = sender.id
        rank_name, rank_score = await get_rank(cid, uid, getattr(sender, 'username', None))

        if text == "ايدي":
            await e.reply(f"👤 **معلوماتك:**\n🆔 الايدي: `{uid}`\n🎖 الرتبة: {rank_name}")
            return

        if text == "رتبتي":
            await e.reply(f"🎖 رتبتك هي: **{rank_name}**")
            return

        if text.startswith(("كشف", "معلوماته", "رتبته")):
            t_id, t_ent = await resolve_user(e)
            if not t_ent: return await e.reply("⚠️ حدد المستخدم بالرد أو اليوزر.")
            t_rank, _ = await get_rank(cid, t_id, getattr(t_ent, 'username', None))
            await e.reply(f"🕵️‍♂️ **البطاقة:**\n👤 الاسم: {t_ent.first_name}\n🆔 الايدي: `{t_id}`\n🎖 الرتبة: {t_rank}")
            return

        if text.startswith(("رفع", "تنزيل")) and "الكل" not in text:
            if rank_score < 20: return 
            target_id, target_entity = await resolve_user(e)
            if not target_id: return await e.reply("⚠️ حدد العضو بالرد أو المنشن.")
            parts = text.split()
            if len(parts) < 2: return
            if text.startswith("رفع"):
                role = parts[1]
                if role not in ranks_power:
                    return await e.reply(f"⚠️ الرتبة **{role}** غير موجودة.")
                requested_role_power = ranks_power.get(role, 0)
                _, target_current_power = await get_rank(cid, target_id)
                if rank_name != "مطور" and target_current_power >= rank_score:
                    return await e.reply("❌ لا يمكنك تغيير رتبة شخص رتبته أعلى منك أو مساوية لك.")
                if rank_name != "مطور" and requested_role_power >= rank_score:
                    return await e.reply(f"❌ لا يمكنك رفع عضو لرتبة أعلى من رتبتك.")
                cr.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?)', (cid, target_id, role))
                db.commit()
                await e.reply(f"✅ تم تنفيذ الأمر: أصبح العضو **{role}**")
            elif text.startswith("تنزيل"):
                _, target_current_power = await get_rank(cid, target_id)
                if rank_name != "مطور" and target_current_power >= rank_score:
                    return await e.reply("❌ لا يمكنك تنزيل شخص رتبته أعلى منك.")
                cr.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?)', (cid, target_id, "عضو"))
                db.commit()
                await e.reply(f"✅ تم تنزيل العضو إلى رتبة **عضو**")
            return

        if text.startswith(("حظر", "طرد", "كتم", "تقييد", "الغاء", "رفع القيود")):
            # تعديل الصلاحية لـ "رفع القيود" لتكون من مدير (30) فأعلى
            if text.startswith(("الغاء", "رفع القيود")):
                if rank_score < 30: return
            else:
                if rank_score < 20: return

            t_id, t_ent = await resolve_user(e)
            if not t_id: return await e.reply("⚠️ يرجى الرد على الشخص أو منشنته.")
            _, t_score = await get_rank(cid, t_id)
            if t_score >= rank_score and not text.startswith(("الغاء", "رفع القيود")): 
                return await e.reply("❌ العضو محمي برتبته.")

            until = parse_time(text)
            time_match = re.search(r'(\d+)\s*\w+', text)
            time_text = time_match.group(0) if time_match else ""
            t_str = f"لمدة {time_text}" if until else "مؤبد"

            try:
                if text.startswith("حظر"):
                    await client.edit_permissions(cid, t_id, view_messages=False, until_date=until)
                    await e.reply(f"🚫 تم **حظر** العضو {t_str}")
                elif text.startswith("طرد"):
                    await client.kick_participant(cid, t_id)
                    await e.reply("👢 تم **طرد** العضو.")
                elif text.startswith("كتم"):
                    await client.edit_permissions(cid, t_id, send_messages=False, until_date=until)
                    await e.reply(f"😶 تم **كتم** العضو {t_str}")
                elif text.startswith("تقييد"):
                    await client.edit_permissions(cid, t_id, send_messages=False, until_date=until)
                    await e.reply(f"⛓ تم **تقييد** العضو بالكامل {t_str}")
                elif text.startswith(("الغاء", "رفع القيود")):
                    await client.edit_permissions(cid, t_id, send_messages=True, send_media=True, send_stickers=True, send_gifs=True, embed_links=True)
                    await e.reply("✅ تم **رفع القيود** عن العضو بنجاح.")
            except Exception as ex:
                await e.reply(f"❌ خطأ: {ex}")
            return

        if text.startswith(("قفل", "فتح")):
            if rank_score < 30: return
            parts = text.split()
            if len(parts) < 2: return
            item = parts[1]
            if item not in VALID_LOCKS: return 
            if "قفل" in text:
                cr.execute('INSERT OR REPLACE INTO locks VALUES (?, ?)', (cid, item))
                await e.reply(f"🔒 تم قفل **{item}**")
            else:
                cr.execute('DELETE FROM locks WHERE cid=? AND type=?', (cid, item))
                await e.reply(f"🔓 تم فتح **{item}**")
            db.commit()
            return

        if text == "اضف رد":
            if rank_score < 30: return
            async with client.conversation(cid, timeout=60) as conv:
                await conv.send_message("📝 **أرسل الآن الكلمة التي تريد الرد عليها:**")
                w_msg = await conv.get_response()
                word = w_msg.text
                await conv.send_message(f"🖼 **أرسل الآن الرد (نص، صورة، ملصق...) ليكون رداً على ({word}):**")
                r = await conv.get_response()
                cr.execute('INSERT OR REPLACE INTO replies VALUES (?, ?, ?, ?)', (cid, word, r.id, 'media'))
                db.commit()
                await conv.send_message(f"✅ تم حفظ الرد لـ ({word})")
            return

        if text == "اضف امر":
            if rank_score < 40: return
            async with client.conversation(cid, timeout=60) as conv:
                await conv.send_message("⚙️ **أرسل الأمر القديم (مثلاً: كتم):**")
                old_cmd = (await conv.get_response()).text
                await conv.send_message(f"🆕 **أرسل الآن الأمر الجديد ليكون بديلاً لـ ({old_cmd}):**")
                new_cmd = (await conv.get_response()).text
                cr.execute('INSERT OR REPLACE INTO aliases VALUES (?, ?, ?)', (cid, new_cmd, old_cmd))
                db.commit()
                await conv.send_message(f"✅ تم ربط **{new_cmd}** بـ **{old_cmd}**")
            return

        if text == "تنزيل الكل":
            if rank_score < 50: return
            target_id, _ = await resolve_user(e)
            if target_id:
                _, t_power = await get_rank(cid, target_id)
                if rank_name != "مطور" and t_power >= rank_score:
                    return await e.reply("❌ لا يمكنك تنزيل شخص رتبته أعلى منك.")
                cr.execute('DELETE FROM users WHERE cid=? AND uid=?', (cid, target_id))
                await e.reply("✅ تم تنزيل العضو من كافة الرتب.")
            else:
                cr.execute('DELETE FROM users WHERE cid=?', (cid,))
                await e.reply("✅ تم تصفير كافة الرتب في المجموعة.")
            db.commit()
            return

        if text == "كشف البوتات":
            bots = []
            async for u in client.iter_participants(cid):
                if u.bot: bots.append(f"🤖 @{u.username or u.id}")
            await e.reply("\n".join(bots) if bots else "لم يتم العثور على بوتات.")

    except Exception as ex:
        print(f"Admin Error: {ex}")

# ------------------- [ التشغيل ] -------------------
print("🚀 تم تشغيل البوت بنجاح.. جرب الأوامر الآن!")
client.start(bot_token=BOT_TOKEN)
client.run_until_disconnected()
