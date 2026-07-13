"""Модуль для управления базой данных"""

import sqlite3
from contextlib import contextmanager

DB_NAME = "bookings.db" # имя базы данных

def get_db_connection():
    """Создает подключение к БД"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db():
    """Контекстный менеджер для работы с БД"""
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db() -> None:
    """
    Создаёт таблицы для хранения информации о комнатах и бронированиях.
    Если таблицы уже существуют, функция не сделает ничего и не вернёт ошибку.

    ## rooms
    Таблица, в которой хранится информация о всех комнатах Сириуса, а именно:

    **id** (`INTEGER`) - уникальный ID комнаты (первый ID - 1, второй - 2 и т.д.);

    **name** (`TEXT`) - название комнаты (например, "Переговорная комната №1");

    **capacity** (`INTEGER`) - вместимость комнаты в человеках;

    **equipment** (`TEXT`) - доступное оборудование в комнате. Должно перечисляться через запятую,
    без пробелов после них. Пример: `доска,проектор,конференц-связь`.

    ## bookings
    Таблица, в которой хранится информация о бронировании комнат, а именно:

    **id** (`INTEGER`) - уникальный ID брони (первый ID - 1, второй - 2 и т.д.);

    **room_id** (`INTEGER`) - ID забронированной комнаты;

    **start** (`INTEGER`) - UNIX-время начала сеанса (кол-во секунд от 01.01.1970);

    **end** (`INTEGER`) - UNIX-время конца сеанса;

    **username** (`TEXT`) - имя пользователя, забронировавшего комнату;

    **status** (`INTEGER`) - активно бронирование (`1`) или отменено (`0`).

    ## users
    Таблица для хранения пользователей и их паролей в виде хеша.
    Для хеширования используется bcrypt: он и не быстрый, и безопасный.

    **username** (`TEXT`) - имя пользователя;

    **password_hash** (`TEXT`) - захешированный пароль пользователя.
    """

    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    # Создаём таблицу rooms

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id >= 0),
    name TEXT,
    capacity INTEGER CHECK (capacity > 0),
    equipment TEXT
    );
    """)

    # Создаём таблицу bookings

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id >= 0),
    room_id INTEGER CHECK (room_id >= 0),
    start INTEGER CHECK (start >= 0),
    end INTEGER CHECK (end >= 0),
    username TEXT,
    status INTEGER CHECK (status == 0 OR status == 1)               
    );
    """)

    # Создаём таблицу users

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT
    );
    """)

init_db()