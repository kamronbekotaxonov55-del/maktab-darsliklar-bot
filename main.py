import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiohttp import web

# ==============================================================================
# 1. LOGGING VA ASOSIY SOZLAMALAR
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)

TOKEN = "8810265819:AAF9wvFi4q_6-AECFEt3qEh73dT5ZXekcvA"
ADMIN_ID = 8761111637  # Sizning Admin ID raqamingiz

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ==============================================================================
# 2. MA'LUMOTLAR BAZASI (HAKERLARDAN VA SQL-INJECTION'DAN HIMOYA)
# ==============================================================================
DB_NAME = "database.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            referrer_id INTEGER,
            reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_num TEXT,
            subject TEXT,
            file_id TEXT
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('required_channel', '')")
    
    conn.commit()
    conn.close()
    logger.info("Ma'lumotlar bazasi xavfsiz ishga tushirildi.")

init_db()

def get_required_channel() -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'required_channel'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

# ==============================================================================
# 3. ADMIN PANEL UCHUN FSM HOLATLARI
# ==============================================================================
class AdminStates(StatesGroup):
    waiting_for_channel = State()
    waiting_for_book_class = State()
    waiting_for_book_subject = State()
    waiting_for_book_file = State()

# ==============================================================================
# 4. DINAMIK MENYU VA TUGMALAR
# ==============================================================================

def get_user_favorite_class(user_id: int) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT file_name FROM history WHERE user_id = ? ORDER BY id DESC', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        for row in rows:
            fname = row[0]
            if "-sinf" in fname:
                parts = fname.split("-sinf")
                cls_num = ''.join(filter(str.isdigit, parts[0]))
                if cls_num:
                    return cls_num
    return "8"

def get_main_menu(user_id: int) -> ReplyKeyboardMarkup:
    fav_class = get_user_favorite_class(user_id)
    keyboard = [
        [KeyboardButton(text=f"📚 {fav_class}-sinf darsliklarim")],
        [KeyboardButton(text="📚 Darsliklar"), KeyboardButton(text="🔍 Qidirish")],
        [KeyboardButton(text="🔥 Eng ko'p yuklangan")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="👥 Do'st taklif")],
        [KeyboardButton(text="ℹ️ Ma'lumot")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="🛠️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_classes_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text=f"{i}-sinf", callback_data=f"class_{i}")] for i in range(1, 12)
    ]
    keyboard.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def check_subscription(user_id: int) -> bool:
    channel = get_required_channel()
    if not channel or channel.strip() == "":
        return True  
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
    except Exception:
        pass
    return False

# ==============================================================================
# 5. BOT HANDLERLARI
# ==============================================================================

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    username = message.from_user.username or ""

    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_val = int(args[1].replace("ref_", ""))
            if ref_val != user_id:
                referrer_id = ref_val
        except ValueError:
            pass

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, full_name, username, referrer_id) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username, referrer_id)
        )
        conn.commit()
    conn.close()

    text = (
        "👋 <b>Xush kelibsiz!</b>\n\n"
        "📚 <b>1-11-sinf</b> maktab darsliklari — bepul PDF, bir bosishda.\n\n"
        "🔍 Fan nomini yozsangiz ham bo'ladi: <i>8 sinf tarix</i>\n"
        "👇 Boshlash uchun 📚 <b>Darsliklar</b> tugmasini bosing"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_menu(user_id))
    await message.answer("<i>Infoedu.uz loyihasi · O'qish yo'lingizdagi hamroh</i>", parse_mode="HTML")

@dp.message(Command("help"))
@dp.message(F.text == "ℹ️ Ma'lumot")
async def help_cmd(message: types.Message):
    help_text = (
        "📌 <b>Bot haqida ma'lumot va yo'riqnoma</b>\n\n"
        "🤖 Bu bot 1-11-sinf o'quvchilari uchun barcha maktab darsliklarini PDF formatida bepul taqdim etadi.\n\n"
        "<b>Qanday foydalaniladi?</b>\n"
        "1️⃣ 📚 <b>Darsliklar</b> tugmasini bosing yoki o'zingizga kerakli sinfni tanlang.\n"
        "2️⃣ Kerakli fanni bosib, PDF kitobni darhol oling.\n"
        "3️⃣ 🔍 <b>Qidirish</b> orqali fan yoki sinf nomini yozib darhol topishingiz mumkin."
    )
    await message.answer(help_text, parse_mode="HTML")

# ==============================================================================
# 6. ADMIN PANEL
# ==============================================================================

@dp.message(F.text == "🛠️ Admin Panel")
async def admin_panel_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    current_channel = get_required_channel() or "O'rnatilmagan (Ochiq)"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM books")
    books_count = cursor.fetchone()[0]
    conn.close()

    text = (
        f"🛠️ <b>Admin Boshqaruv Paneli</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{users_count}</b> ta\n"
        f"📚 Bazadagi darsliklar: <b>{books_count}</b> ta\n"
        f"📢 Hozirgi majburiy kanal: <code>{current_channel}</code>\n\n"
        f"👇 Kerakli amalni tanlang:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Majburiy kanalni o'zgartirish", callback_data="admin_set_channel")],
        [InlineKeyboardButton(text="➕ Yangi kitob qo'shish", callback_data="admin_add_book")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats_cb(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    u = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM history")
    h = cursor.fetchone()[0]
    conn.close()
    await callback.answer(f"Statistika: {u} ta foydalanuvchi, {h} ta yuklab olish bajarildi.", show_alert=True)

@dp.callback_query(F.data == "admin_set_channel")
async def admin_set_channel_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("📢 Yangi majburiy kanal username'ini yuboring (Masalan: @kanal_nomi yoki bo'sh qilish uchun 'yo'q' deb yuboring):")
    await state.set_state(AdminStates.waiting_for_channel)
    await callback.answer()

@dp.message(AdminStates.waiting_for_channel)
async def save_channel_state(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    val = message.text.strip()
    if val.lower() in ["yo'q", "yoq", "none", "0", "bo'sh"]:
        val = ""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET value = ? WHERE key = 'required_channel'", (val,))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ Majburiy kanal yangilandi: <code>{val or 'O\'rnatilmagan'}</code>", parse_mode="HTML")

@dp.callback_query(F.data == "admin_add_book")
async def admin_add_book_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("📚 Kitob qo'shish uchun sinf raqamini yuboring (Masalan: 1):")
    await state.set_state(AdminStates.waiting_for_book_class)
    await callback.answer()

@dp.message(AdminStates.waiting_for_book_class)
async def book_class_state(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(class_num=message.text.strip())
    await message.answer("📖 Endi fan nomini yuboring (Masalan: Alifbe):")
    await state.set_state(AdminStates.waiting_for_book_subject)

@dp.message(AdminStates.waiting_for_book_subject)
async def book_subject_state(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(subject=message.text.strip())
    await message.answer("📄 Endi kitobning PDF faylini hujjat (Document) ko'rinishida tashlang:")
    await state.set_state(AdminStates.waiting_for_book_file)

@dp.message(AdminStates.waiting_for_book_file, F.document)
async def book_file_state(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    file_id = message.document.file_id
    data = await state.get_data()
    class_num = data.get("class_num")
    subject = data.get("subject")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (class_num, subject, file_id) VALUES (?, ?, ?)", (class_num, subject, file_id))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ {class_num}-sinf uchun <b>{subject}</b> darsligi bazaga muvaffaqiyatli saqlandi va o'zimizda saqlanib qoldi!", parse_mode="HTML")

# ==============================================================================
# 7. QIDIRUV VA MENYULAR
# ==============================================================================

@dp.message(F.text == "📚 Darsliklar")
async def darsliklar_menu(message: types.Message):
    text = "📚 <b>Qaysi sinfdasiz?</b>\n\nSinfni tanlang 👇"
    await message.answer(text, parse_mode="HTML", reply_markup=get_classes_keyboard())

@dp.message(F.text == "🔍 Qidirish")
async def search_menu(message: types.Message):
    text = "🔍 <b>Darslik qidirish</b>\n\nFan yoki sinf nomini yozing (masalan: <i>1 sinf Alifbe</i>):"
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text, ~F.text.startswith("/"))
async def handle_text_menus(message: types.Message):
    user_id = message.from_user.id
    text_val = message.text.strip()

    if "darsliklarim" in text_val.lower():
        fav_class = get_user_favorite_class(user_id)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT subject, file_id FROM books WHERE class_num = ?", (fav_class,))
        books = cursor.fetchall()
        conn.close()
        
        if not books:
            await message.answer(f"📖 {fav_class}-sinf uchun darsliklar topilmadi.", parse_mode="HTML")
            return
        
        keyboard = [[InlineKeyboardButton(text=f"📖 {subj}", callback_data=f"getbook_{fav_class}_{subj}")] for subj, _ in books]
        keyboard.append([InlineKeyboardButton(text="🔙 Sinf tanlash", callback_data="back_to_classes")])
        await message.answer(f"📖 <b>{fav_class}-sinf darsliklari:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        return

    if text_val in ["🛠️ Admin Panel", "ℹ️ Ma'lumot"]:
        return

    q_lower = text_val.lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT class_num, subject, file_id FROM books")
    all_books = cursor.fetchall()
    conn.close()

    results = []
    for cls, subj, f_id in all_books:
        if q_lower in subj.lower() or q_lower in f"{cls}-sinf" or q_lower in cls:
            results.append((cls, subj, f_id))

    results = results[:10]
    if not results:
        await message.answer(f"🔍 <b>\"{text_val}\"</b> bo'yicha darslik topilmadi.", parse_mode="HTML")
        return

    keyboard = [[InlineKeyboardButton(text=f"📖 {cls}-sinf | {subj}", callback_data=f"getbook_{cls}_{subj}")] for cls, subj, _ in results]
    keyboard.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_to_main")])
    await message.answer(f"🔍 <b>Natijalar ({len(results)} ta):</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

# ==============================================================================
# 8. CALLBACK TUGMALAR VA PDF YUBORISH (RASMDAGI FORMAT)
# ==============================================================================

@dp.callback_query(F.data.startswith("class_"))
async def class_cb(callback: types.CallbackQuery):
    class_num = callback.data.split("_")[1]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT subject FROM books WHERE class_num = ?", (class_num,))
    books = cursor.fetchall()
    conn.close()

    if not books:
        await callback.message.edit_text(f"📖 <b>{class_num}-sinf</b>\n\nHali darsliklar qo'shilmagan.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Sinflar", callback_data="back_to_classes")]]))
        await callback.answer()
        return

    keyboard = [[InlineKeyboardButton(text=f"📖 {subj[0]}", callback_data=f"getbook_{class_num}_{subj[0]}")] for subj in books]
    keyboard.append([InlineKeyboardButton(text="🔙 Sinflar", callback_data="back_to_classes")])
    
    await callback.message.edit_text(f"📖 <b>{class_num}-sinf darsliklari:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()

@dp.callback_query(F.data == "back_to_classes")
async def back_to_classes_cb(callback: types.CallbackQuery):
    await callback.message.edit_text("📚 <b>Qaysi sinfdasiz?</b>\n\nSinfni tanlang 👇", parse_mode="HTML", reply_markup=get_classes_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.delete()
    await callback.message.answer("🏠 <b>Bosh menyudasiz.</b>", parse_mode="HTML", reply_markup=get_main_menu(user_id))
    await callback.answer()

@dp.callback_query(F.data.startswith("getbook_"))
async def getbook_cb(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    parts = callback.data.split("_", 2)
    class_num = parts[1]
    subject = parts[2]

    is_sub = await check_subscription(user_id)
    if not is_sub:
        channel = get_required_channel()
        sub_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{channel.replace('@','')}")],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data=callback.data)]
        ])
        await callback.message.answer("🔒 Darslikni olish uchun kanalga obuna bo'ling!", reply_markup=sub_keyboard)
        await callback.answer("Obuna bo'lish shart!", show_alert=True)
        return

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_id FROM books WHERE class_num = ? AND subject = ?", (class_num, subject))
    row = cursor.fetchone()
    
    file_title = f"{class_num}-sinf · {subject}"
    cursor.execute("INSERT INTO history (user_id, file_name) VALUES (?, ?)", (user_id, file_title))
    conn.commit()
    conn.close()

    bot_info = await bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

    # RASMDAGI ANIQ FORMAT
    caption_text = (
        f"📚 <b>{file_title}</b>\n\n"
        f"🔄 Boshqa darsliklar: @{bot_username}\n"
        f"📖 Infoedu.uz — O'qish yo'lingizdagi hamroh"
    )

    book_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Yana fan tanlash", callback_data="back_to_classes")],
        [InlineKeyboardButton(text="👥 Sinfdoshlarga ulashish", url=f"https://t.me/share/url?url={ref_link}&text=Maktab+darsliklarini+bepul+yuklab+oling!")]
    ])

    if row and row[0]:
        await bot.send_document(
            chat_id=user_id, 
            document=row[0], 
            caption=caption_text, 
            parse_mode="HTML", 
            reply_markup=book_keyboard
        )
    else:
        await callback.message.answer(f"⚠️ {file_title} darsligi topilmadi.")
    await callback.answer()

# ==============================================================================
# 9. RENDER WEB-SERVER (24/7 ISHLASH)
# ==============================================================================

async def handle_ping(request):
    return web.Response(text="Bot is running safely 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Veb-server {port}-portda ishga tushdi.")

async def main():
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
