import os
import random
import aiosqlite
from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
import asyncio
import re
from datetime import datetime, timedelta
router = Router()

# Загрузка токена бота из .env файла
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
dp.include_router(router)

# Определяем состояния
class Form(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_report = State()

# Определяем колоду карт с мастями
suits = ['♠', '♥', '♦', '♣']
ranks = [
    {'rank': '2', 'value': 2}, {'rank': '3', 'value': 3}, {'rank': '4', 'value': 4},
    {'rank': '5', 'value': 5}, {'rank': '6', 'value': 6}, {'rank': '7', 'value': 7},
    {'rank': '8', 'value': 8}, {'rank': '9', 'value': 9}, {'rank': '10', 'value': 10},
    {'rank': 'J', 'value': 10}, {'rank': 'Q', 'value': 10}, {'rank': 'K', 'value': 10},
    {'rank': 'A', 'value': 11}
]

# Создание и перемешивание колоды карт
def create_deck():
    deck = [{'rank': rank['rank'], 'value': rank['value'], 'suit': suit} for suit in suits for rank in ranks]
    random.shuffle(deck)
    return deck

# Подключение к базе данных
async def create_connection():
    return await aiosqlite.connect('bot_database.db')


# Создание таблицы пользователей
async def create_table():
    conn = await create_connection()
    async with conn.cursor() as cursor:
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                games INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                ties INTEGER DEFAULT 0,
                balance INTEGER DEFAULT 1000 -- Начальный баланс 1000 единиц
            )
        ''')
        await conn.commit()

create_table()

# Получение статистики пользователя
async def get_user_stats(user_id):
    conn = await create_connection()
    async with conn.cursor() as cursor:
        await cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'games': row[2],
                'wins': row[3],
                'losses': row[4],
                'ties': row[5],
                'username': row[1],
                'balance': row[6]  # Добавляем баланс
            }
    return {'games': 0, 'wins': 0, 'losses': 0, 'ties': 0, 'username': None, 'balance': 1000}


# Сохранение или обновление статистики пользователя
async def save_user_stats(user_id, stats):
    conn = await create_connection()
    async with conn.cursor() as cursor:
        await cursor.execute('''
            INSERT INTO users (id, username, games, wins, losses, ties, balance)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                games = excluded.games,
                wins = excluded.wins,
                losses = excluded.losses,
                ties = excluded.ties,
                balance = excluded.balance
        ''', (user_id, stats['username'], stats['games'], stats['wins'], stats['losses'], stats['ties'], stats['balance']))
        await conn.commit()

# Главное меню
def main_menu():
    buttons = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🎮 Играть", callback_data="play")],
        [InlineKeyboardButton(text="🏆 Топ", callback_data="top"),
         InlineKeyboardButton(text="📕 Правила игры", callback_data="rules")],
        [InlineKeyboardButton(text="✍  Сообщить о баге", callback_data="report")]  # Добавлена кнопка для отчета
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Меню игры
def blackjack_menu():
    buttons = [
        [InlineKeyboardButton(text="Взять карту", callback_data="hit"),
         InlineKeyboardButton(text="Остаться", callback_data="stand")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Функция для вывода состояния карт
def display_hand(hand, reveal=False):
    if reveal:
        return " ".join([f"{card['rank']}{card['suit']}" for card in hand])
    else:
        return f"{hand[0]['rank']}{hand[0]['suit']} ?"

# Подсчет очков
def calculate_score(hand):
    score = sum(card['value'] for card in hand)
    aces = sum(1 for card in hand if card['rank'] == 'A')
    while score > 21 and aces:
        score -= 10
        aces -= 1
    return score

# Создание текста и разметки для различных состояний
def profile_text(user_nickname, stats):
    return (
        f"👤 Профиль:\n\n"
        f"Никнейм: {user_nickname}\n"
        f"Игр сыграно: {stats['games']}\n"
        f"Побед: {stats['wins']}\n"
        f"Поражений: {stats['losses']}\n"
        f"Ничьих: {stats['ties']}\n"
    )

def top_text():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT username, games, wins FROM users WHERE username IS NOT NULL AND username != "None" ORDER BY wins DESC LIMIT 50')
    rows = cursor.fetchall()
    conn.close()

    top_list = "\n".join(
        [f"{idx + 1}. {row[0]} - Игр: {row[1]}, Побед: {row[2]}, G/W: {row[2] / row[1] if row[1] > 0 else 0:.2f}" for idx, row in enumerate(rows)]
    )
    return f"🏆 Глобальный рейтинг:\n\n{top_list}"

def rules_text():
    return (
        "📕 Правила игры Blackjack:\n\n"
        "1. Цель игры — набрать сумму карт близкую к 21, но не превышающую её.\n"
        "2. Карты с числом отображают свою номинальную стоимость, карты с лицами (J, Q, K) оцениваются в 10 очков, туз — в 11 очков, если это не перебор.\n"
        "3. Игрок может взять карту или остаться. Если сумма карт игрока превышает 21, он проигрывает.\n"
        "4. Если игрок остается, дилер добирает карты до 17 и больше. Если у дилера сумма карт превышает 21, игрок выигрывает.\n"
        "5. Побеждает тот, кто набрал сумму карт ближе к 21, чем противник."
    )

# Проверка сообщений на спам
def is_spam(text):
    # Простой пример фильтрации спама
    if len(text) > 2000:  # Ограничение длины сообщения
        return True
    if len(set(text)) / len(text) > 0.8:  # Проверка на повторяющиеся символы
        return True
    return False

@router.message(F.text)
async def handle_message(message: Message):
    if is_spam(message.text):
        try:
            await message.delete()
        except Exception as e:
            print(f"Не удалось удалить сообщение: {e}")
        await message.answer("Ваше сообщение содержит спам и было удалено❗.")

# Обработчик команды /start
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Добро пожаловать в игру Blackjack! Выберите действие.", reply_markup=main_menu())

@dp.callback_query(lambda call: call.data == "report")
async def report_handler(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Пожалуйста, опишите проблему, и я передам её администратору.")
    await state.set_state(Form.waiting_for_report)

@dp.message(Form.waiting_for_report)
async def process_report(message: Message, state: FSMContext):
    report_text = message.text.strip()

    if not report_text:
        await message.answer("Описание не может быть пустым❗. Пожалуйста, введите описание проблемы.")
        return

    # Отправка отчета администратору
    await bot.send_message(ADMIN_ID, f"❗Сообщение от пользователя (ID: {message.from_user.id}):\n\n{report_text}")

    await message.answer("Ваш отчет отправлен. Спасибо за помощь!")
    await state.clear()


# Обработка нажатий на кнопки
@dp.callback_query(lambda call: call.data in ["profile", "play", "top", "rules", "hit", "stand"])
async def callback_handler(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    deck = data.get("deck", create_deck())
    user_hand = data.get("user_hand", [])
    dealer_hand = data.get("dealer_hand", [])
    stats = get_user_stats(user_id)
    user_nickname = stats.get('username')

    message_text = ""
    reply_markup = None

    if call.data == "profile":
        if user_nickname is None:
            message_text = "Пожалуйста, введите ваш никнейм для отображения в списке Топ."
            await call.message.answer(message_text)
            await state.set_state(Form.waiting_for_nickname)
            return

        new_message_text = profile_text(user_nickname, stats)
        new_reply_markup = main_menu()

        # Проверка изменений перед редактированием
        if (call.message.text != new_message_text) or (call.message.reply_markup != new_reply_markup):
            try:
                await call.message.edit_text(new_message_text, reply_markup=new_reply_markup)
            except Exception as e:
                print(f"Error editing message: {e}")

    elif call.data == "play":
        # Начало новой игры, раздача карт
        user_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        # Проверка количества карт у игрока
        while len(user_hand) == 0 or calculate_score(user_hand) < 1:
            user_hand = [deck.pop(), deck.pop()]

        # Проверка на Blackjack (21) для игрока
        user_score = calculate_score(user_hand)
        if user_score == 21:
            stats['wins'] += 1
            message_text = (
                f"Ваши карты: {display_hand(user_hand, reveal=True)} (Очки: {user_score})\n"
                f"Карты дилера: {display_hand(dealer_hand, reveal=False)}\n"
                f"Поздравляем! Вы набрали Blackjack и автоматически выиграли! +🏆"
            )
            reply_markup = main_menu()
            stats['games'] += 1
            save_user_stats(user_id, stats)
            await state.clear()
            try:
                await call.message.edit_text(message_text, reply_markup=reply_markup)
            except Exception as e:
                print(f"Error editing message: {e}")
            return  # Завершаем обработку команды
        else:
            message_text = (
                f"Ваши карты: {display_hand(user_hand, reveal=True)} (Очки: {user_score})\n"
                f"Карты дилера: {display_hand(dealer_hand, reveal=False)}"
            )
            reply_markup = blackjack_menu()

            # Сохранение состояния игры
            await state.update_data(deck=deck, user_hand=user_hand, dealer_hand=dealer_hand)

            try:
                await call.message.answer(message_text, reply_markup=reply_markup)
            except Exception as e:
                print(f"Error sending message: {e}")


    elif call.data == "top":
        new_message_text = top_text()
        new_reply_markup = main_menu()
        # Проверка изменений перед редактированием
        if (call.message.text != new_message_text) or (call.message.reply_markup != new_reply_markup):
            try:
                await call.message.edit_text(new_message_text, reply_markup=new_reply_markup)
            except Exception as e:
                print(f"Error editing message: {e}")

    elif call.data == "rules":
        new_message_text = rules_text()
        new_reply_markup = main_menu()

        # Проверка изменений перед редактированием
        if (call.message.text != new_message_text) or (call.message.reply_markup != new_reply_markup):
            try:
                await call.message.edit_text(new_message_text, reply_markup=new_reply_markup)
            except Exception as e:
                print(f"Error editing message: {e}")

    elif call.data == "hit":
        # Игрок берет карту
        user_hand.append(deck.pop())
        user_score = calculate_score(user_hand)

        if user_score > 21:
            stats['losses'] += 1
            save_user_stats(user_id, stats)
            message_text = (
                f"Ваши карты: {display_hand(user_hand, reveal=True)} (Очки: {user_score})\n"
                f"Вы перебрали. Вы проиграли!"
            )
            reply_markup = main_menu()
        else:
            message_text = (
                f"Ваши карты: {display_hand(user_hand, reveal=True)} (Очки: {user_score})\n"
                f"Карты дилера: {display_hand(dealer_hand, reveal=False)}"
            )
            reply_markup = blackjack_menu()

        # Сохранение состояния игры
        await state.update_data(deck=deck, user_hand=user_hand, dealer_hand=dealer_hand)

        try:
            await call.message.edit_text(message_text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Error editing message: {e}")

    elif call.data == "stand":
        # Игрок завершает игру, дилер играет
        dealer_score = calculate_score(dealer_hand)  # Инициализация переменной

        while dealer_score < 17:
            dealer_hand.append(deck.pop())
            dealer_score = calculate_score(dealer_hand)

        user_score = calculate_score(user_hand)
        message_text = (
            f"Ваши карты: {display_hand(user_hand, reveal=True)} (Очки: {user_score})\n"
            f"Карты дилера: {display_hand(dealer_hand, reveal=True)} (Очки: {dealer_score})\n"
        )

        if dealer_score > 21 or user_score > dealer_score:
            stats['wins'] += 1
            message_text += "Вы выиграли! +🏆"
        elif user_score < dealer_score:
            stats['losses'] += 1
            message_text += "Вы проиграли!"
        else:
            stats['ties'] += 1
            message_text += "Ничья!"

        # Увеличиваем количество игр только после завершения
        stats['games'] += 1
        save_user_stats(user_id, stats)
        reply_markup = main_menu()

        # Очистка состояния игры
        await state.clear()

        try:
            await call.message.edit_text(message_text, reply_markup=reply_markup)
        except Exception as e:
            print(f"Error editing message: {e}")

# Обработка ввода никнейма
@dp.message(Form.waiting_for_nickname)
async def process_nickname(message: Message, state: FSMContext):
    user_id = message.from_user.id
    nickname = message.text.strip()

    if not nickname:
        await message.answer("Никнейм не может быть пустым. Пожалуйста, введите ваш никнейм.")
        return

    # Сохраняем никнейм в базе данных
    stats = get_user_stats(user_id)
    stats['username'] = nickname
    save_user_stats(user_id, stats)

    await message.answer(f"Ваш никнейм '{nickname}' успешно сохранен!")
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=main_menu())

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
