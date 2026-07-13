from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

# 1. Создание пользователя

def create_user(username, password):
    response = client.post(
        "/account",
        params={"username": username, "password": password}
    )
    print(response.json())
    print()
    return response.status_code

assert create_user("alice", "123456") == 201
assert create_user("aLiCE", "qwerty") == 400

# 2. Создание комнаты

def create_room(name, capacity, equipment):
    response = client.post(
        "/rooms",
        json={"name": name, "capacity": capacity, "equipment": equipment}
    )

    print(response.json())
    print()
    return response.status_code

assert create_room(name="Комната №1", capacity=25, equipment=["доска", "прожектор"]) == 201
assert create_room(name="Комната №2", capacity=20, equipment=["доска", "прожектор", "конференц-связь"]) == 201

# 3. Создание брони

def create_booking(room_id, date, start_time, end_time, username, password):
    response = client.post(
        "/bookings",
        json={
            "room_id": room_id,
            "date": date,
            "start_time": start_time,
            "end_time": end_time,
            "username": username,
            "password": password
        }
    )

    print(response.json())
    print()
    return response.status_code

assert create_booking(
    room_id=1,
    date="2026-07-12",
    start_time="15:00",
    end_time="16:00",
    username="alice",
    password="123456"
) == 201 # здесь всё верно

assert create_booking(
    room_id=1,
    date="2026-07-12",
    start_time="10:00",
    end_time="12:00",
    username="alice",
    password="123456"
) == 201 # здесь тоже всё верно

assert create_booking(
    room_id=1,
    date="2026-07-12",
    start_time="13:30",
    end_time="15:30",
    username="alice",
    password="123456"
) == 409 # конфликт броней

assert create_booking(
    room_id=1,
    date="2026-07-12",
    start_time="18:00",
    end_time="19:00",
    username="bob",
    password="123456"
) == 404 # несуществующий пользователь

assert create_booking(
    room_id=1,
    date="2026-07-12",
    start_time="18:00",
    end_time="19:00",
    username="alice",
    password="123456qwerty"
) == 403 # некорректная аутентификация

# 4. Список доступных комнат

def get_available_rooms(date, start_time, end_time, capacity = 0):
    response = client.get(
        "/rooms/available",
        params={"date": date, "start_time": start_time, "end_time": end_time, "capacity": capacity}
    )

    print(response.json())
    print()
    return response.json()

rooms = get_available_rooms(
    date="2026-07-12",
    start_time="12:00",
    end_time="15:00"
)
assert len(rooms) == 2

# 5. Получение всех броней комнаты

def get_room_bookings(room_id, date, tz, inactive = False):
    response = client.get(
        f"/rooms/{room_id}/bookings",
        params={"room_id": room_id, "date": date, "tz": tz, "inactive": inactive}
    )

    print(response.json())
    print()
    return response.status_code

assert get_room_bookings(room_id=1, date="2026-07-12", tz=3) == 200

# 6. Удаление брони

def cancel_booking(booking_id, username, password):
    response = client.delete(
        f"/bookings/{booking_id}",
        params={"booking_id": booking_id, "username": username, "password": password}
    )

    print("No return")
    print()
    return response.status_code

assert cancel_booking(booking_id=1, username="alice", password="123456") == 204
assert cancel_booking(booking_id=3, username="alice", password="123456") == 404
assert cancel_booking(booking_id=2, username="alice", password="123456") == 204

# 7. Удаление комнат

def delete_room(room_id):
    response = client.delete(
        f"/rooms/{room_id}",
        params={"room_id": room_id}
    )

    print("No return")
    print()
    return response.status_code

assert delete_room(3) == 404
assert delete_room(2) == 204
assert delete_room(1) == 204
