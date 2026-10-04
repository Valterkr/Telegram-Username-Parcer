import asyncio
import concurrent.futures
import copy
import json
import os
import queue
import random
import re
import string
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from urllib.parse import urlparse, unquote

from telethon import TelegramClient, functions, errors


APP_TITLE = "Telegram Username Scanner"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "accounts.json")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
LETTERS = string.ascii_lowercase
DEFAULT_CHARS = string.ascii_lowercase + string.digits + "_"
ALLOWED = set(string.ascii_lowercase + string.digits + "_")
MAX_FLOOD_WAIT = 300  # если Telegram просит ждать дольше (сек) — аккаунт отключаем до конца запуска

BG = "#111318"
PANEL = "#191c23"
FG = "#f0f2f5"
MUTED = "#9aa3b2"
ACCENT = "#5865f2"
GREEN = "#43d17a"


# ---------------------------------------------------------------- helpers
def make_username(length, chars, prefix, suffix):
    """Генерирует username по правилам Telegram:
    a-z, 0-9, _ ; начинается с буквы; не заканчивается на _ ; без двойных __.
    """
    middle_len = length - len(prefix) - len(suffix)
    if middle_len < 0:
        return None

    for _ in range(200):
        middle = [random.choice(chars) for _ in range(middle_len)]
        if not prefix and middle:
            middle[0] = random.choice(LETTERS)

        username = prefix + "".join(middle) + suffix

        if not (5 <= len(username) <= 32):
            continue
        if not username[0].isalpha():
            continue
        if username.endswith("_") or "__" in username:
            continue
        return username
    return None


def parse_proxy(text):
    """Строка -> dict для Telethon. Пустая строка -> None. Ошибка -> ValueError.

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
        raise ValueError("Не удалось разобрать прокси. Пример: socks5://user:pass@1.2.3.4:1080")

    if scheme == "socks5h":
        scheme = "socks5"
    if scheme == "https":
        scheme = "http"
    if scheme not in ("socks5", "socks4", "http"):
        raise ValueError("Поддерживаются socks5, socks4 и http прокси.")
    if not host or not port or not (0 < int(port) < 65536):
        raise ValueError("Укажите адрес и порт прокси (host:port).")

    return {"proxy_type": scheme, "addr": host, "port": int(port),
            "username": user, "password": pwd, "rdns": True}


def proxy_label(text):
    """Короткая подпись прокси без логина/пароля."""
    try:
        p = parse_proxy(text)
    except ValueError:
        return "ошибка в прокси"
    if not p:
        return "без прокси"
    return f"{p['proxy_type']}://{p['addr']}:{p['port']}"


# ------------------------------------------------------------------- app
class TelegramUsernameScanner:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1150x780")
        self.root.minsize(1050, 700)

        self.stop_event = threading.Event()
        self.worker = None
        self.clients = []
        self.ui_queue = queue.Queue()

        self.checked = 0
        self.claimed = 0
        self.available = 0
        self.occupied = 0
        self.invalid = 0
        self.errors_count = 0
        self.total = 0
        self.exhausted = False

        self.available_usernames = []
        self.seen = set()

        self.accounts = []
        self.acc_state = {}

        self.api_id_var = tk.StringVar()
        self.api_hash_var = tk.StringVar()
        self.length_var = tk.StringVar(value="5")
        self.amount_var = tk.StringVar(value="1000")
        self.delay_var = tk.StringVar(value="1.0")
        self.mode_var = tk.StringVar(value="Буквы + цифры")
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.autosave_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Готово")
        self.stats_var = tk.StringVar(value="Проверено: 0   Свободно: 0   Занято: 0")

        self.load_config()
        self.setup_style()
        self.build_ui()
        self.refresh_accounts()

        # Автосохранение API ID / API Hash через полсекунды после ввода
        self._save_job = None
        self.api_id_var.trace_add("write", lambda *a: self.schedule_save())
        self.api_hash_var.trace_add("write", lambda *a: self.schedule_save())

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.poll_queue)

    # ------------------------------------------------------------ config
    def load_config(self):
        data = {}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                data = {}

        self.api_id_var.set(str(data.get("api_id", "") or ""))
        self.api_hash_var.set(data.get("api_hash", "") or "")
        self.accounts = [a for a in data.get("accounts", []) if a.get("name")]

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
        }
        tmp = CONFIG_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)  # запись без риска получить пустой/битый файл
        except OSError as e:
            if not getattr(self, "_save_error_shown", False):
                self._save_error_shown = True
                messagebox.showerror(
                    "Не удалось сохранить настройки",
                    f"Файл: {CONFIG_PATH}\n\n{e}\n\n"
                    "Переместите программу в папку, куда можно писать "
                    "(например, Документы или Рабочий стол).")

    # ------------------------------------------------------------- style
    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(bg=BG)

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Foot.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=FG, font=("Segoe UI", 20, "bold"))
        style.configure("PanelTitle.TLabel", background=PANEL, foreground=FG, font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground="#0d0f13", foreground=FG, insertcolor=FG)
        style.configure("TSpinbox", fieldbackground="#0d0f13", foreground=FG, insertcolor=FG)
        style.configure("TCombobox", fieldbackground="#0d0f13", foreground=FG)
        style.map("TCombobox", fieldbackground=[("readonly", "#0d0f13")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(16, 9), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#4752c4")])
        style.configure("Stop.TButton", background="#d83c4a", foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(16, 9), borderwidth=0)
        style.map("Stop.TButton", background=[("active", "#b52f3b")])
        style.configure("Green.TButton", background=GREEN, foreground="#07120b",
                        font=("Segoe UI", 10, "bold"), padding=(12, 8), borderwidth=0)
        style.map("Green.TButton", background=[("active", "#35b86a")])
        style.configure("Small.TButton", background="#2a2f3a", foreground=FG,
                        font=("Segoe UI", 9), padding=(8, 5), borderwidth=0)
        style.map("Small.TButton", background=[("active", "#3a4150")])
        style.configure("TCheckbutton", background=PANEL, foreground=FG)

        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(14, 6))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "white")])

        style.configure("Treeview", background="#0d0f13", fieldbackground="#0d0f13",
                        foreground=FG, rowheight=24, borderwidth=0)
        style.configure("Treeview.Heading", background=PANEL, foreground=MUTED,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])

    # ---------------------------------------------------------------- UI
    def build_ui(self):
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Telegram Username Scanner", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="  генерация и проверка @username", style="Foot.TLabel").pack(
            side="left", pady=(7, 0))

        content = ttk.Frame(outer)
        content.pack(fill="both", expand=True)

        left = ttk.Frame(content)
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(content, style="Panel.TFrame", padding=16)
        right.pack(side="left", fill="both", expand=True)

        # --- left: tabs
        nb = ttk.Notebook(left, width=360)
        nb.pack(fill="both", expand=True)

        tab_acc = ttk.Frame(nb, style="Panel.TFrame", padding=14)
        tab_gen = ttk.Frame(nb, style="Panel.TFrame", padding=14)
        nb.add(tab_acc, text="Аккаунты")
        nb.add(tab_gen, text="Генерация")

        self.build_accounts_tab(tab_acc)
        self.build_generation_tab(tab_gen)

        # --- right: controls + results
        top = ttk.Frame(right, style="Panel.TFrame")
        top.pack(fill="x")

        self.start_btn = ttk.Button(top, text="▶  НАЧАТЬ", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left")

        self.stop_btn = ttk.Button(top, text="■  ОСТАНОВИТЬ", style="Stop.TButton",
                                   command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)

        ttk.Button(top, text="Сохранить .txt", style="Green.TButton",
                   command=self.save_file).pack(side="right")
        ttk.Button(top, text="Копировать", style="Green.TButton",
                   command=self.copy_all).pack(side="right", padx=8)

        ttk.Label(right, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(12, 4))
        ttk.Label(right, textvariable=self.stats_var, style="Panel.TLabel").pack(anchor="w", pady=(0, 8))

        self.progress = ttk.Progressbar(right, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(0, 10))

        ttk.Label(right, text="Свободные username", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.output = self.make_text(right, fg="#72e6a0", expand=True, height=10)

        ttk.Label(right, text="Журнал", style="PanelTitle.TLabel").pack(anchor="w", pady=(10, 6))
        self.log_box = self.make_text(right, fg=MUTED, expand=False, height=8, font_size=9)

        ttk.Label(
            outer,
            text="Используйте только свои аккаунты и свой API ID/Hash. Не передавайте файлы .session другим людям.",
            style="Foot.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    def build_accounts_tab(self, tab):
        ttk.Label(tab, text="Telegram API", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 4))
        self.add_field(tab, "API ID", self.api_id_var, "")
        self.add_field(tab, "API Hash", self.api_hash_var, "my.telegram.org → API Development Tools", show="*")

        ttk.Separator(tab).pack(fill="x", pady=10)
        ttk.Label(tab, text="Аккаунты", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))

        wrap = ttk.Frame(tab, style="Panel.TFrame")
        wrap.pack(fill="x")
        self.tree = ttk.Treeview(wrap, columns=("acc", "proxy", "state"), show="headings",
                                 height=6, selectmode="browse")
        self.tree.heading("acc", text="Аккаунт")
        self.tree.heading("proxy", text="Прокси")
        self.tree.heading("state", text="Статус")
        self.tree.column("acc", width=95, anchor="w")
        self.tree.column("proxy", width=120, anchor="w")
        self.tree.column("state", width=105, anchor="w")
        self.tree.pack(side="left", fill="x", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.toggle_account())

        btns = ttk.Frame(tab, style="Panel.TFrame")
        btns.pack(fill="x", pady=(8, 0))
        for i, (text, cmd) in enumerate([
            ("＋ Добавить", self.add_account),
            ("✎ Прокси", self.edit_account),
            ("✓/✗ Вкл/Выкл", self.toggle_account),
            ("🗑 Удалить", self.remove_account),
        ]):
            ttk.Button(btns, text=text, style="Small.TButton", command=cmd).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=2, pady=2)
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)

        ttk.Label(
            tab, style="Muted.TLabel", wraplength=320, justify="left",
            text=("Двойной клик по аккаунту — включить/выключить.\n"
                  "Прокси: socks5://user:pass@host:port, http://host:port "
                  "или host:port. Лучше свой прокси на каждый аккаунт."),
        ).pack(anchor="w", pady=(8, 0))

    def build_generation_tab(self, tab):
        self.add_spin(tab, "Длина username (5–32)", self.length_var, 5, 32)
        self.add_spin(tab, "Количество проверок (всего)", self.amount_var, 1, 1000000)
        self.add_spin(tab, "Задержка на аккаунт, сек. (≥ 1)", self.delay_var, 0.1, 10.0, increment=0.1)

        ttk.Label(tab, text="Набор символов", style="Panel.TLabel").pack(anchor="w", pady=(8, 3))
        ttk.Combobox(
            tab, textvariable=self.mode_var,
            values=("Буквы + цифры", "Только буквы", "Только цифры"),
            state="readonly",
        ).pack(fill="x")

        self.add_field(tab, "Префикс (необязательно)", self.prefix_var, "")
        self.add_field(tab, "Суффикс (необязательно)", self.suffix_var, "")

        ttk.Checkbutton(
            tab, text="Автосохранять свободные в available.txt", variable=self.autosave_var
        ).pack(anchor="w", pady=(12, 0))

    def make_text(self, parent, fg, expand, height, font_size=11):
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="both" if expand else "x", expand=expand)
        text = tk.Text(
            wrap, bg="#0d0f13", fg=fg, insertbackground="white",
            selectbackground=ACCENT, relief="flat", bd=0,
            font=("Consolas", font_size), padx=10, pady=8, height=height,
        )
        sb = ttk.Scrollbar(wrap, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=sb.set)
        text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return text

    def add_field(self, parent, label, variable, hint="", show=None):
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", pady=(6, 3))
        ttk.Entry(parent, textvariable=variable, show=show, width=34).pack(fill="x")
        if hint:
            ttk.Label(parent, text=hint, style="Muted.TLabel").pack(anchor="w", pady=(1, 0))

    def add_spin(self, parent, label, variable, lo, hi, increment=1):
        ttk.Label(parent, text=label, style="Panel.TLabel").pack(anchor="w", pady=(6, 3))
        ttk.Spinbox(parent, from_=lo, to=hi, increment=increment, textvariable=variable).pack(fill="x")

    # ------------------------------------------------- accounts management
    def is_busy(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Занято", "Сначала остановите сканирование.")
            return True
        return False

    def selected_account(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Аккаунты", "Выберите аккаунт в списке.")
            return None
        for a in self.accounts:
            if a["name"] == sel[0]:
                return a
        return None

    def refresh_accounts(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for a in self.accounts:
            mark = "✓" if a.get("enabled", True) else "✗"
            self.tree.insert("", "end", iid=a["name"], values=(
                f"{mark} {a['name']}",
                proxy_label(a.get("proxy", "")),
                self.acc_state.get(a["name"], "выключен" if not a.get("enabled", True) else ""),
            ))
        for iid in sel:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)

    def _set_state_ui(self, name, text):
        self.acc_state[name] = text
        self.refresh_accounts()

    def set_acc_state(self, name, text):
        self.post(self._set_state_ui, name, text)

    def account_dialog(self, acc=None):
        """Окно добавления/редактирования. Возвращает dict {name, proxy} или None."""
        editing = acc is not None
        dlg = tk.Toplevel(self.root)
        dlg.title("Прокси аккаунта" if editing else "Новый аккаунт")
        dlg.configure(bg=PANEL)
        dlg.transient(self.root)
        dlg.resizable(False, False)

        frm = ttk.Frame(dlg, style="Panel.TFrame", padding=16)
        frm.pack(fill="both", expand=True)

        name_var = tk.StringVar(value=acc["name"] if editing else "")
        proxy_var = tk.StringVar(value=acc.get("proxy", "") if editing else "")

        ttk.Label(frm, text="Название (латиница, цифры, - и _)", style="Panel.TLabel").pack(anchor="w")
        name_entry = ttk.Entry(frm, textvariable=name_var, width=46,
                               state="disabled" if editing else "normal")
        name_entry.pack(fill="x", pady=(3, 8))

        ttk.Label(frm, text="Прокси (необязательно)", style="Panel.TLabel").pack(anchor="w")
        ttk.Entry(frm, textvariable=proxy_var, width=46).pack(fill="x", pady=(3, 2))
        ttk.Label(frm, style="Muted.TLabel", justify="left",
                  text="socks5://user:pass@host:port\nhttp://host:port\nhost:port  или  host:port:user:pass"
                  ).pack(anchor="w", pady=(0, 8))
        ttk.Label(frm, style="Muted.TLabel", justify="left",
                  text="Номер телефона и код программа спросит при первом запуске.").pack(anchor="w")

        result = {}

        def ok():
            name = name_var.get().strip()
            proxy = proxy_var.get().strip()
            if not editing:
                if not re.fullmatch(r"[A-Za-z0-9_\-]{1,32}", name):
                    messagebox.showerror("Ошибка", "Название: 1–32 символа, только латиница, цифры, - и _.",
                                         parent=dlg)
                    return
                if any(a["name"].lower() == name.lower() for a in self.accounts):
                    messagebox.showerror("Ошибка", "Аккаунт с таким названием уже есть.", parent=dlg)
                    return
            try:
                parse_proxy(proxy)
            except ValueError as e:
                messagebox.showerror("Ошибка прокси", str(e), parent=dlg)
                return
            result.update(name=name, proxy=proxy)
            dlg.destroy()

        row = ttk.Frame(frm, style="Panel.TFrame")
        row.pack(fill="x", pady=(14, 0))
        ttk.Button(row, text="Сохранить", style="Accent.TButton", command=ok).pack(side="right")
        ttk.Button(row, text="Отмена", style="Small.TButton", command=dlg.destroy).pack(side="right", padx=8)

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
        if not messagebox.askyesno(
                "Удалить", f"Убрать аккаунт «{acc['name']}» из списка?\n"
                           "Файл сессии на диске останется."):
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

    def _append(self, widget, text):
        widget.insert("end", text + "\n")
        widget.see("end")

    def log(self, text):
        self.post(self._append, self.log_box, text)

    def set_status(self, text):
        self.post(self.status_var.set, text)

    def update_stats(self):
        pct = min(100, self.checked / max(1, self.total) * 100)
        text = (f"Проверено: {self.checked}   Свободно: {self.available}   "
                f"Занято: {self.occupied}   Недоступно: {self.invalid}   "
                f"Ошибки: {self.errors_count}")
        self.post(self.progress.configure, value=pct)
        self.post(self.stats_var.set, text)

    def set_running(self, running):
        self.post(self.start_btn.configure, state="disabled" if running else "normal")
        self.post(self.stop_btn.configure, state="normal" if running else "disabled")

    # ------------------------------------------------------------ validation
    def validate(self):
        try:
            api_id = int(self.api_id_var.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "API ID должен быть числом.")
            return None

        api_hash = self.api_hash_var.get().strip()
        if len(api_hash) < 16:
            messagebox.showerror("Ошибка", "Введите корректный API Hash.")
            return None

        accounts = [copy.deepcopy(a) for a in self.accounts if a.get("enabled", True)]
        if not accounts:
            messagebox.showerror("Ошибка", "Добавьте и включите хотя бы один аккаунт (вкладка «Аккаунты»).")
            return None
        for a in accounts:
            try:
                parse_proxy(a.get("proxy", ""))
            except ValueError as e:
                messagebox.showerror("Ошибка прокси", f"Аккаунт {a['name']}: {e}")
                return None

        try:
            length = int(self.length_var.get())
            amount = int(self.amount_var.get())
            delay = float(self.delay_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Ошибка", "Длина, количество и задержка должны быть числами.")
            return None

        if not (5 <= length <= 32):
            messagebox.showerror("Ошибка", "Длина username должна быть от 5 до 32.")
            return None
        if amount < 1:
            messagebox.showerror("Ошибка", "Количество проверок должно быть больше 0.")
            return None
        delay = max(0.1, delay)

        prefix = self.prefix_var.get().strip().lower().lstrip("@")
        suffix = self.suffix_var.get().strip().lower()

        if any(c not in ALLOWED for c in prefix + suffix):
            messagebox.showerror("Ошибка", "Префикс и суффикс могут содержать только a-z, 0-9 и _.")
            return None
        if len(prefix) + len(suffix) > length:
            messagebox.showerror("Ошибка", "Префикс + суффикс длиннее username.")
            return None
        if prefix and not prefix[0].isalpha():
            messagebox.showerror("Ошибка", "Username должен начинаться с буквы.")
            return None

        mode = self.mode_var.get()
        if mode == "Только буквы":
            chars = string.ascii_lowercase
        elif mode == "Только цифры":
            chars = string.digits
        else:
            chars = DEFAULT_CHARS

        if make_username(length, chars, prefix, suffix) is None:
            messagebox.showerror(
                "Ошибка",
                "С такими префиксом/суффиксом нельзя получить корректный username\n"
                "(он не должен заканчиваться на _ и содержать __).")
            return None

        return {
            "api_id": api_id, "api_hash": api_hash, "length": length,
            "amount": amount, "delay": delay, "chars": chars,
            "prefix": prefix, "suffix": suffix, "accounts": accounts,
            "autosave": self.autosave_var.get(),
        }

    # ---------------------------------------------------------- start / stop
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        cfg = self.validate()
        if not cfg:
            return
        self.save_config()

        self.checked = self.claimed = 0
        self.available = self.occupied = self.invalid = self.errors_count = 0
        self.exhausted = False
        self.total = cfg["amount"]
        self.available_usernames.clear()
        self.seen.clear()
        self.acc_state.clear()
        self.refresh_accounts()
        self.output.delete("1.0", "end")
        self.log_box.delete("1.0", "end")
        self.progress["value"] = 0
        self.update_stats()

        self.stop_event.clear()
        self.set_running(True)
        self.set_status("Подключение к Telegram...")

        self.worker = threading.Thread(target=self.worker_main, args=(cfg,), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.set_status("Остановка...")

    def worker_main(self, cfg):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        failed = False
        try:
            loop.run_until_complete(self.scan(cfg))
        except Exception as e:
            failed = True
            self.errors_count += 1
            self.log(f"[ERROR] {type(e).__name__}: {e}")
            self.set_status("Ошибка. Подробности в журнале.")
            self.update_stats()
        finally:
            for c in self.clients:
                try:
                    loop.run_until_complete(c.disconnect())
                except Exception:
                    pass
            self.clients = []
            loop.close()
            self.set_running(False)
            if self.stop_event.is_set() and not failed:
                self.set_status(f"Остановлено. Свободных найдено: {self.available}.")

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
            f"Авторизация: {name}",
            f"Аккаунт «{name}».\nВведите номер Telegram в международном формате:\n"
            "Например: +491234567890")
        if not phone:
            return None
        phone = phone.strip().replace(" ", "")

        sent = await client.send_code_request(phone)
        code_hash = sent.phone_code_hash

        def describe(t):
            tname = type(t).__name__ if t is not None else ""
            return {
                "SentCodeTypeApp": "в приложение Telegram (чат «Telegram» на другом устройстве)",
                "SentCodeTypeSms": "по SMS",
                "SentCodeTypeCall": "звонком",
                "SentCodeTypeFlashCall": "звонком (flash call)",
                "SentCodeTypeMissedCall": "пропущенным звонком",
            }.get(tname, tname or "неизвестным способом")

        for _ in range(6):
            how = describe(sent.type)
            self.log(f"[{name}] Код отправлен: {how}.")
            code = await self.ask_string_async(
                f"Код Telegram: {name}",
                f"Аккаунт «{name}». Код отправлен: {how}.\n\n"
                "Введите код. Если не пришёл — введите букву r\n"
                "и нажмите OK, чтобы отправить повторно (SMS/звонок):")
            if not code:
                return None
            code = code.strip().replace(" ", "")

            if code.lower() == "r":
                try:
                    sent = await client(functions.auth.ResendCodeRequest(
                        phone_number=phone, phone_code_hash=code_hash))
                    code_hash = sent.phone_code_hash
                except errors.RPCError as e:
                    self.log(f"[{name}] Не удалось отправить повторно: {type(e).__name__}: {e}")
                continue

            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
                break
            except errors.SessionPasswordNeededError:
                password = await self.ask_string_async(
                    f"Пароль 2FA: {name}", "Введите пароль двухэтапной аутентификации:", secret=True)
                if not password:
                    return None
                await client.sign_in(password=password)
                break
            except errors.PhoneCodeInvalidError:
                self.log(f"[{name}] Неверный код, попробуйте ещё раз.")
        return client if await client.is_user_authorized() else None

    # ------------------------------------------------------------------ scan
    async def check_one(self, client, username):
        """Возвращает 'free' | 'occupied' | 'invalid'. FloodWait пробрасывается наружу."""
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
            msg = (getattr(e, "message", "") or str(e)).upper()
            # Ник продаётся/на аукционе (Fragment) — для обычной регистрации недоступен.
            if "PURCHASE_AVAILABLE" in msg or "USERNAME_NOT_MODIFIED" in msg:
                return "occupied"
            if "USERNAME_INVALID" in msg:
                return "invalid"
            raise

    def next_username(self, cfg):
        """Следующий ещё не проверявшийся username или None, если комбинации кончились."""
        for _ in range(5000):
            username = make_username(cfg["length"], cfg["chars"], cfg["prefix"], cfg["suffix"])
            if not username:
                break
            if username not in self.seen:
                self.seen.add(username)
                return username
        if not self.exhausted:
            self.exhausted = True
            self.log("[INFO] Уникальные комбинации закончились.")
        return None

    async def scan(self, cfg):
        # 1) Последовательно подключаем и авторизуем аккаунты (диалоги ввода кода идут по очереди).
        ready = []
        for acc in cfg["accounts"]:
            if self.stop_event.is_set():
                break
            name = acc["name"]
            self.set_acc_state(name, "вход...")
            self.set_status(f"Подключение: {name}...")
            try:
                client = await self.authenticate(cfg, acc)
            except Exception as e:
                self.log(f"[{name}] Ошибка входа: {type(e).__name__}: {e}")
                self.set_acc_state(name, "ошибка входа")
                continue
            if client is None:
                self.log(f"[{name}] Не авторизован — пропускаю.")
                self.set_acc_state(name, "не вошёл")
                continue
            self.log(f"[{name}] Авторизация успешна ({proxy_label(acc.get('proxy', ''))}).")
            ready.append((acc, client))

        if self.stop_event.is_set():
            return
        if not ready:
            self.set_status("Нет ни одного авторизованного аккаунта.")
            return

        self.set_status(f"Проверка идёт. Аккаунтов: {len(ready)}")
        self.log(f"[INFO] План проверок: {cfg['amount']}, аккаунтов: {len(ready)}, "
                 f"задержка на аккаунт {cfg['delay']} сек.")

        # 2) Все аккаунты сканируют параллельно, каждый со своей задержкой и своим прокси.
        await asyncio.gather(*[self.account_loop(cfg, acc, client) for acc, client in ready])

        self.update_stats()
        if not self.stop_event.is_set():
            tail = " Сохранено в available.txt." if cfg["autosave"] and self.available else ""
            incomplete = ""
            if self.checked < cfg["amount"] and not self.exhausted:
                incomplete = " Не все проверки выполнены: аккаунты отключились (см. журнал)."
            self.set_status(f"Завершено. Свободных: {self.available}.{tail}{incomplete}")

    async def account_loop(self, cfg, acc, client):
        name = acc["name"]
        delay = cfg["delay"]
        err_streak = 0
        self.set_acc_state(name, "работает")

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
                    self.post(self._append, self.output, "@" + username)
                    if cfg["autosave"]:
                        self.append_to_file(os.path.join(BASE_DIR, "available.txt"), "@" + username)
                elif result == "occupied":
                    self.occupied += 1
                else:
                    self.invalid += 1

            except errors.FloodWaitError as e:
                # Возвращаем ник в пул — его проверит этот или другой аккаунт.
                self.seen.discard(username)
                self.claimed -= 1
                wait = int(e.seconds) + 1
                if wait > MAX_FLOOD_WAIT:
                    self.log(f"[{name}] FloodWait {wait} сек. — слишком долго, аккаунт отключён до конца запуска.")
                    self.set_acc_state(name, f"флуд {wait}с, откл.")
                    return
                delay = min(delay * 1.5, 10.0)
                self.log(f"[{name}] FloodWait: ждём {wait} сек. Новая задержка: {delay:.1f} сек.")
                for left in range(wait, 0, -1):
                    if self.stop_event.is_set():
                        break
                    self.set_acc_state(name, f"флуд {left}с")
                    await asyncio.sleep(1)
                self.set_acc_state(name, "работает")

            except Exception as e:
                self.checked += 1
                self.errors_count += 1
                err_streak += 1
                self.log(f"[{name}] @{username}: {type(e).__name__}: {e}")
                if err_streak >= 10:
                    self.log(f"[{name}] 10 ошибок подряд — аккаунт отключён (проверьте прокси/интернет).")
                    self.set_acc_state(name, "отключён (ошибки)")
                    return

            self.update_stats()
            await asyncio.sleep(delay)

        self.set_acc_state(name, "готов")

    # ----------------------------------------------------------------- files
    def append_to_file(self, filename, username):
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(username + "\n")
        except OSError as e:
            self.log(f"[FILE ERROR] {e}")

    def copy_all(self):
        if not self.available_usernames:
            messagebox.showinfo("Копирование", "Свободных username пока нет.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(self.available_usernames))
        self.status_var.set(f"Скопировано: {len(self.available_usernames)}")

    def save_file(self):
        if not self.available_usernames:
            messagebox.showinfo("Сохранение", "Свободных username пока нет.")
            return
        path = filedialog.asksaveasfilename(
            title="Сохранить свободные username",
            defaultextension=".txt", initialfile="available.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.available_usernames) + "\n")
            messagebox.showinfo("Готово", f"Сохранено: {len(self.available_usernames)} username.")
        except OSError as e:
            messagebox.showerror("Ошибка", str(e))

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Выход", "Сканирование ещё идёт. Остановить и выйти?"):
                return
            self.stop_event.set()
        self.save_config()
        self.root.destroy()


def main():
    root = tk.Tk()
    TelegramUsernameScanner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
