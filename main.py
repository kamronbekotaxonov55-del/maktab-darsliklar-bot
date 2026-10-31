import asyncio
import logging
import os
import sqlite3
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# --- SOZLAMALAR ---
TOKEN = "8810265819:AAhTL6C3Jn6W0ccoVa8FY_ya-6MV12lTdZ0"
ADMIN_ID = 8761111637  # Sizning Telegram ID raqamingiz

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- BAZA BILAN ISHLASH (SQLite) ---
def db_connect():
    conn = sqlite3.connect("bot_database.db")
    return conn

def init_db():
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- FSM (Holatlar) ---
class AddBookState(StatesGroup):
    waiting_for_title = State()
    waiting_for_file = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class DeleteBookState(StatesGroup):
    waiting_for_id = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    buttons = [
        [KeyboardButton(text="📚 Darsliklar ro'yxati"), KeyboardButton(text="ℹ️ Bot haqida")]
    ]
    if user_id == ADMIN_ID:
        buttons.append([KeyboardButton(text="⚙️ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_menu():
    buttons = [
        [KeyboardButton(text="➕ Kitob qo'shish"), KeyboardButton(text="🗑 Kitobni o'chirish")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
        [KeyboardButton(text="🔙 Asosiy menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- START VA ASOSiy BUYRUQLAR ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    await message.answer(
        f"Assalomu alaykum, {message.from_user.first_name}!\n"
        "Maktab darsliklarini PDF formatida yuklab olish uchun mo'ljallangan botga xush kelibsiz. 📚",
        reply_markup=main_menu(user_id)
    )

@dp.message(F.text == "ℹ️ Bot haqida")
async def about_bot(message: types.Message):
    await message.answer("Ushbu bot maktab o'quvchilari uchun barcha darsliklarni PDF formatida taqdim etadi.")

@dp.message(F.text == "🔙 Asosiy menyu")
async def back_to_main(message: types.Message):
    await message.answer("Asosiy menyu:", reply_markup=main_menu(message.from_user.id))

# --- DARSLIKLAR RO'YXATI ---
@dp.message(F.text == "📚 Darsliklar ro'yxati")
async def list_books(message: types.Message):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, file_id FROM books")
    books = cursor.fetchall()
    conn.close()

    if not books:
        await message.answer("Hozircha botga darsliklar qo'shilmagan.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=book[1], callback_data=f"book_{book[0]}")] for book in books
    ])

    await message.answer("Mavjud darsliklarni tanlang:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("book_"))
async def send_book_pdf(callback: types.CallbackQuery):
    book_id = int(callback.data.split("_")[1])
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT title, file_id FROM books WHERE id = ?", (book_id,))
    book = cursor.fetchone()
    conn.close()

    if book:
        await callback.message.answer_document(document=book[1], caption=f"📖 {book[0]}")
    else:
        await callback.answer("Kechirasiz, bu kitob topilmadi.", show_alert=True)
    await callback.answer()

# --- ADMIN PANEL ---
@dp.message(F.text == "⚙️ Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Admin panelga xush kelibsiz:", reply_markup=admin_menu())

@dp.message(F.text == "📊 Statistika")
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM books")
    book_count = cursor.fetchone()[0]
    conn.close()

    await message.answer(f"📊 **Bot statistikasi:**\n\n👤 Foydalanuvchilar soni: {user_count}\n📚 Darsliklar soni: {book_count}")

# --- KITOB QO'SHISH (FSM) ---
@dp.message(F.text == "➕ Kitob qo'shish")
async def add_book_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Kitob nomini kiriting (masalan: *5-sinf Matematika*):")
    await state.set_state(AddBookState.waiting_for_title)

@dp.message(AddBookState.waiting_for_title)
async def process_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Endi ushbu kitobning **PDF faylini** yuboring:")
    await state.set_state(AddBookState.waiting_for_file)

@dp.message(AddBookState.waiting_for_file, F.document)
async def process_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    file_id = message.document.file_id

    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (title, file_id) VALUES (?, ?)", (title, file_id))
    conn.commit()
    conn.close()

    await message.answer(f"✅ Kitob muvaffaqiyatli qo'shildi!\nNomi: {title}", reply_markup=admin_menu())
    await state.clear()

# --- KITOBNI O'CHIRISH ---
@dp.message(F.text == "🗑 Kitobni o'chirish")
async def delete_book_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM books")
    books = cursor.fetchall()
    conn.close()

    if not books:
        await message.answer("O'chirish uchun kitoblar mavjud emas.")
        return

    text = "O'chirish uchun kitob ID raqamini yuboring:\n\n"
    for book in books:
        text += f"🆔 ID: {book[0]} — {book[1]}\n"

    await message.answer(text)
    await state.set_state(DeleteBookState.waiting_for_id)

@dp.message(DeleteBookState.waiting_for_id)
async def process_delete_book(message: types.Message, state: FSMContext):
    try:
        book_id = int(message.text)
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
        conn.commit()
        conn.close()

        await message.answer("✅ Kitob muvaffaqiyatli o'chirildi!", reply_markup=admin_menu())
    except ValueError:
        await message.answer("Iltimos, faqat raqam (ID) kiriting!")
    await state.clear()

# --- REKLAMA TARQATISH (Broadcast) ---
@dp.message(F.text == "📢 Reklama yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni (matn, rasm yoki video) yuboring:")
    await state.set_state(BroadcastState.waiting_for_message)

@dp.message(BroadcastState.waiting_for_message)
async def broadcast_process(message: types.Message, state: FSMContext):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    success = 0
    failed = 0

    await message.answer("⏳ Reklama yuborish boshlandi...")

    for user in users:
        try:
            await message.send_copy(chat_id=user[0])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await message.answer(f"✅ Reklama tarqatildi!\n\nMuvaffaqiyatli: {success}\nXatoliklar (bloklaganlar): {failed}", reply_markup=admin_menu())
    await state.clear()

# --- RENDER UCHUN VEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- MAIN FUNKSIYA ---
async def main():
    print("Bot ishga tushdi...")
    await asyncio.gather(
        dp.start_polling(bot),
        web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
