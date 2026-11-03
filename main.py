import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)

# --- SOZLAMALAR ---
API_TOKEN = '8810265819:AAF9wvFi4q_6-AECFEt3qEh73dT5ZXekcvA'
ADMIN_ID = 8761111637  # Sizning Admin ID'ingiz
BOT_USERNAME = "maktab_darslik_pdf_bot"

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR BAZASI (SQLITE) ---
conn = sqlite3.connect("bot_data.db")
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT DEFAULT '',
    genre TEXT,
    title TEXT,
    file_id TEXT DEFAULT '',
    audio_file_id TEXT DEFAULT '',
    downloads INTEGER DEFAULT 0
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS channels (
    channel_username TEXT PRIMARY KEY,
    channel_title TEXT DEFAULT 'Kanal'
)''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    full_name TEXT DEFAULT '',
    phone_number TEXT DEFAULT '',
    last_class TEXT DEFAULT '',
    referrer_id INTEGER DEFAULT 0,
    created_at TEXT DEFAULT ''
)''')

try:
    cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT DEFAULT ''")
    conn.commit()
except sqlite3.OperationalError:
    pass

cursor.execute('''
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    book_title TEXT,
    downloaded_at TEXT
)''')
conn.commit()

# --- 1-11 SINFLAR VA FANLAR RO'YXATI ---
EXACT_CLASS_BOOKS = {
    "1-sinf": ["Alifbe", "Matematika", "Ona tili", "O'qish kitobi", "Tasviriy san'at", "Musiqa", "Texnologiya", "Jismoniy tarbiya", "Tarbiya"],
    "2-sinf": ["Ona tili", "Matematika", "O'qish kitobi", "Rus tili", "Ingliz tili", "Tasviriy san'at", "Musiqa", "Texnologiya", "Jismoniy tarbiya", "Tarbiya"],
    "3-sinf": ["Ona tili", "Matematika", "O'qish kitobi", "Tabiatshunoslik", "Rus tili", "Ingliz tili", "Tasviriy san'at", "Musiqa", "Texnologiya", "Jismoniy tarbiya", "Tarbiya"],
    "4-sinf": ["Ona tili", "Matematika", "O'qish kitobi", "Tabiatshunoslik", "Tarixdan hikoyalar", "Rus tili", "Ingliz tili", "Tasviriy san'at", "Musiqa", "Texnologiya", "Jismoniy tarbiya", "Tarbiya"],
    "5-sinf": ["Ona tili", "Adabiyot 1-qism", "Adabiyot 2-qism", "Matematika", "Tarix", "Botanika", "Informatika", "Ingliz tili", "Rus tili", "Geografiya", "Tasviriy san'at", "Musiqa", "Texnologiya", "Jismoniy tarbiya", "Tarbiya"],
    "6-sinf": ["Adabiyot 1-qism", "Adabiyot 2-qism", "Matematika", "Qadimgi dunyo tarixi", "Botanika", "Fizika", "Geografiya", "Informatika", "Ingliz tili", "Ona tili", "Rus tili", "Tasviriy san'at", "Texnologiya", "Musiqa", "Jismoniy tarbiya", "Vatan tuyg'usi"],
    "7-sinf": ["Ona tili", "Adabiyot", "Algebra", "Geometriya", "Fizika", "Kimyo", "Biologiya (Zoologiya)", "O'zbekiston tarixi", "Jahon tarixi", "Geografiya", "Informatika", "Ingliz tili", "Rus tili", "Texnologiya", "Jismoniy tarbiya"],
    "8-sinf": ["Ona tili", "Adabiyot", "Algebra", "Geometriya", "Fizika", "Kimyo", "Biologiya (Inson)", "O'zbekiston tarixi", "Jahon tarixi", "Geografiya", "Informatika", "Ingliz tili", "Huquq asoslari", "Texnologiya"],
    "9-sinf": ["Ona tili", "Adabiyot", "Algebra", "Geometriya", "Fizika", "Kimyo", "Biologiya", "O'zbekiston tarixi", "Jahon tarixi", "Geografiya", "Informatika", "Ingliz tili", "Iqtisodiy bilim asoslari", "Huquq asoslari", "Boshlang'ich harbiy ta'lim"],
    "10-sinf": ["Ona tili", "Adabiyot", "Algebra", "Geometriya", "Fizika", "Kimyo", "Biologiya", "O'zbekiston tarixi", "Jahon tarixi", "Geografiya", "Informatika", "Ingliz tili", "Jamiyat tarixi va nazariyasi", "Chaqiruvga qadar boshlang'ich tayyorgarlik"],
    "11-sinf": ["Ona tili", "Adabiyot", "Algebra", "Geometriya", "Fizika", "Kimyo", "Biologiya", "O'zbekiston tarixi", "Jahon tarixi", "Informatika", "Ingliz tili", "Iqtisodiyot", "Dinshunoslik", "Hayotiy faoliyat xavfsizligi"]
}

for sinf, fanlar in EXACT_CLASS_BOOKS.items():
    for fan in fanlar:
        cursor.execute("SELECT id FROM books WHERE LOWER(genre) = LOWER(?) AND LOWER(title) = LOWER(?)", (sinf, fan))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO books (genre, title) VALUES (?, ?)", (sinf, fan))
conn.commit()

# --- HOLATLAR (STATES) ---
class SearchState(StatesGroup):
    waiting_for_query = State()

class AdminState(StatesGroup):
    waiting_for_channel = State()
    waiting_for_broadcast = State()
    waiting_for_book_file = State()

# --- MAJBURIY OBUNANI TEKSHIRISH ---
async def check_subscription(user_id: int) -> bool:
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    if not channels:
        return True
    
    for channel in channels:
        ch_username = channel[0]
        try:
            member = await bot.get_chat_member(chat_id=ch_username, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            pass
    return True

async def get_subscription_keyboard():
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    
    keyboard = []
    for ch in channels:
        ch_username = ch[0]
        clean_username = ch_username.replace("@", "")
        keyboard.append([InlineKeyboardButton(text=f"📢 {ch_username} kanaliga obuna bo'ling", url=f"https://t.me/{clean_username}")])
    
    keyboard.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- BOT MENYU BUYRUQLARI ---
async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="search", description="Darslik qidirish"),
        BotCommand(command="history", description="Yuklab olish tarixi"),
        BotCommand(command="profile", description="Mening profilim"),
        BotCommand(command="top", description="Reyting — eng faol foydalanuvchilar"),
        BotCommand(command="referral", description="Do'st taklif qilish")
    ]
    try:
        await bot.set_my_commands(commands)
    except Exception as e:
        print(f"Xatolik: {e}")

# --- TUGMALAR ---
def get_main_keyboard(user_id: int, last_class: str = ""):
    buttons = []
    if last_class:
        buttons.append([KeyboardButton(text=f"📚 {last_class}-sinf darsliklarim")])
    else:
        buttons.append([KeyboardButton(text="📚 1-sinf darsliklarim")])
    
    buttons.extend([
        [KeyboardButton(text="📚 Darsliklar"), KeyboardButton(text="🔍 Qidirish")],
        [KeyboardButton(text="🔥 Eng ko'p yuklangan")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="👥 Do'st taklif")]
    ])
    
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Admin Panel")])
        
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_classes_keyboard(prefix="class"):
    inline_kb = [
        [InlineKeyboardButton(text="1-sinf", callback_data=f"{prefix}_1"), InlineKeyboardButton(text="2-sinf", callback_data=f"{prefix}_2"), InlineKeyboardButton(text="3-sinf", callback_data=f"{prefix}_3")],
        [InlineKeyboardButton(text="4-sinf", callback_data=f"{prefix}_4"), InlineKeyboardButton(text="5-sinf", callback_data=f"{prefix}_5"), InlineKeyboardButton(text="6-sinf", callback_data=f"{prefix}_6")],
        [InlineKeyboardButton(text="7-sinf", callback_data=f"{prefix}_7"), InlineKeyboardButton(text="8-sinf", callback_data=f"{prefix}_8"), InlineKeyboardButton(text="9-sinf", callback_data=f"{prefix}_9")],
        [InlineKeyboardButton(text="10-sinf", callback_data=f"{prefix}_10"), InlineKeyboardButton(text="11-sinf", callback_data=f"{prefix}_11")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb)

def get_admin_keyboard():
    buttons = [
        [KeyboardButton(text="➕ Kitob Qo'shish"), KeyboardButton(text="📢 Reklama Yuborish")],
        [KeyboardButton(text="📢 Kanallarni Boshqarish"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🔙 Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- REYTING (/TOP) ---
@dp.message(Command("top"))
async def top_command(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
        return
    
    cursor.execute('''
        SELECT u.full_name, COUNT(h.id) as dl_count,
        (SELECT COUNT(*) FROM users ref WHERE ref.referrer_id = u.user_id) as ref_count
        FROM users u
        LEFT JOIN history h ON u.user_id = h.user_id
        GROUP BY u.user_id
        ORDER BY dl_count DESC
        LIMIT 10
    ''')
    top_downloaders = cursor.fetchall()

    cursor.execute('''
        SELECT u.full_name,
        (SELECT COUNT(*) FROM history h WHERE h.user_id = u.user_id) as dl_count,
        COUNT(ref.user_id) as ref_count
        FROM users u
        JOIN users ref ON ref.referrer_id = u.user_id
        GROUP BY u.user_id
        ORDER BY ref_count DESC
        LIMIT 5
    ''')
    top_referrers = cursor.fetchall()

    medals = ["🥇", "🥈", "🥉", "4.", "5.", "6.", "7.", "8.", "9.", "10."]

    dl_text = ""
    for idx, row in enumerate(top_downloaders):
        name = row[0] if row[0] else "Foydalanuvchi"
        dl = row[1]
        ref = row[2]
        dl_text += f"{medals[idx]} {name} — 📥 {dl} | 👥 {ref}\n"
    if not dl_text:
        dl_text = "<i>Hozircha yuklab olganlar yo'q.</i>\n"

    ref_text = ""
    for idx, row in enumerate(top_referrers):
        name = row[0] if row[0] else "Foydalanuvchi"
        dl = row[1]
        ref = row[2]
        ref_text += f"{medals[idx]} {name} — 📥 {dl} | 👥 {ref}\n"
    if not ref_text:
        ref_text = "<i>Hozircha do'st taklif qilganlar yo'q.</i>\n"

    response_text = (
        f"🏆 <b>Eng faol o'quvchilar</b>\n\n"
        f"{dl_text}\n"
        f"🏆 <b>Eng ko'p do'st taklif qilganlar</b>\n\n"
        f"{ref_text}"
    )
    await message.answer(response_text, parse_mode="HTML")

@dp.message(Command("help"))
async def help_command(message: types.Message):
    text = (
        "ℹ️ <b>Qanday foydalanish kerak?</b>\n\n"
        "1️⃣ /start — botni boshlash\n"
        "2️⃣ 📚 <b>Darsliklar</b> → sinf → fan → PDF yuklab olish\n\n"
        "🔍 /search — darslik qidirish\n"
        "🗣 /history — yuklab olish tarixi\n"
        "👤 /profile — profilingiz\n"
        "🏆 /top — eng faol o'quvchilar\n"
        "👥 /referral — do'st taklif qilish"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("search"))
@dp.message(F.text == "🔍 Qidirish")
async def search_command(message: types.Message, state: FSMContext):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
        return
        
    await state.set_state(SearchState.waiting_for_query)
    text = (
        "🔍 <b>Darslik qidirish</b>\n\n"
        "Fan nomini yozing, sinf bilan yozsangiz yanada aniq:\n"
        "<i>8 sinf tarix, fizika 7, algebra</i>\n\n"
        "Men mos darsliklarni topib beraman 👇"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("history"))
async def history_command(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
        return
        
    user_id = message.from_user.id
    cursor.execute("SELECT book_title, downloaded_at FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cursor.fetchall()
    
    if not rows:
        history_list = "<i>Hozircha darslik yuklab olmadingiz.</i>"
    else:
        history_list = "\n\n".join([f"📖 {r[0]}\n⏰ {r[1]}" for r in rows])
        
    text = (
        f"🗣 <b>Yuklab olish tarixi</b>\n\n"
        f"{history_list}\n\n"
        f"📚 Davom eting — barcha darsliklar bepul!"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("profile"))
@dp.message(F.text == "👤 Profil")
async def profile_command(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
        return
        
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    cursor.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,))
    dl_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT created_at FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    reg_date = row[0] if row and row[0] else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    text = (
        f"👤 <b>Mening profilim</b>\n\n"
        f"👋 Ism: <b>{full_name}</b>\n"
        f"📥 Yuklab olingan: <b>{dl_count} ta</b>\n"
        f"👥 Taklif qilgan: <b>{ref_count} ta</b>\n"
        f"📅 Ro'yxatdan o'tgan: <b>{reg_date}</b>\n\n"
        f"👇 Do'stlaringizni taklif qiling:"
    )
    
    share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}?start=ref_{user_id}&text=Botdan%20darsliklarni%20bepul%20yuklab%20oling!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Do'stlarga ulashish ↗️", url=share_url)],
        [InlineKeyboardButton(text="📋 Havolani nusxalash", callback_data=f"copy_ref_{user_id}")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(Command("referral"))
@dp.message(F.text == "👥 Do'st taklif")
async def referral_command(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
        return
        
    user_id = message.from_user.id
    
    cursor.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,))
    dl_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    ref_count = cursor.fetchone()[0]
    
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    text = (
        f"👥 <b>Do'stlarni taklif qiling!</b>\n\n"
        f"🔗 <b>Sizning taklif havolangiz:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 <b>Statistikangiz:</b>\n"
        f"📥 Yuklab olingan: <b>{dl_count} ta</b>\n"
        f"👥 Taklif qilgan: <b>{ref_count} ta</b>"
    )
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=Maktab%20darsliklarini%20bepul%20yuklab%20oling!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Do'stlarga ulashish ↗️", url=share_url)],
        [InlineKeyboardButton(text="📋 Havolani nusxalash", callback_data=f"copy_ref_{user_id}")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- ADMIN PANEL ---
@dp.message(F.text == "➕ Kitob Qo'shish")
async def add_book_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("➕ <b>Kitob qo'shish</b>\n\nQaysi sinfga kitob qo'shmoqchisiz? Sinfni tanlang:", reply_markup=get_classes_keyboard(prefix="addclass"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("addclass_"))
async def admin_select_class(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    class_num = callback.data.split("_")[1]
    book_class = f"{class_num}-sinf"
    await state.update_data(book_class=book_class)
    
    cursor.execute("SELECT id, title FROM books WHERE genre = ?", (book_class,))
    books = cursor.fetchall()
    
    inline_kb = []
    row = []
    for b_id, title in books:
        row.append(InlineKeyboardButton(text=f"📖 {title}", callback_data=f"addbook_{b_id}"))
        if len(row) == 2:
            inline_kb.append(row)
            row = []
    if row:
        inline_kb.append(row)
    inline_kb.append([InlineKeyboardButton(text="🔙 Sinflar", callback_data="admin_back_classes")])
    
    await callback.message.edit_text(
        f"🏫 Sinf: <b>{book_class}</b>\n\nKerakli fanni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "admin_back_classes")
async def admin_back_classes(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.edit_text("➕ <b>Kitob qo'shish</b>\n\nQaysi sinfga kitob qo'shmoqchisiz? Sinfni tanlang:", reply_markup=get_classes_keyboard(prefix="addclass"), parse_mode="HTML")

@dp.callback_query(F.data.startswith("addbook_"))
async def admin_select_book(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    book_id = callback.data.split("_")[1]
    await state.update_data(book_id=book_id)
    await state.set_state(AdminState.waiting_for_book_file)
    
    cursor.execute("SELECT genre, title FROM books WHERE id = ?", (book_id,))
    row = cursor.fetchone()
    if row:
        genre, title = row
        await callback.message.answer(f"✅ Tanlandi: <b>{genre} | {title}</b>\n\n📄 Endi ushbu kitobning **PDF faylini** yuboring:", parse_mode="HTML")

@dp.message(AdminState.waiting_for_book_file, F.document)
async def process_book_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    book_id = data.get('book_id')
    file_id = message.document.file_id
    
    cursor.execute("UPDATE books SET file_id = ? WHERE id = ?", (file_id, book_id))
    conn.commit()
    
    cursor.execute("SELECT genre, title FROM books WHERE id = ?", (book_id,))
    row = cursor.fetchone()
    genre, title = row if row else ("", "")
    
    await state.clear()
    await message.answer(f"✅ <b>Kitob muvaffaqiyatli saqlandi va bog'landi!</b>\n\n🏫 Sinf: <b>{genre}</b>\n📖 Fan: <b>{title}</b>\n\n🔑 <b>file_id:</b> <code>{file_id}</code>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📢 Reklama Yuborish")
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_broadcast)
    await message.answer("📢 Reklama xabarini/faylini yuboring:", parse_mode="HTML")

@dp.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    success, failed = 0, 0
    status_msg = await message.answer("⏳ Reklama yuborilmoqda...")
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await status_msg.edit_text(f"✅ <b>Reklama tarqatildi!</b>\n\n👥 Yetkazildi: <b>{success}</b> ta\n❌ Bloklagan: <b>{failed}</b> ta", parse_mode="HTML")

@dp.message(F.text == "📢 Kanallarni Boshqarish")
async def manage_channels(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    
    ch_list = "\n".join([f"• {ch[0]}" for ch in channels]) if channels else "<i>Hozircha kanallar qo'shilmagan.</i>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel_btn")],
        [InlineKeyboardButton(text="❌ Kanalni o'chirish", callback_data="del_channel_btn")]
    ])
    
    await message.answer(
        f"📢 <b>Majburiy obuna kanallari:</b>\n\n{ch_list}\n\nAmalni tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "add_channel_btn")
async def add_channel_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.waiting_for_channel)
    await callback.message.answer("📢 Yangi kanal username'ini yuboring (masalan: @maktab_darsliklari):", parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "del_channel_btn")
async def del_channel_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT channel_username FROM channels")
    channels = cursor.fetchall()
    if not channels:
        await callback.answer("O'chirish uchun kanallar mavjud emas!", show_alert=True)
        return
    
    kb = [[InlineKeyboardButton(text=f"🗑 {ch[0]} ni o'chirish", callback_data=f"remove_ch_{ch[0]}")] for ch in channels]
    kb.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_admin")])
    
    await callback.message.edit_text("O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("remove_ch_"))
async def remove_channel_action(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    ch_username = callback.data.replace("remove_ch_", "")
    cursor.execute("DELETE FROM channels WHERE channel_username = ?", (ch_username,))
    conn.commit()
    await callback.answer(f"✅ {ch_username} o'chirildi!", show_alert=True)
    await callback.message.edit_text(f"✅ Kanal bazadan olib tashlandi: <b>{ch_username}</b>", parse_mode="HTML")

@dp.message(AdminState.waiting_for_channel)
async def process_add_channel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    channel = message.text.strip()
    cursor.execute("INSERT OR REPLACE INTO channels (channel_username) VALUES (?)", (channel,))
    conn.commit()
    await state.clear()
    await message.answer(f"✅ Kanal muvaffaqiyatli saqlandi: <b>{channel}</b>\n\n<i>Eslatma: Botimiz ushbu kanalda ADMIN bo'lishi shart!</i>", parse_mode="HTML", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM books")
    book_count = cursor.fetchone()[0]
    await message.answer(f"📊 <b>Statistika:</b>\n\n👥 Foydalanuvchilar: <b>{user_count}</b>\n📚 Kitoblar: <b>{book_count}</b>", parse_mode="HTML")

# --- OBUNANI TEKSHIRISH CALLBACK ---
@dp.callback_query(F.data == "check_sub")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        cursor.execute("SELECT last_class FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        last_class = row[0] if row and row[0] else ""
        
        await callback.message.delete()
        await callback.message.answer(
            "✅ <b>Obuna tasdiqlandi!</b>\n\nEndi sinfni tanlang — darslik darhol yuboriladi ⚡️",
            reply_markup=get_main_keyboard(user_id, last_class),
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Siz hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

# --- ASOSIY XABARLAR (/START VA BOSHQA BUYRUQLAR) ---
@dp.message()
async def echo_all(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if message.text and message.text.startswith("/start"):
        ref_id = 0
        if "ref_" in message.text:
            try:
                ref_id = int(message.text.split("ref_")[1])
            except Exception:
                ref_id = 0
                
        reg_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, referrer_id, created_at) VALUES (?, ?, ?, ?)", 
                       (user_id, message.from_user.full_name, ref_id, reg_date))
        conn.commit()
        
        if not await check_subscription(user_id):
            sub_photo_id = "SHU_YERGA_RASMINGIZNING_FILE_ID_SINI_YOZING"
            sub_text = (
                "🔒 <b>BOTDAN FOYDALANISH — OBUNANGIZ KERAK</b>\n\n"
                "Obuna bo'ling — darslik bepul 📲\n\n"
                "<b>Darslikni olish uchun bir qadam:</b>\n"
                "1️⃣ <b>1–11 sinf</b> darsligini olishdan oldin ta'lim kanallariga obuna bo'ling — bot shu tufayli bepul ishlaydi 👤\n\n"
                "1️⃣ Kanallarga obuna bo'lish tugmasini bosing\n"
                "2️⃣ So'ng ✅ Obunani tekshirish ni bosing\n"
                "3️⃣ Darslik avtomatik keladi ⚡️"
            )
            try:
                await message.answer_photo(
                    photo=sub_photo_id,
                    caption=sub_text,
                    reply_markup=await get_subscription_keyboard(),
                    parse_mode="HTML"
                )
            except Exception:
                await message.answer(
                    sub_text,
                    reply_markup=await get_subscription_keyboard(),
                    parse_mode="HTML"
                )
            return

        cursor.execute("SELECT last_class FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        last_class = row[0] if row and row[0] else ""

        # Yuqorida yasab bergan rasmimizning file_id sini shu yerga yozasiz:
        photo_file_id = "SHU_YERGA_RASMINGIZNING_FILE_ID_SINI_YOZING"

        welcome_text = (
            "👋 <b>Xush kelibsiz!</b>\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "📚 <b>1–11 sinf barcha darsliklari — bepul, tez va telefoningizda!</b>\n\n"
            "🔍 Fan nomini yozsangiz ham bo'ladi: <i>8 sinf tarix</i>\n"
            "👇 Boshlash uchun 📚 <b>Darsliklar</b> tugmasini bosing\n\n"
            "🔗 <a href='https://t.me/maktab_darslik_pdf_bot'>@maktab_darslik_pdf_bot</a> · <i>O'qish yo'lingizdagi hamroh</i>"
        )

        try:
            await message.answer_photo(
                photo=photo_file_id,
                caption=welcome_text,
                reply_markup=get_main_keyboard(user_id, last_class),
                parse_mode="HTML"
            )
        except Exception:
            await message.answer(
                welcome_text,
                reply_markup=get_main_keyboard(user_id, last_class),
                parse_mode="HTML"
            )

    elif message.text == "📚 Darsliklar" or (message.text and "darsliklarim" in message.text):
        if not await check_subscription(user_id):
            await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
            return
        await message.answer("📚 <b>Qaysi sinfdasiz?</b>\n\nSinfni tanlang — barcha darsliklar ro'yxati chiqadi 👇", reply_markup=get_classes_keyboard(prefix="class"), parse_mode="HTML")
        
    elif message.text == "🔥 Eng ko'p yuklangan":
        if not await check_subscription(user_id):
            await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
            return
        cursor.execute("SELECT genre, title, downloads FROM books WHERE file_id != '' ORDER BY downloads DESC LIMIT 5")
        top_b = cursor.fetchall()
        t_text = "🔥 <b>Eng ko'p yuklangan darsliklar:</b>\n\n"
        for idx, b in enumerate(top_b, 1):
            t_text += f"{idx}. 📖 <b>{b[0]} | {b[1]}</b> — {b[2]} marta yuklangan\n"
        await message.answer(t_text, parse_mode="HTML")
        
    elif message.text == "⚙️ Admin Panel":
        if user_id != ADMIN_ID:
            return
        await message.answer("<b>⚙️ ADMIN BOSHQARUV PANELI</b>", reply_markup=get_admin_keyboard(), parse_mode="HTML")
        
    elif message.text == "🔙 Bosh menyu":
        await state.clear()
        cursor.execute("SELECT last_class FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        last_class = row[0] if row and row[0] else ""
        await message.answer("<b>🏠 Bosh menyu</b>", reply_markup=get_main_keyboard(user_id, last_class), parse_mode="HTML")
    else:
        current_state = await state.get_state()
        if current_state == SearchState.waiting_for_query.state:
            if not await check_subscription(user_id):
                await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=await get_subscription_keyboard())
                return
                
            query = message.text.strip()
            
            cursor.execute("SELECT id, title, genre FROM books WHERE (title LIKE ? OR genre LIKE ?) AND file_id != ''", (f"%{query}%", f"%{query}%"))
            books = cursor.fetchall()
            
            if not books:
                words = query.split()
                if words:
                    conditions = []
                    params = []
                    for word in words:
                        if len(word) > 1:
                            conditions.append("(title LIKE ? OR genre LIKE ?)")
                            params.extend([f"%{word}%", f"%{word}%"])
                    
                    if conditions:
                        sql = f"SELECT id, title, genre FROM books WHERE ({' OR '.join(conditions)}) AND file_id != '' LIMIT 10"
                        cursor.execute(sql, tuple(params))
                        books = cursor.fetchall()

            await state.clear()
            
            if not books:
                cursor.execute("SELECT id, title, genre FROM books WHERE file_id != '' LIMIT 10")
                books = cursor.fetchall()
                if books:
                    inline_kb = [[InlineKeyboardButton(text=f"📖 {g} | {t}", callback_data=f"getbook_{b_id}")] for b_id, t, g in books]
                    await message.answer("🔍 Siz kiritgan so'z bo'yicha aniq darslik topilmadi, lekin mana bu mavjud darsliklarni tanlashingiz mumkin:", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb))
                else:
                    await message.answer("🔍 Hozircha botga PDF darsliklar yuklanmagan.")
                return

            inline_kb = [[InlineKeyboardButton(text=f"📖 {g} | {t}", callback_data=f"getbook_{b_id}")] for b_id, t, g in books]
            await message.answer("🔍 <b>Topilgan darsliklar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb), parse_mode="HTML")

# --- INLINE TUGMALAR VA FANLARNI KO'RSATISH ---
@dp.callback_query(F.data.startswith("class_"))
async def show_class_books(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await check_subscription(user_id):
        await callback.answer("⚠️ Avval kanallarga obuna bo'ling!", show_alert=True)
        return
        
    class_num = callback.data.split("_")[1]
    cursor.execute("UPDATE users SET last_class = ? WHERE user_id = ?", (class_num, user_id))
    conn.commit()
    
    cursor.execute("SELECT id, title, file_id FROM books WHERE genre = ?", (f"{class_num}-sinf",))
    books = cursor.fetchall()
    
    if not books:
        await callback.answer("⚠️ Bu sinf uchun fanlar topilmadi!", show_alert=True)
        return

    inline_kb = []
    row = []
    for b_id, title, f_id in books:
        status_icon = "📖" if f_id else "⏳"
        row.append(InlineKeyboardButton(text=f"{status_icon} {title}", callback_data=f"getbook_{b_id}"))
        if len(row) == 2:
            inline_kb.append(row)
            row = []
    if row:
        inline_kb.append(row)
        
    inline_kb.append([InlineKeyboardButton(text="🔙 Sinflar", callback_data="back_to_classes")])
    
    await callback.message.edit_text(
        f"📖 <b>{class_num}-sinf darsliklari</b>\n\nKerakli fanni tanlang — (⏳ - hali PDF yuklanmagan, 📖 - tayyor):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_kb),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("getbook_"))
async def send_pdf_book(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if not await check_subscription(user_id):
        await callback.answer("⚠️ Darslikni olish uchun kanallarga obuna bo'lishingiz kerak!", show_alert=True)
        return
        
    book_id = callback.data.split("_")[1]
    cursor.execute("SELECT title, file_id, genre FROM books WHERE id = ?", (book_id,))
    row = cursor.fetchone()
    
    if row:
        title, file_id, genre = row
        
        if file_id:
            cursor.execute("UPDATE books SET downloads = downloads + 1 WHERE id = ?", (book_id,))
            now_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            cursor.execute("INSERT INTO history (user_id, book_title, downloaded_at) VALUES (?, ?, ?)", 
                           (user_id, f"{genre} | {title}", now_str))
            conn.commit()
            
            await callback.answer("📥 Darslik yuborilmoqda...")
            
            caption_text = (
                f"📚 <b>{genre} | {title}</b>\n\n"
                f"✅ <b>Yuklab oldingiz! Sinfdoshlarga ham ulashing — birga o'qish osonroq 📲</b>\n\n"
                f"🔄 <b>Boshqa darslik: @{BOT_USERNAME}</b>"
            )
            
            share_text = f"📚 {genre} {title} darsligini ushbu bot orqali yuklab oling!"
            share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME}&text={share_text}"
            
            file_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📖 Yana fan tanlash", callback_data="back_to_classes")],
                [InlineKeyboardButton(text="👥 Sinfdoshlarga ulashish ↗️", url=share_url)]
            ])
            
            await callback.message.answer_document(
                document=file_id,
                caption=caption_text,
                reply_markup=file_kb,
                parse_mode="HTML"
            )
        else:
            await callback.answer(f"⚠️ '{genre} - {title}' uchun hali PDF fayl yuklanmagan. Tez orada qo'shiladi!", show_alert=True)

@dp.callback_query(F.data.startswith("copy_ref_"))
async def copy_ref_callback(callback: types.CallbackQuery):
    await callback.answer("📋 Havola nusxalandi!", show_alert=True)

@dp.callback_query(F.data == "back_to_classes")
async def back_to_classes(callback: types.CallbackQuery):
    await callback.message.answer("📚 <b>Qaysi sinfdasiz?</b>", reply_markup=get_classes_keyboard(prefix="class"), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except Exception:
        pass
    user_id = callback.from_user.id
    cursor.execute("SELECT last_class FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    last_class = row[0] if row and row[0] else ""
    await callback.message.answer("<b>🏠 Bosh menyu</b>", reply_markup=get_main_keyboard(user_id, last_class), parse_mode="HTML")

# --- ISHGA TUSHIRISH ---
async def main():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Diqqat: Webhookni tozalashda xatolik yuz berdi: {e}")
        
    await set_bot_commands()
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
