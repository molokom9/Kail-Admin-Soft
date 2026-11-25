#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kail Admin — менеджер Telegram-ботов (Linux + Windows).

Положи файл в папку с ботами (*.py) и запусти:  python3 kail_admin.py  (Windows: python kail_admin.py)
"""

import os
import sys
import re
import ast
import glob
import json
import time
import queue
import shutil
import signal
import atexit
import random
import getpass
import hashlib
import platform
import threading
import importlib
import subprocess
import traceback
from datetime import datetime
from collections import deque

IS_WIN = platform.system() == 'Windows'
SCRIPT_PATH = os.path.abspath(__file__)
BASE_DIR = os.path.dirname(SCRIPT_PATH)

# Всё (state, логи, настройки, дочерние терминалы) живёт рядом со скриптом —
# так главный и дочерние терминалы всегда видят одни и те же файлы.
try:
    os.chdir(BASE_DIR)
except OSError:
    pass

# Локальные папки для библиотек самого менеджера (работает даже на Linux с PEP 668 и без root)
LIBS_DIRS = [os.path.join(BASE_DIR, '.kail_libs'),
             os.path.join(os.path.expanduser('~'), '.kail_libs')]
for _d in LIBS_DIRS:
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)

try:
    import psutil
except Exception:
    psutil = None

try:
    import readline  # noqa: F401  (история стрелками на Linux/macOS)
    HAS_READLINE = True
except Exception:
    HAS_READLINE = False

# Консоль не должна падать на юникоде (cp1251/cp866, перенаправление вывода, LANG=C)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# ======================================================================
#  Цвета (собственные ANSI — colorama больше не обязательна)
# ======================================================================
class Fore:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    LIGHTBLACK_EX = '\033[90m'
    LIGHTRED_EX = '\033[91m'
    LIGHTGREEN_EX = '\033[92m'
    LIGHTYELLOW_EX = '\033[93m'
    LIGHTBLUE_EX = '\033[94m'
    LIGHTMAGENTA_EX = '\033[95m'
    LIGHTCYAN_EX = '\033[96m'
    LIGHTWHITE_EX = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


_builtin_print = print


def print(*args, **kw):  # noqa: A001  (autoreset как у colorama + защита от падений консоли)
    sep = kw.pop('sep', ' ')
    end = kw.pop('end', '\n')
    file = kw.pop('file', None)
    flush = kw.pop('flush', False)
    text = sep.join(str(a) for a in args)
    if '\033[' in text:
        text += Fore.RESET
    try:
        _builtin_print(text, end=end, file=file, flush=flush)
    except UnicodeEncodeError:
        try:
            enc = (getattr(file or sys.stdout, 'encoding', None) or 'ascii')
            _builtin_print(text.encode(enc, 'replace').decode(enc, 'replace'),
                           end=end, file=file, flush=flush)
        except Exception:
            pass
    except (OSError, ValueError):
        pass  # консоль закрыта / сломанный pipe


VT_OK = True


def _enable_windows_ansi():
    """Включает ANSI-цвета в консоли Windows (нативно, а если не вышло — через colorama)."""
    global VT_OK
    if not IS_WIN:
        return
    ok = False
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.GetStdHandle.restype = wintypes.HANDLE
        k.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        for std in (-11, -12):
            h = k.GetStdHandle(std)
            mode = wintypes.DWORD()
            if h and k.GetConsoleMode(h, ctypes.byref(mode)):
                if k.SetConsoleMode(h, mode.value | 0x0001 | 0x0004):
                    ok = True
    except Exception:
        ok = False
    if not ok:
        try:
            import colorama
            colorama.init()
            ok = True
        except Exception:
            pass
    VT_OK = ok


def clear_screen():
    try:
        if IS_WIN and not VT_OK:
            os.system('cls')
        elif sys.stdout.isatty():
            sys.stdout.write('\033[2J\033[3J\033[H')
            sys.stdout.flush()
    except Exception:
        pass


def _set_title(title):
    try:
        if IS_WIN:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(str(title))
        elif sys.stdout.isatty():
            sys.stdout.write(f"\033]0;{title}\007")
            sys.stdout.flush()
    except Exception:
        pass


# ======================================================================
#  Настройки
# ======================================================================
SETTINGS_FILE = "kail_settings.json"
STATE_FILE = "kail_state.json"
ERROR_LOG_FILE = "kail_errors.log"
CHILD_DIR = "kail_children"
BOT_DIR = "kail_bots"          # реестр окон ботов (PID, код выхода)
BINDS_FILE = "kail_binds.json" # привязанные боты из других папок (сохраняются между запусками)
PREFS_FILE = "kail_botprefs.json"  # сохранённые параметры запуска ботов (run <num> ... sv)

DEFAULT_SETTINGS = {
    "auto_system_packages": True,
    "bot_window": True,
    "window_hold": 10,
    "monitor_interval": 30,
    "auto_restart": True,
    "max_restarts": 5,
    "log_dir": "logs",
    "sudo_confirm": True,
    "use_venv": True,
    "venv_fallback": True,
    "auto_install_deps": True,
    "stop_grace": 3,
    "child_check_interval": 3,
    "auto_open_logs": False,
    "state_sync_interval": 2,
    "boot_animation": True,
}

SETTINGS_DESCRIPTIONS = {
    "auto_system_packages":  "Linux: если нет venv/pip — поставить python3-venv/pip через apt/dnf (нужен root или sudo без пароля, иначе спросит).",
    "bot_window":            "Каждый бот — в своём окне консоли (Linux/Windows), как при ручном запуске. Вывод пишется и в лог.",
    "window_hold":           "Сколько секунд окно бота остаётся открытым после его падения (прочитать ошибку).",
    "monitor_interval":      "Интервал проверки ботов (секунд).",
    "auto_restart":          "Авто-перезапуск упавших ботов (true/false).",
    "max_restarts":          "Макс. авто-перезапусков бота за 10 минут (защита от бесконечного цикла).",
    "log_dir":               "Папка для хранения логов ботов.",
    "sudo_confirm":          "Подтверждение перед sudo-командой (true/false).",
    "use_venv":              "Запускать ботов в venv (рекомендуется). false — в глобальном Python.",
    "venv_fallback":         "Если venv создать не вышло — запустить в глобальном Python (true/false).",
    "auto_install_deps":     "Авто-установка недостающих библиотек (true/false).",
    "stop_grace":            "Сколько секунд ждать мягкой остановки бота перед kill.",
    "child_check_interval":  "Проверка родителя в дочернем терминале (секунд).",
    "auto_open_logs":        "Авто-открытие логов при запуске бота (true/false).",
    "state_sync_interval":   "Как часто главный терминал пишет состояние для child (секунд).",
    "boot_animation":        "Анимация загрузки при старте (true/false).",
}

SETTINGS_MIN = {
    "monitor_interval": 1, "max_restarts": 1, "stop_grace": 0,
    "child_check_interval": 1, "state_sync_interval": 1, "window_hold": 0,
}

SETTINGS = dict(DEFAULT_SETTINGS)
TRUE_WORDS = ('1', 'true', 'yes', 'y', 'on', 'вкл', 'да', 'д')


def _coerce(key, val):
    default = DEFAULT_SETTINGS[key]
    try:
        if isinstance(default, bool):
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in TRUE_WORDS
        if isinstance(default, int):
            return max(SETTINGS_MIN.get(key, 0), int(val))
        val = str(val).strip()
        return val or default
    except (ValueError, TypeError):
        return default


_err_lock = threading.Lock()


def log_error(msg, show=True):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with _err_lock:
        try:
            with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass
    if show:
        print(f"{Fore.RED}⚠ {str(msg).splitlines()[0] if msg else ''}")


def save_settings():
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_error(f"Ошибка сохранения настроек: {e}")
        return False


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8-sig') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("ожидался JSON-объект")
        for k in DEFAULT_SETTINGS:
            if k in data:
                SETTINGS[k] = _coerce(k, data[k])
    except Exception as e:
        log_error(f"Не удалось загрузить настройки ({e}); использую значения по умолчанию.")
        try:
            os.replace(SETTINGS_FILE, SETTINGS_FILE + '.bak')
        except Exception:
            pass


def _atomic_write_json(path, data):
    """Атомарная запись JSON. На Windows os.replace падает, если файл кто-то читает — ретраим."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        return False
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(0.05)
        except OSError:
            break
    try:
        os.remove(tmp)
    except Exception:
        pass
    return False


def _read_json(path, retries=3):
    for i in range(retries):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (PermissionError, ValueError, OSError):
            time.sleep(0.05)
    return None


# ======================================================================
#  Глобальное состояние
# ======================================================================
VERSION = "v251126.2257"
PRODUCT_NAME = "Kail Admin"

BINDS = []                     # абсолютные пути привязанных ботов
BOT_PREFS = {}                 # имя бота -> {"venv": bool, "window": bool} (сохранённые параметры запуска)
BOTS = {}                      # имя файла -> Bot
BOTS_LOCK = threading.RLock()  # сериализует запуск/остановку (пользователь + монитор)
STATE_LOCK = threading.Lock()
file_list = []
running = True
child_terms = {}               # action -> ChildTerm
command_history = deque(maxlen=50)

SYSTEM_CMDS = ['reboot', 'shutdown', 'poweroff', 'halt', 'systemctl',
               'service', 'apt', 'yum', 'dnf', 'pacman', 'chmod', 'chown']
LINUX_ONLY_CMDS = {'apt', 'apt-get', 'yum', 'dnf', 'pacman', 'zypper', 'dpkg', 'snap',
                   'chmod', 'chown', 'service'}
POWER_CMDS = ('reboot', 'shutdown', 'poweroff', 'halt')

# ---------- Маппинг import -> pip ----------
PIP_NAME_MAP = {
    'PIL': 'Pillow', 'cv2': 'opencv-python', 'bs4': 'beautifulsoup4',
    'sklearn': 'scikit-learn', 'yaml': 'PyYAML', 'dotenv': 'python-dotenv',
    'telegram': 'python-telegram-bot', 'telebot': 'pyTelegramBotAPI',
    'discord': 'discord.py', 'Crypto': 'pycryptodome', 'serial': 'pyserial',
    'dateutil': 'python-dateutil', 'pkg_resources': 'setuptools',
    'OpenSSL': 'pyOpenSSL', 'win32com': 'pywin32', 'win32api': 'pywin32',
    'MySQLdb': 'mysqlclient', 'psycopg2': 'psycopg2-binary',
    'speech_recognition': 'SpeechRecognition',
    'googleapiclient': 'google-api-python-client',
    'fitz': 'PyMuPDF', 'docx': 'python-docx', 'pptx': 'python-pptx',
    'magic': 'python-magic', 'jwt': 'PyJWT', 'multipart': 'python-multipart',
    'nacl': 'PyNaCl', 'flask_sqlalchemy': 'Flask-SQLAlchemy',
    'flask_login': 'Flask-Login', 'flask_wtf': 'Flask-WTF',
    'flask_cors': 'Flask-Cors', 'rest_framework': 'djangorestframework',
    'crispy_forms': 'django-crispy-forms', 'allauth': 'django-allauth',
    'telethon': 'Telethon', 'pyrogram': 'Pyrogram', 'tgcrypto': 'TgCrypto',
    'sqlalchemy': 'SQLAlchemy', 'xlsxwriter': 'XlsxWriter',
    'apscheduler': 'APScheduler', 'undetected_chromedriver': 'undetected-chromedriver',
    'fake_useragent': 'fake-useragent', 'attr': 'attrs', 'markdown': 'Markdown',
    'zmq': 'pyzmq', 'socks': 'PySocks', 'bson': 'pymongo', 'usb': 'pyusb',
}

# Модули stdlib, которых может не быть на текущей ОС — их НИКОГДА нельзя ставить из PyPI
PLATFORM_STDLIB = {
    'msvcrt', 'winreg', '_winapi', 'winsound', 'nt', 'fcntl', 'termios', 'pwd', 'grp',
    'resource', 'posix', 'readline', 'curses', 'tkinter', 'syslog', 'crypt', 'spwd',
    'nis', 'ossaudiodev', 'asyncio', 'distutils', 'imp', 'asynchat', 'asyncore', 'smtpd',
}
WINDOWS_ONLY_PKGS = {'win32api', 'win32com', 'win32con', 'win32gui', 'win32file', 'win32process',
                     'win32service', 'win32serviceutil', 'pywintypes', 'pythoncom', 'wmi', 'comtypes'}

STDLIB_SAFE = set(getattr(sys, 'stdlib_module_names', ())) | PLATFORM_STDLIB


# ======================================================================
#  Процессы: проверка, дерево, завершение
# ======================================================================
def _win_pid_alive(pid):
    try:
        import ctypes
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        h = k.OpenProcess(0x1000, 0, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # access denied => процесс существует
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259    # STILL_ACTIVE
    except Exception:
        return False


def pid_alive(pid, ctime=None):
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if psutil:
        try:
            p = psutil.Process(pid)
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                return False
            if ctime:
                try:
                    if abs(p.create_time() - float(ctime)) > 2:
                        return False  # PID переиспользован другим процессом
                except Exception:
                    pass
            return True
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True
        except Exception:
            return False
    if IS_WIN:
        return _win_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _ps_alive(p):
    try:
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except Exception:
        return True


def _taskkill_tree(pid):
    try:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                       capture_output=True, timeout=15, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:
        pass


def terminate_tree(pid, grace=3.0, group=False, proc=None):
    """
    Завершает процесс и ВСЕХ его потомков.
    Linux: SIGTERM -> ждём grace -> SIGKILL (по группе и по дереву psutil).
    Windows: taskkill /F /T + добивание через psutil (venv-python на Windows — «трамплин», дерево обязательно).
    Никогда не убивает собственную группу процессов. Ничего не бросает наружу.
    """
    if not pid:
        return True
    family = []
    if psutil:
        try:
            root = psutil.Process(pid)
            family = root.children(recursive=True) + [root]
        except Exception:
            family = []

    def alive():
        if proc is not None:
            if proc.poll() is None:
                return True
        elif pid_alive(pid):
            return True
        if psutil:
            return any(_ps_alive(p) for p in family if p.pid != pid)
        return False

    try:
        if IS_WIN:
            if alive():
                _taskkill_tree(pid)
                for p in family:
                    try:
                        p.kill()
                    except Exception:
                        pass
                if psutil and family:
                    try:
                        psutil.wait_procs(family, timeout=3)
                    except Exception:
                        pass
        else:
            pgid = None
            if group and (proc is None or proc.poll() is None):
                try:
                    g = os.getpgid(pid)
                    if g != os.getpgrp():
                        pgid = g
                except Exception:
                    pgid = None

            def send(sig):
                if pgid:
                    try:
                        os.killpg(pgid, sig)
                    except Exception:
                        pass
                for p in family:
                    try:
                        p.send_signal(sig)
                    except Exception:
                        pass
                if not family:
                    try:
                        os.kill(pid, sig)
                    except Exception:
                        pass

            if grace and grace > 0:
                send(signal.SIGTERM)
                end = time.time() + grace
                while time.time() < end and alive():
                    time.sleep(0.1)
            if alive() or (pgid and not psutil):
                send(signal.SIGKILL)
    except Exception as e:
        log_error(f"terminate_tree({pid}): {e}", show=False)

    if proc is not None:
        try:
            proc.wait(timeout=3)
        except Exception:
            pass
    end = time.time() + 2
    while time.time() < end and alive():
        time.sleep(0.05)
    return not alive()


def _group_kwargs():
    """Отдельная группа/сессия: Ctrl+C менеджера не убивает ботов, а мы можем убить всё дерево."""
    if IS_WIN:
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}   # вместо preexec_fn — тот может дедлочить в многопоточной программе


# ======================================================================
#  Запуск команд с живым статусом (pip и т.п.) — не «замирает», Ctrl+C прерывает
# ======================================================================
def _status(text):
    try:
        if not sys.stdout.isatty():
            return
        w = max(20, shutil.get_terminal_size((100, 25)).columns - 6)
        t = text.strip().replace('\t', ' ')[:w]
        erase = '\033[K' if (not IS_WIN or VT_OK) else ' ' * 4
        sys.stdout.write(f"\r{Fore.LIGHTBLACK_EX}  {t}{Fore.RESET}{erase}")
        sys.stdout.flush()
    except Exception:
        pass


def _status_clear():
    try:
        if sys.stdout.isatty():
            erase = '\033[K' if (not IS_WIN or VT_OK) else ' ' * 80
            sys.stdout.write('\r' + erase + '\r')
            sys.stdout.flush()
    except Exception:
        pass


def _clean_env():
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    env['PIP_NO_INPUT'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def run_stream(cmd, cwd=None, timeout=900, show=True):
    """Запускает команду, показывает последнюю строку вывода. Возвращает (rc, хвост_вывода)."""
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=_clean_env(), **_group_kwargs())
    except Exception as e:
        return -1, str(e)

    q = queue.Queue()

    def reader():
        try:
            for raw in iter(p.stdout.readline, b''):
                q.put(raw.decode('utf-8', 'replace'))
        except Exception:
            pass
        q.put(None)

    threading.Thread(target=reader, daemon=True).start()
    tail = deque(maxlen=60)
    start = last_data = time.time()
    timed_out = False
    try:
        while True:
            try:
                item = q.get(timeout=0.5)
            except queue.Empty:
                item = ''
                if p.poll() is not None and time.time() - last_data > 2:
                    break
            if item is None:
                break
            if item:
                last_data = time.time()
                line = item.rstrip()
                if line:
                    tail.append(line)
                    if show:
                        _status(line)
            if time.time() - start > timeout:
                timed_out = True
                terminate_tree(p.pid, grace=0, group=True, proc=p)
                break
    except KeyboardInterrupt:
        terminate_tree(p.pid, grace=0, group=True, proc=p)
        if show:
            _status_clear()
        raise
    if show:
        _status_clear()
    try:
        rc = p.wait(timeout=10)
    except Exception:
        terminate_tree(p.pid, grace=0, group=True, proc=p)
        rc = -9
    if timed_out:
        tail.append(f"[таймаут {timeout} c]")
        rc = rc if rc not in (0, None) else -9
    try:
        p.stdout.close()
    except Exception:
        pass
    return rc, '\n'.join(tail)


def _run_quiet(cmd, timeout=60, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                           stdin=subprocess.DEVNULL, env=_clean_env(),
                           encoding='utf-8', errors='replace')
        return r.returncode == 0, (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return False, str(e)


# ======================================================================
#  pip / зависимости
# ======================================================================
def pip_install(python_exe, args, cwd=None, is_venv=True, timeout=900, show=True):
    """pip install с обходными путями: ensurepip, PEP 668 (--break-system-packages), --user."""
    base = [python_exe, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input']
    rc, out = run_stream(base + list(args), cwd=cwd, timeout=timeout, show=show)
    low = out.lower()
    if rc != 0 and 'no module named pip' in low:
        _run_quiet([python_exe, '-m', 'ensurepip', '--upgrade'], timeout=180)
        if not _pip_works(python_exe):
            _bootstrap_pip(python_exe)
        rc, out = run_stream(base + list(args), cwd=cwd, timeout=timeout, show=show)
        low = out.lower()
    if rc != 0 and not is_venv:
        if 'externally-managed-environment' in low or 'externally managed' in low:
            rc, out = run_stream(base + ['--break-system-packages'] + list(args),
                                 cwd=cwd, timeout=timeout, show=show)
        elif 'permission denied' in low or 'errno 13' in low or 'access is denied' in low:
            rc, out = run_stream(base + ['--user'] + list(args), cwd=cwd, timeout=timeout, show=show)
    return rc == 0, out


def _pip_target_install(pkg):
    """Ставит библиотеку самого менеджера в локальную папку (обходит PEP 668 и нехватку прав)."""
    for target in LIBS_DIRS:
        try:
            os.makedirs(target, exist_ok=True)
        except OSError:
            continue
        rc, _ = run_stream([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
                            '--no-input', '--target', target, pkg], timeout=300)
        if rc == 0:
            if target not in sys.path:
                sys.path.append(target)
            importlib.invalidate_caches()
            return True
    ok, _ = pip_install(sys.executable, [pkg], is_venv=False, timeout=300)
    importlib.invalidate_caches()
    return ok


def _try_import(name):
    try:
        importlib.invalidate_caches()
        return importlib.import_module(name)
    except Exception:
        return None


def _is_local_module(name, dirs):
    for d in dirs:
        if os.path.isfile(os.path.join(d, name + '.py')) or os.path.isdir(os.path.join(d, name)):
            return True
    return False


def get_imports(filepath):
    """Сторонние модули, которые импортирует файл (через ast; локальные модули и stdlib отброшены)."""
    mods = set()
    try:
        with open(filepath, 'rb') as f:
            src = f.read().decode('utf-8-sig', errors='replace')
    except Exception as e:
        log_error(f"Ошибка чтения {filepath}: {e}", show=False)
        return mods
    try:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    mods.add(a.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    mods.add(node.module.split('.')[0])
    except Exception:
        for m in re.finditer(r'^\s*import\s+([^\n#]+)', src, re.MULTILINE):
            for part in m.group(1).split(','):
                part = part.strip().split(' ')[0]
                if part:
                    mods.add(part.split('.')[0])
        for m in re.finditer(r'^\s*from\s+([a-zA-Z_][\w\.]*)\s+import', src, re.MULTILINE):
            mods.add(m.group(1).split('.')[0])

    dirs = {os.path.dirname(os.path.abspath(filepath)), os.getcwd()}
    result = set()
    for m in mods:
        if not m or not m.isidentifier() or m.startswith('_') or m == '__future__':
            continue
        if m in STDLIB_SAFE or _is_local_module(m, dirs):
            continue
        if m in WINDOWS_ONLY_PKGS and not IS_WIN:
            continue
        result.add(m)
    return result


def find_missing(python_exe, mods, cwd):
    """Какие модули не находятся в указанном Python (один запуск вместо N). None — проверка не удалась."""
    if not mods:
        return []
    code = ("import sys, json, importlib.util as u\n"
            "r = []\n"
            "for m in sys.argv[1:]:\n"
            "    try:\n"
            "        s = u.find_spec(m)\n"
            "    except Exception:\n"
            "        s = None\n"
            "    if s is None:\n"
            "        r.append(m)\n"
            "print(json.dumps(r))\n")
    ok, out = _run_quiet([python_exe, '-c', code] + sorted(mods), timeout=90, cwd=cwd)
    if ok:
        try:
            return json.loads(out.strip().splitlines()[-1])
        except Exception:
            pass
    return None


def _parse_requirements(req_file):
    specs = []
    try:
        with open(req_file, 'r', encoding='utf-8-sig', errors='replace') as f:
            for line in f:
                line = re.sub(r'\s+#.*$', '', line).strip()
                if not line or line.startswith('#') or line.startswith('-'):
                    continue
                specs.append(line)
    except Exception as e:
        log_error(f"Не прочитал {req_file}: {e}", show=False)
    return specs


def _deps_signature(python_exe, req_file, filepath):
    h = hashlib.sha1(python_exe.encode('utf-8', 'replace'))
    try:
        if os.path.isfile(req_file):
            with open(req_file, 'rb') as f:
                h.update(b'req:' + f.read())
        else:
            h.update(b'imp:' + ','.join(sorted(get_imports(filepath))).encode())
    except Exception:
        return None
    return h.hexdigest()


def install_dependencies(python_exe, dir_path, filepath, is_venv, venv_dir=None, quiet=False):
    """Ставит зависимости бота в выбранный Python (venv или глобальный). True — всё на месте."""
    if not SETTINGS["auto_install_deps"]:
        return True

    req_file = os.path.join(dir_path, 'requirements.txt')
    cache_file = os.path.join(venv_dir, '.kail_deps.json') if (is_venv and venv_dir) else None
    sig = _deps_signature(python_exe, req_file, filepath) if cache_file else None
    if cache_file and sig:
        cached = _read_json(cache_file, retries=1) or {}
        if sig in (cached.get('sigs') or {}):
            if not quiet:
                print(f"{Fore.GREEN}✅ Зависимости актуальны (кэш).")
            return True

    where = "venv" if is_venv else "глобальный Python"
    failed = []

    if os.path.isfile(req_file):
        print(f"{Fore.YELLOW}Устанавливаю requirements.txt ({where})...")
        ok, out = pip_install(python_exe, ['-r', req_file], cwd=dir_path, is_venv=is_venv, timeout=1800)
        if ok:
            print(f"{Fore.GREEN}✅ Requirements установлены.")
        else:
            print(f"{Fore.YELLOW}⚠ pip -r не прошёл — ставлю по одному пакету, чтобы один сбой не ломал всё...")
            log_error(f"pip -r fail: {out[-400:]}", show=False)
            for spec in _parse_requirements(req_file):
                ok1, out1 = pip_install(python_exe, [spec], cwd=dir_path, is_venv=is_venv,
                                        timeout=900, show=True)
                if ok1:
                    print(f"{Fore.GREEN}  ✅ {spec}")
                else:
                    print(f"{Fore.RED}  ❌ {spec}")
                    failed.append(spec)
                    log_error(f"pip fail {spec}: {out1[-300:]}", show=False)
    else:
        imports = get_imports(filepath)
        if imports:
            print(f"{Fore.YELLOW}Проверяю библиотеки для {os.path.basename(filepath)} ({where})...")
            missing = find_missing(python_exe, imports, dir_path)
            if missing is None:
                print(f"{Fore.YELLOW}⚠ Не удалось проверить библиотеки — пропускаю установку.")
                return False
            if not missing:
                print(f"{Fore.GREEN}✅ Все библиотеки уже установлены.")
            else:
                print(f"{Fore.YELLOW}Не хватает: {Fore.LIGHTCYAN_EX}{', '.join(sorted(missing))}")
                pip_names = []
                for m in sorted(missing):
                    n = PIP_NAME_MAP.get(m, m)
                    if n not in pip_names:
                        pip_names.append(n)
                print(f"{Fore.YELLOW}→ Устанавливаю: {Fore.LIGHTCYAN_EX}{' '.join(pip_names)}")
                ok, out = pip_install(python_exe, pip_names, cwd=dir_path, is_venv=is_venv, timeout=1800)
                if not ok:
                    print(f"{Fore.YELLOW}  ↻ Пакетная установка не прошла, ставлю по одному...")
                    for n in pip_names:
                        ok1, out1 = pip_install(python_exe, ['--no-cache-dir', n], cwd=dir_path,
                                                is_venv=is_venv, timeout=900)
                        if ok1:
                            print(f"{Fore.GREEN}  ✅ {n}")
                        else:
                            print(f"{Fore.RED}  ❌ {n}")
                            for line in out1.strip().splitlines()[-3:]:
                                print(f"{Fore.LIGHTBLACK_EX}     {line}")
                            failed.append(n)
                            log_error(f"pip fail {n}: {out1[-400:]}", show=False)
                still = find_missing(python_exe, set(missing), dir_path) or []
                if not still and not failed:
                    print(f"{Fore.GREEN}✅ Установлено библиотек: {len(pip_names)}")
                failed = failed or list(still)

    if failed:
        print(f"{Fore.RED}Не удалось установить: {', '.join(failed)}")
        return False
    if cache_file and sig:
        sigs = (_read_json(cache_file, retries=1) or {}).get('sigs') or {}
        sigs[sig] = time.time()
        if len(sigs) > 200:
            sigs = dict(sorted(sigs.items(), key=lambda kv: kv[1])[-100:])
        _atomic_write_json(cache_file, {"sigs": sigs})
    return True


# ======================================================================
#  venv (с обходными путями)
# ======================================================================
def _rmtree(path):
    def onerr(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=onerr)
    except Exception:
        pass


def _venv_dir_for(dir_path):
    """venv из другой ОС (общая папка Linux/Windows) не трогаем — создаём рядом venv-win / venv-linux."""
    base = os.path.join(dir_path, 'venv')
    has_bin = os.path.isdir(os.path.join(base, 'bin'))
    has_scripts = os.path.isdir(os.path.join(base, 'Scripts'))
    if IS_WIN and has_bin and not os.path.exists(os.path.join(base, 'Scripts', 'python.exe')):
        return base + '-win'
    if not IS_WIN and has_scripts and not has_bin:
        return base + '-linux'
    return base


def _venv_python(venv_dir):
    if IS_WIN:
        return os.path.join(venv_dir, 'Scripts', 'python.exe')
    for n in ('python3', 'python'):
        p = os.path.join(venv_dir, 'bin', n)
        if os.path.exists(p):
            return p
    return os.path.join(venv_dir, 'bin', 'python3')


def _python_works(py, timeout=30):
    ok, _ = _run_quiet([py, '-c', 'import sys; print(sys.version_info[0])'], timeout=timeout)
    return ok


def _pip_works(py):
    ok, _ = _run_quiet([py, '-m', 'pip', '--version'], timeout=60)
    return ok


def _base_pythons():
    cands = []

    def add(p):
        if p and os.path.exists(p) and p not in cands:
            cands.append(p)

    try:
        if getattr(sys, 'base_prefix', sys.prefix) != sys.prefix:
            base = sys.base_prefix
            add(os.path.join(base, 'python.exe') if IS_WIN else os.path.join(base, 'bin', 'python3'))
    except Exception:
        pass
    add(sys.executable)
    if IS_WIN:
        add(shutil.which('python'))
    else:
        add(shutil.which('python3'))
    return [c for c in cands if _python_works(c, 20)]


def _global_python():
    exe = sys.executable
    if IS_WIN and exe.lower().endswith('pythonw.exe'):
        alt = exe[:-len('pythonw.exe')] + 'python.exe'
        if os.path.exists(alt):
            return alt
    return exe or shutil.which('python3') or shutil.which('python') or 'python'


def _has_pyvenv_cfg(venv_dir):
    return os.path.isfile(os.path.join(venv_dir, 'pyvenv.cfg'))


def _download(url, dest, timeout=90):
    """Скачивает файл штатным urllib (проверка сертификатов НЕ отключается)."""
    try:
        import urllib.request
        tmp = dest + '.part'
        with urllib.request.urlopen(url, timeout=timeout) as r, open(tmp, 'wb') as f:
            shutil.copyfileobj(r, f)
        os.replace(tmp, dest)
        return os.path.getsize(dest) > 1000
    except Exception as e:
        log_error(f"download {url}: {e}", show=False)
        return False


def _tool_file(fname, url, min_size=1000):
    """Файл-помощник (virtualenv.pyz, get-pip.py) — лежит в .kail_libs, при отсутствии скачивается."""
    for d in LIBS_DIRS:
        p = os.path.join(d, fname)
        if os.path.isfile(p) and os.path.getsize(p) > min_size:
            return p
    for d in LIBS_DIRS:
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            continue
        p = os.path.join(d, fname)
        print(f"{Fore.YELLOW}⬇ Скачиваю {fname}...")
        if _download(url, p) and os.path.getsize(p) > min_size:
            return p
    return None


def _bootstrap_pip(py):
    """Нет pip и ensurepip (Debian/Ubuntu без python3-pip): ставим pip через get-pip.py."""
    gp = _tool_file('get-pip.py', 'https://bootstrap.pypa.io/get-pip.py', 100000)
    if not gp:
        return False
    for extra in (['--user', '--break-system-packages'], ['--user'], []):
        run_stream([py, gp] + extra, timeout=300)
        if _pip_works(py):
            return True
    return False


def _ask_timeout(prompt, timeout=60):
    """Вопрос с таймаутом (Linux): никто не ответил — считаем «нет», окно бота не зависает навсегда."""
    try:
        import select
        sys.stdout.write(prompt)
        sys.stdout.flush()
        r, _, _ = select.select([sys.stdin], [], [], timeout)
        if r:
            return sys.stdin.readline().strip().lower()
    except Exception:
        pass
    print()
    return 'n'


def _linux_install_python_tools():
    """Linux: ставит python3-venv / pip системным менеджером пакетов. True — команда прошла."""
    if IS_WIN or threading.current_thread() is not threading.main_thread():
        return False
    table = [('apt-get', ['apt-get', 'install', '-y', 'python3-venv', 'python3-pip']),
             ('dnf', ['dnf', 'install', '-y', 'python3-pip']),
             ('yum', ['yum', 'install', '-y', 'python3-pip']),
             ('pacman', ['pacman', '-S', '--noconfirm', 'python-pip']),
             ('zypper', ['zypper', '--non-interactive', 'install', 'python3-pip']),
             ('apk', ['apk', 'add', 'python3', 'py3-pip'])]
    cmd = None
    for exe, c in table:
        if shutil.which(exe):
            cmd = c
            break
    if not cmd:
        return False
    silent = False
    if _is_root():
        silent = True
    elif shutil.which('sudo'):
        try:
            silent = subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=15,
                                    stdin=subprocess.DEVNULL).returncode == 0
        except Exception:
            silent = False
    print(f"{Fore.YELLOW}Не хватает системных пакетов Python (venv/pip): {' '.join(cmd)}")
    if not (silent and SETTINGS.get("auto_system_packages", True)):
        if _ask_timeout(f"{Fore.YELLOW}Установить сейчас? (Y/n, 60 с): {Fore.WHITE}") in ('n', 'no', 'н', 'нет'):
            return False
    prefix = _sudo_prefix()
    if prefix is None:
        return False
    if cmd[0] == 'apt-get':
        _run_inherit(prefix + ['apt-get', 'update'], timeout=300)
    return _run_inherit(prefix + cmd, timeout=900) == 0


def _venv_finish(venv_dir):
    """venv создан? Есть ли в нём pip? Возвращает python venv или None."""
    vpy = _venv_python(venv_dir)
    if not (os.path.exists(vpy) and _python_works(vpy)):
        return None
    if not _pip_works(vpy):
        _run_quiet([vpy, '-m', 'ensurepip', '--upgrade'], timeout=180)
    if not _pip_works(vpy):
        return None
    _run_quiet([vpy, '-m', 'pip', 'install', '--upgrade', 'pip', '--quiet',
                '--disable-pip-version-check'], timeout=180)
    return vpy


def ensure_venv(dir_path, quiet=False):
    """
    Возвращает (python_venv, venv_dir) или (None, None).
    Цепочка обходных путей: venv -> virtualenv (модуль) -> virtualenv.pyz (качается сам, pip и
    python3-venv не нужны) -> установка python3-venv системным пакетным менеджером.
    """
    venv_dir = _venv_dir_for(dir_path)
    vpy = _venv_python(venv_dir)

    if os.path.exists(vpy) and _python_works(vpy):
        if not quiet:
            print(f"{Fore.GREEN}✅ venv уже существует: {venv_dir}")
        return vpy, venv_dir
    if os.path.isdir(venv_dir) and _has_pyvenv_cfg(venv_dir):
        print(f"{Fore.YELLOW}⚠ venv повреждён (обновился Python / перенесли папку?) — пересоздаю...")
        _rmtree(venv_dir)
    existed = os.path.isdir(venv_dir)

    print(f"{Fore.YELLOW}Создаю venv в {venv_dir}...")
    bases = _base_pythons()
    if not bases:
        print(f"{Fore.RED}❌ Не найден рабочий Python для создания venv.")
        return None, None

    state = {'out': ''}

    def attempt(cmd):
        rc, out = run_stream(cmd, timeout=300)
        vp = _venv_finish(venv_dir) if rc == 0 else None
        if vp:
            return vp
        state['out'] = out or state['out']
        if os.path.isdir(venv_dir) and (_has_pyvenv_cfg(venv_dir) or not existed):
            _rmtree(venv_dir)
        return None

    for bp in bases:
        vp = attempt([bp, '-m', 'venv', venv_dir])
        if vp:
            print(f"{Fore.GREEN}✅ venv создан: {venv_dir}")
            return vp, venv_dir

    print(f"{Fore.YELLOW}⚠ Стандартный venv не создался "
          f"{'(на Debian/Ubuntu: apt install python3-venv)' if not IS_WIN else ''} — пробую virtualenv...")
    for line in state['out'].strip().splitlines()[-2:]:
        print(f"{Fore.LIGHTBLACK_EX}   {line}")
    for bp in bases:
        ok, _ = _run_quiet([bp, '-m', 'virtualenv', '--version'], timeout=60)
        if not ok:
            ok, _ = pip_install(bp, ['virtualenv'], is_venv=False, timeout=300)
        if not ok:
            continue
        vp = attempt([bp, '-m', 'virtualenv', venv_dir])
        if vp:
            print(f"{Fore.GREEN}✅ venv создан через virtualenv: {venv_dir}")
            return vp, venv_dir

    pyz = _tool_file('virtualenv.pyz', 'https://bootstrap.pypa.io/virtualenv.pyz', 100000)
    if pyz:
        for bp in bases:
            vp = attempt([bp, pyz, venv_dir])
            if vp:
                print(f"{Fore.GREEN}✅ venv создан через virtualenv.pyz: {venv_dir}")
                return vp, venv_dir

    if not IS_WIN and _linux_install_python_tools():
        importlib.invalidate_caches()
        for bp in bases:
            vp = attempt([bp, '-m', 'venv', venv_dir])
            if vp:
                print(f"{Fore.GREEN}✅ venv создан: {venv_dir}")
                return vp, venv_dir

    log_error(f"Не удалось создать venv в {venv_dir}: {state['out'][-300:]}", show=False)
    return None, None


# ======================================================================
#  Боты
# ======================================================================
class WindowProc:
    """
    Бот, запущенный в отдельном окне консоли. Ведёт себя как subprocess.Popen (pid/poll/wait),
    но состояние берёт из реестра kail_bots/<token>.json, который пишет процесс-обёртка в окне.
    """
    def __init__(self, token, launcher=None, via=''):
        self.token = token
        self.launcher = launcher
        self.via = via
        self.pid = None
        self.ctime = None
        self.started = time.time()
        self.user_closed = False     # окно закрыли / Ctrl+C в окне — это не падение
        self._rc = None

    @property
    def reg_path(self):
        return os.path.join(BOT_DIR, self.token + '.json')

    def refresh(self):
        data = _read_json(self.reg_path, retries=1)
        if not data:
            return
        if data.get('pid') and not self.pid:
            self.pid = int(data['pid'])
            self.ctime = data.get('ctime')
        if data.get('exit') is not None:
            self._rc = int(data['exit'])
        self.user_closed = bool(data.get('closed'))

    def wait_registered(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            self.refresh()
            if self.pid:
                return True
            if self.launcher is not None:
                rc = self.launcher.poll()
                if rc is not None and rc != 0:
                    return False
            time.sleep(0.1)
        return False

    def poll(self):
        if self._rc is None:
            self.refresh()
        if self._rc is not None:
            return self._rc
        if self.pid:
            if pid_alive(self.pid, self.ctime):
                return None
            self.refresh()
            return self._rc if self._rc is not None else -1
        if self.launcher is not None:
            rc = self.launcher.poll()
            if rc not in (None, 0):
                return rc
        return None if time.time() - self.started < 20 else -1

    @property
    def returncode(self):
        return self.poll()

    def wait(self, timeout=None):
        end = time.time() + timeout if timeout else None
        while True:
            rc = self.poll()
            if rc is not None:
                return rc
            if end and time.time() > end:
                raise subprocess.TimeoutExpired('bot-window', timeout)
            time.sleep(0.1)

    def cleanup(self):
        try:
            os.remove(self.reg_path)
        except Exception:
            pass


class Bot:
    def __init__(self, name, proc, python, venv, want_venv, log_path, restarts=None, window=False):
        self.window = window
        self.name = name
        self.proc = proc
        self.pid = proc.pid
        self.python = python
        self.venv = venv              # реально запущен в venv
        self.want_venv = want_venv    # что просили (для перезапусков)
        self.log_path = log_path
        self.started = time.time()
        self.restarts = restarts if restarts is not None else deque(maxlen=50)

    def alive(self):
        return self.proc.poll() is None

    @property
    def returncode(self):
        return self.proc.poll()


def log_path_for(name):
    stem = os.path.splitext(os.path.basename(name))[0]
    if os.path.isabs(name):      # привязанный бот: папка в имени лога, чтобы main.py из разных папок не путались
        stem = re.sub(r'[^\w\-]', '_', os.path.basename(os.path.dirname(name)) or 'root')[:30] + '_' + stem
    return os.path.join(SETTINGS["log_dir"], stem + '.log')


def bot_name(num):
    idx = num - 1
    if 0 <= idx < len(file_list):
        return file_list[idx]
    return None


def _same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def scan_files():
    global file_list
    found = set()
    for f in glob.glob('*.py'):
        if os.path.isfile(f) and not _same_path(f, SCRIPT_PATH):
            found.add(f)
    for f in BINDS:
        if os.path.isfile(f) and not _same_path(f, SCRIPT_PATH):
            found.add(f)
    with BOTS_LOCK:
        for n, b in BOTS.items():      # работающий бот не пропадает из списка, даже если файл удалили
            if b.alive():
                found.add(n)
        file_list = sorted(found)
    return file_list


def _tail_lines(path, n):
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            f.seek(max(0, size - 65536))
            data = f.read()
        return data.decode('utf-8', 'replace').splitlines()[-n:], size
    except Exception:
        return [], 0


def _bot_env():
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def _choose_python(dir_path, want_venv, quiet=False):
    """(python_exe, venv_dir, is_venv) либо None, если запускать нечем."""
    if want_venv:
        py, vdir = ensure_venv(dir_path, quiet=quiet)
        if py:
            return py, vdir, True
        if SETTINGS["venv_fallback"]:
            print(f"{Fore.YELLOW}⚠ venv недоступен — запускаю в глобальном Python (venv_fallback).")
            return _global_python(), None, False
        print(f"{Fore.RED}❌ Не удалось подготовить venv (venv_fallback выключен).")
        return None
    return _global_python(), None, False


def _win_title(name):
    return re.sub(r'[^\w\-]', '_', os.path.splitext(os.path.basename(name))[0])[:20] or 'bot'


def _launch_bot_window(name, want_venv, install_deps, append_log, restarts):
    """
    Открывает отдельное окно консоли (Windows: новая консоль; Linux: терминал / tmux),
    а в нём — обёртку `kail_admin.py --botrun`: она сама ставит библиотеки, запускает бота
    с живым вводом/выводом (как руками) и дублирует вывод в лог. Возвращает Bot или None.
    """
    token = f"{os.getpid()}_{int(time.time() * 1000)}_{random.randint(100, 999)}"
    stem = _win_title(name)
    args = [_global_python(), SCRIPT_PATH, '--botrun', name, '--bot-id', token,
            '--parent-pid', str(os.getpid()),
            '--venv', '1' if want_venv else '0',
            '--deps', '1' if install_deps else '0',
            '--append', '1' if append_log else '0']
    try:
        os.makedirs(BOT_DIR, exist_ok=True)
    except OSError:
        pass
    if not IS_WIN:
        # tmux-сервер хранит СВОЁ окружение (PATH, токены...), а не наше — передаём окружение файлом
        env_path = os.path.join(BOT_DIR, token + '.env')
        try:
            with open(env_path, 'w', encoding='utf-8') as ef:
                json.dump(dict(os.environ), ef)
            try:
                os.chmod(env_path, 0o600)
            except OSError:
                pass
            args += ['--env-file', env_path]
        except Exception as e:
            log_error(f"env-файл: {e}", show=False)

    proc = None
    if IS_WIN:
        try:
            launcher = subprocess.Popen(args, cwd=BASE_DIR, close_fds=True,
                                        creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            log_error(f"Не открыть окно бота: {e}", show=False)
            return None
        cand = WindowProc(token, launcher, via='console')
        if cand.wait_registered(15):
            proc = cand
        else:
            terminate_tree(launcher.pid, grace=0, proc=launcher)
            cand.cleanup()
    else:
        for exe, cmd in _terminal_candidates(args, background=True, detached_tmux=True, title=stem):
            try:
                launcher = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            start_new_session=True)
            except Exception as e:
                log_error(f"Терминал {exe} не стартовал: {e}", show=False)
                continue
            cand = WindowProc(token, launcher, via=exe)
            if cand.wait_registered(10):
                proc = cand
                break
            if cand.pid:
                terminate_tree(cand.pid, grace=0.5)
            cand.cleanup()
    if proc is None:
        return None

    bot = Bot(name, proc, None, want_venv, want_venv, log_path_for(name), restarts, window=True)
    with BOTS_LOCK:
        BOTS[name] = bot
    return bot


def launch_bot(name, use_venv=None, install_deps=True, append_log=False,
               restarts=None, quiet=False, window=None):
    """Запускает бота. Возвращает Bot или None. venv и окно — по умолчанию из настроек."""
    abs_path = os.path.abspath(name)
    if not os.path.isfile(abs_path):
        log_error(f"Файл {abs_path} не найден!")
        return None
    dir_path = os.path.dirname(abs_path)
    want_venv, use_window = effective_opts(name, use_venv, window)

    if use_window:
        bot = _launch_bot_window(name, want_venv, install_deps, append_log, restarts)
        if bot:
            return bot
        print(f"{Fore.YELLOW}⚠ Не удалось открыть окно консоли (нет графического терминала/tmux?) — "
              f"запускаю в фоне, без ввода с клавиатуры.")

    chosen = _choose_python(dir_path, want_venv, quiet=quiet)
    if not chosen:
        return None
    python_exe, venv_dir, is_venv = chosen

    if install_deps:
        try:
            install_dependencies(python_exe, dir_path, abs_path, is_venv, venv_dir, quiet=quiet)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            log_error(f"Ошибка установки зависимостей: {e}", show=False)
            print(f"{Fore.YELLOW}⚠ Установка зависимостей прервалась ({e}) — пробую запустить как есть.")

    log_path = log_path_for(name)
    try:
        os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)
    except OSError as e:
        log_error(f"Не создать папку логов: {e}")
        return None

    mode = 'a' if append_log else 'w'
    try:
        if append_log and os.path.getsize(log_path) > 20 * 1024 * 1024:
            mode = 'w'
    except OSError:
        pass

    try:
        with open(log_path, mode, encoding='utf-8') as lf:
            stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            tag = ' [venv]' if is_venv else ''
            lf.write(("\n" if mode == 'a' else "") + f"=== Логи {name}{tag} | старт {stamp} ===\n")
            lf.write(f"Команда: {python_exe} -u {abs_path}\n")
            lf.write(f"Рабочая папка: {dir_path}\n")
            lf.write("=" * 50 + "\n\n")
            lf.flush()
            proc = subprocess.Popen([python_exe, '-u', abs_path], cwd=dir_path,
                                    stdin=subprocess.DEVNULL, stdout=lf, stderr=subprocess.STDOUT,
                                    env=_bot_env(), **_group_kwargs())
    except Exception as e:
        log_error(f"Ошибка запуска {name}: {e}")
        return None

    deadline = time.time() + 1.0
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.1)
    if proc.poll() is not None:
        last, _ = _tail_lines(log_path, 25)
        print(f"{Fore.RED}❌ {name} завершился сразу (код {proc.returncode})! Логи:")
        for line in last:
            print(f"{Fore.YELLOW}{line.rstrip()}")
        return None

    bot = Bot(name, proc, python_exe, is_venv, want_venv, log_path, restarts)
    with BOTS_LOCK:
        BOTS[name] = bot
    return bot


def kill_bot_process(bot, force=False):
    grace = 0 if force else SETTINGS["stop_grace"]
    if isinstance(bot.proc, WindowProc):
        # обёртка в окне при SIGTERM сама гасит бота и закрывается; добиваем по дереву
        ok = terminate_tree(bot.pid, grace=grace, group=True)
        bot.proc.cleanup()
        return ok
    return terminate_tree(bot.pid, grace=grace, group=True, proc=bot.proc)


def stop_bot(name, force=False):
    """Убирает бота из списка (чтобы монитор не перезапустил) и завершает всё его дерево."""
    with BOTS_LOCK:
        bot = BOTS.pop(name, None)
    if bot is None:
        return True
    return kill_bot_process(bot, force=force)


def stop_all_bots():
    with BOTS_LOCK:
        items = list(BOTS.values())
        BOTS.clear()
    if not items:
        return 0
    threads = []
    try:
        for b in items:
            t = threading.Thread(target=kill_bot_process, args=(b,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=SETTINGS["stop_grace"] + 10)
    except RuntimeError:       # завершение интерпретатора — потоки уже нельзя, делаем по очереди
        for b in items:
            kill_bot_process(b)
    return len(items)


# ---------- Привязка ботов из других папок ----------
def load_binds():
    BINDS.clear()
    data = _read_json(BINDS_FILE)
    if isinstance(data, list):
        for p in data:
            if isinstance(p, str) and p and p not in BINDS:
                BINDS.append(p)
    for p in BINDS:
        if not os.path.isfile(p):
            print(f"{Fore.YELLOW}⚠ Привязанный файл не найден: {p}  (уберите: unbind или верните файл)")


def save_binds():
    return _atomic_write_json(BINDS_FILE, list(BINDS))


# ---------- Сохранённые параметры запуска ботов ----------
def load_bot_prefs():
    BOT_PREFS.clear()
    data = _read_json(PREFS_FILE)
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                clean = {kk: bool(v[kk]) for kk in ('venv', 'window') if kk in v}
                if clean:
                    BOT_PREFS[k] = clean


def save_bot_prefs():
    return _atomic_write_json(PREFS_FILE, dict(BOT_PREFS))


def effective_opts(name, use_venv=None, window=None):
    """(venv, window): явный аргумент -> сохранённый для бота -> общие настройки."""
    p = BOT_PREFS.get(name, {})
    if use_venv is None:
        use_venv = p.get('venv', SETTINGS["use_venv"])
    if window is None:
        window = p.get('window', SETTINGS["bot_window"])
    return bool(use_venv), bool(window)


def _prefs_text(pf):
    bits = []
    if 'venv' in pf:
        bits.append('venv' if pf['venv'] else 'novenv')
    if 'window' in pf:
        bits.append('окно' if pf['window'] else 'фон')
    return ', '.join(bits)


def _parse_run_flags(raw):
    """Разбор флагов run. Возвращает (use_venv, use_window, save, reset) или None при ошибке."""
    venv_on = venv_off = win_on = win_off = save = reset = False
    for f in (x.lower() for x in raw):
        if f == '-venv-':
            venv_on = True
        elif f == '-novenv-':
            venv_off = True
        elif f == '-window-':
            win_on = True
        elif f == '-nowindow-':
            win_off = True
        elif f in ('sv', '-sv-', 'save', '-save-'):
            save = True
        elif f in ('-default-', '-reset-'):
            reset = True
        else:
            print(f"{Fore.RED}Неизвестный параметр: {f}")
            print(f"{Fore.LIGHTBLACK_EX}Доступно: -venv- -novenv- -window- -nowindow- sv -default-")
            return None
    if (venv_on and venv_off) or (win_on and win_off):
        print(f"{Fore.RED}Противоречивые параметры (например -venv- и -novenv- одновременно).")
        return None
    use_venv = True if venv_on else (False if venv_off else None)
    use_window = True if win_on else (False if win_off else None)
    return use_venv, use_window, save, reset


def _apply_run_prefs(num, name, use_venv, use_window, save, reset):
    """Сохраняет / сбрасывает постоянные параметры запуска бота. Вызывается до запуска."""
    if reset:
        if BOT_PREFS.pop(name, None) is not None:
            save_bot_prefs()
            print(f"{Fore.GREEN}✅ Бот {num}: сохранённые параметры сброшены — снова по общим настройкам.")
        else:
            print(f"{Fore.YELLOW}У бота {num} нет сохранённых параметров.")
        return
    if not save:
        return
    if use_venv is None and use_window is None:
        print(f"{Fore.YELLOW}sv: нечего сохранять — укажите параметр, например: run {num} -novenv- sv")
        return
    p = BOT_PREFS.setdefault(name, {})
    if use_venv is not None:
        p['venv'] = use_venv
    if use_window is not None:
        p['window'] = use_window
    if save_bot_prefs():
        print(f"{Fore.GREEN}✅ Сохранено для бота {num}: {_prefs_text(p)} "
              f"{Fore.LIGHTBLACK_EX}(теперь так же при обычном run {num} и после перезапуска менеджера)")


def cmd_prefs(parts):
    """prefs — список сохранённых параметров; prefs reset <num|all> — сбросить."""
    if len(parts) >= 2 and parts[1].lower() == 'reset':
        if len(parts) < 3:
            print(f"{Fore.RED}Пример: prefs reset 2   |   prefs reset all")
            return
        if parts[2].lower() == 'all':
            n = len(BOT_PREFS)
            BOT_PREFS.clear()
            save_bot_prefs()
            print(f"{Fore.GREEN}✅ Сброшено сохранённых параметров: {n}")
            return
        r = _bot_by_arg(parts[1:], "prefs reset 2")
        if not r:
            return
        if BOT_PREFS.pop(r[1], None) is not None:
            save_bot_prefs()
            print(f"{Fore.GREEN}✅ Параметры бота {r[0]} сброшены.")
        else:
            print(f"{Fore.YELLOW}У бота {r[0]} нет сохранённых параметров.")
        return
    if not BOT_PREFS:
        print(f"{Fore.YELLOW}Сохранённых параметров нет. Пример: run 2 -novenv- sv")
        return
    print(f"\n{Fore.CYAN}=== Сохранённые параметры запуска ({len(BOT_PREFS)}) ===\n")
    for name, pf in BOT_PREFS.items():
        num = file_list.index(name) + 1 if name in file_list else None
        label = f"{Fore.GREEN}№{num}" if num else f"{Fore.RED}нет в списке"
        print(f"  {label}{Fore.WHITE}  {name}  {Fore.LIGHTMAGENTA_EX}[{_prefs_text(pf)}]")
    print(f"\n{Fore.LIGHTBLACK_EX}Сбросить: {Fore.GREEN}prefs reset <num>{Fore.LIGHTBLACK_EX} | {Fore.GREEN}prefs reset all"
          f"{Fore.LIGHTBLACK_EX} | {Fore.GREEN}run <num> -default-")


def _clean_path(raw):
    raw = (raw or '').strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in '"\'':
        raw = raw[1:-1]
    return os.path.abspath(os.path.expanduser(os.path.expandvars(raw)))


def _bind_file(path):
    """True — добавлен. Печатает причину, если нет."""
    if not path.lower().endswith('.py'):
        print(f"{Fore.RED}Это не .py файл: {path}")
        return False
    if _same_path(path, SCRIPT_PATH):
        print(f"{Fore.RED}Нельзя привязать сам менеджер.")
        return False
    if os.path.normcase(os.path.dirname(path)) == os.path.normcase(BASE_DIR):
        print(f"{Fore.YELLOW}{os.path.basename(path)} лежит рядом с менеджером — он и так в списке.")
        return False
    if path in BINDS:
        print(f"{Fore.YELLOW}Уже привязан: {path}")
        return False
    BINDS.append(path)
    return True


def cmd_bind(raw):
    """bind <путь к .py или к папке с ботом> — привязывает бота; сохраняется между запусками."""
    if not raw.strip():
        print(f"{Fore.RED}Пример: bind /home/user/mybot   |   bind /home/user/mybot/main.py   |   bind \"C:\\боты\\tiktok\"")
        return
    path = _clean_path(raw)
    if not os.path.exists(path):
        print(f"{Fore.RED}Путь не найден: {path}")
        return
    added = []
    if os.path.isfile(path):
        if _bind_file(path):
            added.append(path)
    else:
        skip = {'setup.py', 'conftest.py', '__init__.py'}
        cands = sorted(f for f in os.listdir(path)
                       if f.lower().endswith('.py') and f not in skip
                       and os.path.isfile(os.path.join(path, f)))
        if not cands:
            print(f"{Fore.RED}В папке нет .py файлов: {path}")
            return
        if len(cands) == 1:
            pick = [cands[0]]
        else:
            print(f"{Fore.CYAN}В папке несколько скриптов:")
            for i, f in enumerate(cands, 1):
                print(f"  {Fore.WHITE}{i}. {f}")
            try:
                ans = read_line(f"{Fore.YELLOW}Номер (или несколько через пробел, all — все, Enter — отмена): "
                                f"{Fore.WHITE}").strip().lower()
            except (KeyboardInterrupt, EOFError):
                return
            if not ans:
                print(f"{Fore.YELLOW}Отменено.")
                return
            if ans == 'all':
                pick = cands
            else:
                pick = []
                for t in ans.replace(',', ' ').split():
                    if t.isdigit() and 1 <= int(t) <= len(cands):
                        pick.append(cands[int(t) - 1])
                if not pick:
                    print(f"{Fore.RED}Неверный выбор.")
                    return
        for f in pick:
            full = os.path.join(path, f)
            if _bind_file(full):
                added.append(full)
    if not added:
        return
    save_binds()
    scan_files()
    save_state()
    for full in added:
        n = file_list.index(full) + 1 if full in file_list else '?'
        print(f"{Fore.GREEN}✅ Привязан как бот {n}: {full}")
    print(f"{Fore.LIGHTBLACK_EX}Путь сохранён в {BINDS_FILE} — после перезапуска менеджера бот останется в списке.")


def cmd_unbind(num_str):
    try:
        num = int(num_str)
    except ValueError:
        print(f"{Fore.RED}Пример: unbind 3")
        return
    name = bot_name(num)
    if not name:
        print(f"{Fore.RED}Неверный номер.")
        return
    if name not in BINDS:
        print(f"{Fore.YELLOW}Бот {num} не привязан (лежит рядом с менеджером) — отвязывать нечего.")
        return
    with BOTS_LOCK:
        running_now = name in BOTS
    if running_now:
        print(f"{Fore.YELLOW}Останавливаю бота {num}...")
        stop_bot(name)
    BINDS.remove(name)
    save_binds()
    scan_files()
    save_state()
    print(f"{Fore.GREEN}✅ Отвязан: {name} (файл не тронут).")


def cmd_binds():
    if not BINDS:
        print(f"{Fore.YELLOW}Привязанных ботов нет. Добавить: bind <путь к папке или .py>")
        return
    print(f"\n{Fore.CYAN}=== Привязанные боты ({len(BINDS)}) ===\n")
    for p in BINDS:
        num = file_list.index(p) + 1 if p in file_list else None
        st = f"{Fore.GREEN}№{num}" if num else f"{Fore.RED}файл не найден"
        print(f"  {st}{Fore.WHITE}  {p}")
    print(f"\n{Fore.LIGHTBLACK_EX}Убрать: {Fore.GREEN}unbind <num>")


# ---------- State (для дочерних терминалов) ----------
def save_state():
    try:
        with BOTS_LOCK:
            names = list(file_list)
            bots = dict(BOTS)
            children = {}
            for k, t in list(child_terms.items()):
                if t.pid:
                    children[k] = t.pid
        procs, status, logs = {}, {}, {}
        for i, n in enumerate(names, 1):
            b = bots.get(n)
            if b:
                procs[str(i)] = b.pid
                status[str(i)] = b.alive()
            logs[str(i)] = log_path_for(n)
        state = {
            "manager_pid": os.getpid(),
            "file_list": names,
            "processes": procs,
            "process_status": status,
            "log_files": logs,
            "child_processes": children,
            "timestamp": time.time(),
        }
        with STATE_LOCK:
            _atomic_write_json(STATE_FILE, state)
    except Exception as e:
        log_error(f"Не удалось сохранить state: {e}", show=False)


def load_state():
    return _read_json(STATE_FILE)


# ---------- Уведомления из фоновых потоков ----------
_prompt_visible = False
_current_prompt = ''


def notify(msg):
    print(f"\n{msg}")
    if _prompt_visible and _current_prompt:
        try:
            sys.stdout.write(_current_prompt)
            sys.stdout.flush()
        except Exception:
            pass


# ---------- Авто-перезапуск ----------
def _monitor_once():
    with BOTS_LOCK:
        dead = [(n, b) for n, b in BOTS.items() if not b.alive()]
    for name, old in dead:
        with BOTS_LOCK:
            if BOTS.get(name) is not old:
                continue                      # пользователь уже сам что-то сделал
            if getattr(old.proc, 'user_closed', False):
                BOTS.pop(name, None)
                old.proc.cleanup()
                notify(f"{Fore.YELLOW}ℹ Окно бота {name} закрыто вручную (Ctrl+C / крестик) — "
                       f"бот остановлен, авто-перезапуска не будет. Запуск: run <num>")
                continue
            now = time.time()
            recent = [t for t in old.restarts if now - t < 600]
            if len(recent) >= SETTINGS["max_restarts"]:
                BOTS.pop(name, None)
                notify(f"{Fore.RED}⛔ Бот {name} падает слишком часто "
                       f"({len(recent)} раз за 10 минут) — авто-перезапуск отключён. "
                       f"Смотрите логи: logs <num>")
                continue
            recent.append(now)
            old.restarts = deque(recent, maxlen=50)
            tail_lines, _sz = _tail_lines(old.log_path, 6)
            tail_txt = ''.join(f"\n{Fore.LIGHTBLACK_EX}   │ {ln.rstrip()[:160]}" for ln in tail_lines)
            notify(f"{Fore.RED}⚠ Бот {name} упал (код {old.returncode}), перезапускаем...{tail_txt}")
            new = launch_bot(name, use_venv=old.want_venv, install_deps=False,
                             append_log=True, restarts=old.restarts, quiet=True,
                             window=old.window)
            if new:
                notify(f"{Fore.GREEN}✅ Бот {name} перезапущен (PID {new.pid})")
            else:
                notify(f"{Fore.RED}❌ Не удалось перезапустить {name} (повторю позже)")
    if dead:
        save_state()


def monitor_loop():
    waited = 0
    while running:
        time.sleep(1)
        waited += 1
        if waited < SETTINGS["monitor_interval"]:
            continue
        waited = 0
        if not SETTINGS["auto_restart"] or not running:
            continue
        try:
            _monitor_once()
        except Exception as e:
            log_error(f"monitor: {e}", show=False)


def state_saver():
    while running:
        save_state()
        for _ in range(max(1, SETTINGS["state_sync_interval"]) * 5):
            if not running:
                return
            time.sleep(0.2)


# ======================================================================
#  Дочерние терминалы (ott)
# ======================================================================
def _join_cmd(args):
    import shlex
    return ' '.join(shlex.quote(a) for a in args)


class ChildTerm:
    """
    Дочернее окно. Раньше хранили PID «лаунчера» (gnome-terminal / cmd start) — он умирает сразу,
    поэтому закрыть окно было невозможно. Теперь дочерний процесс сам регистрирует свой настоящий PID.
    """
    def __init__(self, action, token, launcher):
        self.action = action
        self.token = token
        self.launcher = launcher
        self.pid = None
        self.ctime = None
        self.started = time.time()

    @property
    def reg_path(self):
        return os.path.join(CHILD_DIR, self.token + '.json')

    def refresh(self):
        if self.pid:
            return
        data = _read_json(self.reg_path, retries=1)
        if data and data.get('pid'):
            self.pid = int(data['pid'])
            self.ctime = data.get('ctime')

    def alive(self):
        self.refresh()
        if self.pid:
            return pid_alive(self.pid, self.ctime)
        return time.time() - self.started < 10     # ещё запускается

    def close(self):
        self.refresh()
        ok = True
        if self.pid:
            ok = terminate_tree(self.pid, grace=1.0)
        elif self.launcher is not None and self.launcher.poll() is None:
            ok = terminate_tree(self.launcher.pid, grace=1.0, proc=self.launcher)
        try:
            os.remove(self.reg_path)
        except Exception:
            pass
        return ok


def _terminal_candidates(args, background=False, detached_tmux=False, title='kail'):
    """
    Список (имя, команда) способов открыть новое окно терминала на Linux/macOS.
    Порядок: окно tmux (если мы внутри tmux) -> графический терминал -> фоновая сессия tmux «kail»
    (для серверов без GUI / по SSH: посмотреть можно командой `tmux attach -t kail`).
    """
    cands = []
    if os.environ.get('TMUX') and shutil.which('tmux'):
        cands.append(('tmux', ['tmux', 'new-window'] + (['-d'] if background else [])
                      + ['-n', title, _join_cmd(args)]))
    in_ssh = bool(os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_CLIENT'))
    has_gui = bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')) and not in_ssh
    if has_gui:
        cands += _gui_terminal_candidates(args, os.environ.get('TERMINAL'))
    if detached_tmux and not os.environ.get('TMUX') and shutil.which('tmux'):
        try:
            has = subprocess.run(['tmux', 'has-session', '-t', 'kail'], capture_output=True,
                                 stdin=subprocess.DEVNULL, timeout=10).returncode == 0
        except Exception:
            has = False
        if has:
            cands.append(('tmux-detached', ['tmux', 'new-window', '-d', '-t', 'kail:', '-n', title,
                                            _join_cmd(args)]))
        else:
            cands.append(('tmux-detached', ['tmux', 'new-session', '-d', '-s', 'kail', '-n', title,
                                            _join_cmd(args)]))
    return cands


def _gui_terminal_candidates(args, term_env):
    cands = []
    if term_env and shutil.which(term_env):
        cands.append((term_env, [term_env, '-e'] + args))
    table = [
        ('gnome-terminal', lambda a: ['gnome-terminal', '--'] + a),
        ('konsole', lambda a: ['konsole', '-e'] + a),
        ('xfce4-terminal', lambda a: ['xfce4-terminal', '-x'] + a),
        ('mate-terminal', lambda a: ['mate-terminal', '-x'] + a),
        ('tilix', lambda a: ['tilix', '-e', _join_cmd(a)]),
        ('lxterminal', lambda a: ['lxterminal', '-e', _join_cmd(a)]),
        ('terminator', lambda a: ['terminator', '-x'] + a),
        ('kitty', lambda a: ['kitty'] + a),
        ('alacritty', lambda a: ['alacritty', '-e'] + a),
        ('foot', lambda a: ['foot'] + a),
        ('xterm', lambda a: ['xterm', '-e'] + a),
        ('x-terminal-emulator', lambda a: ['x-terminal-emulator', '-e'] + a),
    ]
    for exe, build in table:
        if shutil.which(exe):
            cands.append((exe, build(args)))
    return cands


def _wait_registration(term, timeout):
    end = time.time() + timeout
    while time.time() < end:
        term.refresh()
        if term.pid:
            return True
        if term.launcher is not None:
            rc = term.launcher.poll()
            if rc is not None and rc != 0:
                return False
        time.sleep(0.1)
    return False


def spawn_child_terminal(action):
    """Открывает окно дочернего терминала. Возвращает ChildTerm или None."""
    token = f"{os.getpid()}_{int(time.time() * 1000)}_{random.randint(100, 999)}"
    args = [_global_python(), SCRIPT_PATH, '--child', action,
            '--parent-pid', str(os.getpid()), '--child-id', token]
    save_state()
    try:
        os.makedirs(CHILD_DIR, exist_ok=True)
    except OSError:
        pass

    if IS_WIN:
        try:
            launcher = subprocess.Popen(args, cwd=BASE_DIR, close_fds=True,
                                        creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:
            log_error(f"Ошибка запуска дочернего: {e}")
            return None
        term = ChildTerm(action, token, launcher)
        if _wait_registration(term, 12):
            return term
        term.close()
        return None

    for exe, cmd in _terminal_candidates(args):
        try:
            launcher = subprocess.Popen(cmd, cwd=BASE_DIR, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
        except Exception as e:
            log_error(f"Терминал {exe} не стартовал: {e}", show=False)
            continue
        term = ChildTerm(action, token, launcher)
        if _wait_registration(term, 8):
            return term
        term.close()
    return None


def _sweep_child_registry(only_parent=None):
    """Чистит реестр дочерних окон. only_parent — убить всех детей этого родителя (при выходе)."""
    for fp in (glob.glob(os.path.join(CHILD_DIR, '*.json')) + glob.glob(os.path.join(BOT_DIR, '*.json'))):
        d = _read_json(fp, retries=1)
        if not d:
            try:
                os.remove(fp)
            except Exception:
                pass
            continue
        pid, par, ct = d.get('pid'), d.get('parent'), d.get('ctime')
        try:
            if only_parent is not None:
                if par != only_parent:
                    continue
                if pid and pid_alive(pid, ct):
                    terminate_tree(pid, grace=1.0)
                os.remove(fp)
            else:
                if not pid_alive(pid, ct):
                    os.remove(fp)
                elif par and not pid_alive(par):
                    terminate_tree(pid, grace=1.0)
                    os.remove(fp)
        except Exception:
            pass


def close_child_terminal(action):
    term = child_terms.pop(action, None)
    if term is None:
        return False
    try:
        term.close()
        return True
    except Exception as e:
        log_error(f"Ошибка закрытия дочернего: {e}")
        return False


def open_child_terminal(action, inline_fallback=True):
    """ott -y <action>. Если окно открыть нельзя (нет GUI/ssh) — выполняем прямо здесь."""
    existing = child_terms.get(action)
    if existing and existing.alive():
        print(f"{Fore.YELLOW}Уже открыт '{action}'.")
        return True
    if existing:
        child_terms.pop(action, None)

    parts = action.split()
    if parts and parts[0].lower() == 'logs':
        try:
            ln = int(parts[1])
        except (ValueError, IndexError):
            print(f"{Fore.RED}Синтаксис: ott -y logs <num>")
            return False
        if not resolve_log_path(ln):
            print(f"{Fore.RED}Лог бота {ln} ещё не создан. Запустите бота сначала.")
            return False

    term = spawn_child_terminal(action)
    if term:
        child_terms[action] = term
        print(f"{Fore.GREEN}✅ Дочерний '{action}' открыт (PID {term.pid})")
        save_state()
        return True

    if inline_fallback:
        print(f"{Fore.YELLOW}⚠ Не удалось открыть отдельное окно "
              f"({'нет графического терминала' if not IS_WIN else 'ошибка консоли'}) — "
              f"выполняю прямо здесь.")
        run_child_inline(action)
        return True
    print(f"{Fore.RED}❌ Не удалось открыть дочерний терминал.")
    return False


def run_child_inline(action):
    parts = action.split()
    if len(parts) == 2 and parts[0].lower() == 'logs':
        try:
            n = int(parts[1])
        except ValueError:
            return
        path = resolve_log_path(n)
        if not path:
            print(f"{Fore.RED}Лог не найден.")
            return
        print(f"{Fore.MAGENTA}Live-режим. Ctrl+C — выйти в консоль.\n")
        stop_ev = threading.Event()
        t = threading.Thread(target=_follow_log_thread, args=(path, n, stop_ev), daemon=True)
        t.start()
        try:
            while t.is_alive():
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        finally:
            stop_ev.set()
        print(f"\n{Fore.YELLOW}Выход из live-режима.")
    else:
        child_execute_action(action, load_state())


def cmd_ott_list():
    for action, t in list(child_terms.items()):
        if not t.alive():
            child_terms.pop(action, None)
            try:
                os.remove(t.reg_path)
            except Exception:
                pass
    if not child_terms:
        print(f"{Fore.YELLOW}Нет открытых дочерних терминалов.")
        return
    print(f"\n{Fore.CYAN}=== Дочерние терминалы ({len(child_terms)}) ===\n")
    for i, (action, t) in enumerate(child_terms.items(), 1):
        status = f"{Fore.GREEN}РАБОТАЕТ" if t.alive() else f"{Fore.RED}ЗАКРЫТ"
        print(f"  {Fore.WHITE}{i}. [{Fore.LIGHTCYAN_EX}{action}{Fore.WHITE}] PID {t.pid or '…'}  {status}")
    print(f"\n{Fore.LIGHTBLACK_EX}Закрыть: {Fore.GREEN}ott -n <action>{Fore.LIGHTBLACK_EX}  |  "
          f"Закрыть все: {Fore.GREEN}ott -n all")


# ======================================================================
#  Логотип
# ======================================================================
def show_banner():
    W = 75

    def row(text, color, left):
        return f"{Fore.CYAN}║{color}{' ' * left}{text}{' ' * max(0, W - left - len(text))}{Fore.CYAN}║"

    ver = f"Kail Admin  {VERSION}   [Admin bot OS]"
    print(f"""
{Fore.CYAN}╔═══════════════════════════════════════════════════════════════════════════╗
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}                                                                           {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   ██╗  ██╗ █████╗ ██╗██╗         █████╗ ██████╗ ███╗   ███╗██╗███╗   ██╗  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   ██║ ██╔╝██╔══██╗██║██║        ██╔══██╗██╔══██╗████╗ ████║██║████╗  ██║  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   █████╔╝ ███████║██║██║        ███████║██║  ██║██╔████╔██║██║██╔██╗ ██║  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   ██╔═██╗ ██╔══██║██║██║        ██╔══██║██║  ██║██║╚██╔╝██║██║██║╚██╗██║  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   ██║  ██╗██║  ██║██║███████╗   ██║  ██║██████╔╝██║ ╚═╝ ██║██║██║ ╚████║  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝   ╚═╝  ╚═╝╚═════╝ ╚═╝     ╚═╝╚═╝╚═╝  ╚═══╝  {Fore.CYAN}║
{Fore.CYAN}║{Fore.LIGHTGREEN_EX}                                                                           {Fore.CYAN}║
{Fore.CYAN}╠═══════════════════════════════════════════════════════════════════════════╣
{row(ver, Fore.YELLOW, 16)}
{row('"exclusively for Qwile Software"', Fore.MAGENTA, 16)}
{Fore.CYAN}╚═══════════════════════════════════════════════════════════════════════════╝
""")


def show_logo_only():
    clear_screen()
    show_banner()


# ======================================================================
#  Ввод
# ======================================================================
_ANSI_RE = re.compile(r'\033\[[0-9;]*m')


def _flush_stdin():
    """Сбрасывает буфер stdin, чтобы мусор от подпроцессов не «съедал» Enter."""
    try:
        if IS_WIN:
            import msvcrt
            n = 0
            while msvcrt.kbhit() and n < 2000:
                msvcrt.getwch()
                n += 1
        elif sys.stdin.isatty():
            import termios
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass


def read_line(prompt):
    global _prompt_visible, _current_prompt
    _flush_stdin()
    shown = prompt
    if HAS_READLINE and not IS_WIN:   # без этого readline неверно считает длину цветного приглашения
        shown = _ANSI_RE.sub(lambda m: '\001' + m.group(0) + '\002', prompt)
    _current_prompt = prompt
    _prompt_visible = True
    try:
        return input(shown)
    finally:
        _prompt_visible = False
        try:
            sys.stdout.write(Fore.RESET)
            sys.stdout.flush()
        except Exception:
            pass


# ======================================================================
#  Действия
# ======================================================================
def resolve_log_path(n, state=None):
    if state and state.get("log_files"):
        p = state["log_files"].get(str(n))
        if p and os.path.exists(p):
            return p
    name = bot_name(n)
    if name:
        p = log_path_for(name)
        if os.path.exists(p):
            return p
    legacy = os.path.join(SETTINGS["log_dir"], f"bot_{n}.log")
    return legacy if os.path.exists(legacy) else None


def action_list(state=None):
    if state is not None:
        files = state.get("file_list", [])
        procs = state.get("process_status", {})
        extra = {}
    else:
        files = list(file_list)
        with BOTS_LOCK:
            procs = {str(i): (n in BOTS and BOTS[n].alive()) for i, n in enumerate(files, 1)}
            extra = {str(i): BOTS[n] for i, n in enumerate(files, 1) if n in BOTS}

    print(f"\n{Fore.CYAN}=== Список файлов ({len(files)}) ===\n")
    if not files:
        print(f"{Fore.YELLOW}Нет .py файлов.")
        return
    for i, f in enumerate(files, 1):
        is_run = procs.get(str(i), False)
        status = f"{Fore.GREEN}[ЗАПУЩЕН]" if is_run else f"{Fore.RED}[ОСТАНОВЛЕН]"
        tail = ''
        b = extra.get(str(i))
        if b is not None:
            if is_run:
                tail = f" {Fore.LIGHTBLACK_EX}PID {b.pid}{' venv' if b.venv else ''}{' окно' if b.window else ''}"
            else:
                tail = f" {Fore.LIGHTBLACK_EX}(упал, код {b.returncode})"
        bind_tag = f" {Fore.LIGHTBLACK_EX}[привязан]" if os.path.isabs(f) else ""
        pf = BOT_PREFS.get(f)
        pref_tag = f" {Fore.LIGHTMAGENTA_EX}[{_prefs_text(pf)}*]" if pf else ""
        print(f"  {Fore.WHITE}{i}. {f}{bind_tag}{pref_tag} {status}{tail}")


def action_settings_show():
    print(f"\n{Fore.CYAN}=== Текущие настройки ===\n")
    for k, v in SETTINGS.items():
        desc = SETTINGS_DESCRIPTIONS.get(k, "")
        print(f"  {Fore.YELLOW}{k:<24}{Fore.WHITE}= {Fore.GREEN}{v}")
        if desc:
            print(f"      {Fore.LIGHTBLACK_EX}└─ {desc}")


def action_logs(parts, state=None):
    """Просмотр логов в текущей консоли (без окна)."""
    if len(parts) < 2:
        print(f"{Fore.RED}Синтаксис: logs <num> | logs all")
        print(f"{Fore.LIGHTBLACK_EX}Для живого просмотра: {Fore.GREEN}ott -y logs <num>")
        return

    if parts[1].lower() == 'all':
        print(f"\n{Fore.CYAN}=== Логи всех ботов ===\n")
        names = (state or {}).get("file_list") if state else file_list
        shown = 0
        for i, name in enumerate(names or [], 1):
            path = resolve_log_path(i, state)
            if not path:
                continue
            lines, size = _tail_lines(path, 15)
            print(f"{Fore.YELLOW}--- Бот {i} ({name}, {size // 1024} КБ) ---")
            for line in lines:
                print(f"{Fore.WHITE}{line.rstrip()}")
            print()
            shown += 1
        if not shown:
            print(f"{Fore.YELLOW}Нет логов. Сначала запустите ботов.")
        return

    try:
        n = int(parts[1])
    except ValueError:
        print(f"{Fore.RED}Неверный номер.")
        return
    path = resolve_log_path(n, state)
    if not path:
        print(f"{Fore.RED}Лог для бота {n} не найден.")
        return
    lines, size = _tail_lines(path, 30)
    print(f"\n{Fore.YELLOW}--- Бот {n} (последние 30 строк, {size // 1024} КБ) ---")
    for line in lines:
        print(f"{Fore.WHITE}{line.rstrip()}")
    print(f"\n{Fore.LIGHTBLACK_EX}Live-просмотр: {Fore.GREEN}ott -y logs {n}")


def action_info():
    print(f"\n{Fore.CYAN}=== ИНФОРМАЦИЯ О СИСТЕМЕ ===\n")
    print(f"  ОС:          {Fore.GREEN}{platform.system()} {platform.release()}")
    print(f"  Архитектура: {Fore.GREEN}{platform.machine()}")
    print(f"  Python:      {Fore.GREEN}{platform.python_version()}")
    print(f"  Имя узла:    {Fore.GREEN}{platform.node()}")
    if psutil:
        try:
            print(f"  Процессор:   {Fore.GREEN}{psutil.cpu_count()} ядер ({psutil.cpu_percent(interval=0.3)}%)")
            mem = psutil.virtual_memory()
            print(f"  RAM:         {Fore.GREEN}{mem.used / (1024 ** 3):.2f} / {mem.total / (1024 ** 3):.2f} GB ({mem.percent}%)")
        except Exception as e:
            log_error(f"Ошибка чтения CPU/RAM: {e}", show=False)
    else:
        print(f"  Процессор:   {Fore.GREEN}{os.cpu_count()} ядер {Fore.LIGHTBLACK_EX}(psutil не установлен — подробностей нет)")
    try:
        d = shutil.disk_usage('.')
        print(f"  Диск (cwd):  {Fore.GREEN}{(d.total - d.free) / (1024 ** 3):.2f} / {d.total / (1024 ** 3):.2f} GB "
              f"({(d.total - d.free) * 100 / d.total:.1f}%)")
    except Exception as e:
        log_error(f"Ошибка чтения диска: {e}", show=False)


def action_date():
    print(f"{Fore.LIGHTCYAN_EX}Дата/время: {Fore.GREEN}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def action_whoami():
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'
    print(f"{Fore.LIGHTCYAN_EX}Пользователь: {Fore.GREEN}{user}")


def _boot_timestamp():
    if psutil:
        try:
            return psutil.boot_time()
        except Exception:
            pass
    if IS_WIN:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.GetTickCount64.restype = ctypes.c_ulonglong
            return time.time() - k.GetTickCount64() / 1000.0
        except Exception:
            return None
    try:
        with open('/proc/uptime') as f:
            return time.time() - float(f.read().split()[0])
    except Exception:
        return None


def action_uptime():
    ts = _boot_timestamp()
    if ts is None:
        print(f"{Fore.YELLOW}Не удалось определить uptime.")
        return
    boot = datetime.fromtimestamp(ts)
    delta = datetime.now() - boot
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    print(f"{Fore.LIGHTCYAN_EX}Uptime: {Fore.GREEN}{delta.days}д {h}ч {m}м {s}с")
    print(f"{Fore.LIGHTCYAN_EX}Загрузка: {Fore.GREEN}{boot.strftime('%Y-%m-%d %H:%M:%S')}")


def action_history():
    if not command_history:
        print(f"{Fore.YELLOW}История пуста.")
        return
    print(f"\n{Fore.CYAN}=== История ({len(command_history)}) ===\n")
    for i, c in enumerate(command_history, 1):
        print(f"  {Fore.LIGHTBLACK_EX}{i:3}. {Fore.WHITE}{c}")


def action_version():
    print(f"{Fore.LIGHTCYAN_EX}{PRODUCT_NAME} {Fore.GREEN}{VERSION}{Fore.LIGHTCYAN_EX} [Admin bot OS]")
    print(f"{Fore.MAGENTA}exclusively for Qwile Software")


def action_refresh(state=None):
    if state is None:
        print(f"{Fore.YELLOW}Обновляю список файлов...")
        old = len(file_list)
        scan_files()
        new = len(file_list)
        if new > old:
            print(f"{Fore.GREEN}✅ Добавлено: {new - old}.")
        elif new < old:
            print(f"{Fore.YELLOW}⚠ Удалено: {old - new}.")
        else:
            print(f"{Fore.GREEN}✅ Актуально. Файлов: {new}")
        save_state()
    else:
        print(f"{Fore.GREEN}✅ Состояние синхронизировано с главным терминалом.")


# ---------- rename ----------
def cmd_rename(num_str, newname):
    """sudo rename <num> to <newname> — переименовать файл бота."""
    try:
        num = int(num_str)
    except ValueError:
        print(f"{Fore.RED}Неверный номер: {num_str}")
        return
    old_file = bot_name(num)
    if not old_file:
        print(f"{Fore.RED}Номер {num} вне списка (всего: {len(file_list)}).")
        return
    old_abs = os.path.abspath(old_file)
    dir_path = os.path.dirname(old_abs)

    newname = newname.strip()
    if newname.lower().endswith('.py'):
        newname = newname[:-3]
    if not newname:
        print(f"{Fore.RED}Пустое имя.")
        return
    if re.search(r'[\\/<>:"|?*\x00-\x1f]', newname) or newname in ('.', '..') or newname.endswith(('.', ' ')):
        print(f"{Fore.RED}Имя содержит недопустимые символы.")
        return

    new_file = newname + '.py'
    new_abs = os.path.join(dir_path, new_file)
    if _same_path(new_abs, SCRIPT_PATH):
        print(f"{Fore.RED}Это имя занято самим менеджером.")
        return
    if os.path.exists(new_abs) and not (os.path.exists(old_abs) and os.path.samefile(old_abs, new_abs)):
        print(f"{Fore.RED}Файл {new_file} уже существует.")
        return

    with BOTS_LOCK:
        running_now = old_file in BOTS
    if running_now:
        print(f"{Fore.YELLOW}Останавливаю бота {num} перед переименованием...")
        stop_bot(old_file)
    try:
        os.rename(old_abs, new_abs)
        was_bound = old_file in BINDS
        if was_bound:
            BINDS[BINDS.index(old_file)] = new_abs
            save_binds()
        if old_file in BOT_PREFS:
            BOT_PREFS[new_abs if was_bound else new_file] = BOT_PREFS.pop(old_file)
            save_bot_prefs()
        print(f"{Fore.GREEN}✅ Переименовано: {old_file} → {new_file}")
        scan_files()
        save_state()
    except Exception as e:
        print(f"{Fore.RED}❌ Ошибка переименования: {e}")
        log_error(f"rename fail: {e}", show=False)


# ======================================================================
#  Системные команды (sudo ...) — Linux и Windows
# ======================================================================
def _is_root():
    return hasattr(os, 'geteuid') and os.geteuid() == 0


def _run_inherit(cmd, timeout=None, shell=False):
    """Запуск с наследованием консоли: виден вывод, работает ввод пароля sudo (раньше это вешало программу)."""
    try:
        return subprocess.run(cmd, shell=shell, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"{Fore.RED}Таймаут команды.")
        return 124
    except FileNotFoundError:
        print(f"{Fore.RED}Команда не найдена: {cmd[0] if isinstance(cmd, list) else cmd}")
        return 127
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Прервано.")
        return 130
    except Exception as e:
        log_error(f"Ошибка выполнения команды: {e}")
        return 1


def _sudo_prefix():
    """[] если root, ['sudo'] если sudo есть и пароль получен / не нужен, None — sudo недоступен."""
    if IS_WIN or _is_root():
        return []
    if not shutil.which('sudo'):
        return None
    try:
        if subprocess.run(['sudo', '-n', 'true'], capture_output=True, timeout=15,
                          stdin=subprocess.DEVNULL).returncode == 0:
            return ['sudo']
    except Exception:
        pass
    print(f"{Fore.LIGHTBLACK_EX}Нужны права администратора — введите пароль sudo:")
    if _run_inherit(['sudo', '-v'], timeout=120) == 0:
        return ['sudo']
    return None


def _parse_shutdown_args(args):
    kind, delay, cancel, extra = 'poweroff', 0, False, []
    for a in args:
        la = a.lower()
        if la in ('-r', '--reboot'):
            kind = 'reboot'
        elif la in ('-h', '-p', '--poweroff', '--halt', '-halt'):
            kind = 'poweroff'
        elif la == '-c':
            cancel = True
        elif la == 'now':
            delay = 0
        elif la.startswith('+') and la[1:].isdigit():
            delay = int(la[1:]) * 60
        elif la in ('-f', '--force'):
            pass
        else:
            extra.append(a)
    return kind, delay, cancel, extra


def _power_windows(kind, delay=0, cancel=False):
    if cancel:
        return _run_inherit(['shutdown', '/a'])
    flag = '/r' if kind == 'reboot' else '/s'
    return _run_inherit(['shutdown', flag, '/f', '/t', str(int(delay))])


def _power_linux(kind):
    """Цепочка запасных вариантов: systemctl -> shutdown -> reboot/poweroff/halt -> loginctl."""
    table = {
        'reboot':   [['systemctl', 'reboot'], ['shutdown', '-r', 'now'], ['reboot']],
        'poweroff': [['systemctl', 'poweroff'], ['shutdown', '-h', 'now'], ['poweroff']],
        'halt':     [['systemctl', 'halt'], ['shutdown', '-H', 'now'], ['halt']],
    }
    prefix = _sudo_prefix()
    attempts = []
    if prefix is not None:
        attempts += [prefix + c for c in table[kind] if shutil.which(c[0])]
    if prefix != []:     # без sudo: polkit/logind часто разрешает локальному пользователю
        if shutil.which('systemctl'):
            attempts.append(table[kind][0])
        if shutil.which('loginctl'):
            attempts.append(['loginctl', kind])
    if not attempts:
        print(f"{Fore.RED}❌ Нет ни одного способа выполнить '{kind}' (нужен sudo/systemctl).")
        return 1
    last = 1
    for cmd in attempts:
        print(f"{Fore.LIGHTBLACK_EX}→ {' '.join(cmd)}")
        last = _run_inherit(cmd, timeout=60)
        if last == 0:
            return 0
    return last


def _win_systemctl(rest):
    if len(rest) < 2:
        print(f"{Fore.RED}Пример: sudo systemctl restart <служба>   (start | stop | restart | status)")
        return 1
    action, svc = rest[0].lower(), rest[1]
    if action == 'status':
        return _run_inherit(['sc', 'query', svc])
    if action == 'start':
        return _run_inherit(['net', 'start', svc])
    if action == 'stop':
        return _run_inherit(['net', 'stop', svc])
    if action == 'restart':
        _run_inherit(['net', 'stop', svc])
        return _run_inherit(['net', 'start', svc])
    print(f"{Fore.RED}На Windows поддерживаются: start | stop | restart | status")
    return 1


def execute_system_cmd(cmd_parts):
    if len(cmd_parts) < 2:
        print(f"{Fore.RED}Укажите команду. Пример: sudo reboot")
        return
    args = cmd_parts[1:]
    name = args[0].lower()
    rest = args[1:]
    cmdline = ' '.join(args)

    if IS_WIN and name in LINUX_ONLY_CMDS:
        print(f"{Fore.RED}❌ '{name}' — команда Linux, на Windows недоступна.")
        return

    print(f"{Fore.YELLOW}Выполняю: {cmdline}")
    if SETTINGS["sudo_confirm"]:
        print(f"{Fore.RED}⚠ Системная команда!")
        try:
            confirm = read_line(f"{Fore.YELLOW}Продолжить? (y/N): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            confirm = 'n'
        if confirm not in ('y', 'yes', 'д', 'да'):
            print(f"{Fore.RED}Отменено.")
            return

    rc = 0
    try:
        if name in POWER_CMDS:
            if name == 'reboot':
                kind, delay, cancel, extra = 'reboot', 0, False, []
                for a in rest:
                    if a.startswith('+') and a[1:].isdigit():
                        delay = int(a[1:]) * 60
            elif name == 'shutdown':
                kind, delay, cancel, extra = _parse_shutdown_args(rest)
            else:
                kind, delay, cancel, extra = ('poweroff' if name == 'poweroff' else 'halt'), 0, False, []
            if IS_WIN:
                if extra:
                    print(f"{Fore.YELLOW}Параметры {extra} на Windows не поддерживаются — игнорирую.")
                rc = _power_windows(kind, delay, cancel)
            elif delay or cancel or extra or (name != 'shutdown' and rest and rest != ['now']):
                prefix = _sudo_prefix()          # нестандартные параметры — передаём как есть
                rc = _run_inherit((prefix or []) + args)
            else:
                rc = _power_linux(kind)
            if rc == 0:
                print(f"{Fore.GREEN}✅ Команда принята системой.")
        elif name == 'systemctl' and IS_WIN:
            rc = _win_systemctl(rest)
        elif IS_WIN:
            rc = _run_inherit(cmdline, shell=True)
        else:
            prefix = _sudo_prefix()
            if prefix is None:
                print(f"{Fore.YELLOW}⚠ sudo недоступен — пробую без него.")
                prefix = []
            rc = _run_inherit(prefix + args)

        if rc == 0:
            if name not in POWER_CMDS:
                print(f"{Fore.GREEN}✅ Выполнено")
        else:
            print(f"{Fore.RED}❌ Ошибка (код {rc})")
            if IS_WIN and name not in POWER_CMDS:
                print(f"{Fore.LIGHTBLACK_EX}Возможно, нужны права администратора "
                      f"(запустите консоль «От имени администратора»).")
            log_error(f"Системная команда '{cmdline}' завершилась с кодом {rc}", show=False)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Прервано.")
    except Exception as e:
        log_error(f"Ошибка системной команды: {e}")


# ======================================================================
#  Настройки (меню)
# ======================================================================
def settings_menu():
    while True:
        clear_screen()
        show_banner()
        print(f"{Fore.YELLOW}=== НАСТРОЙКИ СИСТЕМЫ ===\n")
        items = list(SETTINGS.keys())
        for i, key in enumerate(items, 1):
            val = SETTINGS[key]
            if isinstance(val, bool):
                vs = f"{Fore.GREEN}ВКЛ" if val else f"{Fore.RED}ВЫКЛ"
            else:
                vs = f"{Fore.LIGHTCYAN_EX}{val}"
            print(f"  {Fore.WHITE}{i:2}. {Fore.YELLOW}{key:<24}{Fore.WHITE}= {vs}")
            desc = SETTINGS_DESCRIPTIONS.get(key, "")
            if desc:
                print(f"      {Fore.LIGHTBLACK_EX}└─ {desc}")
        print(f"\n  {Fore.GREEN}<номер>{Fore.WHITE} - изменить  |  "
              f"{Fore.GREEN}reset{Fore.WHITE} - сброс  |  "
              f"{Fore.GREEN}save{Fore.WHITE} - сохранить  |  "
              f"{Fore.GREEN}exit{Fore.WHITE} - назад\n")
        try:
            cmd = read_line(f"{Fore.YELLOW}settings> {Fore.WHITE}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue
        low = cmd.lower()
        if low == 'exit':
            break
        if low == 'save':
            if save_settings():
                print(f"{Fore.GREEN}✅ Сохранено в {SETTINGS_FILE}")
            time.sleep(0.8)
            continue
        if low == 'reset':
            for k, v in DEFAULT_SETTINGS.items():
                SETTINGS[k] = v
            save_settings()
            _ensure_log_dir()
            print(f"{Fore.GREEN}✅ Сброшено.")
            time.sleep(0.8)
            continue
        try:
            idx = int(cmd) - 1
            if 0 <= idx < len(items):
                key = items[idx]
                cur = SETTINGS[key]
                print(f"\n{Fore.LIGHTCYAN_EX}{key}: {Fore.LIGHTBLACK_EX}{SETTINGS_DESCRIPTIONS.get(key, '')}")
                print(f"{Fore.WHITE}Текущее: {Fore.GREEN}{cur}")
                if isinstance(cur, bool):
                    print(f"{Fore.LIGHTBLACK_EX}Введите true/false")
                elif isinstance(cur, int):
                    print(f"{Fore.LIGHTBLACK_EX}Введите целое число")
                nv = read_line(f"{Fore.YELLOW}Новое (Enter — отмена): {Fore.WHITE}").strip()
                if nv:
                    if isinstance(cur, int) and not isinstance(cur, bool):
                        int(nv)  # проверка: ValueError -> «Неверный ввод»
                    SETTINGS[key] = _coerce(key, nv)
                    if key == 'log_dir':
                        _ensure_log_dir()
                    save_settings()
                    print(f"{Fore.GREEN}✅ {key} = {SETTINGS[key]}")
                    time.sleep(0.8)
        except ValueError:
            print(f"{Fore.RED}Неверный ввод.")
            time.sleep(0.8)
        except (KeyboardInterrupt, EOFError):
            break


def _ensure_log_dir():
    try:
        os.makedirs(SETTINGS["log_dir"], exist_ok=True)
    except OSError as e:
        log_error(f"Не удалось создать папку логов '{SETTINGS['log_dir']}': {e}; использую 'logs'")
        SETTINGS["log_dir"] = "logs"
        try:
            os.makedirs("logs", exist_ok=True)
        except OSError:
            pass


# ======================================================================
#  Справка
# ======================================================================
def show_help():
    if IS_WIN:
        sudo_block = f"""
{Fore.LIGHTCYAN_EX}══════════ СИСТЕМНЫЕ КОМАНДЫ (через sudo, Windows) ══════════
  {Fore.GREEN}sudo reboot             {Fore.WHITE}- перезагрузить систему
  {Fore.GREEN}sudo shutdown now       {Fore.WHITE}- выключить сейчас
  {Fore.GREEN}sudo poweroff           {Fore.WHITE}- выключить
  {Fore.GREEN}sudo halt               {Fore.WHITE}- выключить
  {Fore.GREEN}sudo systemctl restart <svc>   {Fore.WHITE}- перезапустить службу Windows (start|stop|restart|status)
  {Fore.GREEN}sudo <команда>          {Fore.WHITE}- любая команда cmd (для служб нужна консоль от администратора)
"""
    else:
        sudo_block = f"""
{Fore.LIGHTCYAN_EX}══════════ СИСТЕМНЫЕ КОМАНДЫ (через sudo) ══════════
  {Fore.GREEN}sudo reboot             {Fore.WHITE}- перезагрузить систему
  {Fore.GREEN}sudo shutdown now       {Fore.WHITE}- выключить сейчас
  {Fore.GREEN}sudo poweroff           {Fore.WHITE}- выключить
  {Fore.GREEN}sudo halt               {Fore.WHITE}- остановить
  {Fore.GREEN}sudo systemctl restart <svc>   {Fore.WHITE}- перезапустить сервис
  {Fore.GREEN}sudo apt update         {Fore.WHITE}- обновить список пакетов
  {Fore.GREEN}sudo chmod +x <file>    {Fore.WHITE}- сделать исполняемым
"""
    print(f"""
{Fore.LIGHTCYAN_EX}══════════ УПРАВЛЕНИЕ БОТАМИ ══════════
  {Fore.GREEN}list                    {Fore.WHITE}- список .py файлов
  {Fore.GREEN}run <num>               {Fore.WHITE}- запустить бота (venv — по настройке use_venv, по умолчанию ВКЛ)
  {Fore.GREEN}run <num> -venv-        {Fore.WHITE}- запустить в отдельном venv
  {Fore.GREEN}run <num> -novenv-      {Fore.WHITE}- запустить в глобальном Python
  {Fore.GREEN}run <num> -window-      {Fore.WHITE}- запустить в отдельном окне консоли (по умолчанию — настройка bot_window)
  {Fore.GREEN}run <num> -nowindow-    {Fore.WHITE}- запустить в фоне, без окна
  {Fore.GREEN}run <num> <флаги> sv    {Fore.WHITE}- ЗАПОМНИТЬ флаги для этого бота (напр. run 2 -novenv- sv) —
                          {Fore.WHITE}  дальше обычный run 2 / restart / allrun / авто-перезапуск идут так же,
                          {Fore.WHITE}  и после перезапуска менеджера тоже ({PREFS_FILE})
  {Fore.GREEN}run <num> -default-     {Fore.WHITE}- сбросить сохранённое и запустить по общим настройкам
  {Fore.GREEN}prefs                   {Fore.WHITE}- список сохранённых параметров ботов
  {Fore.GREEN}prefs reset <num|all>   {Fore.WHITE}- сбросить сохранённые параметры
  {Fore.GREEN}allrun                  {Fore.WHITE}- запустить всех
  {Fore.GREEN}stop <num>              {Fore.WHITE}- остановить бота
  {Fore.GREEN}allstop / stopall       {Fore.WHITE}- остановить всех ботов
  {Fore.GREEN}allrestart              {Fore.WHITE}- перезапустить всех запущенных
  {Fore.GREEN}restart <num>           {Fore.WHITE}- перезапустить бота
  {Fore.GREEN}kill <num>              {Fore.WHITE}- убить принудительно
  {Fore.GREEN}sudo rename <num> to <name>  {Fore.WHITE}- переименовать файл бота
  {Fore.GREEN}fix <num>               {Fore.WHITE}- пересоздать venv бота и запустить заново
  {Fore.GREEN}doctor [num]            {Fore.WHITE}- диагностика окружения (и бота) — почему не запускается
  {Fore.GREEN}attach [num]            {Fore.WHITE}- Linux/tmux: открыть консоль бота (выход: Ctrl+B, D)

{Fore.LIGHTCYAN_EX}══════════ БОТЫ В ДРУГИХ ПАПКАХ ══════════
  {Fore.GREEN}bind <путь>             {Fore.WHITE}- привязать бота: путь к .py или к папке (запоминается навсегда)
  {Fore.GREEN}unbind <num>            {Fore.WHITE}- отвязать бота (файл не удаляется)
  {Fore.GREEN}binds                   {Fore.WHITE}- список привязанных

{Fore.LIGHTCYAN_EX}══════════ ЛОГИ ══════════
  {Fore.GREEN}logs <num>              {Fore.WHITE}- показать логи в консоли
  {Fore.GREEN}logs all                {Fore.WHITE}- показать все логи в консоли
  {Fore.LIGHTBLACK_EX}  (для live-просмотра используйте дочерний терминал ↓)

{Fore.LIGHTCYAN_EX}══════════ ДОЧЕРНИЕ ТЕРМИНАЛЫ ══════════
  {Fore.GREEN}ott list                {Fore.WHITE}- список дочерних
  {Fore.GREEN}ott -y <action>         {Fore.WHITE}- открыть дочерний (list, settings, logs <n>)
  {Fore.GREEN}ott -y logs <num>       {Fore.WHITE}- live-просмотр логов бота
  {Fore.GREEN}ott -n <action>         {Fore.WHITE}- закрыть конкретный
  {Fore.GREEN}ott -n all              {Fore.WHITE}- закрыть все дочерние

{Fore.LIGHTCYAN_EX}══════════ СИСТЕМА ══════════
  {Fore.GREEN}info                    {Fore.WHITE}- инфо о системе
  {Fore.GREEN}date                    {Fore.WHITE}- дата и время
  {Fore.GREEN}whoami                  {Fore.WHITE}- пользователь
  {Fore.GREEN}uptime                  {Fore.WHITE}- время работы
  {Fore.GREEN}history                 {Fore.WHITE}- история команд
  {Fore.GREEN}version                 {Fore.WHITE}- версия
  {Fore.GREEN}banner                  {Fore.WHITE}- показать лого
  {Fore.GREEN}refresh                 {Fore.WHITE}- обновить список файлов
  {Fore.GREEN}echo <text>             {Fore.WHITE}- вывести текст
{sudo_block}
{Fore.LIGHTCYAN_EX}══════════ ИНТЕРФЕЙС ══════════
  {Fore.GREEN}settings                {Fore.WHITE}- меню настроек (сохраняются в {SETTINGS_FILE})
  {Fore.GREEN}clear / cls             {Fore.WHITE}- очистить экран (лого остаётся)
  {Fore.GREEN}help                    {Fore.WHITE}- эта справка
  {Fore.GREEN}exit                    {Fore.WHITE}- выход

{Fore.YELLOW}Логи ошибок: {ERROR_LOG_FILE}
{Fore.LIGHTCYAN_EX}═════════════════════════════════════════
""")


# ======================================================================
#  Child mode
# ======================================================================
def _follow_log_thread(log_path, bot_num, stop_event, tail_lines=30):
    """Live-просмотр лога: переживает перезапись лога и неполные строки."""
    label = f"{Fore.LIGHTCYAN_EX}[bot {bot_num}]{Fore.WHITE}"
    try:
        while not os.path.exists(log_path):
            if stop_event.wait(0.5):
                return
        with open(log_path, 'rb') as f:
            data = f.read()
            for line in data.decode('utf-8', 'replace').splitlines()[-tail_lines:]:
                if stop_event.is_set():
                    return
                print(f"{label} {line}")
            pos = f.tell()
            buf = b''
            while not stop_event.is_set():
                try:
                    size = os.path.getsize(log_path)
                except OSError:
                    size = pos
                if size < pos:     # лог перезаписан (новый запуск бота)
                    f.seek(0)
                    pos, buf = 0, b''
                    print(f"{Fore.YELLOW}--- лог перезапущен ---")
                chunk = f.read()
                if chunk:
                    pos = f.tell()
                    buf += chunk
                    *lines, buf = buf.split(b'\n')
                    for line in lines:
                        print(f"{label} {line.decode('utf-8', 'replace').rstrip()}")
                else:
                    stop_event.wait(0.3)
    except Exception as e:
        print(f"{Fore.RED}Ошибка чтения лога: {e}")


def _box(lines, color=Fore.YELLOW, width=62):
    out = [f"{color}╔{'═' * width}╗"]
    for text, c in lines:
        out.append(f"{color}║{c}{text[:width].ljust(width)}{color}║")
    out.append(f"{color}╚{'═' * width}╝")
    return '\n'.join(out)


def draw_child_header(action, parent_pid, live=False):
    clear_screen()
    title = "ДОЧЕРНИЙ ТЕРМИНАЛ — " + ("LIVE LOGS" if live else "CHILD PROCESS")
    print(_box([
        (title.center(62), Fore.LIGHTRED_EX),
        (f"  Родитель: {parent_pid:<10}  Мой PID: {os.getpid():<15}", Fore.WHITE),
        (f"  Действие: {action}", Fore.LIGHTCYAN_EX),
    ]))
    if live:
        print(f"{Fore.MAGENTA}  Live-режим. Нажмите Ctrl+C чтобы выйти.")
        print(f"{Fore.MAGENTA}  Автоматически закроется при закрытии главного терминала.\n")
    else:
        print(f"{Fore.MAGENTA}  Состояние синхронизируется автоматически каждые {SETTINGS.get('state_sync_interval', 2)}с.")
        print(f"{Fore.MAGENTA}  Введите {Fore.GREEN}exit{Fore.MAGENTA} для закрытия.\n")


def child_execute_action(action, state=None):
    parts = action.strip().split()
    if not parts:
        return
    if state and state.get("file_list") is not None:
        file_list[:] = state["file_list"]     # номера в child = номера в главном терминале
    cmd = parts[0].lower()

    if cmd == 'list':
        action_list(state)
    elif cmd == 'settings':
        action_settings_show()
    elif cmd == 'logs':
        action_logs(parts, state)
    elif cmd == 'info':
        action_info()
    elif cmd == 'date':
        action_date()
    elif cmd == 'whoami':
        action_whoami()
    elif cmd == 'uptime':
        action_uptime()
    elif cmd == 'history':
        action_history()
    elif cmd == 'version':
        action_version()
    elif cmd == 'banner':
        show_banner()
    elif cmd == 'refresh':
        pass
    elif cmd == 'echo':
        print(' '.join(parts[1:]))
    elif cmd == 'help':
        show_help()
    elif cmd in ('clear', 'cls'):
        pass
    else:
        print(f"{Fore.RED}Неизвестная команда: {cmd}. Введите help.")


def redraw_child(action, parent_pid, state=None):
    draw_child_header(action, parent_pid)
    if state is None:
        state = load_state()
    if state:
        action_list(state)


def _argval(flag, default=None):
    try:
        return sys.argv[sys.argv.index(flag) + 1]
    except (ValueError, IndexError):
        return default


def _register_child(token, action, parent_pid):
    """Дочерний процесс сообщает родителю свой НАСТОЯЩИЙ PID — по нему окно можно закрыть."""
    if not token:
        return None
    try:
        os.makedirs(CHILD_DIR, exist_ok=True)
    except OSError:
        return None
    path = os.path.join(CHILD_DIR, token + '.json')
    ct = None
    if psutil:
        try:
            ct = psutil.Process().create_time()
        except Exception:
            pass
    _atomic_write_json(path, {"pid": os.getpid(), "action": action, "parent": parent_pid,
                              "ctime": ct, "started": time.time()})
    return path


def _child_watchdog(parent_pid, reg_path):
    """Закрывает child, когда умер родитель — даже если child сидит в input()."""
    interval = max(1, int(SETTINGS.get("child_check_interval", 3)))
    while True:
        time.sleep(interval)
        if parent_pid and not pid_alive(parent_pid):
            try:
                if reg_path:
                    os.remove(reg_path)
            except Exception:
                pass
            os._exit(0)


def _run_child_mode_impl():
    action = _argval('--child', 'help')
    try:
        parent_pid = int(_argval('--parent-pid', 0))
    except (TypeError, ValueError):
        parent_pid = 0
    token = _argval('--child-id')

    reg_path = _register_child(token, action, parent_pid)
    if reg_path:
        atexit.register(lambda: os.path.exists(reg_path) and os.remove(reg_path))
    threading.Thread(target=_child_watchdog, args=(parent_pid, reg_path), daemon=True).start()
    _set_title(f"Kail child: {action}")

    state = load_state()
    if state and state.get("file_list") is not None:
        file_list[:] = state["file_list"]

    parts = action.strip().split()

    # --- Спец-режим: live-просмотр логов (ott -y logs <num>) ---
    if len(parts) == 2 and parts[0].lower() == 'logs' and parts[1].isdigit():
        n = int(parts[1])
        draw_child_header(f"logs {n}", parent_pid, live=True)
        path = resolve_log_path(n, state) or os.path.join(SETTINGS["log_dir"], f"bot_{n}.log")
        stop_ev = threading.Event()
        t = threading.Thread(target=_follow_log_thread, args=(path, n, stop_ev), daemon=True)
        t.start()
        try:
            while t.is_alive():
                time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Выход из live-режима.")
        stop_ev.set()
        return

    # --- Обычный режим child ---
    draw_child_header(action, parent_pid)
    if state:
        action_list(state)
    child_execute_action(action, state)

    while True:
        try:
            cmd = read_line(f"{Fore.YELLOW}child [{action}]> {Fore.WHITE}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue
        command_history.append(f"[child] {cmd}")
        low = cmd.lower()

        if low == 'exit':
            break
        if low.startswith('ott') and '-n' in cmd.split():
            break
        if low in ('clear', 'cls'):
            redraw_child(action, parent_pid, load_state())
            continue
        if low == 'refresh':
            redraw_child(action, parent_pid, load_state())
            print(f"{Fore.GREEN}✅ Состояние синхронизировано с главным терминалом.")
            continue
        if low == 'banner':
            show_banner()
            continue
        try:
            child_execute_action(cmd, load_state())
        except Exception as e:
            log_error(f"child: {e}", show=False)
            print(f"{Fore.RED}Ошибка: {e}")

    print(f"\n{Fore.YELLOW}Дочерний терминал завершён.")
    time.sleep(0.5)


def run_child_mode():
    try:
        _run_child_mode_impl()
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        log_error(f"child crash: {tb}", show=False)
        print(f"{Fore.RED}{tb}")
        time.sleep(8)    # окно не исчезает мгновенно — успеете прочитать ошибку


# ======================================================================
#  Окно бота (--botrun): как ручной запуск, плюс копия вывода в лог
# ======================================================================
_NOMOD_RE = re.compile(r"No module named ['\"]([\w\.\-]+)['\"]")


def _missing_module_from(text, dir_path):
    """Из хвоста вывода достаёт имя модуля, которого не хватило (ModuleNotFoundError)."""
    found = _NOMOD_RE.findall(text or '')
    if not found:
        return None
    top = found[-1].split('.')[0]
    if not top or top in STDLIB_SAFE or _is_local_module(top, {dir_path, os.getcwd()}):
        return None
    return top


def _wait_interruptible(proc, holder):
    """Ждёт бота. Ctrl+C в окне = остановить бота (второй раз — убить сразу)."""
    while True:
        try:
            return proc.wait()
        except KeyboardInterrupt:
            holder['stop'] = True
            print(f"\n{Fore.YELLOW}Ctrl+C — останавливаю бота (ещё раз Ctrl+C — убить сразу)...")
            try:
                return proc.wait(timeout=8)
            except (KeyboardInterrupt, subprocess.TimeoutExpired):
                terminate_tree(proc.pid, grace=0, proc=proc)
                try:
                    return proc.wait(timeout=3)
                except Exception:
                    return -9


def _run_bot_mode_impl():
    import codecs
    envf = _argval('--env-file')
    if envf:
        try:
            with open(envf, 'r', encoding='utf-8') as ef:
                for k, v in json.load(ef).items():
                    if k not in ('TERM', 'TMUX', 'TMUX_PANE', 'COLUMNS', 'LINES'):
                        os.environ[k] = str(v)
        except Exception as e:
            log_error(f"env-файл: {e}", show=False)
        finally:
            try:
                os.remove(envf)
            except Exception:
                pass
    name = _argval('--botrun')
    token = _argval('--bot-id')
    try:
        parent_pid = int(_argval('--parent-pid', 0))
    except (TypeError, ValueError):
        parent_pid = 0
    want_venv = _argval('--venv', '1') == '1'
    want_deps = _argval('--deps', '1') == '1'
    append = _argval('--append', '0') == '1'
    abs_path = os.path.abspath(name)
    dir_path = os.path.dirname(abs_path)
    stem = os.path.splitext(os.path.basename(name))[0]
    _set_title(f"Kail bot: {stem}")
    _ensure_log_dir()

    # --- регистрация: менеджер узнаёт НАСТОЯЩИЙ PID окна и код завершения ---
    reg_path = os.path.join(BOT_DIR, token + '.json') if token else None
    ct = None
    if psutil:
        try:
            ct = psutil.Process().create_time()
        except Exception:
            pass
    reg = {"pid": os.getpid(), "name": name, "parent": parent_pid, "ctime": ct,
           "started": time.time(), "exit": None, "closed": False}

    def reg_update(**kw):
        reg.update(kw)
        if reg_path:
            try:
                os.makedirs(BOT_DIR, exist_ok=True)
            except OSError:
                pass
            _atomic_write_json(reg_path, reg)

    reg_update()
    holder = {'proc': None, 'stop': False}

    def kill_child():
        p = holder['proc']
        if p is not None and p.poll() is None:
            terminate_tree(p.pid, grace=2.0, proc=p)

    def on_exit(signum=None, frame=None):       # SIGTERM от менеджера / закрыли окно (SIGHUP, крестик)
        try:
            kill_child()
            reg_update(exit=-2, closed=True)
        finally:
            os._exit(0)

    _install_exit_handlers(on_exit)

    def watchdog():                             # менеджер умер — бот не должен жить сиротой
        interval = max(1, int(SETTINGS.get("child_check_interval", 3)))
        while True:
            time.sleep(interval)
            if parent_pid and not pid_alive(parent_pid):
                try:
                    kill_child()
                finally:
                    try:
                        if reg_path:
                            os.remove(reg_path)
                    except Exception:
                        pass
                    os._exit(0)

    threading.Thread(target=watchdog, daemon=True).start()

    # --- лог: создаём сразу, чтобы `logs <num>` работал уже во время установки библиотек ---
    log_path = log_path_for(name)
    mode = 'ab' if append else 'wb'
    try:
        if append and os.path.getsize(log_path) > 20 * 1024 * 1024:
            mode = 'wb'
    except OSError:
        pass
    lf = open(log_path, mode)

    def lw(text):
        try:
            lf.write(text.encode('utf-8', 'replace'))
            lf.flush()
        except Exception:
            pass

    def stamp():
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lw(("\n" if mode == 'ab' else "") + f"=== Логи {name} | старт {stamp()} ===\n")

    clear_screen()
    print(_box([
        (f"БОТ — {name}".center(62), Fore.LIGHTGREEN_EX),
        (f"  Менеджер: {parent_pid:<10}  Окно (PID): {os.getpid():<12}", Fore.WHITE),
        (f"  Лог: {log_path}", Fore.LIGHTCYAN_EX),
    ], color=Fore.GREEN))
    print(f"{Fore.MAGENTA}  Ctrl+C — остановить бота. Закрытие окна тоже останавливает бота.\n")

    def finish(rc, closed=False):
        lw(f"\n=== Бот завершён, код {rc} | {stamp()} ===\n")
        try:
            lf.close()
        except Exception:
            pass
        reg_update(exit=rc, closed=closed)

    chosen = _choose_python(dir_path, want_venv)
    if not chosen:
        lw("Не удалось подготовить Python/venv.\n")
        finish(-1)
        print(f"{Fore.RED}❌ Не удалось подготовить Python/venv. Закроется через "
              f"{SETTINGS['window_hold']} с.")
        time.sleep(SETTINGS['window_hold'])
        return
    python_exe, venv_dir, is_venv = chosen

    if want_deps:
        try:
            install_dependencies(python_exe, dir_path, abs_path, is_venv, venv_dir)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Установка прервана — запускаю как есть.")
        except Exception as e:
            log_error(f"Ошибка установки зависимостей: {e}", show=False)
            print(f"{Fore.YELLOW}⚠ Установка зависимостей прервалась ({e}) — пробую запустить как есть.")

    tried, attempt, rc = set(), 0, None
    while True:
        attempt += 1
        tag = ' [venv]' if is_venv else ''
        lw(f"Команда{tag}: {python_exe} -u {abs_path}\nРабочая папка: {dir_path}\n"
           + "=" * 50 + "\n\n")
        print(f"{Fore.CYAN}▶ Запуск {name}{tag}...\n")
        try:
            proc = subprocess.Popen([python_exe, '-u', abs_path], cwd=dir_path,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    env=_bot_env())          # stdin наследуется: input() работает
        except Exception as e:
            print(f"{Fore.RED}❌ Не удалось запустить: {e}")
            lw(f"Не удалось запустить: {e}\n")
            log_error(f"botrun {name}: {e}", show=False)
            rc = -1
            break
        holder['proc'] = proc
        chunks = []
        dec = codecs.getincrementaldecoder('utf-8')('replace')

        def pump(p=proc, d=dec, buf=chunks):
            fd = p.stdout.fileno()
            while True:
                try:
                    data = os.read(fd, 8192)
                except OSError:
                    break
                if not data:
                    break
                lw_bytes(data)
                text = d.decode(data)
                if text:
                    try:
                        sys.stdout.write(text)
                        sys.stdout.flush()
                    except Exception:
                        pass
                    buf.append(text)
                    if len(buf) > 60:
                        del buf[:-60]

        def lw_bytes(data):
            try:
                lf.write(data)
                lf.flush()
            except Exception:
                pass

        pt = threading.Thread(target=pump, daemon=True)
        pt.start()
        try:
            rc = _wait_interruptible(proc, holder)
        finally:
            kill_child()
        pt.join(2)
        tail = ''.join(chunks)[-8000:]

        if holder['stop'] or rc == 0:
            break
        mod = _missing_module_from(tail, dir_path)
        if mod and SETTINGS["auto_install_deps"] and mod not in tried and attempt <= 8:
            tried.add(mod)
            pip_name = PIP_NAME_MAP.get(mod, mod)
            print(f"\n{Fore.YELLOW}⚠ Боту не хватило модуля '{mod}' — ставлю {pip_name} и запускаю снова...")
            lw(f"\n[kail] не хватает модуля {mod} — pip install {pip_name}\n")
            ok, out = pip_install(python_exe, [pip_name], cwd=dir_path, is_venv=is_venv, timeout=900)
            if ok:
                print(f"{Fore.GREEN}✅ {pip_name} установлен.\n")
                lw(f"[kail] {pip_name} установлен, перезапуск\n\n")
                continue
            print(f"{Fore.RED}❌ Не удалось установить {pip_name}")
            lw(f"[kail] не удалось установить {pip_name}: {out[-300:]}\n")
            log_error(f"pip fail {pip_name}: {out[-300:]}", show=False)
        break

    closed = holder['stop']
    rc = -1 if rc is None else rc
    finish(rc, closed)
    color = Fore.GREEN if rc == 0 else Fore.RED
    print(f"\n{color}■ Бот {name} завершился (код {rc}).")
    hold = 2
    if rc != 0 and not closed:
        hold = SETTINGS.get('window_hold', 10)
        print(f"{Fore.LIGHTBLACK_EX}Окно закроется через {hold} с. Полный лог: {log_path}  "
              f"(в менеджере: logs <num>)")
    end = time.time() + hold
    try:
        while time.time() < end:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass


def run_bot_mode():
    try:
        _run_bot_mode_impl()
    except SystemExit:
        raise
    except Exception:
        tb = traceback.format_exc()
        log_error(f"botrun crash: {tb}", show=False)
        print(f"{Fore.RED}{tb}")
        time.sleep(10)


# ======================================================================
#  Загрузочный экран и зависимости самого менеджера
# ======================================================================
def _boot_sequence():
    L = Fore
    clear_screen()
    lines = [
        (f"{L.LIGHTGREEN_EX}[BOOT]{L.RESET} Kail Admin OS initializing...", 0.012),
        (f"{L.LIGHTGREEN_EX}[BOOT]{L.RESET} Kernel: Python {platform.python_version()}", 0.012),
        (f"{L.LIGHTGREEN_EX}[BOOT]{L.RESET} Platform: {platform.system()} {platform.release()}", 0.012),
        (f"{L.LIGHTGREEN_EX}[BOOT]{L.RESET} Arch: {platform.machine()}   Host: {platform.node()}", 0.012),
        (f"{L.LIGHTYELLOW_EX}[SCAN]{L.RESET} Checking system integrity...", 0.03),
        (f"{L.LIGHTYELLOW_EX}[SCAN]{L.RESET} Mounting virtual filesystem...", 0.02),
        (f"{L.LIGHTYELLOW_EX}[SCAN]{L.RESET} Loading security modules...", 0.025),
        (f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} Security handshake complete", 0.012),
        (f"{L.LIGHTCYAN_EX}[NET ]{L.RESET} Establishing local socket...", 0.02),
        (f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} Connection secured", 0.012),
        (f"{L.LIGHTMAGENTA_EX}[CORE]{L.RESET} Decrypting kernel modules...", 0.025),
        (f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} Handshake with matrix successful", 0.015),
    ]
    for text, d in lines:
        print(text)
        time.sleep(d)
    for _ in range(6):
        print(f"{L.LIGHTGREEN_EX}{''.join(random.choice('01') for _ in range(64))}")
        time.sleep(0.02)
    time.sleep(0.1)
    clear_screen()


def _scan_bar(package, required=True, animate=True):
    L = Fore
    bar_len = 28
    prefix = f"{L.LIGHTYELLOW_EX}[SCAN]{L.RESET} {package:<10}"
    if animate:
        for i in range(bar_len + 1):
            sys.stdout.write(f"\r{prefix} [{L.LIGHTGREEN_EX}{'█' * i}{L.DIM}{'░' * (bar_len - i)}{L.RESET}]")
            sys.stdout.flush()
            time.sleep(0.01)
    if _try_import(package):
        sys.stdout.write(f"\r{prefix} [{L.LIGHTGREEN_EX}{'█' * bar_len}{L.RESET}] {L.LIGHTGREEN_EX}[ FOUND ]{L.RESET}\n")
        sys.stdout.flush()
        return True
    sys.stdout.write(f"\r{prefix} [{L.LIGHTRED_EX}{'█' * bar_len}{L.RESET}] {L.LIGHTRED_EX}[ MISSING ]{L.RESET}\n")
    sys.stdout.flush()
    print(f"{L.LIGHTYELLOW_EX}[PIP ]{L.RESET} Installing {L.LIGHTCYAN_EX}{package}{L.RESET}...")
    try:
        _pip_target_install(package)
    except KeyboardInterrupt:
        pass
    if _try_import(package):
        print(f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} {package} installed successfully\n")
        return True
    if required:
        print(f"{L.LIGHTRED_EX}[FAIL]{L.RESET} {package} не установился "
              f"(продолжаю в упрощённом режиме)\n")
    else:
        print(f"{L.LIGHTYELLOW_EX}[SKIP]{L.RESET} {package} необязателен — пропускаю\n")
    return False


def _boot_loader(animated=True):
    global psutil
    L = Fore
    if animated:
        _boot_sequence()
        print(f"{L.CYAN}{L.BOLD}╔══════════════════════════════════════════════╗")
        print(f"{L.CYAN}{L.BOLD}║    KAIL ADMIN — BOOT LOADER {VERSION}   ║")
        print(f"{L.CYAN}{L.BOLD}╚══════════════════════════════════════════════╝\n")
        print(f"{L.CYAN}[DEPS]{L.RESET} Scanning required modules...\n")
        _scan_bar('colorama', required=False)
        _scan_bar('psutil', required=True)
    elif psutil is None:
        print(f"{L.YELLOW}[DEPS] psutil не найден — устанавливаю...")
        _pip_target_install('psutil')
    if psutil is None:
        psutil = _try_import('psutil')
    if psutil is None:
        print(f"{L.YELLOW}[WARN]{L.RESET} psutil недоступен: часть функций (info, проверка процессов) "
              f"работает в упрощённом режиме. Ставится так: {sys.executable} -m pip install psutil")
        time.sleep(1.5 if animated else 0)
    if not animated:
        return
    print(f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} Dependencies ready.")
    print(f"{L.LIGHTYELLOW_EX}[INFO]{L.RESET} Starting Kail Admin core...\n")
    total = 24
    for i in range(total):
        pct = int((i + 1) / total * 100)
        bar = '█' * (i + 1) + '░' * (total - i - 1)
        sys.stdout.write(f"\r{L.CYAN}[LOAD]{L.RESET} [{L.LIGHTGREEN_EX}{bar}{L.RESET}] {pct:3d}%")
        sys.stdout.flush()
        time.sleep(0.03)
    print()
    time.sleep(0.1)
    print(f"{L.LIGHTGREEN_EX}[ OK ]{L.RESET} Kernel loaded.")
    print(f"{L.LIGHTMAGENTA_EX}[INFO]{L.RESET} Welcome to the matrix, operator.")
    time.sleep(0.5)
    clear_screen()


# ======================================================================
#  Завершение / сигналы / осиротевшие процессы
# ======================================================================
_cleanup_done = False
_CTRL_REF = None


def cleanup():
    global running, _cleanup_done
    running = False
    if _cleanup_done:
        return
    _cleanup_done = True
    try:
        for action in list(child_terms.keys()):
            try:
                close_child_terminal(action)
            except Exception:
                pass
        _sweep_child_registry(only_parent=os.getpid())
        if BOTS:
            print(f"\n{Fore.RED}Останавливаем все процессы...")
            stop_all_bots()
    except Exception as e:
        log_error(f"cleanup: {e}", show=False)
    try:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    except Exception as e:
        log_error(f"Не удалось удалить state: {e}", show=False)


def _install_exit_handlers(on_exit=None):
    """Закрыли окно / kill / logoff — боты останавливаются, а не остаются «осиротевшими»."""
    def graceful(signum=None, frame=None):
        try:
            (on_exit or cleanup)()
        finally:
            os._exit(0)

    for sig_name in ('SIGTERM', 'SIGHUP', 'SIGBREAK'):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                signal.signal(sig, graceful)
            except Exception:
                pass
    if IS_WIN:
        try:
            import ctypes
            global _CTRL_REF
            handler_t = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

            def ctrl(event):
                if event in (2, 5, 6):      # CLOSE / LOGOFF / SHUTDOWN
                    graceful()
                return 0

            _CTRL_REF = handler_t(ctrl)
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_CTRL_REF, True)
        except Exception:
            pass


def _looks_like_manager(pid):
    if not psutil:
        return True
    try:
        cmd = ' '.join(psutil.Process(pid).cmdline()).lower()
        return os.path.basename(SCRIPT_PATH).lower() in cmd
    except Exception:
        return False


def reap_orphans():
    """После аварийного выхода боты могли остаться живыми — второй экземпляр даёт Telegram Conflict."""
    st = load_state()
    if st:
        mp = st.get('manager_pid')
        if mp and mp != os.getpid() and pid_alive(mp) and _looks_like_manager(mp):
            print(f"{Fore.YELLOW}⚠ Уже запущен другой экземпляр Kail Admin (PID {mp}). "
                  f"Два менеджера одновременно будут дублировать ботов!")
            return
        killed = 0
        names = st.get('file_list') or []
        if psutil:
            for num, pid in (st.get('processes') or {}).items():
                try:
                    pid = int(pid)
                    idx = int(num) - 1
                    if not (0 <= idx < len(names)) or not pid_alive(pid):
                        continue
                    cmd = ' '.join(psutil.Process(pid).cmdline()).lower()
                    if os.path.basename(names[idx]).lower() in cmd:
                        terminate_tree(pid, grace=2, group=not IS_WIN)
                        killed += 1
                except Exception:
                    continue
        if killed:
            print(f"{Fore.YELLOW}⚠ Найдено и остановлено осиротевших ботов после прошлого сеанса: {killed}")
        try:
            os.remove(STATE_FILE)
        except Exception:
            pass
    _sweep_child_registry()


# ======================================================================
#  Диагностика и сервис: doctor / fix / attach / allrestart
# ======================================================================
def _check_url(url, timeout=8):
    try:
        import urllib.request
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': 'kail-admin'})
        with urllib.request.urlopen(req, timeout=timeout):
            return True, ''
    except Exception as e:
        code = getattr(e, 'code', None)
        if code:                       # сервер ответил (даже 4xx) — сеть работает
            return True, ''
        return False, str(e)[:80]


def cmd_doctor(parts):
    """doctor [num] — проверка окружения; с номером — ещё и проверка конкретного бота."""
    def ok(t):
        print(f"  {Fore.GREEN}✔ {Fore.WHITE}{t}")

    def warn(t, hint=''):
        print(f"  {Fore.YELLOW}⚠ {Fore.WHITE}{t}" + (f"\n      {Fore.LIGHTBLACK_EX}→ {hint}" if hint else ''))

    def bad(t, hint=''):
        print(f"  {Fore.RED}✘ {Fore.WHITE}{t}" + (f"\n      {Fore.LIGHTBLACK_EX}→ {hint}" if hint else ''))

    print(f"\n{Fore.CYAN}=== ДИАГНОСТИКА ===\n")
    py = _global_python()
    v = sys.version_info
    ok(f"Python {platform.python_version()} ({py})") if v >= (3, 9) else \
        warn(f"Python {platform.python_version()} — старый", "python-telegram-bot 22+ требует Python 3.9+")
    if _pip_works(py):
        ok("pip в системном Python есть")
    else:
        warn("pip в системном Python нет", "менеджер поставит pip сам (get-pip.py) или: apt install python3-pip")
    okv, _o = _run_quiet([py, '-c', 'import venv, ensurepip'], timeout=30)
    if okv:
        ok("venv + ensurepip доступны")
    else:
        warn("стандартный venv не работает", "менеджер обойдёт через virtualenv.pyz; или: apt install python3-venv")
    ok("psutil установлен") if psutil else warn("psutil не установлен", f"{py} -m pip install psutil (работает и без него)")

    n1, e1 = _check_url('https://pypi.org/simple/pip/')
    ok("PyPI доступен (pip сможет ставить библиотеки)") if n1 else bad("PyPI недоступен", f"нет сети/прокси: {e1}")
    n2, e2 = _check_url('https://api.telegram.org')
    ok("api.telegram.org доступен") if n2 else bad("api.telegram.org недоступен — боты не подключатся", e2)

    if IS_WIN:
        ok("Windows: каждый бот открывается в своей консоли")
    else:
        names = [c[0] for c in _terminal_candidates(['x'], background=True, detached_tmux=True)]
        if names:
            ok(f"Способы открыть окно бота: {', '.join(names)}")
        else:
            warn("Нет ни GUI-терминала, ни tmux — боты пойдут в фоне, без ввода с клавиатуры",
                 "apt install tmux — тогда у каждого бота будет настоящая консоль (tmux attach -t kail)")
        if _is_root():
            ok("Запущено от root")
        elif shutil.which('sudo'):
            ok("sudo есть")
        else:
            warn("sudo нет", "системные пакеты менеджер ставить не сможет")
    try:
        os.makedirs(SETTINGS["log_dir"], exist_ok=True)
        probe = os.path.join(SETTINGS["log_dir"], '.w')
        with open(probe, 'w') as f:
            f.write('1')
        os.remove(probe)
        ok(f"Папка логов '{SETTINGS['log_dir']}' доступна для записи")
    except Exception as e:
        bad("Нельзя писать в папку логов", str(e))
    try:
        free = shutil.disk_usage('.').free / (1024 ** 3)
        ok(f"Свободно на диске: {free:.1f} ГБ") if free > 0.5 else warn(f"Мало места на диске: {free:.2f} ГБ")
    except Exception:
        pass

    if len(parts) >= 2:
        r = _bot_by_arg(parts, "doctor 1")
        if r:
            num, name = r
            ap = os.path.abspath(name)
            print(f"\n{Fore.CYAN}--- Бот {num}: {name} ---")
            if not os.path.isfile(ap):
                bad("Файл не найден")
                return
            try:
                with open(ap, 'rb') as f:
                    ast.parse(f.read().decode('utf-8-sig', 'replace'))
                ok("Синтаксис корректен")
            except SyntaxError as e:
                bad(f"Синтаксическая ошибка: строка {e.lineno}: {e.msg}", f"Python {platform.python_version()} может не понимать этот код")
            d = os.path.dirname(ap)
            ok(f"requirements.txt найден") if os.path.isfile(os.path.join(d, 'requirements.txt')) else \
                ok("requirements.txt нет — зависимости определяются по import")
            vd = _venv_dir_for(d)
            vpy = _venv_python(vd)
            target = vpy if (os.path.exists(vpy) and _python_works(vpy)) else py
            ok(f"venv: {vd}") if target == vpy else warn("venv ещё не создан (создастся при запуске)")
            imps = get_imports(ap)
            miss = find_missing(target, imps, d) if imps else []
            if miss is None:
                warn("Не удалось проверить библиотеки")
            elif miss:
                warn(f"Не хватает библиотек: {', '.join(sorted(miss))}", "поставятся при запуске (run) или командой fix")
            else:
                ok(f"Все библиотеки на месте ({len(imps)})")
            lp = resolve_log_path(num)
            if lp:
                lines, _sz = _tail_lines(lp, 8)
                print(f"  {Fore.LIGHTBLACK_EX}Последние строки лога:")
                for ln in lines:
                    print(f"    {Fore.LIGHTBLACK_EX}│ {Fore.WHITE}{ln.rstrip()[:150]}")
    print()


def cmd_fix(parts):
    """fix <num> — пересоздать venv бота с нуля и запустить заново (лечит битые/устаревшие библиотеки)."""
    r = _bot_by_arg(parts, "fix 1")
    if not r:
        return
    num, name = r
    d = os.path.dirname(os.path.abspath(name))
    vd = _venv_dir_for(d)
    with BOTS_LOCK:
        others = [n for n, b in BOTS.items()
                  if n != name and b.alive() and os.path.dirname(os.path.abspath(n)) == d]
    if others:
        print(f"{Fore.RED}В этой папке работают другие боты ({', '.join(others)}) — они используют тот же venv. "
              f"Сначала остановите их.")
        return
    print(f"{Fore.YELLOW}Будет удалён venv: {vd} и создан заново, библиотеки поставятся заново.")
    try:
        if read_line(f"{Fore.YELLOW}Продолжить? (y/N): ").strip().lower() not in ('y', 'yes', 'д', 'да'):
            print(f"{Fore.RED}Отменено.")
            return
    except (KeyboardInterrupt, EOFError):
        return
    with BOTS_LOCK:
        was = name in BOTS
    if was:
        stop_bot(name)
    if os.path.isdir(vd):
        _rmtree(vd)
    _start_bot(num, name)


def cmd_attach(parts):
    """attach [num] — показать консоль бота из tmux (Linux). Выйти, не останавливая бота: Ctrl+B, затем D."""
    if IS_WIN or not shutil.which('tmux'):
        print(f"{Fore.YELLOW}attach нужен только для Linux с tmux. На Windows каждый бот уже в своём окне.")
        return
    inside = bool(os.environ.get('TMUX'))
    title = None
    if len(parts) >= 2:
        r = _bot_by_arg(parts, "attach 1")
        if not r:
            return
        title = _win_title(r[1])
    if inside:
        if title:
            _run_inherit(['tmux', 'select-window', '-t', title])
        else:
            print(f"{Fore.YELLOW}Вы уже внутри tmux — боты открыты окнами этой сессии (Ctrl+B, N — следующее окно).")
        return
    has = subprocess.run(['tmux', 'has-session', '-t', 'kail'], capture_output=True,
                         stdin=subprocess.DEVNULL).returncode == 0
    if not has:
        print(f"{Fore.YELLOW}tmux-сессии 'kail' нет: боты запущены в обычных окнах или в фоне.")
        return
    if title:
        subprocess.run(['tmux', 'select-window', '-t', f'kail:{title}'], capture_output=True,
                       stdin=subprocess.DEVNULL)
    print(f"{Fore.LIGHTBLACK_EX}Выход обратно в менеджер: Ctrl+B, затем D")
    _run_inherit(['tmux', 'attach', '-t', 'kail'])


def cmd_allrestart():
    with BOTS_LOCK:
        items = list(BOTS.items())
    if not items:
        print(f"{Fore.RED}Нет запущенных ботов.")
        return
    print(f"{Fore.YELLOW}Перезапускаю всех ({len(items)})...")
    for name, old in items:
        num = file_list.index(name) + 1 if name in file_list else '?'
        stop_bot(name)
        time.sleep(0.5)
        bot = launch_bot(name, use_venv=old.want_venv, window=old.window)
        if bot:
            print(f"{Fore.GREEN}✅ Бот {num} перезапущен (PID {bot.pid})")
        else:
            print(f"{Fore.RED}❌ Бот {num} не запустился")
    save_state()


# ======================================================================
#  Команды
# ======================================================================
def _bot_by_arg(parts, example):
    """Возвращает (num, name) или None, печатая понятную ошибку."""
    if len(parts) < 2:
        print(f"{Fore.RED}Пример: {example}")
        return None
    try:
        num = int(parts[1])
    except ValueError:
        print(f"{Fore.RED}Номер — целое число.")
        return None
    name = bot_name(num)
    if not name:
        print(f"{Fore.RED}Неверный номер.")
        return None
    return num, name


def _start_bot(num, name, use_venv=None, window=None):
    with BOTS_LOCK:
        was = name in BOTS
    if was:
        print(f"{Fore.YELLOW}Перезапускаю бота {num}...")
        stop_bot(name)
    mode_venv, _w = effective_opts(name, use_venv, window)
    if mode_venv:
        print(f"{Fore.MAGENTA}Запуск {name} в изолированном venv...")
    else:
        print(f"{Fore.CYAN}Запуск {name}...")
    bot = launch_bot(name, use_venv=use_venv, window=window)
    if bot:
        tag = " [venv]" if bot.venv else ""
        if bot.window:
            tag += " [окно]"
        print(f"{Fore.GREEN}✅ Бот {num} запущен{tag} (PID {bot.pid})")
        if bot.window and getattr(bot.proc, 'via', '') == 'tmux-detached':
            print(f"{Fore.LIGHTBLACK_EX}   Консоль бота — в tmux-сессии: {Fore.GREEN}tmux attach -t kail"
                  f"{Fore.LIGHTBLACK_EX}  (выйти, не останавливая: Ctrl+B, затем D)")
        save_state()
        if SETTINGS["auto_open_logs"]:
            try:
                open_child_terminal(f"logs {num}", inline_fallback=False)
            except Exception as e:
                log_error(f"auto_open_logs: {e}", show=False)
        return True
    print(f"{Fore.RED}❌ Ошибка запуска.")
    return False


def handle_command(cmd):
    """Обрабатывает одну команду. False — выйти из программы."""
    global running
    parts = cmd.split()
    command = parts[0].lower()

    # ---- ИНТЕРФЕЙС ----
    if command in ('clear', 'cls'):
        show_logo_only()
        return True
    if command == 'help':
        print()
        show_help()
        return True
    if command == 'banner':
        show_banner()
        return True
    if command == 'settings':
        settings_menu()
        show_logo_only()
        return True
    if command == 'exit':
        print(f"{Fore.RED}Выход...")
        running = False
        return False

    # ---- БОТЫ ----
    if command == 'list':
        action_list()
        return True

    if command == 'run':
        r = _bot_by_arg(parts, "run 1  |  run 1 -novenv-  |  run 1 -novenv- sv  (sv — запомнить навсегда)")
        if r:
            parsed = _parse_run_flags(parts[2:])
            if parsed is None:
                return True
            use_venv, use_window, save, reset = parsed
            _apply_run_prefs(r[0], r[1], use_venv, use_window, save, reset)
            if reset:
                use_venv = use_window = None
            _start_bot(r[0], r[1], use_venv, use_window)
        return True

    if command == 'allrun':
        if not file_list:
            print(f"{Fore.RED}Нет файлов.")
            return True
        print(f"{Fore.CYAN}Запуск всех...")
        ok_count = 0
        for i, name in enumerate(list(file_list), 1):
            with BOTS_LOCK:
                b = BOTS.get(name)
                if b and b.alive():
                    continue
            bot = launch_bot(name)
            if bot:
                print(f"{Fore.GREEN}✅ Бот {i} запущен (PID {bot.pid})")
                ok_count += 1
            else:
                print(f"{Fore.RED}❌ Ошибка бота {i}")
            time.sleep(0.5)
        print(f"{Fore.GREEN}Запущено {ok_count} из {len(file_list)}.")
        save_state()
        return True

    if command == 'stop':
        r = _bot_by_arg(parts, "stop 1")
        if not r:
            return True
        num, name = r
        with BOTS_LOCK:
            present = name in BOTS
        if not present:
            print(f"{Fore.RED}Бот {num} не запущен.")
            return True
        print(f"{Fore.YELLOW}Останавливаю бота {num}...")
        stop_bot(name)
        print(f"{Fore.GREEN}✅ Остановлен.")
        save_state()
        return True

    if command in ('stopall', 'allstop'):
        with BOTS_LOCK:
            nums = [i for i, n in enumerate(file_list, 1) if n in BOTS]
        if not nums:
            print(f"{Fore.RED}Нет ботов.")
            return True
        print(f"{Fore.YELLOW}Останавливаю всех...")
        stop_all_bots()
        for n in nums:
            print(f"  Бот {n} остановлен.")
        print(f"{Fore.GREEN}✅ Все остановлены.")
        save_state()
        return True

    if command == 'allrestart':
        cmd_allrestart()
        return True

    if command == 'bind':
        rest = cmd.split(None, 1)
        cmd_bind(rest[1] if len(rest) > 1 else '')
        return True
    if command == 'unbind':
        cmd_unbind(parts[1] if len(parts) > 1 else '')
        return True
    if command == 'binds':
        cmd_binds()
        return True
    if command == 'prefs':
        cmd_prefs(parts)
        return True
    if command == 'doctor':
        cmd_doctor(parts)
        return True
    if command == 'fix':
        cmd_fix(parts)
        return True
    if command == 'attach':
        cmd_attach(parts)
        return True

    if command == 'restart':
        r = _bot_by_arg(parts, "restart 1")
        if not r:
            return True
        num, name = r
        with BOTS_LOCK:
            old = BOTS.get(name)
        want = old.want_venv if old else None
        print(f"{Fore.YELLOW}Перезапуск {num}...")
        if old:
            stop_bot(name)
            time.sleep(0.5)
        else:
            print(f"{Fore.LIGHTBLACK_EX}(бот не был запущен — просто запускаю)")
        bot = launch_bot(name, use_venv=want, window=(old.window if old else None))
        if bot:
            print(f"{Fore.GREEN}✅ Бот {num} перезапущен (PID {bot.pid})")
            save_state()
        else:
            print(f"{Fore.RED}❌ Ошибка.")
        return True

    if command == 'kill':
        r = _bot_by_arg(parts, "kill 1")
        if not r:
            return True
        num, name = r
        with BOTS_LOCK:
            present = name in BOTS
        if not present:
            print(f"{Fore.RED}Бот {num} не запущен.")
            return True
        stop_bot(name, force=True)
        print(f"{Fore.GREEN}✅ Бот {num} убит.")
        save_state()
        return True

    # ---- ЛОГИ ----
    if command == 'logs':
        action_logs(parts)
        return True
    if command == 'logclose':
        print(f"{Fore.YELLOW}Окна логов открываются только в дочернем терминале (ott -y logs <num>).")
        return True

    # ---- ДОЧЕРНИЕ ТЕРМИНАЛЫ ----
    if command == 'ott':
        sub = parts[1].lower() if len(parts) >= 2 else ''
        if sub == 'list':
            cmd_ott_list()
            return True
        if sub == '-n' and len(parts) >= 3:
            if parts[2].lower() == 'all':
                if not child_terms:
                    print(f"{Fore.YELLOW}Нет открытых дочерних.")
                    return True
                for action in list(child_terms.keys()):
                    close_child_terminal(action)
                print(f"{Fore.GREEN}✅ Все дочерние закрыты.")
                save_state()
                return True
            action = ' '.join(parts[2:])
            if close_child_terminal(action):
                print(f"{Fore.GREEN}✅ Дочерний '{action}' закрыт.")
                save_state()
            else:
                print(f"{Fore.RED}Не найден '{action}'.")
            return True
        if sub == '-y' and len(parts) >= 3:
            open_child_terminal(' '.join(parts[2:]))
            return True
        print(f"{Fore.RED}Синтаксис: ott list | ott -y <action> | ott -n <action> | ott -n all")
        print(f"{Fore.YELLOW}Пример: ott -y logs 4 | ott -y list | ott -y settings")
        return True

    # ---- СИСТЕМА ----
    if command == 'sudo':
        if len(parts) >= 5 and parts[1].lower() == 'rename' and parts[3].lower() == 'to':
            cmd_rename(parts[2], parts[4])
            return True
        execute_system_cmd(parts)
        return True

    simple = {'info': action_info, 'date': action_date, 'whoami': action_whoami,
              'uptime': action_uptime, 'history': action_history, 'version': action_version}
    if command in simple:
        simple[command]()
        return True
    if command == 'echo':
        print(' '.join(parts[1:]))
        return True
    if command == 'refresh':
        action_refresh()
        print(f"{Fore.GREEN}Состояние синхронизировано с дочерними терминалами.")
        return True

    print(f"{Fore.RED}❌ Неизвестная команда: {command}. Введите help.")
    return True


# ======================================================================
#  Главная функция
# ======================================================================
def main():
    _enable_windows_ansi()
    load_settings()
    load_bot_prefs()

    if '--botrun' in sys.argv:
        run_bot_mode()
        return

    if '--child' in sys.argv:
        run_child_mode()
        return

    _ensure_log_dir()
    try:
        if os.path.exists(ERROR_LOG_FILE) and os.path.getsize(ERROR_LOG_FILE) > 2 * 1024 * 1024:
            os.replace(ERROR_LOG_FILE, ERROR_LOG_FILE + '.old')
    except Exception:
        pass

    _boot_loader(SETTINGS["boot_animation"])

    load_binds()
    scan_files()
    reap_orphans()
    show_logo_only()

    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=state_saver, daemon=True).start()
    _install_exit_handlers()
    atexit.register(cleanup)

    try:
        while running:
            try:
                line = read_line(f"{Fore.YELLOW}Kail~Admin$: {Fore.WHITE}")
            except (KeyboardInterrupt, EOFError):
                print(f"\n{Fore.RED}Выход...")
                break

            line = line.strip()
            if not line:
                continue
            command_history.append(line)
            try:
                if not handle_command(line):
                    break
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Операция прервана.")
            except Exception as e:
                log_error(f"Ошибка команды '{line}': {e}\n{traceback.format_exc()}")
    finally:
        cleanup()


if __name__ == '__main__':
    main()
