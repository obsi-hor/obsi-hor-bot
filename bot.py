#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import re
import time
import socket
import requests
import telebot
from telebot import types
from flask import Flask, request
from threading import Thread

import database as db

# ============ НАСТРОЙКИ ============
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
DAILY_LIMIT = 20
MIRROR_BONUS_REQUESTS = 5
AI_DAILY_LIMIT = 50

print("[DEBUG] Токен: " + str(len(BOT_TOKEN)))
print("[DEBUG] Groq: " + str(len(GROQ_API_KEY)))

# ============ FLASK ============
app = Flask(__name__)


@app.route("/")
def home():
    return "Obsidian Choir bot works"


@app.route("/health")
def health():
    return "OK"


def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


# ============ БОТ ============
bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
bot._last_result = {}


# ============ МЕНЮ ============
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔍 Поиск", callback_data="menu_search"),
        types.InlineKeyboardButton("🤖 ИИ-ассистент", callback_data="menu_ai"),
    )
    markup.add(
        types.InlineKeyboardButton("📡 Проверить IP", callback_data="menu_ip"),
        types.InlineKeyboardButton("🌐 Домен", callback_data="menu_domain"),
    )
    markup.add(
        types.InlineKeyboardButton("🔁 Зеркало", callback_data="menu_mirror"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
    )
    markup.add(
        types.InlineKeyboardButton("ℹ️ Помощь", callback_data="menu_help"),
    )
    return markup


def search_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📱 Номер телефона", callback_data="search_phone"),
        types.InlineKeyboardButton("📛 ФИО + ДР", callback_data="search_fio"),
        types.InlineKeyboardButton("📧 Email", callback_data="search_email"),
        types.InlineKeyboardButton("💬 ВК / ВК ID", callback_data="search_vk"),
    )
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="menu_back"))
    return markup


def back_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="menu_back"))
    return markup


def send_main_menu(chat_id):
    bot.send_message(chat_id, "🔮 Меню:", reply_markup=main_menu())


# ============ ОБРАБОТЧИКИ ============
if bot:
    @bot.message_handler(commands=["start"])
    def cmd_start(message):
        uid = message.from_user.id
        if not db.get_user(uid):
            db.create_user(uid, message.from_user.username, message.from_user.first_name)
        text = (
            "🔮 ОБСИДИАНОВЫЙ ХОР\n\n"
            "OSINT-бот для поиска по открытым источникам.\n\n"
            "📊 Лимит: " + str(DAILY_LIMIT) + " запросов в день.\n"
            "🤖 ИИ: " + str(AI_DAILY_LIMIT) + " вопросов в день.\n"
            "🔁 Зеркало: +" + str(MIRROR_BONUS_REQUESTS) + " запросов (раз в 7 дней).\n\n"
            "Выбери действие:"
        )
        bot.send_message(message.chat.id, text, reply_markup=main_menu())

    @bot.message_handler(commands=["admin"])
    def cmd_admin(message):
        uid = message.from_user.id
        if not ADMIN_ID or uid != ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Нет доступа")
            return
        try:
            users = db.get_user_count()
            searches = db.get_search_count()
            text = (
                "📊 СТАТИСТИКА\n"
                "━━━━━━━━━━━━━━━\n"
                "👥 Юзеров: " + str(users) + "\n"
                "🔍 Поисков: " + str(searches) + "\n"
            )
            bot.send_message(message.chat.id, text)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Ошибка: " + str(e)[:200])

    @bot.callback_query_handler(func=lambda call: call.data == "menu_back")
    def cb_back(call):
        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🔮 Главное меню:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=main_menu(),
            )
        except Exception:
            send_main_menu(call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_help")
    def cb_help(call):
        bot.answer_callback_query(call.id)
        text = (
            "ℹ️ ПОМОЩЬ\n\n"
            "🔍 Поиск — номер, ФИО+ДР, email, ВК.\n"
            "🤖 ИИ — вопрос по OSINT.\n"
            "📡 IP — геолокация и провайдер.\n"
            "🌐 Домен — регистратор и даты.\n"
            "🔁 Зеркало — +5 запросов.\n"
            "👤 Профиль — лимиты.\n\n"
            "📊 Лимит: " + str(DAILY_LIMIT) + " запросов/день."
        )
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_menu(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "menu_profile")
    def cb_profile(call):
        bot.answer_callback_query(call.id)
        uid = call.from_user.id
        u = db.get_user(uid)
        if not u:
            db.create_user(uid, call.from_user.username, call.from_user.first_name)
            u = db.get_user(uid)
        left = db.get_requests_left(uid, DAILY_LIMIT)
        text = (
            "👤 ПРОФИЛЬ\n"
            "━━━━━━━━━━━━━━━\n"
            "🆔 ID: " + str(uid) + "\n"
            "📊 Запросов осталось: " + str(left) + "/" + str(DAILY_LIMIT) + "\n"
        )
        mirror_left = "доступно" if db.can_use_mirror_bonus(uid) else "через 7 дней"
        text += "🔁 Зеркало: " + mirror_left + "\n"
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=back_menu(),
        )
@bot.callback_query_handler(func=lambda call: call.data == "menu_ip")
def cb_ip(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📡 Введи IP-адрес:")
    bot.register_next_step_handler(msg, process_ip)

def process_ip(message):
    uid = message.from_user.id
    ip = message.text.strip()

    if not re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
        bot.send_message(message.chat.id, "❌ Неверный формат IP")
        send_main_menu(message.chat.id)
        return

    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return

    bot.send_message(message.chat.id, "🔍 Ищу...")
    try:
        r = requests.get(
            "http://ip-api.com/json/" + ip,
            params={"fields": "status,message,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,org,as"},
            timeout=10,
        )
        data = r.json()

        if data.get("status") != "success":
            bot.send_message(message.chat.id, "❌ Ошибка: " + str(data.get("message", "?")))
            send_main_menu(message.chat.id)
            return

        text = "📡 IP: " + ip + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        text += "🌍 Страна: " + str(data.get("country") or "?") + "\n"
        text += "🏙 Регион: " + str(data.get("regionName") or "?") + "\n"
        text += "🏘 Город: " + str(data.get("city") or "?") + "\n"
        text += "📮 Индекс: " + str(data.get("zip") or "?") + "\n"
        text += "📍 Координаты: " + str(data.get("lat")) + ", " + str(data.get("lon")) + "\n"
        text += "🕐 TZ: " + str(data.get("timezone") or "?") + "\n"
        text += "📶 ISP: " + str(data.get("isp") or "?") + "\n"
        text += "🏢 Организация: " + str(data.get("org") or "?") + "\n"
        text += "🔢 AS: " + str(data.get("as") or "?") + "\n"

        db.log_search(uid, "ip", ip, 1)
        bot._last_result[uid] = text
        bot.send_message(message.chat.id, text)
        send_main_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка: " + str(e)[:200])
        send_main_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "menu_domain")
def cb_domain(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "🌐 Введи домен (google.com):")
    bot.register_next_step_handler(msg, process_domain)

def process_domain(message):
    uid = message.from_user.id
    domain = message.text.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]

    if not re.match(r"^[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", domain):
        bot.send_message(message.chat.id, "❌ Неверный формат домена")
        send_main_menu(message.chat.id)
        return

    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return

    bot.send_message(message.chat.id, "🔍 Ищу...")
    try:
        text = "🌐 ДОМЕН: " + domain + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"

        try:
            ip = socket.gethostbyname(domain)
            text += "📡 IP: " + ip + "\n"
            r = requests.get("http://ip-api.com/json/" + ip, timeout=10)
            d = r.json()
            if d.get("status") == "success":
                text += "🌍 Страна: " + str(d.get("country") or "?") + "\n"
                text += "🏙 Город: " + str(d.get("city") or "?") + "\n"
                text += "📶 ISP: " + str(d.get("isp") or "?") + "\n"
        except Exception:
            text += "📡 IP: не определён\n"

        try:
            rq = requests.get("https://rdap.org/domain/" + domain, timeout=15)
            if rq.status_code == 200:
                data = rq.json()
                for ev in data.get("events", []):
                    if ev.get("eventAction") == "registration":
                        text += "📅 Создан: " + ev.get("eventDate", "")[:10] + "\n"
                    elif ev.get("eventAction") == "expiration":
                        text += "📅 Истекает: " + ev.get("eventDate", "")[:10] + "\n"
                for ent in data.get("entities", []):
                    if "registrar" in ent.get("roles", []):
                        vcard = ent.get("vcardArray", [])
                        if len(vcard) > 1:
                            for item in vcard[1]:
                                if item[0] == "fn":
                                    text += "📋 Регистратор: " + item[3] + "\n"
        except Exception:
            pass

        db.log_search(uid, "domain", domain, 1)
        bot._last_result[uid] = text
        bot.send_message(message.chat.id, text)
        send_main_menu(message.chat.id)
    except Exception as e:
        bot.send_message(message.chat.id, "❌ Ошибка: " + str(e)[:200])
        send_main_menu(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "menu_search")
def cb_search(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "🔍 Выбери тип поиска:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=search_menu(),
    )

@bot.callback_query_handler(func=lambda call: call.data == "search_phone")
def cb_search_phone(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📱 Введи номер телефона:")
    bot.register_next_step_handler(msg, process_search_phone)

def process_search_phone(message):
    uid = message.from_user.id
    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return
    phone = message.text.strip()
    text = "📱 НОМЕР: " + phone + "\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "🔍 Google Dorks:\n"
    text += '• "' + phone + '" утечка\n'
    text += '• "' + phone + '" объявление\n'
    text += '• site:vk.com "' + phone + '"\n'
    text += '• site:avito.ru "' + phone + '"\n'
    text += '• site:2gis.ru "' + phone + '"\n'
    db.log_search(uid, "phone", phone, 0)
    bot._last_result[uid] = text
    bot.send_message(message.chat.id, text)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💾 Скачать результат", callback_data="export_result"))
    markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="menu_back"))
    bot.send_message(message.chat.id, "Действия:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "search_fio")
def cb_search_fio(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📛 Введи ФИО и ДР (если есть):")
    bot.register_next_step_handler(msg, process_search_fio)

def process_search_fio(message):
    uid = message.from_user.id
    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return
    query = message.text.strip()
    text = "📛 ФИО: " + query + "\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "🔍 Google Dorks:\n"
    text += '• "' + query + '" резюме\n'
    text += '• "' + query + '" работа\n'
    text += '• site:vk.com "' + query + '"\n'
    text += '• site:ok.ru "' + query + '"\n'
    text += '• site:t.me "' + query + '"\n'
    text += '• "' + query + '" суд\n'
    db.log_search(uid, "fio", query, 0)
    bot._last_result[uid] = text
    bot.send_message(message.chat.id, text)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💾 Скачать результат", callback_data="export_result"))
    markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="menu_back"))
    bot.send_message(message.chat.id, "Действия:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "search_email")
def cb_search_email(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📧 Введи email:")
    bot.register_next_step_handler(msg, process_search_email)

def process_search_email(message):
    uid = message.from_user.id
    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return
    email = message.text.strip()
    text = "📧 EMAIL: " + email + "\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "🔍 Google Dorks:\n"
    text += '• "' + email + '" утечка\n'
    text += '• "' + email + '" пароль\n'
    text += '• site:pastebin.com "' + email + '"\n'
    text += '• site:github.com "' + email + '"\n'
    db.log_search(uid, "email", email, 0)
    bot._last_result[uid] = text
    bot.send_message(message.chat.id, text)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💾 Скачать результат", callback_data="export_result"))
    markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="menu_back"))
    bot.send_message(message.chat.id, "Действия:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "search_vk")
def cb_search_vk(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "💬 Введи ВК (ссылка, @ник или ID):")
    bot.register_next_step_handler(msg, process_search_vk)

def process_search_vk(message):
    uid = message.from_user.id
    if not db.use_request(uid, DAILY_LIMIT):
        bot.send_message(message.chat.id, "❌ Лимит исчерпан. Попробуй завтра.")
        send_main_menu(message.chat.id)
        return
    vk = message.text.strip()
    nick = vk.replace("@", "").replace("https://vk.com/", "").replace("vk.com/", "")
    text = "💬 ВК: " + vk + "\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n\n"
    text += "🔗 Ссылки:\n"
    text += "• https://vk.com/" + nick + "\n"
    text += "• https://ok.ru/profile/" + nick + "\n"
    db.log_search(uid, "vk", vk, 0)
    bot._last_result[uid] = text
    bot.send_message(message.chat.id, text)
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💾 Скачать результат", callback_data="export_result"))
    markup.add(types.InlineKeyboardButton("⬅️ Главное меню", callback_data="menu_back"))
    bot.send_message(message.chat.id, "Действия:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "export_result")
def cb_export(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    text = bot._last_result.get(uid)
    if not text:
        bot.send_message(call.message.chat.id, "❌ Результат не найден")
        return
    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = "obsi_hor_result.txt"
    bot.send_document(call.message.chat.id, buf, caption="💾 Результат поиска")
    @bot.callback_query_handler(func=lambda call: call.data == "menu_mirror")
    def cb_mirror(call):
        bot.answer_callback_query(call.id)
        uid = call.from_user.id
        if not db.can_use_mirror_bonus(uid):
            bot.send_message(
                call.message.chat.id,
                "❌ Бонус за зеркало доступен раз в 7 дней.\nПопробуй позже."
            )
            return
        text = (
            "🔁 СОЗДАНИЕ ЗЕРКАЛА\n\n"
            "За создание зеркала — +" + str(MIRROR_BONUS_REQUESTS) + " запросов (раз в 7 дней).\n\n"
            "1. Открой @BotFather\n"
            "2. /newbot\n"
            "3. Создай бота\n"
            "4. Скопируй токен\n"
            "5. Отправь сюда"
        )
        msg = bot.send_message(call.message.chat.id, text)
        bot.register_next_step_handler(msg, process_mirror)

    def process_mirror(message):
        uid = message.from_user.id
        token = message.text.strip()
        if not re.match(r"^\d{8,12}:[A-Za-z0-9_\-]{30,}$", token):
            bot.send_message(message.chat.id, "❌ Неверный формат токена")
            send_main_menu(message.chat.id)
            return
        if not db.can_use_mirror_bonus(uid):
            bot.send_message(message.chat.id, "❌ Бонус доступен раз в 7 дней.")
            send_main_menu(message.chat.id)
            return
        if db.create_mirror(uid, token):
            db.add_bonus_requests(uid, MIRROR_BONUS_REQUESTS)
            db.use_mirror_bonus(uid)
            bot.send_message(
                message.chat.id,
                "✅ Заявка принята!\n+" + str(MIRROR_BONUS_REQUESTS) + " запросов начислено."
            )
            if ADMIN_ID:
                try:
                    bot.send_message(ADMIN_ID, "🔁 ЗЕРКАЛО от " + str(uid))
                except Exception:
                    pass
        else:
            bot.send_message(message.chat.id, "❌ Ошибка")
        send_main_menu(message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "menu_ai")
    def cb_ai(call):
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🤖 Задай вопрос по OSINT (макс " + str(AI_DAILY_LIMIT) + " в день):"
        )
        bot.register_next_step_handler(msg, process_ai)

    def process_ai(message):
        uid = message.from_user.id
        question = message.text.strip()
        if len(question) < 3:
            bot.send_message(message.chat.id, "❌ Слишком короткий вопрос")
            send_main_menu(message.chat.id)
            return

        if not GROQ_API_KEY:
            bot.send_message(message.chat.id, "❌ Groq API не настроен")
            send_main_menu(message.chat.id)
            return

        bot.send_message(message.chat.id, "🤖 Думаю...")

        try:
            from groq import Groq
            client = Groq(api_key=GROQ_API_KEY)

            system_prompt = (
                "Ты OSINT-ассистент. Отвечай кратко и по делу. "
                "Помогай с поиском информации по открытым источникам, "
                "объясняй инструменты OSINT, Google Dorks, методы поиска. "
                "Не давай советов по незаконным действиям."
            )

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                max_tokens=800,
                temperature=0.7,
            )
            answer = response.choices[0].message.content

            db.log_ai(uid, question)
            bot.send_message(message.chat.id, "🤖 " + answer)
            send_main_menu(message.chat.id)
        except Exception as e:
            bot.send_message(message.chat.id, "❌ Ошибка: " + str(e)[:200])
            send_main_menu(message.chat.id)


# ============ WEBHOOK ============
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        print("[ERROR] webhook: " + str(e))
    return "OK", 200


def set_webhook():
    try:
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
        if not render_url:
            print("[!] RENDER_EXTERNAL_URL не задан")
            return False
        webhook_url = render_url + "/webhook"
        resp = requests.post(
            "https://api.telegram.org/bot" + BOT_TOKEN + "/setWebhook",
            json={"url": webhook_url, "allowed_updates": ["message", "callback_query"]},
        )
        print("[+] Webhook: " + str(resp.json()))
        return True
    except Exception as e:
        print("[ERROR] set_webhook: " + str(e))
        return False


# ============ MAIN ============
if __name__ == "__main__":
    print("[+] Запускаю Flask...")
    t = Thread(target=run_web)
    t.daemon = True
    t.start()
    if bot:
        time.sleep(3)
        print("[+] Устанавливаю webhook...")
        set_webhook()
        print("[+] Бот запущен")
        while True:
            time.sleep(60)
    else:
        while True:
            time.sleep(60)
