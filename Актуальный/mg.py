import asyncio
import json
import os
import re
import string
import secrets
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = "8378826726:AAE7KLaf6YwqpFFF8OKI4wQQA5OMeRzmufg"
API_ID = 34156040
API_HASH = "e08ce93ff25dfaeb8d442d2656051fb2"
SESSION_NAME = "analytics_session"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ================== USER-SCOPED STORAGE ==================
def user_file(uid, name):
    user_dir = os.path.join(BASE_DIR, "users", str(uid))
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, name)


# ============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
tg = TelegramClient(SESSION_NAME, API_ID, API_HASH)

state = {}
temp = {}

# ================= ХРАНЕНИЕ =================

# ================== VERIFIED USERS ==================

VERIFIED_USERS_DB = "verified_users.json"

def load_verified_users():
    path = os.path.join(BASE_DIR, VERIFIED_USERS_DB)
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return {}

    return data


def save_verified_users(users: dict):
    path = os.path.join(BASE_DIR, VERIFIED_USERS_DB)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def is_verified(uid):
    users = load_verified_users()
    return str(uid) in users


def set_verified(uid: int, expires_at: str | None):
    users = load_verified_users()
    users[str(uid)] = expires_at
    save_verified_users(users)


# ================== KEYS STORAGE ==================

KEYS_DB = "keys_db.json"

def load_keys():
    path = os.path.join(BASE_DIR, KEYS_DB)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_keys(keys):
    path = os.path.join(BASE_DIR, KEYS_DB)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)

def generate_key(length=16):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))



# ================== KEY TIME UTILS ==================

def parse_duration(text: str):
    text = text.lower().strip().replace(" ", "")
    total_seconds = 0

    patterns = [
        (r"(\d+)(ч|час|часа|часов)", 3600),
        (r"(\d+)(д|день|дня|дней)", 86400),
        (r"(\d+)(м|мин|минута|минут|минуты)", 60),
    ]

    for pattern, mult in patterns:
        m = re.search(pattern, text)
        if m:
            total_seconds += int(m.group(1)) * mult

    return total_seconds if total_seconds > 0 else None

# ================= КНОПКИ =================

def kb_main():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Анализ канала")],
                        [KeyboardButton(text="📂 Папка рекламы")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

def kb_after_analysis():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Анализ рекламы")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

def kb_ads_info():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 Рекламные посты")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

def kb_ads_period():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1 день"), KeyboardButton(text="3 дня")],
            [KeyboardButton(text="7 дней")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

# ================= УТИЛИТЫ =================

# --- расширенный поиск рекламируемых каналов (публичные + приватные) ---

# ====== FIX: распознавание рекламных каналов через text-link ======

# ====== FIX: кликабельные invite-ссылки вида t.me/+HASH ======

# ====== FIX: контакт берем из РЕКЛАМИРУЕМОГО канала ======

def has_telegram_channel_link(msg):
    # text-based
    if msg.text:
        if re.search(r"@([A-Za-z0-9_]{4,})", msg.text):
            return True
        if re.search(r"t\.me/(\+|c/|[A-Za-z0-9_]{4,})", msg.text):
            return True

    # entity-based (hidden links)
    if msg.entities:
        from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
        for ent in msg.entities:
            url = None
            if isinstance(ent, MessageEntityTextUrl):
                url = ent.url
            elif isinstance(ent, MessageEntityUrl):
                url = msg.text[ent.offset: ent.offset + ent.length]
            if url and re.search(r"t\.me/(\+|c/|[A-Za-z0-9_]{4,})", url):
                return True

    return False


async def get_advertised_channel_contact(tg, identifier):
    """
    identifier can be:
    - username
    - c/ID
    - invite:HASH
    """
    try:
        if identifier.startswith("invite:"):
            # невозможно получить данные без вступления
            return "invite link"

        if identifier.startswith("c/"):
            return "private channel"

        # public channel
        entity = await tg.get_entity(identifier)
        full = await tg(GetFullChannelRequest(entity))
        about = full.full_chat.about or ""
        contact = extract_ad_contacts(about)
        return contact if contact else "не найден"
    except:
        return "не найден"


def extract_invite_links_from_entities(msg):
    results = []
    if not msg.entities:
        return results

    for ent in msg.entities:
        url = None
        try:
            from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl
            if isinstance(ent, MessageEntityTextUrl):
                url = ent.url
            elif isinstance(ent, MessageEntityUrl):
                url = msg.text[ent.offset: ent.offset + ent.length]
        except:
            continue

        if not url:
            continue

        # invite link: t.me/+HASH
        m = re.search(r"t\.me/\+([A-Za-z0-9_-]+)", url)
        if m:
            results.append(f"invite:{m.group(1)}")

    return results


from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

# ================= SAFE SEND =================
async def safe_answer(m: Message, text: str, reply_markup=None):
    try:
        await m.answer(text, reply_markup=reply_markup)
    except Exception:
        pass


def extract_ad_channels_from_entities(msg):
    results = []

    if not msg.entities:
        return results

    for ent in msg.entities:
        url = None

        if isinstance(ent, MessageEntityTextUrl):
            url = ent.url
        elif isinstance(ent, MessageEntityUrl):
            url = msg.text[ent.offset: ent.offset + ent.length]

        if not url:
            continue

        # t.me/username
        m = re.search(r"t\.me/([A-Za-z0-9_]{4,})", url)
        if m:
            results.append(m.group(1))
            continue

        # t.me/c/ID/POST
        m = re.search(r"t\.me/c/(\d+)", url)
        if m:
            results.append(f"c/{m.group(1)}")

    return results


def extract_ad_channels(text: str):
    results = []

    # @username
    results += re.findall(r"@([A-Za-z0-9_]{4,})", text)

    # t.me/username
    results += re.findall(r"t\.me/([A-Za-z0-9_]{4,})", text)

    # https://t.me/c/123456/789 (private channels)
    results += [f"c/{cid}" for cid in re.findall(r"t\.me/c/(\d+)", text)]

    return list(dict.fromkeys(results))


def extract_username(text):
    if text.startswith("@"):
        return text[1:]
    m = re.search(r"t\.me/([A-Za-z0-9_]+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_]{4,}", text):
        return text
    return None

async def find_channel_by_name(name):
    result = await tg(SearchRequest(q=name, limit=10))
    best, max_subs = None, -1
    for chat in result.chats:
        if isinstance(chat, Channel):
            try:
                full = await tg(GetFullChannelRequest(chat))
                subs = full.full_chat.participants_count or 0
                if subs > max_subs:
                    best, max_subs = chat, subs
            except:
                pass
    return best

def build_post_link(entity, msg_id):
    if entity.username:
        return f"https://t.me/{entity.username}/{msg_id}"
    return f"https://t.me/c/{entity.id}/{msg_id}"

def is_ad_post(text: str):
    text = (text or "").lower()
    return any(k in text for k in ["реклама", "advert", "promo", "партнер", "партнёр"])

# ================= АНАЛИЗ КАНАЛА =================

async def analyze_channel_stats(entity):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)

    views_24h, post_dates, last_views = [], [], []

    async for msg in tg.iter_messages(entity, limit=80):
        if not msg.date:
            continue
        if msg.views:
            last_views.append(msg.views)
        if msg.date >= since:
            if msg.views:
                views_24h.append(msg.views)
            post_dates.append(msg.date)
        if msg.date < since:
            break

    avg_views = sum(views_24h) // len(views_24h) if views_24h else 0
    posts_per_day = len(post_dates)

    stability = 0
    if len(last_views) >= 5:
        mx, mn = max(last_views[:5]), min(last_views[:5])
        if mx > 0:
            stability = round((1 - (mx - mn) / mx) * 100, 1)

    return avg_views, posts_per_day, stability

def estimate_growth(subs):
    return {"1d": round(subs * 0.002), "7d": round(subs * 0.01), "30d": round(subs * 0.03)}

def estimate_gender():
    return "М ~55% / Ж ~45%"

def extract_ad_contacts(about: str):
    if not about:
        return "—"
    for line in about.splitlines():
        if any(k in line.lower() for k in ["реклам", "advert", "promo", "по вопросам"]):
            return line.strip()
    return "—"

# ================= АНАЛИЗ РЕКЛАМЫ =================

async def analyze_ads(entity):
    now = datetime.now(timezone.utc)
    ads = {"1d": [], "3d": [], "7d": []}

    async for msg in tg.iter_messages(entity, limit=200):
        if not msg.date or not msg.text:
            continue
        if not is_ad_post(msg.text):
            continue

        delta = now - msg.date
        info = {
            "date": msg.date,
            "views": msg.views or 0,
            "id": msg.id,
            "link": build_post_link(entity, msg.id)
        }

        if delta <= timedelta(days=1):
            ads["1d"].append(info)
        if delta <= timedelta(days=3):
            ads["3d"].append(info)
        if delta <= timedelta(days=7):
            ads["7d"].append(info)

        if delta > timedelta(days=7):
            break

    return ads

# ================= HANDLERS =================

@dp.message(CommandStart())
async def start(m: Message):
    state.clear()
    temp.clear()
    await m.answer("🏠 Главное меню", reply_markup=kb_main())


# ================== ПАПКА РЕКЛАМЫ (ИЗОЛИРОВАННАЯ ЛОГИКА) ==================
# ВАЖНО:
# - логика "Анализ канала" и "Мои каналы" НЕ ТРОНУТА
# - используем фильтры, чтобы не конфликтовать с общим handler

ADS_FOLDER_FILE = "ads_folder.json"

def load_ads_folder(uid=None):
    path = user_file(uid, ADS_FOLDER_FILE) if uid is not None else os.path.join(BASE_DIR, ADS_FOLDER_FILE)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_ads_folder(data, uid=None):
    path = user_file(uid, ADS_FOLDER_FILE) if uid is not None else os.path.join(BASE_DIR, ADS_FOLDER_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def kb_ads_folder():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить канал")],
            [KeyboardButton(text="📋 Список каналов")],
            [KeyboardButton(text="📢 Рекламные посты")],
            [KeyboardButton(text="🗄 БД Админы")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )


async def ads_folder_open(m: Message):
    await m.answer("📂 Папка рекламы", reply_markup=kb_ads_folder())


@dp.message(lambda m: m.text == "📂 Папка рекламы")
async def ads_folder_open(m: Message):
    if not await require_active_key(m):
        return
    if not is_verified(m.from_user.id):
        await m.answer("🔐 У вас нет активного доступа. Введите ключ через /key")
        return
    await m.answer("📂 Папка рекламы", reply_markup=kb_ads_folder())


@dp.message(lambda m: m.text == "➕ Добавить канал")
async def ads_folder_add_start(m: Message):
    state[m.from_user.id] = "ads_folder_add"
    await m.answer("Пришли @канал или ссылку")

@dp.message(lambda m: state.get(m.from_user.id) == "ads_folder_add")
async def ads_folder_add_finish(m: Message):
    username = extract_username(m.text)
    if not username:
        await m.answer("❌ Не удалось распознать канал")
        return
    data = load_ads_folder(m.from_user.id)
    if username not in data:
        data.append(username)
        save_ads_folder(data, m.from_user.id)
    state.pop(m.from_user.id, None)
    await m.answer("✅ Канал добавлен", reply_markup=kb_ads_folder())


# ================== БД АДМИНЫ (ПАРСЕР) ==================

ADS_ADMINS_DB = "ads_admins_db.json"

def load_ads_admins_db(uid=None):
    path = user_file(uid, ADS_ADMINS_DB) if uid is not None else os.path.join(BASE_DIR, ADS_ADMINS_DB)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_ads_admins_db(data, uid=None):
    path = user_file(uid, ADS_ADMINS_DB) if uid is not None else os.path.join(BASE_DIR, ADS_ADMINS_DB)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ================== КОНЕЦ ПАПКИ РЕКЛАМЫ ==================



@dp.message(lambda m: m.text == "📋 Список каналов")
async def ads_folder_list(m: Message):
    data = load_ads_folder(m.from_user.id)
    if not data:
        await m.answer("❌ В папке рекламы нет каналов", reply_markup=kb_ads_folder())
        return

    text = "📋 Каналы в папке рекламы:\n\n"
    for ch in data:
        text += f"• @{ch}\n"

    await m.answer(text, reply_markup=kb_ads_folder())


@dp.message(lambda m: m.text == "📢 Рекламные посты")
async def ads_posts_start(m: Message):
    state[m.from_user.id] = "ads_posts_hours"
    await m.answer("⏱ За сколько часов искать рекламу? Введи число")

@dp.message(lambda m: state.get(m.from_user.id) == "ads_posts_hours")
async def ads_posts_hours(m: Message):
    try:
        hours = int(m.text)
    except:
        await m.answer("❌ Нужно число часов")
        return

    state.pop(m.from_user.id, None)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    results = []
    advertised_seen = set()
    advertised_seen = set()
    for ch in load_ads_folder(m.from_user.id):
        try:
            entity = await tg.get_entity(ch)
            full = await tg(GetFullChannelRequest(entity))
            admin = extract_ad_contacts(full.full_chat.about)
        except:
            continue

        async for msg in tg.iter_messages(entity, limit=200):
            if not msg.date or msg.date < since:
                break
            if not has_telegram_channel_link(msg):
                continue

            mentions = extract_ad_channels(msg.text) + extract_ad_channels_from_entities(msg) + extract_invite_links_from_entities(msg)
            for mnt in mentions:
                contact = 'не найден'
                try:
                    contact = await get_advertised_channel_contact(tg, str(mnt))
                except:
                    contact = 'не найден'
                adv_key = str(mnt)
                if adv_key in advertised_seen:
                    continue
                advertised_seen.add(adv_key)
                text = (
                    f"📺 {entity.title}\n"
                    f"📝 Пост: {build_post_link(entity, msg.id)}\n"
                    f"➡️ Рекламируется: " + (
                        'https://t.me/+' + str(mnt).split(':',1)[1]
                        if str(mnt).startswith('invite:')
                        else '@' + str(mnt)
                    ) + "\n"
                    f"👤 Контакт: {contact}"
                )
                results.append(text)
                db = load_ads_admins_db(m.from_user.id)
                post_link = build_post_link(entity, msg.id)
                if not any(x["post"] == post_link for x in db):
                    db.append({
                        "from_channel": entity.title,
                        "post": post_link,
                        "advertised": (
                            'https://t.me/+' + str(mnt).split(':',1)[1]
                            if str(mnt).startswith('invite:')
                            else '@' + str(mnt)
                        ),
                        "contact": contact
                    })
                    save_ads_admins_db(db, m.from_user.id)


    if not results:
        await m.answer("❌ Рекламных постов не найдено", reply_markup=kb_ads_folder())
        return

    for r in results[:10]:
        await m.answer(r)

    await m.answer("Готово", reply_markup=kb_ads_folder())

# ================== БД АДМИНЫ: ПРОСМОТР ==================
@dp.message(lambda m: m.text == "🗄 БД Админы")
async def ads_admins_db_view(m: Message):
    db = load_ads_admins_db(m.from_user.id)
    if not db:
        await m.answer("❌ БД пуста", reply_markup=kb_ads_folder())
        return

    text = "🗄 БД Админы:\n\n"
    for i, row in enumerate(db, 1):
        text += (
            f"{i}.\n"
            f"📺 {row['from_channel']}\n"
            f"📝 {row['post']}\n"
            f"➡️ {row['advertised']}\n"
            f"👤 {row['contact']}\n\n"
        )

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗑 Удалить последний")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )
    await m.answer(text, reply_markup=kb)

@dp.message(lambda m: m.text == "🗑 Удалить последний")
async def ads_admins_db_delete_last(m: Message):
    db = load_ads_admins_db(m.from_user.id)
    if not db:
        await m.answer("❌ БД уже пуста", reply_markup=kb_ads_folder())
        return
    db.pop()
    save_ads_admins_db(db, m.from_user.id)
    await m.answer("🗑 Последняя запись удалена", reply_markup=kb_ads_folder())
# ================== КОНЕЦ БД АДМИНЫ ==================




# ================== ADMIN PANEL ==================

ADMIN_PASSWORD = "123"

def kb_admin():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔑 Создать ключ")],
            [KeyboardButton(text="📋 Все ключи")],
            [KeyboardButton(text="Шаблон 3")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

@dp.message(lambda m: m.text and m.text.strip() == "/admin")
async def admin_start(m: Message):
    state[m.from_user.id] = "admin_password"
    await m.answer("🔐 Введите пароль администратора")

@dp.message(lambda m: state.get(m.from_user.id) == "admin_password")
async def admin_password(m: Message):
    if m.text != ADMIN_PASSWORD:
        await m.answer("❌ Неверный пароль")
        return
    state.pop(m.from_user.id, None)
    await m.answer("✅ Админ-панель", reply_markup=kb_admin())

@dp.message(lambda m: m.text == "🔑 Создать ключ")
async def admin_create_key_start(m: Message):
    state[m.from_user.id] = "wait_key_time"
    await m.answer("⏱ На какое время создать ключ?\nПримеры: 1ч, 2дня, 20мин")

@dp.message(lambda m: state.get(m.from_user.id) == "wait_key_time")
async def admin_create_key_finish(m: Message):
    seconds = parse_duration(m.text)
    if not seconds:
        await m.answer("❌ Не удалось распознать время. Пример: 1ч, 1день, 20мин")
        return

    keys = load_keys()
    new_key = generate_key(16)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    keys.append({
        "key": new_key,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": expires_at
    })
    save_keys(keys)
    state.pop(m.from_user.id, None)
    await m.answer("🔑 Ключ создан:\n" + new_key + f"\n⏱ Действует до: {expires_at}", reply_markup=kb_admin())


@dp.message(lambda m: m.text == "📋 Все ключи")
async def admin_all_keys(m: Message):
    keys = load_keys()
    if not keys:
        await m.answer("🔑 Ключей пока нет", reply_markup=kb_admin())
        return

    lines = ["🔑 Все ключи:"]
    for k in keys:
        if "expires_at" in k and k["expires_at"]:
            msk_time = (
                datetime.fromisoformat(k["expires_at"]) + timedelta(hours=3)
            ).strftime("%d.%m.%Y %H:%M (МСК)")
            lines.append(f"{k['key']} — {msk_time} ({k.get('used_by', {}).get('name', 'не использован')} - @{k.get('used_by', {}).get('username', '—')})")
        else:
            lines.append(f"{k['key']} — без срока ({k.get('used_by', {}).get('name', 'не использован')} - @{k.get('used_by', {}).get('username', '—')})")

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗑 Удалить ключ")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )

    state[m.from_user.id] = "wait_delete_key"
    await m.answer("\n".join(lines), reply_markup=kb)

    await m.answer("\n".join(lines), reply_markup=kb)

@dp.message(lambda m: state.get(m.from_user.id) == "wait_delete_key")
async def admin_delete_key(m: Message):
    text = m.text.strip()
    keys = load_keys()

    if text == "🏠 Главная":
        state.pop(m.from_user.id, None)
        await m.answer("🏠 Главное меню", reply_markup=kb_admin())
        return

    # delete by index
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(keys):
            removed = keys.pop(idx)
            save_keys(keys)
            await m.answer(f"🗑 Ключ удалён:\n{removed['key']}", reply_markup=kb_admin())
            state.pop(m.from_user.id, None)
            return

    # delete by key value
    for k in keys:
        if k["key"] == text:
            keys.remove(k)
            save_keys(keys)
            await m.answer(f"🗑 Ключ удалён:\n{text}", reply_markup=kb_admin())
            state.pop(m.from_user.id, None)
            return

    await m.answer("❌ Ключ не найден. Введи номер или сам ключ.")

@dp.message(lambda m: m.text == "Шаблон 3")
async def admin_template_3(m: Message):
    await m.answer("📄 Выбран Шаблон 3", reply_markup=kb_admin())

# ================== END ADMIN PANEL ==================


@dp.message(lambda m: m.text and m.text.strip() == "/key")
async def key_start(m: Message):
    state[m.from_user.id] = "wait_key_input"
    await m.answer("🔑 Введите ключ")


@dp.message(lambda m: state.get(m.from_user.id) == "wait_key_input")
async def key_check(m: Message):
    key_value = m.text.strip()
    keys = load_keys()

    for k in keys:
        if k["key"] == key_value:
            # ❌ key already used
            if k.get("used_by"):
                await safe_answer(m, "❌ Этот ключ уже используется другим пользователем")
                state.pop(m.from_user.id, None)
                return

            if "expires_at" in k and k["expires_at"]:
                if datetime.now(timezone.utc) > datetime.fromisoformat(k["expires_at"]):
                    await safe_answer(m, "❌ Срок действия ключа истёк")
                    state.pop(m.from_user.id, None)
                    return

            # SAVE WHO USED THE KEY
            k["used_by"] = {
                "id": m.from_user.id,
                "name": m.from_user.full_name,
                "username": m.from_user.username
            }
            save_keys(keys)

            # GRANT ACCESS
            set_verified(m.from_user.id, k.get("expires_at"))
            if k.get("expires_at"):
                msk_time = (
                    datetime.fromisoformat(k["expires_at"]) + timedelta(hours=3)
                ).strftime("%d.%m.%Y %H:%M (МСК)")
                await m.answer(f"✅ Ключ принят\n⏱ Действует до: {msk_time}")
            else:
                await m.answer("✅ Ключ принят\n⏱ Без ограничения по времени")

            state.pop(m.from_user.id, None)
            return

    await m.answer("❌ Ключ неверный")
    state.pop(m.from_user.id, None)


@dp.message()
async def handler(m: Message):
    uid = m.from_user.id
    text = m.text.strip()

    # ---- Главная ----
    if text == "🏠 Главная":
        state.clear()
        temp.clear()
        await m.answer("🏠 Главное меню", reply_markup=kb_main())
        return

    # ---- Анализ канала ----
    if text == "📊 Анализ канала":
        if not await require_active_key(m):
            return
        if not is_verified(uid):
            await m.answer("🔐 У вас нет активного доступа. Введите ключ через /key")
            return
        state[uid] = "wait_channel"
        await m.answer("🔎 Пришли @, ссылку или название канала")
        return

    if state.get(uid) == "wait_channel":
        username = extract_username(text)
        entity = await tg.get_entity(username) if username else await find_channel_by_name(text)
        full = await tg(GetFullChannelRequest(entity))

        subs = full.full_chat.participants_count or 0
        avg_views, posts_per_day, stability = await analyze_channel_stats(entity)
        growth = estimate_growth(subs)

        temp[uid] = {"entity": entity}
        state[uid] = "after_analysis"

        text_out = (
            f"👥 Подписчики: {subs:,}\n"
            f"📈 Прирост:\n"
            f"• 1 день: ~{growth['1d']}\n"
            f"• 7 дней: ~{growth['7d']}\n"
            f"• 30 дней: ~{growth['30d']}\n\n"
            f"👀 Просмотры / пост (24ч): ~{avg_views:,}\n"
            f"🕒 Частота постинга: {posts_per_day} пост/сутки\n"
            f"📊 Стабильность просмотров: {stability}%\n"
            f"👥 Пол аудитории: {estimate_gender()}\n"
            f"📞 Контакты для рекламы:\n{extract_ad_contacts(full.full_chat.about)}"
        )
        await m.answer(text_out, reply_markup=kb_after_analysis())
        return

    # ---- Анализ рекламы ----
    if text == "📢 Анализ рекламы" and state.get(uid) == "after_analysis":
        ads = await analyze_ads(temp[uid]["entity"])
        temp[uid]["ads"] = ads
        state[uid] = "ads_info"

        await m.answer(
            f"📢 Анализ рекламы\n\n"
            f"🕐 1 день: {len(ads['1d'])}\n"
            f"🕒 3 дня: {len(ads['3d'])}\n"
            f"🗓 7 дней: {len(ads['7d'])}",
            reply_markup=kb_ads_info()
        )
        return

    if text == "📄 Рекламные посты" and state.get(uid) == "ads_info":
        state[uid] = "ads_period"
        await m.answer("⏱ Выбери период", reply_markup=kb_ads_period())
        return

    if state.get(uid) == "ads_period" and text in ["1 день", "3 дня", "7 дней"]:
        key = "1d" if text == "1 день" else "3d" if text == "3 дня" else "7d"
        for ad in temp[uid]["ads"][key]:
            hours = int((datetime.now(timezone.utc) - ad["date"]).total_seconds() // 3600)
            await m.answer(
                f"📢 Рекламный пост\n"
                f"👀 {ad['views']:,}\n"
                f"⏱ {hours} ч назад\n"
                f"🔗 {ad['link']}"
            )
        return

    
    if state.get(uid) == "add_channel_link":
        username = extract_username(text)
        entity = await tg.get_entity(username) if username else await find_channel_by_name(text)
        full = await tg(GetFullChannelRequest(entity))

        temp[uid].update({
            "title": entity.title,
            "username": entity.username,
            "subscribers": full.full_chat.participants_count or 0
        })
        state[uid] = "add_channel_theme"
        await m.answer("📁 Введи тематику")
        return

    if state.get(uid) == "add_channel_theme":
        temp[uid]["theme"] = text
        state[uid] = "field_price"
        await m.answer("💰 Цена")
        return

    FIELDS = ["price", "exclude", "payment", "extra", "time", "percent"]
    NAMES = {
        "price": "💰 Цена",
        "exclude": "🚫 Исключения",
        "payment": "💳 Оплата",
        "extra": "➕ Доп",
        "time": "⏱ Время",
        "percent": "📊 %"
    }

    if state.get(uid, "").startswith("field_"):
        field = state[uid].replace("field_", "")
        temp[uid][field] = text
        idx = FIELDS.index(field)

        if idx + 1 < len(FIELDS):
            state[uid] = f"field_{FIELDS[idx+1]}"
            await m.answer(NAMES[FIELDS[idx+1]])
            return

        data = load_data(uid)
        theme = temp[uid]["theme"]

        data.setdefault(theme, []).append({
            "title": temp[uid]["title"],
            "username": temp[uid]["username"],
            "subscribers": temp[uid]["subscribers"],
            "price": temp[uid]["price"],
            "exclude": temp[uid]["exclude"],
            "payment": temp[uid]["payment"],
            "extra": temp[uid]["extra"],
            "time": temp[uid]["time"],
            "percent": temp[uid]["percent"]
        })

        save_data(data, m.from_user.id)
        state.pop(uid, None)
        temp.pop(uid, None)
        await m.answer("✅ Канал добавлен", reply_markup=kb_main())
        return

    if text.startswith("📁 "):
        theme = text.replace("📁 ", "")
        await m.answer(f"📁 {theme}", reply_markup=kb_main())
        return

    if text.startswith("📺 "):
        title = text.replace("📺 ", "")
        data = load_data(uid)
        for theme, channels in data.items():
            for ch in channels:
                if ch["title"] == title:
                    temp[uid] = {"theme": theme, "channel": ch}
                    await m.answer(
                        f"👥 {ch['subscribers']:,}\n"
                        f"💰 {ch['price']}\n"
                        f"🚫 {ch['exclude']}\n"
                        f"💳 {ch['payment']}\n"
                        f"➕ {ch['extra']}\n"
                        f"⏱ {ch['time']}\n"
                        f"📊 {ch['percent']}",
                        reply_markup=kb_main()
                    )
                    return

    if text == "❌ Удалить канал":
        info = temp.get(uid)
        data = load_data(uid)
        theme = info["theme"]
        data[theme] = [c for c in data[theme] if c["title"] != info["channel"]["title"]]
        if not data[theme]:
            data.pop(theme)
        save_data(data, m.from_user.id)
        temp.pop(uid, None)
        await m.answer("🗑 Канал удалён", reply_markup=kb_main())
        return









async def require_active_key(m: Message) -> bool:
    users = load_verified_users()
    exp = users.get(str(m.from_user.id))

    if not exp:
        await m.answer("🔐 Введите ключ через /key", reply_markup=kb_main())
        return False

    if datetime.now(timezone.utc) >= datetime.fromisoformat(exp):
        users.pop(str(m.from_user.id), None)
        save_verified_users(users)
        await m.answer(
            "⏱ Срок действия ключа истёк.\n🔐 Введите новый ключ через /key",
            reply_markup=kb_main()
        )
        return False

    return True


# ================= KEY AUTO-EXPIRATION =================

async def keys_auto_cleaner():
    while True:
        try:
            keys = load_keys()
            users = load_verified_users()
            now = datetime.now(timezone.utc)

            new_keys = []
            expired_keys = set()

            for k in keys:
                exp = k.get("expires_at")
                if exp and now >= datetime.fromisoformat(exp):
                    expired_keys.add(k["key"])
                else:
                    new_keys.append(k)

            if len(new_keys) != len(keys):
                save_keys(new_keys)

            # revoke users whose key expired
            if expired_keys:
                for uid, exp in list(users.items()):
                    if exp and now >= datetime.fromisoformat(exp):
                        users.pop(uid, None)
                save_verified_users(users)

        except Exception:
            pass

        await asyncio.sleep(300)  # check every 5 minutes


# ================= KEY EXPIRATION NOTIFIER =================

async def notify_and_cleanup_keys():
    while True:
        try:
            keys = load_keys()
            users = load_verified_users()
            now = datetime.now(timezone.utc)

            updated_keys = []
            updated_users = dict(users)

            for k in keys:
                exp = k.get("expires_at")
                if exp and now >= datetime.fromisoformat(exp):
                    used = k.get("used_by")
                    if used and used.get("id"):
                        try:
                            await bot.send_message(
                                int(used["id"]),
                                "⏱ Срок действия вашего ключа истёк.\n🔐 Введите новый ключ через /key",
                                reply_markup=kb_main()
                            )
                        except Exception:
                            pass
                    # revoke access
                    if used and used.get("id"):
                        updated_users.pop(str(used["id"]), None)
                else:
                    updated_keys.append(k)

            if updated_keys != keys:
                save_keys(updated_keys)

            if updated_users != users:
                save_verified_users(updated_users)

        except Exception:
            pass

        await asyncio.sleep(300)  # every 5 minutes

# ================= MAIN =================

async def main():
    await tg.start()
    print("Telethon подключён")
    asyncio.create_task(keys_auto_cleaner())
    asyncio.create_task(notify_and_cleanup_keys())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


# ================== ПАПКА РЕКЛАМЫ (НОВАЯ ЛОГИКА) [ОТКЛЮЧЕНА] ==================
#

ADS_FOLDER_FILE = "ads_folder.json"

def load_ads_folder(uid=None):
    path = user_file(uid, ADS_FOLDER_FILE) if uid is not None else os.path.join(BASE_DIR, ADS_FOLDER_FILE)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_ads_folder(data, uid=None):
    path = user_file(uid, ADS_FOLDER_FILE) if uid is not None else os.path.join(BASE_DIR, ADS_FOLDER_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def kb_ads_folder():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить канал")],
            [KeyboardButton(text="📋 Список каналов")],
            [KeyboardButton(text="📢 Рекламные посты")],
            [KeyboardButton(text="🗄 БД Админы")],
            [KeyboardButton(text="🏠 Главная")]
        ],
        resize_keyboard=True
    )