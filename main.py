"""Основная логика программы"""

import bcrypt
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from database import *
from datetime import datetime, timezone
from pydantic import BaseModel

# on_event() устарело, поэтому использую lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

# создаём приложение
app = FastAPI(
    title="Сириус.Аренда",
    description="Сервис для бронирования переговорных комнат",
    version="1.0.0",
    lifespan=lifespan
)

# Коды HTTP-статусов
OK = 200
CREATED = 201
NO_CONTENT = 204 # использовать при удалении
BAD_REQUEST = 400
FORBIDDEN = 403
NOT_FOUND = 404
CONFLICT = 409 # например, комната занята

# BaseModel'ы

class RoomCreate(BaseModel):
    name: str
    capacity: int
    equipment: list[str] = []

class BookingCreate(BaseModel):
    room_id: int
    date: str
    start_time: str
    end_time: str
    username: str
    password: str

# Работа с паролями

def hash_password(password: str) -> str:
    """Возвращает хеш пароля"""

    password_bytes = password.encode('utf-8')
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode('utf-8')

def verify_password(password: str, hash: str) -> bool:
    """Проверка пароля"""

    password_bytes = password.encode('utf-8')
    hashed_bytes = hash.encode('utf-8')
    
    return bcrypt.checkpw(password_bytes, hashed_bytes)

# Эндпоинты

@app.post("/rooms", status_code=CREATED)
def create_room(room: RoomCreate) -> dict:
    """
    Создаёт новую комнату.

    :param name: Имя комнаты.
    :param capacity: Вместимость в человеках.
    :param equipment: Оборудование в комнате.

    Returns:
        out: Данные новой комнаты. Пример:
        {"id": 1, "name": "Комната №1", "capacity": 25, "equipment": ["доска", "прожектор"]}
    """

    name = room.name
    capacity = room.capacity
    equipment = room.equipment

    if capacity <= 0:
        raise HTTPException(status_code=BAD_REQUEST,
                            detail="Вместимость комнаты не может быть 0 или меньше человек"
                            )
    
    equipment = ",".join(map(str, equipment))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rooms (name, capacity, equipment) VALUES (?, ?, ?)",  # ✅ правильно
            (name, capacity, equipment)
        )

        room_id = cursor.lastrowid
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))

        conn.commit()

        row = cursor.fetchone()
        room_info = dict(row)
        room_info["equipment"] = room_info["equipment"].split(",")

        return room_info

@app.get("/rooms", status_code=OK)
def get_rooms(capacity: int = 0, equipment: list[str] | None = None) -> list[dict]:
    """
    Возвращает список подходящих комнат (в том числе и занятых).

    :param capacity: **Минимальная** вместимость комнаты. `0`, если устроит любая вместимость.
        Если не указано, по умолчанию `0`.
    :param equipment: Оборудование, которое должно присутствовать в комнате.
        Если не указано, по умолчанию `[]`.

    Returns:
        out: Список доступных комнат с информацией о каждой комнате. Пример:
        [{"id": 1, "name": "Комната №1", "capacity": 25, "equipment": ["доска", "прожектор"]}]
    """

    if equipment is None:
        equipment = []

    if type(capacity) not in [int, float, str]:
        raise HTTPException(status_code=BAD_REQUEST, detail="Некорректный тип capacity")
    elif type(capacity) == str and not is_number(capacity):
        raise HTTPException(status_code=BAD_REQUEST, detial="capacity должно быть числом")
    
    if type(equipment) not in [list, str]:
        raise HTTPException(status_code=BAD_REQUEST, detail="Некорректный тип equipment")
    
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM ROOMS WHERE capacity >= ?"
        params = [capacity]

        for item in equipment:
            query += " AND equipment LIKE ?"
            params.append(f"%{item}%")
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        rooms_info = []

        for row in rows:
            rooms_info.append({
                "room_id": row["id"],
                "name": row["name"],
                "capacity": row["capacity"],
                "equipment": row["equipment"].split(",")
            })

        return rooms_info
    
@app.get("/rooms/available", status_code=OK)
def get_available_rooms(date: str, start_time: str, end_time: str, capacity: int = 0) -> list[dict]:
    """
    Возвращает список комнат, свободных в указанный интервал времени.

    :param date: Дата в формате YYYY-MM-DD.
    :param start_time: Начало временного интервала в формате HH-MM (UTC 0).
        Если бронь окончилась ровно в `start_time`, она не покажется в списке.
    :param end_time: Окончание временного интервала в том же формате.
        Если бронь началась ровно в `end_time`, она не покажется в списке.
    :param capacity: Минимальная вместимость (по умолчанию 0).
    
    Returns:
        out: Список комнат, которые свободны в указанное время. Пример:
        [{"id": 1,
          "name": "Комната №1",
          "capacity": 25,
          "equipment": ["доска", "прожектор"]
        }]
    """

    try:
        start_dt = datetime.strptime(f"{date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M")
        start = int(start_dt.timestamp())
        end = int(end_dt.timestamp())
    except ValueError:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Неверный формат даты/времени. Используйте YYYY-MM-DD и HH:MM"
        )

    if start >= end:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Время начала должно быть строго раньше времени окончания"
        )

    with get_db() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM rooms WHERE capacity >= ?"
        cursor.execute(query, (capacity,))
        rooms = cursor.fetchall()

        available = []
        for room in rooms:
            conflict = is_room_free(conn, room["id"], start, end)
            if not conflict:
                room_info = dict(room)
                room_info["equipment"] = room_info["equipment"].split(",") if room_info["equipment"] else []
                available.append(room_info)

        return available

@app.get("/rooms/{room_id}", status_code=OK)
def get_room_by_id(room_id: int) -> dict:
    """
    Возвращает всю информацию о конкретной комнате.

    :param room_id: ID комнаты.

    Returns:
        out: Словарь со всей информацией о комнате. Пример:
        ```
        {"id": 1, "name": "Комната №1", "capacity": 25, "equipment": ["доска", "прожектор"]}
        ```
    """

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=NOT_FOUND, detail="Комната не найдена")
        
        room_info = dict(row)
        room_info["equipment"] = room_info["equipment"].split(",")

        return room_info
    
@app.put("/rooms/{room_id}", status_code=OK)
def update_room(room_id: str, **kwargs) -> dict:
    """
    Изменяет данные о комнате.

    :param room_id: ID комнаты.
    :param **kwargs: Какие данные следует изменить и на какие. ID неизменяемый, его изменение
    приведёт к ошибке. Пример:
        
    ```{"name": "Конференц-зал №1", # была Комната №1
        "capacity": 35, # было 25, принесли ещё 10 стульев
        "equipment": ["доска", "прожектор", "конференц-связь"] # хоть доска и прожектор уже были, их всё равно надо указать
        }
    ```

    Returns:
        out: Новые данные комнаты. Пример:
        {"id": 1, "name": "Комната №1", "capacity": 35, "equipment": ["доска", "прожектор", "конференц-связь"]}
    """

    if "room_id" in kwargs.keys():
        raise HTTPException(status_code=BAD_REQUEST, detail="Вы не можете изменить ID комнаты")
    
    if "equipment" in kwargs.keys():
        kwargs["equipment"] = ",".join(kwargs["equipment"])

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=NOT_FOUND, detail="Комната не найдена")
        
        conn.commit()
        
        query = "UPDATE rooms SET"
        params = []

        for kwarg in kwargs.items():
            query += f" {kwarg[0]} = ?,"
            params.append(kwarg[1])
        
        query = query[:-1] # убрал лишнюю запятую в конце
        query += "WHERE id = ?"
        params.append(room_id)

        cursor.execute(query, params)
        conn.commit()

        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        row = cursor.fetchone()
        room_info = dict(row)
        room_info["equipment"] = room_info["equipment"].split(",")

        return room_info

@app.delete("/rooms/{room_id}", status_code=NO_CONTENT)
def delete_room(room_id: str) -> None:
    """
    Удаляет комнату, и все брони на неё становятся неактивными (не удаляются!).

    :param room_id: ID комнаты.
    """

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=NOT_FOUND, detail="Комната не найдена")
        conn.commit()

        cursor.execute(
            "UPDATE bookings SET status = 0 WHERE room_id = ?",
            (room_id,)
        )

    return None

def is_room_free(conn, room_id: int, start: str, end: str) -> int | None:
    """
    Проверяет, свободна ли комната в указанный интервал.
    Возвращает ID конфликтующей брони или None.
    """
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id FROM bookings 
        WHERE room_id = ? 
        AND status = 1
        AND start < ? 
        AND end > ?
    ''', (room_id, end, start))
    row = cursor.fetchone()

    return row['id'] if row else None
    
@app.post("/bookings", status_code=CREATED)
def create_booking(booking: BookingCreate) -> dict:
    """
    Создаёт новую бронь.

    :param room_id: ID комнаты.
    :param date: Дата в формате YYYY-MM-DD (например, 2026-07-11).
    :param start_time: Время начала в формате HH:MM (UTC 0) (например, 15:00, т.е. 18:00 мск).
    :param end_time: Время окончания в формате HH:MM (UTC 0) (например, 16:00, т.е. 19:00 мск).
    :param username: Имя пользователя.
    :param password: Пароль пользователя.

    Returns:
        out: Информация о брони. Пример:
        {"id": 1, # ID самой брони
         "room_id": 1, # ID забронированной комнаты
         "start": 1767225600, # здесь уже UNIX-время!
         "end": 1767232800,
         "username": "bob" # кто забронировал комнату
         "status": 1 # бронь активна
        }
    """

    room_id = booking.room_id
    date = booking.date
    start_time = booking.start_time
    end_time = booking.end_time
    username = booking.username
    password = booking.password

    try:
        start_dt = datetime.strptime(f"{date} {start_time}", r"%Y-%m-%d %H:%M")
        end_dt = datetime.strptime(f"{date} {end_time}", r"%Y-%m-%d %H:%M")
        
        start = int(start_dt.replace(tzinfo=timezone.utc).timestamp())
        end = int(end_dt.replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Неверный формат даты/времени. Используйте YYYY-MM-DD и HH:MM"
        )

    if start >= end:
        raise HTTPException(
            status_code=BAD_REQUEST,
            detail="Время начала должно быть строго раньше времени окончания"
        )

    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM rooms WHERE id = ?", (room_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=NOT_FOUND, detail="Комната не найдена")

        conflict_id = is_room_free(conn, room_id, start, end)
        if conflict_id:
            raise HTTPException(
                status_code=CONFLICT,
                detail=f"Комната уже занята в это время. Конфликт с бронью #{conflict_id}"
            )

        user = cursor.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=NOT_FOUND, detail="Пользователь не найден")

        if not verify_password(password, user["password_hash"]):
            raise HTTPException(status_code=FORBIDDEN, detail="Неверный пароль")

        cursor.execute(
            "INSERT INTO bookings (room_id, start, end, username, status) VALUES (?, ?, ?, ?, 1)",
            (room_id, start, end, username)
        )
        conn.commit()

        cursor.execute("SELECT * FROM bookings WHERE id = last_insert_rowid()")
        row = cursor.fetchone()
        booking = dict(row)
        return booking

@app.delete("/bookings/{booking_id}", status_code=NO_CONTENT)    
def cancel_booking(booking_id: int, username: str, password: str) -> None:
    """
    Отменяет (не удаляет!) конкретную бронь.

    :param booking_id: ID брони
    :param username: Имя пользователя, забронировавшего комнату
    :param password: Пароль пользователя, забронировавшего комнату    
    """

    with get_db() as conn:
        cursor = conn.cursor()

        user = cursor.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

        if not user:
            raise HTTPException(status_code=NOT_FOUND, detail="Пользователь не найден")

        real_hash = user["password_hash"]

        if not verify_password(password, real_hash):
            raise HTTPException(status_code=FORBIDDEN, detail="Неверный пароль")

        cursor.execute(
            "UPDATE bookings SET status = 0 WHERE id = ? and status = 1",
            (booking_id,)
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=NOT_FOUND,
                detail="Брони не существует, либо она уже была отменена"
            )
        
        conn.commit()

    return None


@app.get("/rooms/{room_id}/bookings", status_code=OK)
def get_room_bookings(room_id: int, date: str, tz: int = 0, inactive: bool = False) -> list[dict]:
    """
    Возвращает список бронирований для конкретной комнаты на выбранную дату.
    Возвратятся и те бронировки, которые начались в этот день и закончились на следующий и позже.

    :param room_id: ID комнаты
    :param date: Желаемая дата в формате YYYY-MM-DD. Часы, минуты и секунды не нужны.
    :param tz: Часовой пояс (например, Москва живёт по UTC +3 -> timezone = 3).
        Покажутся бронирования от 0:00 до 23:59 именно по этому часовому поясу.
        0 по умолчанию (т.е. UTC 0).
    :param inactive: Включать ли неактивные бронирования в список. False по умолчанию.

    Returns:
        out: Список бронирований с информацией о каждом из них. Пример:
        [{"id": 0, # ID самой брони
          "room_id": 0, # ID забронированной комнаты
          "start": 1767225600, # UNIX-время начала брони (кол-во секунд от 01.01.1970)
          "end": 1767232800, # UNIX-время окончания брони
          "username": "bob", # кто забронировал комнату
          "status": 1 # бронь активна, 0, если неактивна
        }]
    """

    SECONDS_IN_DAY = 86400
    try:
        dt = datetime.strptime(date, r"%Y-%m-%d").replace(tzinfo=timezone.utc)
        start_of_day = int(dt.timestamp()) - 3600 * tz
        end_of_day = start_of_day + SECONDS_IN_DAY - 1
    except:
        raise HTTPException(status_code=BAD_REQUEST, detail="Некорретный формат даты. Используйте YYYY-MM-DD")
    
    with get_db() as conn:
        cursor = conn.cursor()

        if inactive:
            bookings = cursor.execute(
                "SELECT * FROM bookings WHERE (room_id = ? AND start >= ? AND start <= ?)",
                (room_id, start_of_day, end_of_day)
            )
        else:
            bookings = cursor.execute(
                "SELECT * FROM bookings WHERE (room_id = ? AND start >= ? AND start <= ? AND status = 1)",
                (room_id, start_of_day, end_of_day)
            )

            bookings_info = []

            for booking in bookings:
                bookings_info.append({
                    "id": booking["id"],
                    "room_id": booking["room_id"],
                    "start": booking["start"],
                    "end": booking["end"],
                    "username": booking["username"],
                    "status": booking["status"]
                })

            return bookings_info

@app.post("/account", status_code=CREATED)
def register(username: str, password: str) -> None:
    """
    Создаёт новый аккаунт на Сириус.Аренде.

    :param username: Имя пользователя. Обязано быть уникальным.
    :param password: Пароль пользователя.

    Из соображений безопасности функция возвращает `None`, а не данные о новом пользователе.
    """

    with get_db() as conn:
        cursor = conn.cursor()

        conflict = cursor.execute(
            "SELECT username FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if conflict:
            raise HTTPException(status_code=BAD_REQUEST, detail="Такой пользователь уже существует")
        
        password_hash = hash_password(password)

        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash)
        )

        conn.commit()

    return None