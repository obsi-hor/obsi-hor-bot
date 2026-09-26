#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import psycopg2
from psycopg2 import pool
from datetime import datetime, timezone, date

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Пул соединений (мин 1, макс 10 — не упрёмся в лимит Aiven)
db_pool = None
if DATABASE_URL:
    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, DATABASE_URL, sslmode="require")
        print("[+] Postgres pool создан")
    except Exception as e:
        print("[ERROR] pool: " + str(e))


def _get_conn():
    return db_pool.getconn()


def _put_conn(conn):
    db_pool.putconn(conn)


def _today():
    return date.today()


# ============ ЮЗЕРЫ ============
def get_user(user_id):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, first_name, requests_used, requests_date, mirror_last_bonus FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "username": row[1] or "",
            "first_name": row[2] or "",
            "requests_used": row[3] or 0,
            "requests_date": row[4],
            "mirror_last_bonus": row[5],
        }
    finally:
        _put_conn(conn)


def create_user(user_id, username, first_name):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
            (user_id, username or "", first_name or "")
        )
        conn.commit()
    finally:
        _put_conn(conn)


# ============ ЛИМИТЫ ============
def get_requests_left(user_id, daily_limit=20):
    u = get_user(user_id)
    if not u:
        return daily_limit
    today = _today()
    if u["requests_date"] != today:
        # Сбрасываем счётчик
        conn = _get_conn()
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET requests_used = 0, requests_date = %s WHERE user_id = %s", (today, user_id))
            conn.commit()
        finally:
            _put_conn(conn)
        return daily_limit
    return max(0, daily_limit - u["requests_used"])


def use_request(user_id, daily_limit=20):
    """Возвращает True, если запрос разрешён и списан."""
    left = get_requests_left(user_id, daily_limit)
    if left <= 0:
        return False
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET requests_used = requests_used + 1 WHERE user_id = %s",
            (user_id,)
        )
        conn.commit()
        return True
    finally:
        _put_conn(conn)


# ============ ЗЕРКАЛО ============
def can_use_mirror_bonus(user_id):
    """Проверяет: прошло ли 7 дней с последнего бонуса."""
    u = get_user(user_id)
    if not u:
        return True
    last = u["mirror_last_bonus"]
    if not last:
        return True
    now = datetime.now(timezone.utc)
    diff = (now - last).days
    return diff >= 7


def use_mirror_bonus(user_id):
    """Ставит текущее время как последний бонус."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET mirror_last_bonus = %s WHERE user_id = %s",
            (datetime.now(timezone.utc), user_id)
        )
        conn.commit()
    finally:
        _put_conn(conn)


def add_bonus_requests(user_id, amount=5):
    """Добавляет бонусные запросы (минус из requests_used)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET requests_used = GREATEST(0, requests_used - %s) WHERE user_id = %s",
            (amount, user_id)
        )
        conn.commit()
    finally:
        _put_conn(conn)


# ============ ЛОГИ ПОИСКА ============
def log_search(user_id, kind, query, result_count=0):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO searches (user_id, kind, query, result_count) VALUES (%s, %s, %s, %s)",
            (user_id, kind, query[:300], result_count)
        )
        conn.commit()
    finally:
        _put_conn(conn)


# ============ ЗЕРКАЛА ============
def create_mirror(user_id, bot_token):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mirrors (user_id, bot_token, status) VALUES (%s, %s, 'pending')",
            (user_id, bot_token)
        )
        conn.commit()
        return True
    except Exception as e:
        print("[ERROR] create_mirror: " + str(e))
        return False
    finally:
        _put_conn(conn)


# ============ ЛОГИ ИИ ============
def log_ai(user_id, question):
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO ai_logs (user_id, question) VALUES (%s, %s)",
            (user_id, question[:500])
        )
        conn.commit()
    finally:
        _put_conn(conn)


# ============ СТАТИСТИКА ============
def get_user_count():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0]
    finally:
        _put_conn(conn)


def get_search_count():
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM searches")
        return cur.fetchone()[0]
    finally:
        _put_conn(conn)
