import asyncio
import concurrent.futures
import copy
import json
import os
import queue
import random
import re
import string
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from urllib.parse import urlparse, unquote

from telethon import TelegramClient, functions, errors


APP_TITLE = "Telegram Username Scanner"

# ========================  ВАШИ КОНТАКТЫ (показываются внизу слева)  ========================
CONTACT_TELEGRAM = "@n0c0cu"     # <- замените на свой ник в Telegram
CONTACT_EMAIL = "Valterkreidtner@gmail.com"        # <- замените на свою почту
# ===========================================================================================

# В собранном .exe храним данные рядом с exe-файлом, а не во временной папке PyInstaller.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "accounts.json")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
LETTERS = string.ascii_lowercase
DIGITS = string.digits
DEFAULT_CHARS = string.ascii_lowercase + string.digits
ALLOWED = set(string.ascii_lowercase + string.digits + "_")
CONSONANTS = "bcdfghjklmnprstvwz"
VOWELS = "aeiou"
PATTERN_CLASSES = set("cvldx_")
CLASS_SIZES = {"c": len(CONSONANTS), "v": len(VOWELS), "l": 26, "d": 10, "x": 36, "_": 1}
MAX_FLOOD_WAIT = 300   # если Telegram просит ждать дольше (сек) — аккаунт отключаем до конца запуска
GUARD_MIN_INVALID = 12  # столько «недопустимых» подряд и больше 90% — шаблон Telegram не принимает

LANGS = [("ru", "RU"), ("en", "EN")]

# Пресеты шаблонов: (ключ, шаблон). Каждый всегда даёт допустимый username.
PRESETS = [
    ("none", ""),
    ("pron1", "cvcvc"),
    ("pron2", "cvccv"),
    ("pron3", "vcvcv"),
    ("dbl_start", "AABCD"),
    ("dbl_end", "ABCDD"),
    ("two_pairs", "AABBC"),
    ("mirror", "ABCBA"),
    ("first_last", "ABCDA"),
    ("pair_rep1", "ABABC"),
    ("pair_rep2", "ABCAB"),
    ("triple", "AAABC"),
    ("with_digits", "cvcdd"),
    ("custom", ""),
]

# --- палитра: тёмный «приборный» фон, один синий акцент для действий,
#     остальные цвета несут смысл (свободно / Fragment / ошибка)
BG = "#0f141a"
PANEL = "#161d26"
PANEL2 = "#1d2631"
INPUT = "#0b1016"
BORDER = "#2a3542"
FG = "#e7edf3"
MUTED = "#8b98a7"
ACCENT = "#4c9aff"
ACCENT_DARK = "#3a82e6"
GREEN = "#4ade9f"
AMBER = "#f2b84b"
RED = "#ff6b6b"
BLUE = "#7db4ff"
DISABLED = "#27313d"

STAT_CARDS = [  # (ключ, ключ перевода, цвет числа)
    ("checked", "card_checked", FG),
    ("free", "card_free", GREEN),
    ("fragment", "card_fragment", AMBER),
    ("taken", "card_taken", MUTED),
    ("invalid", "card_invalid", BLUE),
    ("errors", "card_errors", RED),
]


# ------------------------------------------------------------------ переводы
TR = {
    "ru": {
        "subtitle": "генерация и проверка @username",
        "tab_accounts": "Аккаунты", "tab_gen": "Генерация", "tab_gen_warn": "Генерация ⚠",
        "api_title": "Telegram API", "api_id": "API ID", "api_hash": "API Hash",
        "api_hint": "my.telegram.org → API Development Tools",
        "accounts": "Аккаунты",
        "col_acc": "Аккаунт", "col_proxy": "Прокси", "col_state": "Статус",
        "btn_add": "＋  Добавить аккаунт", "btn_proxy": "✎ Прокси", "btn_toggle": "✓/✗ Вкл/Выкл",
        "btn_remove": "🗑 Удалить",
        "no_accounts_hint": "Аккаунтов пока нет. Нажмите «Добавить аккаунт».",
        "acc_hint": ("Двойной клик по аккаунту включает и выключает его.\n"
                     "Прокси: socks5://user:pass@host:port, http://host:port "
                     "или host:port. Лучше свой прокси на каждый аккаунт."),
        "proxy_none": "без прокси", "proxy_bad": "ошибка в прокси", "acc_disabled": "выключен",
        # генерация
        "template": "Шаблон",
        "pattern": "Свой шаблон",
        "pattern_hint": ("Одинаковые заглавные буквы дают одну и ту же букву (AABCD → ttmpk). "
                         "Фиксированные буквы добавляйте в префикс или суффикс."),
        "chip_c": "согл.", "chip_v": "гласн.", "chip_l": "буква", "chip_d": "цифра", "chip_x": "любой",
        "length": "Длина username (5–32)", "charset": "Набор символов",
        "mode_mix": "Буквы + цифры", "mode_letters": "Только буквы",
        "mode_digits": "Цифры (первая — буква)",
        "prefix": "Префикс", "suffix": "Суффикс",
        "amount": "Всего проверок", "delay": "Задержка, сек",
        "autosave": "Сохранять найденные в available.txt и fragment.txt",
        "preset_none": "Без шаблона (случайные символы)",
        "preset_pron1": "Произносимый (cvcvc)", "preset_pron2": "Произносимый (cvccv)",
        "preset_pron3": "Произносимый (vcvcv)",
        "preset_dbl_start": "Двойная буква в начале (AABCD)", "preset_dbl_end": "Двойная буква в конце (ABCDD)",
        "preset_two_pairs": "Две пары (AABBC)", "preset_mirror": "Зеркальный (ABCBA)",
        "preset_first_last": "Первая = последняя (ABCDA)",
        "preset_pair_rep1": "Повтор пары (ABABC)", "preset_pair_rep2": "Повтор пары (ABCAB)",
        "preset_triple": "Тройная буква (AAABC)", "preset_with_digits": "Буквы + 2 цифры (cvcdd)",
        "preset_custom": "Свой шаблон",
        "preview_title": "Предпросмотр", "preview_new": "Другие",
        "preview_ok": "✓ Telegram принимает такие ники",
        "combos": "Возможных вариантов: ≈ {n}",
        "combos_less": "Вариантов (≈ {n}) меньше, чем проверок. Сканирование закончится раньше.",
        "warn_delay": "⚠ Задержка меньше 1 сек. Telegram быстро ограничит аккаунт.",
        # главный экран
        "btn_start": "▶  Начать", "btn_stop": "■  Остановить",
        "btn_save": "Сохранить", "btn_copy": "Копировать", "btn_clear": "Очистить",
        "free_title": "Свободные", "fragment_title": "Продаются на Fragment", "log_title": "Журнал",
        "pane_hint_free": "Двойной клик копирует ник",
        "pane_hint_fragment": "Двойной клик открывает ник на fragment.com",
        "card_checked": "Проверено", "card_free": "Свободно", "card_fragment": "Fragment",
        "card_taken": "Занято", "card_invalid": "Недоступно", "card_errors": "Ошибки",
        "speed": "Скорость {s} в минуту, осталось ≈ {eta}, прошло {el}",
        "speed_done": "Скорость {s} в минуту, всего {el}",
        "speed_calc": "Считаю скорость…",
        "u_h": "ч", "u_m": "мин", "u_s": "с",
        "footer": "Используйте только свои аккаунты и свой API ID/Hash. Не передавайте файлы .session другим людям.",
        "contact": "Связь:",
        "status_ready": "Готово к работе",
        # ошибки валидации
        "err": "Ошибка",
        "err_api_id": "API ID должен быть числом.",
        "err_api_hash": "Введите корректный API Hash.",
        "err_no_accounts": "Добавьте и включите хотя бы один аккаунт на вкладке «Аккаунты».",
        "err_proxy_title": "Ошибка прокси", "err_proxy_acc": "Аккаунт {name}: {err}",
        "proxy_parse": "Не удалось разобрать прокси. Пример: socks5://user:pass@1.2.3.4:1080",
        "proxy_scheme": "Поддерживаются socks5, socks4 и http прокси.",
        "proxy_hostport": "Укажите адрес и порт прокси (host:port).",
        "err_numbers": "Длина, количество и задержка должны быть числами.",
        "err_length": "Длина username должна быть от 5 до 32.",
        "err_amount": "Количество проверок должно быть больше 0.",
        "err_affix_len": "Префикс и суффикс вместе длиннее username.",
        "err_prefix_letter": "Username должен начинаться с буквы: префикс не может начинаться с цифры или «_».",
        "err_gen_fail": ("С такими параметрами нельзя получить допустимый username. "
                         "Проверьте префикс и суффикс."),
        "err_pattern_empty": "Введите шаблон.",
        "err_pattern_chars": "В шаблоне допустимы: c v l d x _ и заглавные буквы A–Z.",
        "err_pattern_len": "Длина username (префикс + шаблон + суффикс) должна быть от 5 до 32, сейчас {n}.",
        "err_pattern_first": ("Username должен начинаться с буквы: первым в шаблоне должен стоять "
                              "c, v, l или заглавная буква."),
        "err_pattern_last": "Username не может заканчиваться на «_».",
        "err_pattern_dunder": "Username не может содержать два «_» подряд.",
        # защита от шаблона, который Telegram не принимает
        "log_guard": "[GUARD] Telegram отклонил {n} из {m} ников как недопустимые. Останавливаюсь.",
        "stat_guard": "Остановлено: Telegram не принимает ники по этим настройкам.",
        "guard_title": "Telegram отклоняет эти ники",
        "guard_msg": ("Telegram отклонил {n} из {m} проверенных ников как недопустимые.\n\n"
                      "Сканирование остановлено, чтобы не тратить лимиты. "
                      "Проверьте шаблон, префикс и суффикс."),
        # диалоги аккаунтов
        "dlg_new": "Новый аккаунт", "dlg_edit": "Прокси аккаунта",
        "dlg_name": "Название (латиница, цифры, - и _)", "dlg_proxy": "Прокси (необязательно)",
        "dlg_formats": "socks5://user:pass@host:port\nhttp://host:port\nhost:port  или  host:port:user:pass",
        "dlg_phone_hint": "Номер телефона и код программа спросит при первом запуске.",
        "dlg_save": "Сохранить", "dlg_cancel": "Отмена",
        "err_name": "Название: 1–32 символа, только латиница, цифры, - и _.",
        "err_dup": "Аккаунт с таким названием уже есть.",
        "busy_title": "Занято", "busy_msg": "Сначала остановите сканирование.",
        "accounts_pick": "Выберите аккаунт в списке.",
        "remove_title": "Удалить",
        "remove_q": "Убрать аккаунт «{name}» из списка?\nФайл сессии на диске останется.",
        # авторизация
        "auth_title": "Авторизация: {name}",
        "auth_phone": ("Аккаунт «{name}».\nВведите номер Telegram в международном формате:\n"
                       "Например: +491234567890"),
        "code_title": "Код Telegram: {name}",
        "code_prompt": ("Аккаунт «{name}». Код отправлен: {how}.\n\n"
                        "Введите код. Если не пришёл — введите букву r\n"
                        "и нажмите OK, чтобы отправить повторно (SMS/звонок):"),
        "how_app": "в приложение Telegram (чат «Telegram» на другом устройстве)",
        "how_sms": "по SMS", "how_call": "звонком", "how_flash": "звонком (flash call)",
        "how_missed": "пропущенным звонком", "how_unknown": "неизвестным способом",
        "pwd_title": "Пароль 2FA: {name}", "pwd_prompt": "Введите пароль двухэтапной аутентификации:",
        # состояния и журнал
        "st_login": "вход...", "st_login_err": "ошибка входа", "st_not_in": "не вошёл",
        "st_working": "работает", "st_flood": "флуд {n}с", "st_flood_off": "флуд {n}с, откл.",
        "st_off_errors": "отключён (ошибки)", "st_done": "готов",
        "log_code_sent": "[{name}] Код отправлен: {how}.",
        "log_resend_fail": "[{name}] Не удалось отправить повторно: {err}",
        "log_bad_code": "[{name}] Неверный код, попробуйте ещё раз.",
        "log_login_err": "[{name}] Ошибка входа: {err}",
        "log_not_auth": "[{name}] Не авторизован, пропускаю.",
        "log_auth_ok": "[{name}] Авторизация успешна ({proxy}).",
        "log_plan": "[INFO] План проверок: {n}, аккаунтов: {k}, задержка на аккаунт {d} сек.",
        "log_exhausted": "[INFO] Уникальные комбинации закончились.",
        "log_flood_long": "[{name}] FloodWait {w} сек. Слишком долго, аккаунт отключён до конца запуска.",
        "log_flood": "[{name}] FloodWait: ждём {w} сек. Новая задержка: {d:.1f} сек.",
        "log_acc_err": "[{name}] @{u}: {err}",
        "log_err_streak": "[{name}] 10 ошибок подряд. Аккаунт отключён (проверьте прокси и интернет).",
        "log_error": "[ERROR] {err}",
        "log_file_err": "[FILE ERROR] {err}",
        # статусы
        "stat_connecting": "Подключение к Telegram...", "stat_connecting_acc": "Подключение: {name}...",
        "stat_running": "Проверка идёт. Аккаунтов: {n}",
        "stat_no_acc": "Нет ни одного авторизованного аккаунта.",
        "stat_stopping": "Остановка...", "stat_stopped": "Остановлено. Свободных найдено: {n}.",
        "stat_finished": "Завершено. Свободных: {n}.{tail}{incomplete}",
        "tail_saved": " Сохранено в available.txt.",
        "incomplete": " Не все проверки выполнены: аккаунты отключились (см. журнал).",
        "stat_error": "Ошибка. Подробности в журнале.", "stat_copied": "Скопировано: {n}",
        "stat_copied_one": "Скопировано: {u}", "stat_opened": "Открыто на Fragment: {u}",
        # файлы
        "copy_title": "Копирование", "save_title": "Сохранение", "empty_list": "Список пока пуст.",
        "save_dialog": "Сохранить список", "saved": "Сохранено: {n} username.",
        "done": "Готово", "exit_title": "Выход",
        "exit_q": "Сканирование ещё идёт. Остановить и выйти?",
        "cfg_err_title": "Не удалось сохранить настройки",
        "cfg_err": ("Файл: {path}\n\n{err}\n\nПереместите программу в папку, куда можно писать "
                    "(например, Документы или Рабочий стол)."),
    },
    "en": {
        "subtitle": "generate & check @username",
        "tab_accounts": "Accounts", "tab_gen": "Generation", "tab_gen_warn": "Generation ⚠",
        "api_title": "Telegram API", "api_id": "API ID", "api_hash": "API Hash",
        "api_hint": "my.telegram.org → API Development Tools",
        "accounts": "Accounts",
        "col_acc": "Account", "col_proxy": "Proxy", "col_state": "Status",
        "btn_add": "＋  Add account", "btn_proxy": "✎ Proxy", "btn_toggle": "✓/✗ On/Off",
        "btn_remove": "🗑 Remove",
        "no_accounts_hint": "No accounts yet. Click “Add account”.",
        "acc_hint": ("Double-click an account to enable or disable it.\n"
                     "Proxy: socks5://user:pass@host:port, http://host:port "
                     "or host:port. A separate proxy per account is best."),
        "proxy_none": "no proxy", "proxy_bad": "invalid proxy", "acc_disabled": "disabled",
        "template": "Template",
        "pattern": "Custom pattern",
        "pattern_hint": ("Identical capitals give the same letter (AABCD → ttmpk). "
                         "Put fixed letters into the prefix or suffix."),
        "chip_c": "cons.", "chip_v": "vowel", "chip_l": "letter", "chip_d": "digit", "chip_x": "any",
        "length": "Username length (5–32)", "charset": "Character set",
        "mode_mix": "Letters + digits", "mode_letters": "Letters only",
        "mode_digits": "Digits (first is a letter)",
        "prefix": "Prefix", "suffix": "Suffix",
        "amount": "Total checks", "delay": "Delay, sec",
        "autosave": "Save finds to available.txt and fragment.txt",
        "preset_none": "No template (random characters)",
        "preset_pron1": "Pronounceable (cvcvc)", "preset_pron2": "Pronounceable (cvccv)",
        "preset_pron3": "Pronounceable (vcvcv)",
        "preset_dbl_start": "Double letter at start (AABCD)", "preset_dbl_end": "Double letter at end (ABCDD)",
        "preset_two_pairs": "Two pairs (AABBC)", "preset_mirror": "Palindrome (ABCBA)",
        "preset_first_last": "First = last (ABCDA)",
        "preset_pair_rep1": "Repeated pair (ABABC)", "preset_pair_rep2": "Repeated pair (ABCAB)",
        "preset_triple": "Triple letter (AAABC)", "preset_with_digits": "Letters + 2 digits (cvcdd)",
        "preset_custom": "Custom pattern",
        "preview_title": "Preview", "preview_new": "Shuffle",
        "preview_ok": "✓ Telegram accepts these usernames",
        "combos": "Possible variants: ≈ {n}",
        "combos_less": "Variants (≈ {n}) are fewer than checks. The scan will end earlier.",
        "warn_delay": "⚠ Delay under 1 sec. Telegram will quickly restrict the account.",
        "btn_start": "▶  Start", "btn_stop": "■  Stop",
        "btn_save": "Save", "btn_copy": "Copy", "btn_clear": "Clear",
        "free_title": "Free", "fragment_title": "For sale on Fragment", "log_title": "Log",
        "pane_hint_free": "Double-click copies the username",
        "pane_hint_fragment": "Double-click opens the username on fragment.com",
        "card_checked": "Checked", "card_free": "Free", "card_fragment": "Fragment",
        "card_taken": "Taken", "card_invalid": "Unavailable", "card_errors": "Errors",
        "speed": "Speed {s} per minute, about {eta} left, {el} elapsed",
        "speed_done": "Speed {s} per minute, {el} in total",
        "speed_calc": "Measuring speed…",
        "u_h": "h", "u_m": "min", "u_s": "s",
        "footer": "Use only your own accounts and your own API ID/Hash. Never share .session files.",
        "contact": "Contact:",
        "status_ready": "Ready",
        "err": "Error",
        "err_api_id": "API ID must be a number.",
        "err_api_hash": "Enter a valid API Hash.",
        "err_no_accounts": "Add and enable at least one account on the “Accounts” tab.",
        "err_proxy_title": "Proxy error", "err_proxy_acc": "Account {name}: {err}",
        "proxy_parse": "Could not parse the proxy. Example: socks5://user:pass@1.2.3.4:1080",
        "proxy_scheme": "Supported proxy types: socks5, socks4 and http.",
        "proxy_hostport": "Specify proxy host and port (host:port).",
        "err_numbers": "Length, amount and delay must be numbers.",
        "err_length": "Username length must be between 5 and 32.",
        "err_amount": "Number of checks must be greater than 0.",
        "err_affix_len": "Prefix and suffix together are longer than the username.",
        "err_prefix_letter": "A username must start with a letter: the prefix cannot start with a digit or “_”.",
        "err_gen_fail": ("A valid username cannot be generated with these settings. "
                         "Check the prefix and suffix."),
        "err_pattern_empty": "Enter a pattern.",
        "err_pattern_chars": "Allowed in a pattern: c v l d x _ and capital letters A–Z.",
        "err_pattern_len": "Username length (prefix + pattern + suffix) must be 5 to 32, now {n}.",
        "err_pattern_first": ("A username must start with a letter: the first pattern character "
                              "must be c, v, l or a capital letter."),
        "err_pattern_last": "A username cannot end with “_”.",
        "err_pattern_dunder": "A username cannot contain two “_” in a row.",
        "log_guard": "[GUARD] Telegram rejected {n} of {m} usernames as invalid. Stopping.",
        "stat_guard": "Stopped: Telegram does not accept usernames with these settings.",
        "guard_title": "Telegram rejects these usernames",
        "guard_msg": ("Telegram rejected {n} of {m} checked usernames as invalid.\n\n"
                      "The scan was stopped so your limits are not wasted. "
                      "Check the pattern, prefix and suffix."),
        "dlg_new": "New account", "dlg_edit": "Account proxy",
        "dlg_name": "Name (Latin letters, digits, - and _)", "dlg_proxy": "Proxy (optional)",
        "dlg_formats": "socks5://user:pass@host:port\nhttp://host:port\nhost:port  or  host:port:user:pass",
        "dlg_phone_hint": "The phone number and code will be requested on first run.",
        "dlg_save": "Save", "dlg_cancel": "Cancel",
        "err_name": "Name: 1–32 characters, Latin letters, digits, - and _ only.",
        "err_dup": "An account with this name already exists.",
        "busy_title": "Busy", "busy_msg": "Stop the scan first.",
        "accounts_pick": "Select an account in the list.",
        "remove_title": "Remove",
        "remove_q": "Remove account “{name}” from the list?\nThe session file stays on disk.",
        "auth_title": "Login: {name}",
        "auth_phone": ("Account “{name}”.\nEnter your Telegram phone number in international format:\n"
                       "Example: +491234567890"),
        "code_title": "Telegram code: {name}",
        "code_prompt": ("Account “{name}”. Code sent: {how}.\n\n"
                        "Enter the code. If it didn't arrive, type the letter r\n"
                        "and press OK to resend (SMS/call):"),
        "how_app": "to the Telegram app (the “Telegram” chat on another device)",
        "how_sms": "by SMS", "how_call": "by phone call", "how_flash": "by flash call",
        "how_missed": "by missed call", "how_unknown": "in an unknown way",
        "pwd_title": "2FA password: {name}", "pwd_prompt": "Enter your two-step verification password:",
        "st_login": "logging in...", "st_login_err": "login error", "st_not_in": "not logged in",
        "st_working": "running", "st_flood": "flood {n}s", "st_flood_off": "flood {n}s, off",
        "st_off_errors": "off (errors)", "st_done": "done",
        "log_code_sent": "[{name}] Code sent: {how}.",
        "log_resend_fail": "[{name}] Could not resend the code: {err}",
        "log_bad_code": "[{name}] Wrong code, try again.",
        "log_login_err": "[{name}] Login error: {err}",
        "log_not_auth": "[{name}] Not authorized, skipping.",
        "log_auth_ok": "[{name}] Logged in ({proxy}).",
        "log_plan": "[INFO] Planned checks: {n}, accounts: {k}, delay per account {d} sec.",
        "log_exhausted": "[INFO] Unique combinations are exhausted.",
        "log_flood_long": "[{name}] FloodWait {w} sec. Too long, account disabled until the end of this run.",
        "log_flood": "[{name}] FloodWait: waiting {w} sec. New delay: {d:.1f} sec.",
        "log_acc_err": "[{name}] @{u}: {err}",
        "log_err_streak": "[{name}] 10 errors in a row. Account disabled (check proxy and internet).",
        "log_error": "[ERROR] {err}",
        "log_file_err": "[FILE ERROR] {err}",
        "stat_connecting": "Connecting to Telegram...", "stat_connecting_acc": "Connecting: {name}...",
        "stat_running": "Scanning. Accounts: {n}",
        "stat_no_acc": "No authorized accounts.",
        "stat_stopping": "Stopping...", "stat_stopped": "Stopped. Free usernames found: {n}.",
        "stat_finished": "Finished. Free: {n}.{tail}{incomplete}",
        "tail_saved": " Saved to available.txt.",
        "incomplete": " Not all checks were done: accounts were disabled (see log).",
        "stat_error": "Error. See the log for details.", "stat_copied": "Copied: {n}",
        "stat_copied_one": "Copied: {u}", "stat_opened": "Opened on Fragment: {u}",
        "copy_title": "Copy", "save_title": "Save", "empty_list": "The list is empty.",
        "save_dialog": "Save list", "saved": "Saved: {n} usernames.",
        "done": "Done", "exit_title": "Exit",
        "exit_q": "A scan is still running. Stop it and exit?",
        "cfg_err_title": "Could not save settings",
        "cfg_err": ("File: {path}\n\n{err}\n\nMove the program to a folder you can write to "
                    "(for example Documents or Desktop)."),
    },
}


# ------------------------------------------------------------ генерация / правила
def is_valid_username(u):
    """Правила Telegram: 5–32 символа, a-z 0-9 _, первая буква, не кончается на _, без __."""
    return bool(u) and (5 <= len(u) <= 32 and u[0].isalpha() and set(u) <= ALLOWED
                        and not u.endswith("_") and "__" not in u)


def clean_pattern(text):
    """Оставляет в шаблоне только допустимые символы."""
    return "".join(ch for ch in text if ch in PATTERN_CLASSES or ch in string.ascii_uppercase)[:32]


def clean_affix(text):
    """Префикс/суффикс: нижний регистр, без @ и недопустимых символов."""
    text = (text or "").lower().replace("@", "")
    return "".join(ch for ch in text if ch in ALLOWED)[:32]


def make_username(length, chars, prefix, suffix):
    """Случайный username из набора символов; всегда проходит is_valid_username."""
    middle_len = length - len(prefix) - len(suffix)
    if middle_len < 0:
        return None

    for _ in range(200):
        middle = [random.choice(chars) for _ in range(middle_len)]
        if not prefix and middle:
            middle[0] = random.choice(LETTERS)
        username = prefix + "".join(middle) + suffix
        if is_valid_username(username):
            return username
    return None


def validate_pattern(pattern, prefix, suffix):
    """None если шаблон гарантированно даёт допустимые ники, иначе (ключ_ошибки, параметры)."""
    if not pattern:
        return ("err_pattern_empty", {})
    if any(not (ch in PATTERN_CLASSES or ch in string.ascii_uppercase) for ch in pattern):
        return ("err_pattern_chars", {})
    total = len(prefix) + len(pattern) + len(suffix)
    if not (5 <= total <= 32):
        return ("err_pattern_len", {"n": total})
    if prefix:
        if not prefix[0].isalpha():
            return ("err_prefix_letter", {})
    elif not (pattern[0] in "clv" or pattern[0] in string.ascii_uppercase):
        return ("err_pattern_first", {})
    last = suffix[-1] if suffix else pattern[-1]
    if last == "_":
        return ("err_pattern_last", {})
    symbols = list(prefix) + list(pattern) + list(suffix)
    if any(a == "_" and b == "_" for a, b in zip(symbols, symbols[1:])):
        return ("err_pattern_dunder", {})
    return None


def make_from_pattern(pattern, prefix, suffix):
    """Генерация по шаблону.
    c согласная, v гласная, l буква, d цифра, x буква/цифра, _ подчёркивание,
    A–Z — переменные: одинаковые заглавные = одна и та же буква, разные = разные буквы.
    """
    variables = sorted({c for c in pattern if c in string.ascii_uppercase})

    for _ in range(300):
        mapping = dict(zip(variables, random.sample(LETTERS, len(variables))))
        out = []
        for ch in pattern:
            if ch == "c":
                out.append(random.choice(CONSONANTS))
            elif ch == "v":
                out.append(random.choice(VOWELS))
            elif ch == "l":
                out.append(random.choice(LETTERS))
            elif ch == "d":
                out.append(random.choice(DIGITS))
            elif ch == "x":
                out.append(random.choice(LETTERS + DIGITS))
            elif ch == "_":
                out.append("_")
            else:
                out.append(mapping[ch])
        username = prefix + "".join(out) + suffix
        if is_valid_username(username):
            return username
    return None


def generate_username(cfg):
    if cfg.get("pattern"):
        return make_from_pattern(cfg["pattern"], cfg["prefix"], cfg["suffix"])
    return make_username(cfg["length"], cfg["chars"], cfg["prefix"], cfg["suffix"])


def count_combinations(cfg):
    """Сколько разных username может дать конфигурация (без учёта редких отбраковок)."""
    if cfg.get("pattern"):
        variables, total = set(), 1
        for ch in cfg["pattern"]:
            if ch in string.ascii_uppercase:
                variables.add(ch)
            else:
                total *= CLASS_SIZES[ch]
        for i in range(len(variables)):
            total *= 26 - i
        return total
    middle = cfg["length"] - len(cfg["prefix"]) - len(cfg["suffix"])
    if middle <= 0:
        return 1
    n = len(cfg["chars"])
    first = n if cfg["prefix"] else 26
    return first * n ** (middle - 1)


def fmt_count(n, lang):
    if n < 1_000_000:
        return f"{n:,}".replace(",", " ")
    for value, ru, en in ((10 ** 12, "трлн", "T"), (10 ** 9, "млрд", "B"), (10 ** 6, "млн", "M")):
        if n >= value:
            return f"{n / value:.1f} {ru if lang == 'ru' else en}"
    return str(n)


def fmt_duration(sec, t):
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} {t('u_h')} {m:02d} {t('u_m')}"
    if m:
        return f"{m} {t('u_m')} {s:02d} {t('u_s')}"
    return f"{s} {t('u_s')}"


# ------------------------------------------------------------------ прокси
def parse_proxy(text):
    """Строка -> dict для Telethon. Пустая строка -> None.
    Ошибка -> ValueError(ключ_перевода).

    Форматы:
      socks5://user:pass@host:port
      socks4://host:port
      http://user:pass@host:port
      host:port                 (считается socks5)
      host:port:user:pass       (считается socks5)
    """
    text = (text or "").strip()
    if not text:
        return None

    scheme, user, pwd = "socks5", None, None
    try:
        if "://" in text:
            u = urlparse(text)
            scheme = (u.scheme or "").lower()
            host, port = u.hostname, u.port
            user = unquote(u.username) if u.username else None
            pwd = unquote(u.password) if u.password else None
        else:
            parts = text.split(":")
            if len(parts) == 2:
                host, port = parts
            elif len(parts) == 4:
                host, port, user, pwd = parts
            else:
                raise ValueError
            port = int(port)
    except ValueError:
        raise ValueError("proxy_parse")

    if scheme == "socks5h":
        scheme = "socks5"
    if scheme == "https":
        scheme = "http"
    if scheme not in ("socks5", "socks4", "http"):
        raise ValueError("proxy_scheme")
    if not host or not port or not (0 < int(port) < 65536):
        raise ValueError("proxy_hostport")

    return {"proxy_type": scheme, "addr": host, "port": int(port),
            "username": user, "password": pwd, "rdns": True}


# ------------------------------------------------------------------- app
class TelegramUsernameScanner:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.setup_window()

        self.stop_event = threading.Event()
        self.worker = None
        self.clients = []
        self.ui_queue = queue.Queue()

        self.checked = 0
        self.claimed = 0
        self.available = 0
        self.fragment = 0
        self.occupied = 0
        self.invalid = 0
        self.errors_count = 0
        self.total = 0
        self.exhausted = False
        self.guard_hit = False
        self.running = False
        self.start_time = None
        self.end_time = None
        self.last_stats = None

        self.available_usernames = []
        self.fragment_usernames = []
        self.seen = set()

        self.accounts = []
        self.acc_state = {}     # имя -> (текст, вид)
        self.lang = "ru"
        self.mode_key = "mix"
        self.preset_key = "none"

        self._save_job = None
        self._prev_job = None
        self._sanitizing = False

        self.api_id_var = tk.StringVar()
        self.api_hash_var = tk.StringVar()
        self.length_var = tk.StringVar(value="5")
        self.amount_var = tk.StringVar(value="1000")
        self.delay_var = tk.StringVar(value="1.0")
        self.pattern_var = tk.StringVar(value="")
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.autosave_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar()
        self.speed_var = tk.StringVar()
        self.pct_var = tk.StringVar(value="0%")
        self.stat_vars = {key: tk.StringVar(value="0") for key, _, _ in STAT_CARDS}
        self.count_vars = {"free": tk.StringVar(value="0"), "fragment": tk.StringVar(value="0")}

        self.load_config()
        self.status_var.set(self.t("status_ready"))

        self.setup_style()
        self.build_ui()
        self._apply_stats(self.stats_snapshot())
        self.refresh_accounts()
        self.refresh_preview()

        # Автосохранение и «живая» проверка настроек при вводе
        for name, var in (("api", self.api_id_var), ("api", self.api_hash_var),
                          ("pattern", self.pattern_var), ("prefix", self.prefix_var),
                          ("suffix", self.suffix_var), ("other", self.length_var),
                          ("other", self.amount_var), ("other", self.delay_var)):
            var.trace_add("write", lambda *a, n=name: self.on_var_change(n))
        self.autosave_var.trace_add("write", lambda *a: self.schedule_save())

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.poll_queue)
        self.root.after(1000, self.tick)

    # ------------------------------------------------------------- окно
    def setup_window(self):
        try:
            self.scale = max(1.0, float(self.root.winfo_fpixels("1i")) / 96.0)
        except Exception:
            self.scale = 1.0
        try:
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            w = min(self.px(1280), sw - 60)
            h = min(self.px(860), sh - 90)
            self.root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
            self.root.minsize(min(self.px(1120), w), min(self.px(740), h))
        except Exception:
            pass

    def px(self, n):
        return int(n * self.scale)

    # ------------------------------------------------------------ переводы
    def t(self, key, **kw):
        s = TR.get(self.lang, TR["ru"]).get(key)
        if s is None:
            s = TR["ru"].get(key, key)
        return s.format(**kw) if kw else s

    def proxy_label(self, text):
        """Короткая подпись прокси без логина/пароля."""
        try:
            p = parse_proxy(text)
        except ValueError:
            return self.t("proxy_bad")
        if not p:
            return self.t("proxy_none")
        return f"{p['proxy_type']}://{p['addr']}:{p['port']}"

    # ------------------------------------------------------------ config
    def load_config(self):
        data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}
        if not isinstance(data, dict):
            data = {}

        self.api_id_var.set(str(data.get("api_id", "") or ""))
        self.api_hash_var.set(data.get("api_hash", "") or "")
        self.accounts = [a for a in data.get("accounts", []) if isinstance(a, dict) and a.get("name")]
        if data.get("lang") in TR:
            self.lang = data["lang"]
        if data.get("preset") in [k for k, _ in PRESETS]:
            self.preset_key = data["preset"]
        self.pattern_var.set(clean_pattern(str(data.get("pattern", "") or "")))

        gen = data.get("gen") if isinstance(data.get("gen"), dict) else {}
        for key, var in (("length", self.length_var), ("amount", self.amount_var), ("delay", self.delay_var)):
            if key in gen:
                var.set(str(gen[key]))
        self.prefix_var.set(clean_affix(str(gen.get("prefix", ""))))
        self.suffix_var.set(clean_affix(str(gen.get("suffix", ""))))
        if gen.get("mode") in ("mix", "letters", "digits"):
            self.mode_key = gen["mode"]
        self.autosave_var.set(bool(gen.get("autosave", True)))

        # Миграция: старая версия хранила один аккаунт в telegram_scanner.session
        if not self.accounts and os.path.exists(os.path.join(BASE_DIR, "telegram_scanner.session")):
            self.accounts.append({"name": "telegram_scanner", "session": "telegram_scanner",
                                  "proxy": "", "enabled": True})

    def schedule_save(self):
        """Сохранить настройки через 0.5 сек после последнего нажатия клавиши."""
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(500, self.save_config)

    def save_config(self):
        self._save_job = None
        data = {
            "api_id": self.api_id_var.get().strip(),
            "api_hash": self.api_hash_var.get().strip(),
            "accounts": self.accounts,
            "lang": self.lang,
            "preset": self.preset_key,
            "pattern": self.pattern_var.get(),
            "gen": {
                "length": self.length_var.get(), "amount": self.amount_var.get(),
                "delay": self.delay_var.get(), "prefix": self.prefix_var.get(),
                "suffix": self.suffix_var.get(), "mode": self.mode_key,
                "autosave": bool(self.autosave_var.get()),
            },
        }
        tmp = CONFIG_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)  # запись без риска получить пустой/битый файл
        except OSError as e:
            if not getattr(self, "_save_error_shown", False):
                self._save_error_shown = True
                messagebox.showerror(self.t("cfg_err_title"),
                                     self.t("cfg_err", path=CONFIG_PATH, err=e))

    # ------------------------------------------------------------- style
    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=BG)
        for opt, val in (("background", INPUT), ("foreground", FG),
                         ("selectBackground", ACCENT), ("selectForeground", "white")):
            self.root.option_add("*TCombobox*Listbox." + opt, val)

        ui = "Segoe UI"
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=(ui, 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=FG, font=(ui, 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=(ui, 9))
        style.configure("Foot.TLabel", background=BG, foreground=MUTED, font=(ui, 9))
        style.configure("Status.TLabel", background=BG, foreground=FG, font=(ui, 10))
        style.configure("Link.TLabel", background=BG, foreground=BLUE, font=(ui, 9, "underline"))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=(ui, 20, "bold"))
        style.configure("PanelTitle.TLabel", background=PANEL, foreground=FG, font=(ui, 11, "bold"))

        field = dict(fieldbackground=INPUT, foreground=FG, insertcolor=FG, bordercolor=BORDER,
                     lightcolor=BORDER, darkcolor=BORDER, padding=5)
        focus = dict(bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                     darkcolor=[("focus", ACCENT)])
        style.configure("TEntry", **field)
        style.map("TEntry", **focus)
        style.configure("TSpinbox", arrowcolor=MUTED, background=PANEL2, **field)
        style.map("TSpinbox", **focus)
        style.configure("TCombobox", arrowcolor=MUTED, background=PANEL2, selectbackground=INPUT,
                        selectforeground=FG, **field)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", INPUT)], selectforeground=[("readonly", FG)], **focus)

        def button(name, bg, fg, hover, font, padding):
            style.configure(name, background=bg, foreground=fg, font=font, padding=padding,
                            borderwidth=0, focusthickness=0, focuscolor=bg)
            style.map(name, background=[("disabled", DISABLED), ("active", hover)],
                      foreground=[("disabled", MUTED)])

        button("Accent.TButton", ACCENT, "#06101d", ACCENT_DARK, (ui, 10, "bold"), (20, 10))
        button("Stop.TButton", "#e5484d", "white", "#c93a3f", (ui, 10, "bold"), (20, 10))
        button("Small.TButton", PANEL2, FG, "#2a3644", (ui, 9), (9, 5))
        button("Chip.TButton", PANEL2, FG, "#2a3644", ("Consolas", 10), (4, 5))
        button("SegOn.TButton", ACCENT, "#06101d", ACCENT, (ui, 9, "bold"), (10, 4))
        button("SegOff.TButton", PANEL2, MUTED, "#2a3644", (ui, 9, "bold"), (10, 4))

        style.configure("TCheckbutton", background=PANEL, foreground=FG, font=(ui, 10))
        style.map("TCheckbutton", background=[("active", PANEL)],
                  indicatorcolor=[("selected", ACCENT), ("!selected", INPUT)])
        style.configure("TSeparator", background=BORDER)

        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("TNotebook.Tab", background="#121920", foreground=MUTED, padding=(18, 9),
                        font=(ui, 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", FG)])

        style.configure("Treeview", background=INPUT, fieldbackground=INPUT, foreground=FG,
                        rowheight=26, borderwidth=0, font=(ui, 9))
        style.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                        font=(ui, 9, "bold"), borderwidth=0, padding=(6, 4))
        style.map("Treeview", background=[("selected", "#244a7a")], foreground=[("selected", "white")])

        style.configure("Accent.Horizontal.TProgressbar", troughcolor=INPUT, background=ACCENT,
                        bordercolor=INPUT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=8)
        style.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=INPUT, bordercolor=INPUT,
                        arrowcolor=MUTED, lightcolor=PANEL2, darkcolor=PANEL2)
        style.map("Vertical.TScrollbar", background=[("active", "#2a3644")])

    # ---------------------------------------------------------------- UI
    def card(self, parent, bg=PANEL):
        return tk.Frame(parent, bg=bg, highlightbackground=BORDER, highlightcolor=BORDER,
                        highlightthickness=1)

    def build_ui(self):
        self.outer = ttk.Frame(self.root, padding=(20, 16, 20, 14))
        outer = self.outer
        outer.pack(fill="both", expand=True)

        # --- шапка
        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 14))
        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text="Telegram Username Scanner", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=self.t("subtitle"), style="Foot.TLabel").pack(anchor="w")

        seg = ttk.Frame(header)
        seg.pack(side="right", pady=(4, 0))
        for code, label in LANGS:
            style = "SegOn.TButton" if code == self.lang else "SegOff.TButton"
            ttk.Button(seg, text=label, style=style, width=4,
                       command=lambda c=code: self.set_language(c)).pack(side="left")

        # --- тело
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="y", padx=(0, 16))
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.nb = ttk.Notebook(left, width=self.px(390))
        self.nb.pack(fill="both", expand=True)
        self.tab_acc = ttk.Frame(self.nb, style="Panel.TFrame", padding=16)
        self.tab_gen = ttk.Frame(self.nb, style="Panel.TFrame", padding=16)
        self.nb.add(self.tab_acc, text=self.t("tab_accounts"))
        self.nb.add(self.tab_gen, text=self.t("tab_gen"))
        self.build_accounts_tab(self.tab_acc)
        self.build_generation_tab(self.tab_gen)

        self.build_right(right)

        # --- подвал: контакты слева, примечание справа
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        contacts = ttk.Frame(footer)
        contacts.pack(side="left")
        ttk.Label(contacts, text=self.t("contact") + " ", style="Foot.TLabel").pack(side="left")
        tg = ttk.Label(contacts, text=f"✈ {CONTACT_TELEGRAM}", style="Link.TLabel", cursor="hand2")
        tg.pack(side="left")
        tg.bind("<Button-1>", lambda e: webbrowser.open("https://t.me/" + CONTACT_TELEGRAM.lstrip("@")))
        ttk.Label(contacts, text="    ", style="Foot.TLabel").pack(side="left")
        mail = ttk.Label(contacts, text=f"✉ {CONTACT_EMAIL}", style="Link.TLabel", cursor="hand2")
        mail.pack(side="left")
        mail.bind("<Button-1>", lambda e: webbrowser.open("mailto:" + CONTACT_EMAIL))
        ttk.Label(footer, text=self.t("footer"), style="Foot.TLabel").pack(side="right")

    def build_right(self, right):
        top = ttk.Frame(right)
        top.pack(fill="x")
        self.start_btn = ttk.Button(top, text=self.t("btn_start"), style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(top, text=self.t("btn_stop"), style="Stop.TButton",
                                   command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        ttk.Label(top, textvariable=self.status_var, style="Status.TLabel", wraplength=self.px(560),
                  justify="left").pack(side="left", padx=(14, 0))

        # --- карточки статистики
        cards = ttk.Frame(right)
        cards.pack(fill="x", pady=(14, 0))
        for i, (key, trk, color) in enumerate(STAT_CARDS):
            cards.columnconfigure(i, weight=1, uniform="card")
            c = self.card(cards)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            tk.Label(c, text=self.t(trk), bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(
                anchor="w", padx=12, pady=(9, 0))
            tk.Label(c, textvariable=self.stat_vars[key], bg=PANEL, fg=color,
                     font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=12, pady=(0, 8))

        # --- прогресс
        pr = ttk.Frame(right)
        pr.pack(fill="x", pady=(12, 0))
        self.progress = ttk.Progressbar(pr, mode="determinate", maximum=100,
                                        style="Accent.Horizontal.TProgressbar")
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Label(pr, textvariable=self.pct_var, style="Foot.TLabel", width=5, anchor="e").pack(
            side="left", padx=(8, 0))
        ttk.Label(right, textvariable=self.speed_var, style="Foot.TLabel").pack(anchor="w", pady=(4, 10))

        # --- две колонки результатов
        res = ttk.Frame(right)
        res.pack(fill="both", expand=True)
        res.rowconfigure(0, weight=1)
        for col in (0, 1):
            res.columnconfigure(col, weight=1, uniform="res")
        self.output = self.build_result_pane(res, 0, "free_title", "pane_hint_free", GREEN, "free")
        self.fragment_box = self.build_result_pane(res, 1, "fragment_title", "pane_hint_fragment",
                                                   AMBER, "fragment")

        # --- журнал
        logc = self.card(right)
        logc.pack(fill="x", pady=(12, 0))
        head = ttk.Frame(logc, style="Panel.TFrame")
        head.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Label(head, text=self.t("log_title"), style="PanelTitle.TLabel").pack(side="left")
        ttk.Button(head, text=self.t("btn_clear"), style="Small.TButton",
                   command=self.clear_log).pack(side="right")
        self.log_box = self.make_text(logc, fg=MUTED, expand=False, height=6, font_size=9, wrap="word")
        self.log_box.tag_configure("err", foreground=RED)
        self.log_box.tag_configure("warn", foreground=AMBER)
        self.log_box.tag_configure("ok", foreground=GREEN)

    def build_result_pane(self, parent, col, title_key, hint_key, color, kind):
        pane = self.card(parent)
        pane.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
        tk.Frame(pane, bg=color, height=3).pack(fill="x")     # цветная кромка = категория
        head = ttk.Frame(pane, style="Panel.TFrame")
        head.pack(fill="x", padx=12, pady=(10, 0))
        ttk.Label(head, text=self.t(title_key), style="PanelTitle.TLabel").pack(side="left")
        tk.Label(head, textvariable=self.count_vars[kind], bg=color, fg="#06101d",
                 font=("Segoe UI", 9, "bold"), padx=8).pack(side="left", padx=8)
        ttk.Button(head, text=self.t("btn_save"), style="Small.TButton",
                   command=lambda: self.save_list(self.items_of(kind), kind)).pack(side="right")
        ttk.Button(head, text=self.t("btn_copy"), style="Small.TButton",
                   command=lambda: self.copy_list(self.items_of(kind))).pack(side="right", padx=(0, 6))
        ttk.Label(pane, text=self.t(hint_key), style="Muted.TLabel").pack(anchor="w", padx=12, pady=(4, 0))
        text = self.make_text(pane, fg=color, expand=True, height=6, font_size=12)
        text.bind("<Double-Button-1>", lambda e: self.on_pane_double_click(e, kind))
        return text

    def items_of(self, kind):
        return self.available_usernames if kind == "free" else self.fragment_usernames

    def make_text(self, parent, fg, expand, height, font_size=11, wrap="none"):
        holder = ttk.Frame(parent, style="Panel.TFrame")
        holder.pack(fill="both" if expand else "x", expand=expand, padx=12, pady=(6, 12))
        text = tk.Text(
            holder, bg=INPUT, fg=fg, insertbackground=FG, selectbackground=ACCENT,
            selectforeground="white", relief="flat", bd=0, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=BORDER, font=("Consolas", font_size),
            padx=10, pady=8, height=height, wrap=wrap,
        )
        sb = ttk.Scrollbar(holder, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return text

    def add_field(self, parent, label, variable, hint="", show=None):
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", pady=(8, 3))
        ttk.Entry(parent, textvariable=variable, show=show).pack(fill="x")
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

    def grid_field(self, parent, row, col, label, cls, **kw):
        padx = (0, 0) if col == 0 else (8, 0)
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(
            row=row * 2, column=col, sticky="w", padx=padx, pady=(10, 3))
        widget = cls(parent, **kw)
        widget.grid(row=row * 2 + 1, column=col, sticky="ew", padx=padx)
        return widget

    # --------------------------------------------------------- вкладка «Аккаунты»
    def build_accounts_tab(self, tab):
        ttk.Label(tab, text=self.t("api_title"), style="PanelTitle.TLabel").pack(anchor="w")
        self.add_field(tab, self.t("api_id"), self.api_id_var, "")

        ttk.Label(tab, text=self.t("api_hash"), style="Panel.TLabel").pack(anchor="w", pady=(8, 3))
        row = ttk.Frame(tab, style="Panel.TFrame")
        row.pack(fill="x")
        self.hash_entry = ttk.Entry(row, textvariable=self.api_hash_var, show="•")
        self.hash_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="👁", style="Small.TButton", width=3,
                   command=self.toggle_hash).pack(side="left", padx=(6, 0))
        ttk.Label(tab, text=self.t("api_hint"), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        ttk.Separator(tab).pack(fill="x", pady=14)
        ttk.Label(tab, text=self.t("accounts"), style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))

        wrap = ttk.Frame(tab, style="Panel.TFrame")
        wrap.pack(fill="x")
        self.tree = ttk.Treeview(wrap, columns=("acc", "proxy", "state"), show="headings",
                                 height=7, selectmode="browse")
        self.tree.heading("acc", text=self.t("col_acc"), anchor="w")
        self.tree.heading("proxy", text=self.t("col_proxy"), anchor="w")
        self.tree.heading("state", text=self.t("col_state"), anchor="w")
        self.tree.column("acc", width=self.px(105), anchor="w")
        self.tree.column("proxy", width=self.px(125), anchor="w")
        self.tree.column("state", width=self.px(110), anchor="w")
        self.tree.pack(fill="x")
        self.tree.bind("<Double-1>", lambda e: self.toggle_account())
        for tag, color in (("ok", GREEN), ("warn", AMBER), ("bad", RED), ("wait", BLUE),
                           ("done", MUTED), ("off", "#5b6775")):
            self.tree.tag_configure(tag, foreground=color)

        self.empty_holder = ttk.Frame(tab, style="Panel.TFrame")
        self.empty_holder.pack(fill="x")
        self.empty_lbl = ttk.Label(self.empty_holder, text=self.t("no_accounts_hint"), style="Muted.TLabel",
                                   wraplength=self.px(350), justify="left")

        ttk.Button(tab, text=self.t("btn_add"), style="Accent.TButton",
                   command=self.add_account).pack(fill="x", pady=(10, 6))
        btns = ttk.Frame(tab, style="Panel.TFrame")
        btns.pack(fill="x")
        for i, (key, cmd) in enumerate([("btn_proxy", self.edit_account),
                                        ("btn_toggle", self.toggle_account),
                                        ("btn_remove", self.remove_account)]):
            btns.columnconfigure(i, weight=1, uniform="b")
            ttk.Button(btns, text=self.t(key), style="Small.TButton", command=cmd).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))

        ttk.Label(tab, style="Muted.TLabel", wraplength=self.px(350), justify="left",
                  text=self.t("acc_hint")).pack(anchor="w", pady=(12, 0))

    def toggle_hash(self):
        self.hash_entry.configure(show="" if self.hash_entry.cget("show") else "•")

    # --------------------------------------------------------- вкладка «Генерация»
    def build_generation_tab(self, tab):
        ttk.Label(tab, text=self.t("template"), style="Panel.TLabel").pack(anchor="w", pady=(0, 3))
        self.preset_combo = ttk.Combobox(
            tab, values=[self.t("preset_" + k) for k, _ in PRESETS], state="readonly")
        self.preset_combo.current([k for k, _ in PRESETS].index(self.preset_key))
        self.preset_combo.pack(fill="x")
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset)

        # Либо блок шаблона, либо блок случайной генерации (apply_pattern_state)
        self.mode_holder = ttk.Frame(tab, style="Panel.TFrame")
        self.mode_holder.pack(fill="x")

        self.pattern_frame = ttk.Frame(self.mode_holder, style="Panel.TFrame")
        ttk.Label(self.pattern_frame, text=self.t("pattern"), style="Panel.TLabel").pack(
            anchor="w", pady=(10, 3))
        self.pattern_entry = ttk.Entry(self.pattern_frame, textvariable=self.pattern_var,
                                       font=("Consolas", 12))
        self.pattern_entry.pack(fill="x")
        chips = ttk.Frame(self.pattern_frame, style="Panel.TFrame")
        chips.pack(fill="x", pady=(6, 0))
        tokens = [("c", "chip_c"), ("v", "chip_v"), ("l", "chip_l"), ("d", "chip_d"),
                  ("x", "chip_x"), ("_", None), ("A", None), ("B", None),
                  ("C", None), ("D", None), ("⌫", None), ("✕", None)]
        for c in range(4):
            chips.columnconfigure(c, weight=1, uniform="chip")
        for i, (tok, cap) in enumerate(tokens):
            label = f"{tok} {self.t(cap)}" if cap else tok
            ttk.Button(chips, text=label, style="Chip.TButton",
                       command=lambda tk_=tok: self.chip_click(tk_)).grid(
                row=i // 4, column=i % 4, sticky="ew", padx=2, pady=2)
        ttk.Label(self.pattern_frame, text=self.t("pattern_hint"), style="Muted.TLabel",
                  wraplength=self.px(350), justify="left").pack(anchor="w", pady=(4, 0))

        self.random_frame = ttk.Frame(self.mode_holder, style="Panel.TFrame")
        ttk.Label(self.random_frame, text=self.t("length"), style="Panel.TLabel").pack(
            anchor="w", pady=(10, 3))
        ttk.Spinbox(self.random_frame, from_=5, to=32, increment=1,
                    textvariable=self.length_var).pack(fill="x")
        ttk.Label(self.random_frame, text=self.t("charset"), style="Panel.TLabel").pack(
            anchor="w", pady=(10, 3))
        modes = ["mix", "letters", "digits"]
        self.mode_combo = ttk.Combobox(self.random_frame, values=[self.t("mode_" + m) for m in modes],
                                       state="readonly")
        self.mode_combo.current(modes.index(self.mode_key))
        self.mode_combo.pack(fill="x")
        self.mode_combo.bind("<<ComboboxSelected>>", self.on_mode)

        grid = ttk.Frame(tab, style="Panel.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(0, weight=1, uniform="g")
        grid.columnconfigure(1, weight=1, uniform="g")
        self.grid_field(grid, 0, 0, self.t("prefix"), ttk.Entry, textvariable=self.prefix_var)
        self.grid_field(grid, 0, 1, self.t("suffix"), ttk.Entry, textvariable=self.suffix_var)
        self.grid_field(grid, 1, 0, self.t("amount"), ttk.Spinbox, from_=1, to=1000000,
                        increment=100, textvariable=self.amount_var)
        self.grid_field(grid, 1, 1, self.t("delay"), ttk.Spinbox, from_=0.1, to=10.0,
                        increment=0.1, textvariable=self.delay_var)

        ttk.Checkbutton(tab, text=self.t("autosave"), variable=self.autosave_var).pack(
            anchor="w", pady=(12, 0))

        # --- предпросмотр: показывает, какие ники реально получатся
        pv = self.card(tab, bg=PANEL2)
        pv.pack(fill="x", pady=(14, 0))
        head = tk.Frame(pv, bg=PANEL2)
        head.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(head, text=self.t("preview_title"), bg=PANEL2, fg=FG,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(head, text="🎲 " + self.t("preview_new"), style="Small.TButton",
                   command=self.refresh_preview).pack(side="right")
        wl = self.px(340)
        self.prev_samples = tk.Label(pv, text="", bg=PANEL2, fg=GREEN, font=("Consolas", 12),
                                     justify="left", anchor="w", wraplength=wl)
        self.prev_samples.pack(fill="x", padx=12)
        self.prev_status = tk.Label(pv, text="", bg=PANEL2, fg=GREEN, font=("Segoe UI", 9),
                                    justify="left", anchor="w", wraplength=wl)
        self.prev_status.pack(fill="x", padx=12, pady=(6, 0))
        self.prev_combos = tk.Label(pv, text="", bg=PANEL2, fg=MUTED, font=("Segoe UI", 9),
                                    justify="left", anchor="w", wraplength=wl)
        self.prev_combos.pack(fill="x", padx=12)
        self.prev_note = tk.Label(pv, text="", bg=PANEL2, fg=AMBER, font=("Segoe UI", 9),
                                  justify="left", anchor="w", wraplength=wl)
        self.prev_note.pack(fill="x", padx=12, pady=(0, 10))

        self.apply_pattern_state()

    def apply_pattern_state(self):
        """Шаблон: свой блок с кнопками. Без шаблона: длина и набор символов."""
        self.pattern_frame.pack_forget()
        self.random_frame.pack_forget()
        (self.pattern_frame if self.preset_key != "none" else self.random_frame).pack(fill="x")

    def on_preset(self, event=None):
        key, pattern = PRESETS[self.preset_combo.current()]
        self.preset_key = key
        if key not in ("none", "custom"):
            self.pattern_var.set(pattern)
        self.apply_pattern_state()
        self.refresh_preview()
        self.schedule_save()

    def on_mode(self, event=None):
        self.mode_key = ["mix", "letters", "digits"][self.mode_combo.current()]
        self.refresh_preview()
        self.schedule_save()

    def chip_click(self, token):
        if token == "⌫":
            self.pattern_var.set(self.pattern_var.get()[:-1])
        elif token == "✕":
            self.pattern_var.set("")
        else:
            self.pattern_entry.insert("insert", token)

    # ---------------------------------------- «живая» проверка настроек
    def on_var_change(self, which):
        if self._sanitizing:
            return
        self._sanitizing = True
        try:
            if which == "pattern":
                value = self.pattern_var.get()
                cleaned = clean_pattern(value)
                if cleaned != value:
                    self.pattern_var.set(cleaned)
                preset = dict(PRESETS).get(self.preset_key, "")
                if self.preset_key not in ("none", "custom") and cleaned != preset:
                    self.preset_key = "custom"
                    self.preset_combo.current([k for k, _ in PRESETS].index("custom"))
            elif which in ("prefix", "suffix"):
                var = self.prefix_var if which == "prefix" else self.suffix_var
                value = var.get()
                cleaned = clean_affix(value)
                if cleaned != value:
                    var.set(cleaned)
        finally:
            self._sanitizing = False
        if which != "api":
            self.schedule_preview()
        self.schedule_save()

    def schedule_preview(self):
        if not hasattr(self, "prev_status"):
            return
        if self._prev_job is not None:
            try:
                self.root.after_cancel(self._prev_job)
            except Exception:
                pass
        self._prev_job = self.root.after(150, self.refresh_preview)

    def parse_generation(self):
        """Разбор настроек генерации без диалогов. -> (cfg, None) или (None, (ключ, параметры))."""
        use_pattern = self.preset_key != "none"
        try:
            amount = int(self.amount_var.get().strip())
            delay = float(self.delay_var.get().strip().replace(",", "."))
            length = 0 if use_pattern else int(self.length_var.get().strip())
        except ValueError:
            return None, ("err_numbers", {})
        if amount < 1:
            return None, ("err_amount", {})
        delay = max(0.1, delay)

        prefix = clean_affix(self.prefix_var.get())
        suffix = clean_affix(self.suffix_var.get())

        if use_pattern:
            pattern = self.pattern_var.get().strip()
            err = validate_pattern(pattern, prefix, suffix)
            if err:
                return None, err
            length = len(prefix) + len(pattern) + len(suffix)
            chars = DEFAULT_CHARS
        else:
            pattern = ""
            if not (5 <= length <= 32):
                return None, ("err_length", {})
            if len(prefix) + len(suffix) > length:
                return None, ("err_affix_len", {})
            if prefix and not prefix[0].isalpha():
                return None, ("err_prefix_letter", {})
            if suffix.endswith("_"):
                return None, ("err_pattern_last", {})
            touching = length - len(prefix) - len(suffix) == 0
            if "__" in prefix or "__" in suffix or (touching and prefix.endswith("_") and suffix.startswith("_")):
                return None, ("err_pattern_dunder", {})
            chars = {"letters": string.ascii_lowercase, "digits": string.digits}.get(
                self.mode_key, DEFAULT_CHARS)

        cfg = {"length": length, "amount": amount, "delay": delay, "chars": chars,
               "prefix": prefix, "suffix": suffix, "pattern": pattern}
        if generate_username(cfg) is None:
            return None, ("err_gen_fail", {})
        return cfg, None

    def refresh_preview(self):
        self._prev_job = None
        if not hasattr(self, "prev_status"):
            return
        cfg, err = self.parse_generation()
        if err:
            self.prev_samples.configure(text="")
            self.prev_status.configure(text=self.t(err[0], **err[1]), fg=RED)
            self.prev_combos.configure(text="")
            self.prev_note.configure(text="")
            self.set_gen_warning(True)
            return

        samples = []
        for _ in range(80):
            u = generate_username(cfg)
            if u and u not in samples:
                samples.append(u)
            if len(samples) == 6:
                break
        rows = ["   ".join(samples[i:i + 3]) for i in range(0, len(samples), 3)]
        self.prev_samples.configure(text="\n".join(rows))
        self.prev_status.configure(text=self.t("preview_ok"), fg=GREEN)

        combos = count_combinations(cfg)
        if combos < cfg["amount"]:
            self.prev_combos.configure(text=self.t("combos_less", n=fmt_count(combos, self.lang)), fg=AMBER)
        else:
            self.prev_combos.configure(text=self.t("combos", n=fmt_count(combos, self.lang)), fg=MUTED)
        self.prev_note.configure(text=self.t("warn_delay") if cfg["delay"] < 1.0 else "")
        self.set_gen_warning(False)

    def set_gen_warning(self, bad):
        try:
            self.nb.tab(self.tab_gen, text=self.t("tab_gen_warn" if bad else "tab_gen"))
        except Exception:
            pass

    # ------------------------------------------------------ смена языка
    def set_language(self, code):
        if code == self.lang:
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(self.t("busy_title"), self.t("busy_msg"))
            return
        self.lang = code
        self.save_config()
        self.rebuild_ui()

    def rebuild_ui(self):
        """Пересобрать интерфейс на новом языке, сохранив введённые данные и результаты."""
        log_text = self.log_box.get("1.0", "end-1c")
        self.outer.destroy()
        self.acc_state.clear()
        self.status_var.set(self.t("status_ready"))

        self.build_ui()
        for line in log_text.splitlines():
            self._append_log(line)
        for u in self.available_usernames:
            self._add_result("free", u)
        for u in self.fragment_usernames:
            self._add_result("fragment", u)
        self._apply_stats(self.last_stats or self.stats_snapshot())
        self.refresh_accounts()
        self.refresh_preview()

    # ------------------------------------------------- accounts management
    def is_busy(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(self.t("busy_title"), self.t("busy_msg"))
            return True
        return False

    def selected_account(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(self.t("tab_accounts"), self.t("accounts_pick"))
            return None
        for a in self.accounts:
            if a["name"] == sel[0]:
                return a
        return None

    def refresh_accounts(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for a in self.accounts:
            enabled = a.get("enabled", True)
            text, kind = self.acc_state.get(a["name"], ("", ""))
            if not enabled and not text:
                text, kind = self.t("acc_disabled"), "off"
            self.tree.insert("", "end", iid=a["name"], tags=(kind,) if kind else (), values=(
                f"{'✓' if enabled else '✗'} {a['name']}",
                self.proxy_label(a.get("proxy", "")),
                text,
            ))
        for iid in sel:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
        if self.accounts:
            self.empty_lbl.pack_forget()
        else:
            self.empty_lbl.pack(anchor="w", pady=(6, 0))

    def _set_state_ui(self, name, text, kind=""):
        self.acc_state[name] = (text, kind)
        self.refresh_accounts()

    def set_acc_state(self, name, text, kind=""):
        self.post(self._set_state_ui, name, text, kind)

    def account_dialog(self, acc=None):
        """Окно добавления/редактирования. Возвращает dict {name, proxy} или None."""
        editing = acc is not None
        dlg = tk.Toplevel(self.root)
        dlg.title(self.t("dlg_edit") if editing else self.t("dlg_new"))
        dlg.configure(bg=PANEL)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        frm = ttk.Frame(dlg, style="Panel.TFrame", padding=18)
        frm.pack(fill="both", expand=True)

        name_var = tk.StringVar(value=acc["name"] if editing else "")
        proxy_var = tk.StringVar(value=acc.get("proxy", "") if editing else "")

        ttk.Label(frm, text=self.t("dlg_name"), style="Panel.TLabel").pack(anchor="w")
        name_entry = ttk.Entry(frm, textvariable=name_var, width=48,
                               state="disabled" if editing else "normal")
        name_entry.pack(fill="x", pady=(3, 10))

        ttk.Label(frm, text=self.t("dlg_proxy"), style="Panel.TLabel").pack(anchor="w")
        ttk.Entry(frm, textvariable=proxy_var, width=48).pack(fill="x", pady=(3, 2))
        ttk.Label(frm, style="Muted.TLabel", justify="left",
                  text=self.t("dlg_formats")).pack(anchor="w", pady=(0, 8))
        ttk.Label(frm, style="Muted.TLabel", justify="left",
                  text=self.t("dlg_phone_hint")).pack(anchor="w")

        result = {}

        def ok():
            name = name_var.get().strip()
            proxy = proxy_var.get().strip()
            if not editing:
                if not re.fullmatch(r"[A-Za-z0-9_\-]{1,32}", name):
                    messagebox.showerror(self.t("err"), self.t("err_name"), parent=dlg)
                    return
                if any(a["name"].lower() == name.lower() for a in self.accounts):
                    messagebox.showerror(self.t("err"), self.t("err_dup"), parent=dlg)
                    return
            try:
                parse_proxy(proxy)
            except ValueError as e:
                messagebox.showerror(self.t("err_proxy_title"), self.t(str(e)), parent=dlg)
                return
            result.update(name=name, proxy=proxy)
            dlg.destroy()

        row = ttk.Frame(frm, style="Panel.TFrame")
        row.pack(fill="x", pady=(16, 0))
        ttk.Button(row, text=self.t("dlg_save"), style="Accent.TButton", command=ok).pack(side="right")
        ttk.Button(row, text=self.t("dlg_cancel"), style="Small.TButton",
                   command=dlg.destroy).pack(side="right", padx=8)

        dlg.bind("<Return>", lambda e: ok())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.update_idletasks()
        dlg.grab_set()
        name_entry.focus_set()
        self.root.wait_window(dlg)
        return result or None

    def add_account(self):
        if self.is_busy():
            return
        res = self.account_dialog()
        if not res:
            return
        self.accounts.append({
            "name": res["name"],
            "session": os.path.join("sessions", res["name"]),
            "proxy": res["proxy"],
            "enabled": True,
        })
        self.save_config()
        self.refresh_accounts()

    def edit_account(self):
        if self.is_busy():
            return
        acc = self.selected_account()
        if not acc:
            return
        res = self.account_dialog(acc)
        if res:
            acc["proxy"] = res["proxy"]
            self.save_config()
            self.refresh_accounts()

    def toggle_account(self):
        if self.is_busy():
            return
        acc = self.selected_account()
        if not acc:
            return
        acc["enabled"] = not acc.get("enabled", True)
        self.acc_state.pop(acc["name"], None)
        self.save_config()
        self.refresh_accounts()

    def remove_account(self):
        if self.is_busy():
            return
        acc = self.selected_account()
        if not acc:
            return
        if not messagebox.askyesno(self.t("remove_title"), self.t("remove_q", name=acc["name"])):
            return
        self.accounts.remove(acc)
        self.acc_state.pop(acc["name"], None)
        self.save_config()
        self.refresh_accounts()

    # --------------------------------------------- thread -> UI communication
    def post(self, func, *args, **kwargs):
        """Потокобезопасно выполнить func в главном потоке Tk."""
        self.ui_queue.put((func, args, kwargs))

    def poll_queue(self):
        try:
            while True:
                func, args, kwargs = self.ui_queue.get_nowait()
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    print("UI error:", e)
        except queue.Empty:
            pass
        self.root.after(50, self.poll_queue)

    def tick(self):
        """Раз в секунду обновляет скорость и оставшееся время, пока идёт сканирование."""
        if self.running:
            try:
                self._apply_stats(self.stats_snapshot())
            except Exception:
                pass
        self.root.after(1000, self.tick)

    def _append(self, widget, text):
        widget.insert("end", text + "\n")
        widget.see("end")

    def _append_log(self, text):
        low = text.lower()
        tag = ""
        if "error" in low or "ошибк" in low or "guard" in low:
            tag = "err"
        elif "flood" in low or "флуд" in low:
            tag = "warn"
        elif "авторизация успешна" in low or "logged in" in low:
            tag = "ok"
        if tag:
            self.log_box.insert("end", text + "\n", tag)
        else:
            self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def _add_result(self, kind, text):
        widget = self.output if kind == "free" else self.fragment_box
        self._append(widget, text)
        self.count_vars[kind].set(str(len(self.items_of(kind))))

    def clear_log(self):
        self.log_box.delete("1.0", "end")

    def log(self, text):
        self.post(self._append_log, text)

    def set_status(self, text):
        self.post(self.status_var.set, text)

    def stats_snapshot(self):
        speed = ""
        if self.start_time:
            end = self.end_time or time.monotonic()
            elapsed = max(0.0, end - self.start_time)
            if self.end_time:
                per_min = self.checked / elapsed * 60 if elapsed > 0 else 0
                speed = self.t("speed_done", s=f"{per_min:.0f}", el=fmt_duration(elapsed, self.t))
            elif elapsed >= 3 and self.checked > 0:
                rate = self.checked / elapsed
                eta = max(0, self.total - self.checked) / rate
                speed = self.t("speed", s=f"{rate * 60:.0f}", eta=fmt_duration(eta, self.t),
                               el=fmt_duration(elapsed, self.t))
            else:
                speed = self.t("speed_calc")
        return {
            "checked": self.checked, "free": self.available, "fragment": self.fragment,
            "taken": self.occupied, "invalid": self.invalid, "errors": self.errors_count,
            "pct": min(100.0, self.checked / max(1, self.total) * 100), "speed": speed,
        }

    def _apply_stats(self, vals):
        self.last_stats = vals
        for key, _, _ in STAT_CARDS:
            self.stat_vars[key].set(str(vals[key]))
        self.speed_var.set(vals["speed"])
        self.pct_var.set(f"{vals['pct']:.0f}%")
        try:
            self.progress.configure(value=vals["pct"])
        except (tk.TclError, AttributeError):
            pass

    def update_stats(self):
        self.post(self._apply_stats, self.stats_snapshot())

    def set_running(self, running):
        self.post(self.start_btn.configure, state="disabled" if running else "normal")
        self.post(self.stop_btn.configure, state="normal" if running else "disabled")

    # ------------------------------------------------------------ validation
    def show_error(self, key, **kw):
        messagebox.showerror(self.t("err"), self.t(key, **kw))
        return None

    def validate(self):
        try:
            api_id = int(self.api_id_var.get().strip())
        except ValueError:
            self.nb.select(self.tab_acc)
            return self.show_error("err_api_id")

        api_hash = self.api_hash_var.get().strip()
        if len(api_hash) < 16:
            self.nb.select(self.tab_acc)
            return self.show_error("err_api_hash")

        accounts = [copy.deepcopy(a) for a in self.accounts if a.get("enabled", True)]
        if not accounts:
            self.nb.select(self.tab_acc)
            return self.show_error("err_no_accounts")
        for a in accounts:
            try:
                parse_proxy(a.get("proxy", ""))
            except ValueError as e:
                self.nb.select(self.tab_acc)
                messagebox.showerror(self.t("err_proxy_title"),
                                     self.t("err_proxy_acc", name=a["name"], err=self.t(str(e))))
                return None

        gen, err = self.parse_generation()
        if err:
            self.nb.select(self.tab_gen)
            return self.show_error(err[0], **err[1])

        cfg = dict(gen)
        cfg.update(api_id=api_id, api_hash=api_hash, accounts=accounts,
                   autosave=bool(self.autosave_var.get()))
        return cfg

    # ---------------------------------------------------------- start / stop
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        cfg = self.validate()
        if not cfg:
            return
        self.save_config()

        self.checked = self.claimed = 0
        self.available = self.fragment = self.occupied = self.invalid = self.errors_count = 0
        self.exhausted = False
        self.guard_hit = False
        self.total = cfg["amount"]
        self.start_time = None
        self.end_time = None
        self.available_usernames.clear()
        self.fragment_usernames.clear()
        self.seen.clear()
        self.acc_state.clear()
        self.refresh_accounts()
        for widget in (self.output, self.fragment_box, self.log_box):
            widget.delete("1.0", "end")
        for var in self.count_vars.values():
            var.set("0")
        self._apply_stats(self.stats_snapshot())

        self.stop_event.clear()
        self.running = True
        self.set_running(True)
        self.set_status(self.t("stat_connecting"))

        self.worker = threading.Thread(target=self.worker_main, args=(cfg,), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.set_status(self.t("stat_stopping"))

    def worker_main(self, cfg):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        failed = False
        try:
            loop.run_until_complete(self.scan(cfg))
        except Exception as e:
            failed = True
            self.errors_count += 1
            self.log(self.t("log_error", err=f"{type(e).__name__}: {e}"))
            self.set_status(self.t("stat_error"))
        finally:
            for c in self.clients:
                try:
                    loop.run_until_complete(c.disconnect())
                except Exception:
                    pass
            self.clients = []
            loop.close()
            self.running = False
            if self.start_time:
                self.end_time = time.monotonic()
            self.update_stats()
            self.set_running(False)
            if self.stop_event.is_set() and not failed and not self.guard_hit:
                self.set_status(self.t("stat_stopped", n=self.available))

    # ------------------------------------------------------------------ auth
    async def ask_string_async(self, title, prompt, secret=False):
        """Показать диалог в главном потоке и дождаться ответа (потокобезопасно)."""
        fut = concurrent.futures.Future()

        def ask():
            try:
                kw = {"show": "*"} if secret else {}
                value = simpledialog.askstring(title, prompt, parent=self.root, **kw)
                fut.set_result(value)
            except Exception as e:
                fut.set_exception(e)

        self.post(ask)
        return await asyncio.wrap_future(fut)

    async def authenticate(self, cfg, acc):
        """Подключает аккаунт (с его прокси) и при необходимости авторизует. Возвращает client или None."""
        name = acc["name"]
        session = acc.get("session") or os.path.join("sessions", name)
        if not os.path.isabs(session):
            session = os.path.join(BASE_DIR, session)
        os.makedirs(os.path.dirname(session), exist_ok=True)

        client = TelegramClient(
            session, cfg["api_id"], cfg["api_hash"],
            proxy=parse_proxy(acc.get("proxy", "")),
            flood_sleep_threshold=0,   # FloodWait обрабатываем сами и показываем в окне
            connection_retries=2,
            retry_delay=1,
            timeout=15,
        )
        self.clients.append(client)
        await client.connect()

        if await client.is_user_authorized():
            return client

        phone = await self.ask_string_async(
            self.t("auth_title", name=name), self.t("auth_phone", name=name))
        if not phone:
            return None
        phone = phone.strip().replace(" ", "")

        sent = await client.send_code_request(phone)
        code_hash = sent.phone_code_hash

        def describe(t):
            tname = type(t).__name__ if t is not None else ""
            key = {
                "SentCodeTypeApp": "how_app", "SentCodeTypeSms": "how_sms",
                "SentCodeTypeCall": "how_call", "SentCodeTypeFlashCall": "how_flash",
                "SentCodeTypeMissedCall": "how_missed",
            }.get(tname, "how_unknown")
            return self.t(key)

        for _ in range(6):
            how = describe(sent.type)
            self.log(self.t("log_code_sent", name=name, how=how))
            code = await self.ask_string_async(
                self.t("code_title", name=name), self.t("code_prompt", name=name, how=how))
            if not code:
                return None
            code = code.strip().replace(" ", "")

            if code.lower() == "r":
                try:
                    sent = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone, phone_code_hash=code_hash))
                    code_hash = sent.phone_code_hash
                except errors.RPCError as e:
                    self.log(self.t("log_resend_fail", name=name, err=f"{type(e).__name__}: {e}"))
                continue

            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
                break
            except errors.SessionPasswordNeededError:
                password = await self.ask_string_async(
                    self.t("pwd_title", name=name), self.t("pwd_prompt"), secret=True)
                if not password:
                    return None
                await client.sign_in(password=password)
                break
            except errors.PhoneCodeInvalidError:
                self.log(self.t("log_bad_code", name=name))
        return client if await client.is_user_authorized() else None

    # ------------------------------------------------------------------ scan
    async def check_one(self, client, username):
        """Возвращает 'free' | 'fragment' | 'occupied' | 'invalid'. FloodWait пробрасывается наружу."""
        try:
            ok = await client(functions.account.CheckUsernameRequest(username=username))
            return "free" if ok else "occupied"
        except errors.UsernameOccupiedError:
            return "occupied"
        except errors.UsernameInvalidError:
            return "invalid"
        except errors.FloodWaitError:
            raise
        except errors.RPCError as e:
            # Telethon подставляет в .message человеческий текст, поэтому смотрим и на имя класса.
            info = f"{type(e).__name__} {getattr(e, 'message', '') or ''} {e}".upper()
            # Ник продаётся на Fragment — обычной регистрацией его не взять.
            if "PURCHASEAVAILABLE" in info or "PURCHASE_AVAILABLE" in info or "FRAGMENT" in info:
                return "fragment"
            if "USERNAMENOTMODIFIED" in info or "USERNAME_NOT_MODIFIED" in info:
                return "occupied"
            if "USERNAMEINVALID" in info or "USERNAME_INVALID" in info:
                return "invalid"
            raise

    def next_username(self, cfg):
        """Следующий ещё не проверявшийся username или None, если комбинации кончились."""
        for _ in range(5000):
            username = generate_username(cfg)
            if not username:
                break
            if username not in self.seen:
                self.seen.add(username)
                return username
        if not self.exhausted:
            self.exhausted = True
            self.log(self.t("log_exhausted"))
        return None

    def check_guard(self):
        """Если Telegram отклоняет почти все ники как недопустимые — останавливаемся, чтобы не жечь лимиты."""
        if self.guard_hit or self.invalid < GUARD_MIN_INVALID or self.invalid < 0.9 * self.checked:
            return
        self.guard_hit = True
        self.log(self.t("log_guard", n=self.invalid, m=self.checked))
        self.set_status(self.t("stat_guard"))
        self.stop_event.set()
        self.post(messagebox.showwarning, self.t("guard_title"),
                  self.t("guard_msg", n=self.invalid, m=self.checked))

    async def scan(self, cfg):
        # 1) Последовательно подключаем и авторизуем аккаунты (диалоги ввода кода идут по очереди).
        ready = []
        for acc in cfg["accounts"]:
            if self.stop_event.is_set():
                break
            name = acc["name"]
            self.set_acc_state(name, self.t("st_login"), "wait")
            self.set_status(self.t("stat_connecting_acc", name=name))
            try:
                client = await self.authenticate(cfg, acc)
            except Exception as e:
                self.log(self.t("log_login_err", name=name, err=f"{type(e).__name__}: {e}"))
                self.set_acc_state(name, self.t("st_login_err"), "bad")
                continue
            if client is None:
                self.log(self.t("log_not_auth", name=name))
                self.set_acc_state(name, self.t("st_not_in"), "bad")
                continue
            self.log(self.t("log_auth_ok", name=name, proxy=self.proxy_label(acc.get("proxy", ""))))
            ready.append((acc, client))

        if self.stop_event.is_set():
            return
        if not ready:
            self.set_status(self.t("stat_no_acc"))
            return

        self.start_time = time.monotonic()
        self.set_status(self.t("stat_running", n=len(ready)))
        self.log(self.t("log_plan", n=cfg["amount"], k=len(ready), d=cfg["delay"]))

        # 2) Все аккаунты сканируют параллельно, каждый со своей задержкой и своим прокси.
        await asyncio.gather(*[self.account_loop(cfg, acc, client) for acc, client in ready])

        self.update_stats()
        if not self.stop_event.is_set():
            tail = self.t("tail_saved") if cfg["autosave"] and self.available else ""
            incomplete = ""
            if self.checked < cfg["amount"] and not self.exhausted:
                incomplete = self.t("incomplete")
            self.set_status(self.t("stat_finished", n=self.available, tail=tail, incomplete=incomplete))

    async def account_loop(self, cfg, acc, client):
        name = acc["name"]
        delay = cfg["delay"]
        err_streak = 0
        self.set_acc_state(name, self.t("st_working"), "ok")

        while not self.stop_event.is_set() and self.claimed < cfg["amount"]:
            username = self.next_username(cfg)
            if username is None:
                break
            self.claimed += 1

            try:
                result = await self.check_one(client, username)
                err_streak = 0
                self.checked += 1

                if result == "free":
                    self.available += 1
                    self.available_usernames.append("@" + username)
                    self.post(self._add_result, "free", "@" + username)
                    if cfg["autosave"]:
                        self.append_to_file(os.path.join(BASE_DIR, "available.txt"), "@" + username)
                elif result == "fragment":
                    self.fragment += 1
                    self.fragment_usernames.append("@" + username)
                    self.post(self._add_result, "fragment", "@" + username)
                    if cfg["autosave"]:
                        self.append_to_file(os.path.join(BASE_DIR, "fragment.txt"), "@" + username)
                elif result == "occupied":
                    self.occupied += 1
                else:
                    self.invalid += 1
                    self.check_guard()

            except errors.FloodWaitError as e:
                # Возвращаем ник в пул — его проверит этот или другой аккаунт.
                self.seen.discard(username)
                self.claimed -= 1
                wait = int(e.seconds) + 1
                if wait > MAX_FLOOD_WAIT:
                    self.log(self.t("log_flood_long", name=name, w=wait))
                    self.set_acc_state(name, self.t("st_flood_off", n=wait), "bad")
                    return
                delay = min(delay * 1.5, 10.0)
                self.log(self.t("log_flood", name=name, w=wait, d=delay))
                for left in range(wait, 0, -1):
                    if self.stop_event.is_set():
                        break
                    self.set_acc_state(name, self.t("st_flood", n=left), "warn")
                    await asyncio.sleep(1)
                self.set_acc_state(name, self.t("st_working"), "ok")

            except Exception as e:
                self.checked += 1
                self.errors_count += 1
                err_streak += 1
                self.log(self.t("log_acc_err", name=name, u=username, err=f"{type(e).__name__}: {e}"))
                if err_streak >= 10:
                    self.log(self.t("log_err_streak", name=name))
                    self.set_acc_state(name, self.t("st_off_errors"), "bad")
                    return

            self.update_stats()
            await asyncio.sleep(delay)

        self.set_acc_state(name, self.t("st_done"), "done")

    # ----------------------------------------------------------------- files
    def append_to_file(self, filename, username):
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(username + "\n")
        except OSError as e:
            self.log(self.t("log_file_err", err=e))

    def copy_list(self, items):
        if not items:
            messagebox.showinfo(self.t("copy_title"), self.t("empty_list"))
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(items))
        self.status_var.set(self.t("stat_copied", n=len(items)))

    def save_list(self, items, kind):
        if not items:
            messagebox.showinfo(self.t("save_title"), self.t("empty_list"))
            return
        name = "available.txt" if kind == "free" else "fragment.txt"
        path = filedialog.asksaveasfilename(
            title=self.t("save_dialog"), defaultextension=".txt", initialfile=name,
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(items) + "\n")
            messagebox.showinfo(self.t("done"), self.t("saved", n=len(items)))
        except OSError as e:
            messagebox.showerror(self.t("err"), str(e))

    def on_pane_double_click(self, event, kind):
        widget = event.widget
        index = widget.index(f"@{event.x},{event.y}")
        line = widget.get(f"{index} linestart", f"{index} lineend").strip()
        if not line.startswith("@"):
            return "break"
        if kind == "fragment":
            webbrowser.open("https://fragment.com/username/" + line[1:])
            self.status_var.set(self.t("stat_opened", u=line))
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(line)
            self.status_var.set(self.t("stat_copied_one", u=line))
        return "break"

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(self.t("exit_title"), self.t("exit_q")):
                return
            self.stop_event.set()
        self.save_config()
        self.root.destroy()


def main():
    if sys.platform == "win32":
        # Чёткий текст на мониторах с масштабированием
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    root = tk.Tk()
    TelegramUsernameScanner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
