import asyncio
import concurrent.futures
import os
import queue
import random
import string
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from telethon import TelegramClient, functions, errors


APP_TITLE = "Telegram Username Scanner"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LETTERS = string.ascii_lowercase
DEFAULT_CHARS = string.ascii_lowercase + string.digits + "_"
ALLOWED = set(string.ascii_lowercase + string.digits + "_")


def make_username(length, chars, prefix, suffix):
    """Генерирует username по правилам Telegram:
    a-z, 0-9, _ ; начинается с буквы; не заканчивается на _ ; без двойных __.
    """
    middle_len = length - len(prefix) - len(suffix)
    if middle_len < 0:
        return None

    for _ in range(200):
        middle = [random.choice(chars) for _ in range(middle_len)]
        # Если префикса нет — первый символ обязан быть буквой
        # (иначе режим «Только цифры» никогда ничего бы не сгенерировал).
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


class TelegramUsernameScanner:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x780")
        self.root.minsize(1000, 720)

        self.stop_event = threading.Event()
        self.worker = None
        self.client = None
        self.ui_queue = queue.Queue()

        self.checked = 0
        self.available = 0
        self.occupied = 0
        self.invalid = 0
        self.errors_count = 0
        self.total = 0

        self.available_usernames = []
        self.seen = set()

        self.api_id_var = tk.StringVar()
        self.api_hash_var = tk.StringVar()
        self.session_var = tk.StringVar(value="telegram_scanner")
        self.length_var = tk.StringVar(value="5")
        self.amount_var = tk.StringVar(value="1000")
        self.delay_var = tk.StringVar(value="1.0")
        self.mode_var = tk.StringVar(value="Буквы + цифры")
        self.prefix_var = tk.StringVar()
        self.suffix_var = tk.StringVar()
        self.autosave_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Готово")
        self.stats_var = tk.StringVar(value="Проверено: 0   Свободно: 0   Занято: 0")

        self.setup_style()
        self.build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.poll_queue)

    # ------------------------------------------------------------------ UI
    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#111318"
        panel = "#191c23"
        fg = "#f0f2f5"
        muted = "#9aa3b2"
        accent = "#5865f2"
        green = "#43d17a"

        self.root.configure(bg=bg)

        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=panel, foreground=fg, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=panel, foreground=muted, font=("Segoe UI", 9))
        style.configure("Foot.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=bg, foreground=fg, font=("Segoe UI", 20, "bold"))
        style.configure("PanelTitle.TLabel", background=panel, foreground=fg, font=("Segoe UI", 11, "bold"))
        style.configure("TEntry", fieldbackground="#0d0f13", foreground=fg, insertcolor=fg)
        style.configure("TSpinbox", fieldbackground="#0d0f13", foreground=fg, insertcolor=fg)
        style.configure("TCombobox", fieldbackground="#0d0f13", foreground=fg)
        style.map("TCombobox", fieldbackground=[("readonly", "#0d0f13")])
        style.configure("Accent.TButton", background=accent, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(16, 9), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#4752c4")])
        style.configure("Stop.TButton", background="#d83c4a", foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(16, 9), borderwidth=0)
        style.map("Stop.TButton", background=[("active", "#b52f3b")])
        style.configure("Green.TButton", background=green, foreground="#07120b",
                        font=("Segoe UI", 10, "bold"), padding=(12, 8), borderwidth=0)
        style.map("Green.TButton", background=[("active", "#35b86a")])
        style.configure("TCheckbutton", background=panel, foreground=fg)

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

        left = ttk.Frame(content, style="Panel.TFrame", padding=16)
        left.pack(side="left", fill="y", padx=(0, 12))

        right = ttk.Frame(content, style="Panel.TFrame", padding=16)
        right.pack(side="left", fill="both", expand=True)

        # --- left: settings
        ttk.Label(left, text="Telegram API", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))
        self.add_field(left, "API ID", self.api_id_var, "Число с my.telegram.org")
        self.add_field(left, "API Hash", self.api_hash_var, "32 символа с my.telegram.org", show="*")
        self.add_field(left, "Session", self.session_var, "Имя файла сессии")

        ttk.Separator(left).pack(fill="x", pady=10)
        ttk.Label(left, text="Генерация", style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 6))

        self.add_spin(left, "Длина username (5–32)", self.length_var, 5, 32)
        self.add_spin(left, "Количество проверок", self.amount_var, 1, 1000000)
        self.add_spin(left, "Задержка, сек. (советую ≥ 1)", self.delay_var, 0.1, 10.0, increment=0.1)

        ttk.Label(left, text="Набор символов", style="Panel.TLabel").pack(anchor="w", pady=(8, 3))
        ttk.Combobox(
            left, textvariable=self.mode_var,
            values=("Буквы + цифры", "Только буквы", "Только цифры"),
            state="readonly",
        ).pack(fill="x")

        self.add_field(left, "Префикс (необязательно)", self.prefix_var, "")
        self.add_field(left, "Суффикс (необязательно)", self.suffix_var, "")

        ttk.Checkbutton(
            left, text="Автосохранять свободные в available.txt", variable=self.autosave_var
        ).pack(anchor="w", pady=(10, 0))

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
        self.log_box = self.make_text(right, fg="#9aa3b2", expand=False, height=8, font_size=9)

        ttk.Label(
            outer,
            text="Используйте собственный API ID/API Hash. Не передавайте файл .session другим людям.",
            style="Foot.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    def make_text(self, parent, fg, expand, height, font_size=11):
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.pack(fill="both" if expand else "x", expand=expand)
        text = tk.Text(
            wrap, bg="#0d0f13", fg=fg, insertbackground="white",
            selectbackground="#5865f2", relief="flat", bd=0,
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
                except Exception as e:  # не даём UI умереть из-за одной ошибки
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

        session = self.session_var.get().strip() or "telegram_scanner"
        if not os.path.isabs(session):
            session = os.path.join(BASE_DIR, session)

        return {
            "api_id": api_id, "api_hash": api_hash, "length": length,
            "amount": amount, "delay": delay, "chars": chars,
            "prefix": prefix, "suffix": suffix, "session": session,
            "autosave": self.autosave_var.get(),
        }

    # ---------------------------------------------------------- start / stop
    def start(self):
        if self.worker and self.worker.is_alive():
            return
        cfg = self.validate()
        if not cfg:
            return

        self.checked = self.available = self.occupied = self.invalid = self.errors_count = 0
        self.total = cfg["amount"]
        self.available_usernames.clear()
        self.seen.clear()
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
            try:
                if self.client:
                    loop.run_until_complete(self.client.disconnect())
            except Exception:
                pass
            self.client = None
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

    async def authenticate(self, cfg):
        self.client = TelegramClient(
            cfg["session"], cfg["api_id"], cfg["api_hash"],
            flood_sleep_threshold=0,  # FloodWait обрабатываем сами и показываем в окне
        )
        await self.client.connect()

        if await self.client.is_user_authorized():
            return True

        phone = await self.ask_string_async(
            "Авторизация",
            "Введите номер Telegram в международном формате:\nНапример: +491234567890")
        if not phone:
            return False
        phone = phone.strip().replace(" ", "")

        sent = await self.client.send_code_request(phone)
        code_hash = sent.phone_code_hash

        def describe(t):
            name = type(t).__name__ if t is not None else ""
            return {
                "SentCodeTypeApp": "в приложение Telegram (чат «Telegram» на другом устройстве)",
                "SentCodeTypeSms": "по SMS",
                "SentCodeTypeCall": "звонком",
                "SentCodeTypeFlashCall": "звонком (flash call)",
                "SentCodeTypeMissedCall": "пропущенным звонком",
            }.get(name, name or "неизвестным способом")

        for attempt in range(6):
            how = describe(sent.type)
            self.log(f"[AUTH] Код отправлен: {how}.")
            code = await self.ask_string_async(
                "Код Telegram",
                f"Код отправлен: {how}.\n\n"
                "Введите код. Если не пришёл — введите букву r\n"
                "и нажмите OK, чтобы отправить повторно (SMS/звонок):")
            if not code:
                return False
            code = code.strip().replace(" ", "")

            if code.lower() == "r":
                try:
                    sent = await self.client(functions.auth.ResendCodeRequest(
                        phone_number=phone, phone_code_hash=code_hash))
                    code_hash = sent.phone_code_hash
                except errors.RPCError as e:
                    self.log(f"[AUTH] Не удалось отправить повторно: {type(e).__name__}: {e}")
                continue

            try:
                await self.client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)
                break
            except errors.SessionPasswordNeededError:
                password = await self.ask_string_async(
                    "Двухэтапная проверка", "Введите пароль двухэтапной аутентификации:", secret=True)
                if not password:
                    return False
                await self.client.sign_in(password=password)
                break
            except errors.PhoneCodeInvalidError:
                self.log("[AUTH] Неверный код, попробуйте ещё раз.")
        return await self.client.is_user_authorized()

    # ------------------------------------------------------------------ scan
    async def check_one(self, username):
        """Возвращает 'free' | 'occupied' | 'invalid'. FloodWait пробрасывается наружу."""
        try:
            ok = await self.client(functions.account.CheckUsernameRequest(username=username))
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

    async def scan(self, cfg):
        if not await self.authenticate(cfg):
            self.set_status("Авторизация отменена.")
            return

        total = cfg["amount"]
        delay = cfg["delay"]
        autosave = cfg["autosave"]

        self.set_status("Telegram подключён. Проверка идёт...")
        self.log("[OK] Авторизация успешна.")
        self.log(f"[INFO] План проверок: {total}, задержка {delay} сек.")

        dup_streak = 0
        err_streak = 0

        while self.checked < total and not self.stop_event.is_set():
            username = make_username(cfg["length"], cfg["chars"], cfg["prefix"], cfg["suffix"])
            if not username:
                self.log("[ERROR] Не удалось сгенерировать username с такими параметрами.")
                break

            if username in self.seen:
                dup_streak += 1
                if dup_streak > 5000:
                    self.log("[INFO] Уникальные комбинации закончились.")
                    break
                continue
            dup_streak = 0
            self.seen.add(username)

            try:
                result = await self.check_one(username)
                err_streak = 0
                self.checked += 1

                if result == "free":
                    self.available += 1
                    self.available_usernames.append("@" + username)
                    self.post(self._append, self.output, "@" + username)
                    if autosave:
                        self.append_to_file(os.path.join(BASE_DIR, "available.txt"), "@" + username)
                elif result == "occupied":
                    self.occupied += 1
                else:
                    self.invalid += 1

            except errors.FloodWaitError as e:
                self.seen.discard(username)  # проверим его позже
                wait = int(e.seconds) + 1
                delay = min(delay * 1.5, 10.0)
                self.log(f"[FLOOD WAIT] Telegram просит подождать {wait} сек. "
                         f"Новая задержка: {delay:.1f} сек.")
                for left in range(wait, 0, -1):
                    if self.stop_event.is_set():
                        break
                    self.set_status(f"FloodWait: ждём {left} сек...")
                    await asyncio.sleep(1)
                self.set_status("Telegram подключён. Проверка идёт...")

            except Exception as e:
                self.checked += 1
                self.errors_count += 1
                err_streak += 1
                self.log(f"[ERROR] @{username}: {type(e).__name__}: {e}")
                if err_streak >= 10:
                    self.log("[ERROR] 10 ошибок подряд — останавливаюсь (проверьте интернет/доступ к Telegram).")
                    break

            self.update_stats()
            await asyncio.sleep(delay)

        self.update_stats()
        if not self.stop_event.is_set():
            tail = " Сохранено в available.txt." if autosave and self.available else ""
            self.set_status(f"Завершено. Свободных: {self.available}.{tail}")

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
        self.root.destroy()


def main():
    root = tk.Tk()
    TelegramUsernameScanner(root)
    root.mainloop()


if __name__ == "__main__":
    main()
