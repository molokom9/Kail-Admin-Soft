#!/usr/bin/env python3
import os
import sys
import subprocess
import time
import platform
import importlib

# =============================================================
#  BOOT LOADER — Kail Admin
# =============================================================

class _ANSI:
    RESET   = '\033[0m'
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'


def _enable_windows_ansi():
    if platform.system() == 'Windows':
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)
        except Exception:
            pass


def _clear():
    os.system('cls' if platform.system() == 'Windows' else 'clear')


def _boot_sequence():
    A = _ANSI
    import random as _r
    _clear()
    lines = [
        (f"{A.GREEN}[BOOT]{A.RESET} Kail Admin OS initializing...", 0.012),
        (f"{A.GREEN}[BOOT]{A.RESET} Kernel: Python {platform.python_version()}", 0.012),
        (f"{A.GREEN}[BOOT]{A.RESET} Platform: {platform.system()} {platform.release()}", 0.012),
        (f"{A.GREEN}[BOOT]{A.RESET} Arch: {platform.machine()}   Host: {platform.node()}", 0.012),
        (f"{A.YELLOW}[SCAN]{A.RESET} Checking system integrity...", 0.03),
        (f"{A.YELLOW}[SCAN]{A.RESET} Mounting virtual filesystem...", 0.02),
        (f"{A.YELLOW}[SCAN]{A.RESET} Loading security modules...", 0.025),
        (f"{A.GREEN}[ OK ]{A.RESET} Security handshake complete", 0.012),
        (f"{A.CYAN}[NET ]{A.RESET} Establishing local socket...", 0.02),
        (f"{A.GREEN}[ OK ]{A.RESET} Connection secured", 0.012),
        (f"{A.MAGENTA}[CORE]{A.RESET} Decrypting kernel modules...", 0.025),
        (f"{A.GREEN}[ OK ]{A.RESET} Handshake with matrix successful", 0.015),
    ]
    for text, d in lines:
        print(text); time.sleep(d)
    for _ in range(6):
        row = ''.join(_r.choice('01') for _ in range(64))
        print(f"{A.GREEN}{row}{A.RESET}"); time.sleep(0.02)
    time.sleep(0.1)
    _clear()


def _scan_bar(package, import_name=None):
    A = _ANSI
    if import_name is None:
        import_name = package
    bar_len = 28
    prefix = f"{A.YELLOW}[SCAN]{A.RESET} {package:<10}"
    for i in range(bar_len + 1):
        sys.stdout.write(f"\r{prefix} [{A.GREEN}{'█' * i}{A.DIM}{'░' * (bar_len - i)}{A.RESET}]")
        sys.stdout.flush(); time.sleep(0.01)
    try:
        __import__(import_name)
        sys.stdout.write(f"\r{prefix} [{A.GREEN}{'█' * bar_len}{A.RESET}] {A.GREEN}[ FOUND ]{A.RESET}\n")
        sys.stdout.flush(); return True
    except ImportError:
        sys.stdout.write(f"\r{prefix} [{A.RED}{'█' * bar_len}{A.RESET}] {A.RED}[ MISSING ]{A.RESET}\n")
        sys.stdout.flush()
        print(f"{A.YELLOW}[PIP ]{A.RESET} Installing {A.CYAN}{package}{A.RESET}...")
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '--quiet'],
                                  stdin=subprocess.DEVNULL,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            importlib.invalidate_caches()
            print(f"{A.GREEN}[ OK ]{A.RESET} {package} installed successfully\n"); return True
        except Exception as e:
            print(f"{A.RED}[FAIL]{A.RESET} {package} failed: {e}\n"); return False


def _boot_loader():
    _enable_windows_ansi()
    A = _ANSI
    _boot_sequence()
    print(f"{A.CYAN}{A.BOLD}╔══════════════════════════════════════════════╗{A.RESET}")
    print(f"{A.CYAN}{A.BOLD}║    KAIL ADMIN — BOOT LOADER v13092026.1642   ║{A.RESET}")
    print(f"{A.CYAN}{A.BOLD}╚══════════════════════════════════════════════╝{A.RESET}\n")
    print(f"{A.CYAN}[DEPS]{A.RESET} Scanning required modules...\n")
    ok1 = _scan_bar('colorama')
    ok2 = _scan_bar('psutil')
    if not (ok1 and ok2):
        print(f"{A.RED}[ERROR]{A.RESET} Критические зависимости не установлены.")
        try: input("Enter...")
        except Exception: pass
        sys.exit(1)
    print(f"{A.GREEN}[ OK ]{A.RESET} All dependencies satisfied.")
    print(f"{A.YELLOW}[INFO]{A.RESET} Starting Kail Admin core...\n")
    total = 24
    for i in range(total):
        pct = int((i + 1) / total * 100)
        bar = '█' * (i + 1) + '░' * (total - i - 1)
        sys.stdout.write(f"\r{A.CYAN}[LOAD]{A.RESET} [{A.GREEN}{bar}{A.RESET}] {pct:3d}%")
        sys.stdout.flush(); time.sleep(0.03)
    print(); time.sleep(0.1)
    print(f"{A.GREEN}[ OK ]{A.RESET} Kernel loaded.")
    print(f"{A.MAGENTA}[INFO]{A.RESET} Welcome to the matrix, operator.")
    time.sleep(0.5)
    _clear()


_boot_loader()

# =============================================================
#  ОСНОВНОЙ КОД
# =============================================================

import signal
import atexit
import glob
import threading
import re
import json
import getpass
from datetime import datetime
from collections import deque

from colorama import Fore, init
import psutil
import shutil

init(autoreset=True)

# ---------- Настройки ----------
SETTINGS_FILE = "kail_settings.json"
DEFAULT_SETTINGS = {
    "monitor_interval": 30,
    "auto_restart": True,
    "log_dir": "logs",
    "sudo_confirm": True,
    "auto_install_deps": True,
    "child_check_interval": 3,
    "auto_open_logs": False,
    "state_sync_interval": 2,
}

SETTINGS_DESCRIPTIONS = {
    "monitor_interval":      "Интервал проверки ботов (секунд).",
    "auto_restart":          "Авто-перезапуск упавших ботов (true/false).",
    "log_dir":               "Папка для хранения логов ботов.",
    "sudo_confirm":          "Подтверждение перед sudo-командой (true/false).",
    "auto_install_deps":     "Авто-установка недостающих библиотек (true/false).",
    "child_check_interval":  "Проверка родителя в дочернем терминале (секунд).",
    "auto_open_logs":        "Авто-открытие логов при запуске бота (true/false).",
    "state_sync_interval":   "Как часто child синхронизирует состояние (секунд).",
}
SETTINGS = dict(DEFAULT_SETTINGS)

STATE_FILE = "kail_state.json"
ERROR_LOG_FILE = "kail_errors.log"

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
    'pytesseract': 'pytesseract', 'fitz': 'PyMuPDF',
    'docx': 'python-docx', 'pptx': 'python-pptx', 'magic': 'python-magic',
    'jwt': 'PyJWT', 'multipart': 'python-multipart', 'aiosqlite': 'aiosqlite',
    'nacl': 'PyNaCl', 'flask_sqlalchemy': 'Flask-SQLAlchemy',
    'flask_login': 'Flask-Login', 'flask_wtf': 'Flask-WTF',
    'flask_cors': 'Flask-Cors', 'rest_framework': 'djangorestframework',
    'crispy_forms': 'django-crispy-forms', 'allauth': 'django-allauth',
    'telethon': 'Telethon', 'aiogram': 'aiogram', 'pyrogram': 'Pyrogram',
    'tgcrypto': 'TgCrypto', 'aiohttp': 'aiohttp', 'requests': 'requests',
    'httpx': 'httpx', 'websockets': 'websockets', 'uvicorn': 'uvicorn',
    'fastapi': 'fastapi', 'sqlalchemy': 'SQLAlchemy', 'redis': 'redis',
    'pymongo': 'pymongo', 'motor': 'motor', 'numpy': 'numpy',
    'pandas': 'pandas', 'matplotlib': 'matplotlib', 'scipy': 'scipy',
    'openpyxl': 'openpyxl', 'xlsxwriter': 'XlsxWriter',
    'moviepy': 'moviepy', 'imageio': 'imageio',
    'aioschedule': 'aioschedule', 'apscheduler': 'APScheduler',
    'schedule': 'schedule', 'colorama': 'colorama', 'psutil': 'psutil',
    'pyfiglet': 'pyfiglet', 'tqdm': 'tqdm', 'rich': 'rich',
    'prompt_toolkit': 'prompt_toolkit', 'loguru': 'loguru',
    'colorlog': 'colorlog', 'lxml': 'lxml', 'html5lib': 'html5lib',
    'selenium': 'selenium', 'playwright': 'playwright',
    'undetected_chromedriver': 'undetected-chromedriver',
    'pyppeteer': 'pyppeteer', 'curl_cffi': 'curl_cffi',
    'cloudscraper': 'cloudscraper', 'fake_useragent': 'fake-useragent',
    'user_agent': 'user_agent', 'pyrogram': 'pyrogram',
}

STDLIB_SAFE = set()
if hasattr(sys, 'stdlib_module_names'):
    STDLIB_SAFE = set(sys.stdlib_module_names)


def log_error(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}\n"
    try:
        with open(ERROR_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception:
        pass
    print(f"{Fore.RED}⚠ {msg}")


def save_settings():
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_error(f"Ошибка сохранения настроек: {e}")
        return False


def load_settings():
    global SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k in DEFAULT_SETTINGS:
                    if k in data:
                        SETTINGS[k] = data[k]
        except Exception as e:
            log_error(f"Не удалось загрузить настройки: {e}")


def save_state():
    try:
        state = {
            "file_list": file_list,
            "processes": {str(num): proc.pid for num, proc in processes.items()},
            "process_status": {str(num): (proc.poll() is None) for num, proc in processes.items()},
            "child_processes": {k: v.pid for k, v in child_processes.items()},
            "log_windows": {str(k): v.pid for k, v in log_windows.items()},
            "timestamp": time.time(),
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        log_error(f"Не удалось сохранить state: {e}")


def load_state():
    if not os.path.exists(STATE_FILE):
        return None
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_error(f"Не удалось прочитать state: {e}")
        return None


load_settings()

# ---------- Глобальные ----------
processes = {}
file_list = []
running = True
log_windows = {}
log_files = {}
child_processes = {}
command_history = deque(maxlen=50)
SYSTEM_CMDS = ['reboot', 'shutdown', 'poweroff', 'halt', 'systemctl',
               'service', 'apt', 'yum', 'dnf', 'pacman', 'chmod', 'chown']

os.makedirs(SETTINGS["log_dir"], exist_ok=True)

VERSION = "v13092026.1647"
PRODUCT_NAME = "Kail Admin"


# ---------- Утилиты ----------
def clear_screen():
    os.system('cls' if platform.system() == 'Windows' else 'clear')


def _flush_stdin():
    """Сбрасывает буфер stdin, чтобы старые нажатия не попадали в input()."""
    try:
        if platform.system() != 'Windows':
            import termios
            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass


def get_python_command(filepath):
    dirname = os.path.dirname(filepath) or '.'
    if platform.system() == 'Windows':
        venv_python = os.path.join(dirname, 'venv', 'Scripts', 'python.exe')
        if os.path.exists(venv_python):
            return venv_python
        if os.path.exists(os.path.join('venv', 'Scripts', 'python.exe')):
            return os.path.abspath(os.path.join('venv', 'Scripts', 'python.exe'))
        if shutil.which('py'):
            return 'py'
        return 'python'
    else:
        venv_python = os.path.join(dirname, 'venv', 'bin', 'python3')
        if os.path.exists(venv_python):
            return venv_python
        if os.path.exists('venv/bin/python3'):
            return os.path.abspath('venv/bin/python3')
        return 'python3'


def scan_files():
    global file_list
    files = [f for f in glob.glob('*.py') if os.path.isfile(f)]
    script_name = os.path.basename(__file__)
    if script_name in files:
        files.remove(script_name)
    files.sort()
    file_list = files
    return files


def get_imports(filepath):
    imports = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        for m in re.finditer(r'^\s*import\s+([a-zA-Z_][\w\.]*)', content, re.MULTILINE):
            imports.add(m.group(1).split('.')[0])
        for m in re.finditer(r'^\s*from\s+([a-zA-Z_][\w\.]*)\s+import', content, re.MULTILINE):
            imports.add(m.group(1).split('.')[0])
        imports = {i for i in imports if i not in STDLIB_SAFE and not i.startswith('_')}
    except Exception as e:
        log_error(f"Ошибка парсинга импортов {filepath}: {e}")
    return imports


def check_module_in_env(python_cmd, module):
    try:
        if python_cmd == 'py':
            cmd = ['py', '-3', '-c', f'import {module}']
        else:
            cmd = [python_cmd, '-c', f'import {module}']
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=15, stdin=subprocess.DEVNULL)
        return result.returncode == 0
    except Exception:
        return False


def pip_install(python_cmd, package, cwd=None):
    try:
        if python_cmd == 'py':
            cmd = ['py', '-3', '-m', 'pip', 'install', package]
        else:
            cmd = [python_cmd, '-m', 'pip', 'install', package]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                                timeout=300, stdin=subprocess.DEVNULL)
        ok = result.returncode == 0
        out = (result.stdout or '') + (result.stderr or '')
        return ok, out
    except Exception as e:
        return False, str(e)


def install_bot_dependencies(dir_path, python_cmd, filepath):
    """Ставит зависимости бота через его же Python."""
    if not SETTINGS["auto_install_deps"]:
        return

    req_file = os.path.join(dir_path, 'requirements.txt')

    if os.path.isfile(req_file):
        print(f"{Fore.YELLOW}Устанавливаю зависимости из requirements.txt...")
        try:
            if python_cmd == 'py':
                cmd = ['py', '-3', '-m', 'pip', 'install', '-r', req_file]
            else:
                cmd = [python_cmd, '-m', 'pip', 'install', '-r', req_file]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    cwd=dir_path, timeout=900,
                                    stdin=subprocess.DEVNULL)
            if result.returncode == 0:
                print(f"{Fore.GREEN}✅ Зависимости из requirements.txt установлены.")
            else:
                print(f"{Fore.RED}⚠ pip install -r fail (код {result.returncode})")
                tail = (result.stderr or '')[-500:]
                print(f"{Fore.LIGHTBLACK_EX}{tail}")
                log_error(f"pip install -r fail: {tail}")
        except Exception as e:
            log_error(f"Ошибка установки из requirements.txt: {e}")
        return

    imports = get_imports(filepath)
    if not imports:
        return

    print(f"{Fore.YELLOW}Проверяю библиотеки для {os.path.basename(filepath)}...")

    missing = []
    for module in sorted(imports):
        if not check_module_in_env(python_cmd, module):
            missing.append(module)

    if not missing:
        print(f"{Fore.GREEN}✅ Все библиотеки уже установлены.")
        return

    print(f"{Fore.YELLOW}Не хватает: {Fore.LIGHTCYAN_EX}{', '.join(missing)}")

    installed = 0
    failed = []
    for module in missing:
        pip_name = PIP_NAME_MAP.get(module, module)
        print(f"{Fore.YELLOW}→ Устанавливаю {Fore.LIGHTCYAN_EX}{pip_name}{Fore.YELLOW} (для {module})...")
        ok, out = pip_install(python_cmd, pip_name, cwd=dir_path)
        if not ok:
            print(f"{Fore.YELLOW}  ↻ Повторная попытка с --no-cache-dir...")
            try:
                if python_cmd == 'py':
                    cmd = ['py', '-3', '-m', 'pip', 'install', '--no-cache-dir', pip_name]
                else:
                    cmd = [python_cmd, '-m', 'pip', 'install', '--no-cache-dir', pip_name]
                r2 = subprocess.run(cmd, capture_output=True, text=True, cwd=dir_path,
                                    timeout=300, stdin=subprocess.DEVNULL)
                ok = r2.returncode == 0
                out = (r2.stdout or '') + (r2.stderr or '')
            except Exception as e:
                ok = False
                out = str(e)

        if ok:
            print(f"{Fore.GREEN}  ✅ {pip_name} установлен.")
            installed += 1
        else:
            print(f"{Fore.RED}  ❌ Не удалось установить {pip_name}.")
            tail = out.strip().split('\n')[-3:]
            for line in tail:
                print(f"{Fore.LIGHTBLACK_EX}     {line}")
            failed.append(pip_name)
            log_error(f"Не удалось установить {pip_name}: {out[:500]}")

    if failed:
        print(f"{Fore.RED}Не удалось установить: {', '.join(failed)}")
    elif installed:
        print(f"{Fore.GREEN}✅ Установлено библиотек: {installed}")


# ---------- Логотип ----------
def show_banner():
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
{Fore.CYAN}║{Fore.YELLOW}                Kail Admin  {VERSION}   [Admin bot OS]                {Fore.CYAN}║
{Fore.CYAN}║{Fore.MAGENTA}                "exclusively for Qwile Software"                           {Fore.CYAN}║
{Fore.CYAN}╚═══════════════════════════════════════════════════════════════════════════╝
""")


def show_logo_only():
    clear_screen()
    show_banner()


# ---------- venv helpers ----------
def _venv_paths(dir_path):
    """Возвращает (venv_dir, venv_python, venv_pip) для указанной папки."""
    venv_dir = os.path.join(dir_path, 'venv')
    if platform.system() == 'Windows':
        venv_python = os.path.join(venv_dir, 'Scripts', 'python.exe')
        venv_pip = os.path.join(venv_dir, 'Scripts', 'pip.exe')
    else:
        venv_python = os.path.join(venv_dir, 'bin', 'python3')
        venv_pip = os.path.join(venv_dir, 'bin', 'pip3')
    return venv_dir, venv_python, venv_pip


def ensure_venv(dir_path):
    """Создаёт venv, если его нет. Возвращает путь к python venv или None."""
    venv_dir, venv_python, _ = _venv_paths(dir_path)

    if os.path.exists(venv_python):
        print(f"{Fore.GREEN}✅ venv уже существует: {venv_dir}")
        return venv_python

    print(f"{Fore.YELLOW}Создаю venv в {venv_dir}...")
    try:
        base_python = sys.executable
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            if platform.system() == 'Windows':
                base_python = os.path.join(sys.base_prefix, 'python.exe')
            else:
                base_python = os.path.join(sys.base_prefix, 'bin', 'python3')
                if not os.path.exists(base_python):
                    base_python = shutil.which('python3') or shutil.which('python')

        r = subprocess.run(
            [base_python, '-m', 'venv', venv_dir],
            capture_output=True, text=True, timeout=300,
            stdin=subprocess.DEVNULL
        )
        if r.returncode != 0:
            print(f"{Fore.RED}❌ Ошибка создания venv: {(r.stderr or '')[-300:]}")
            return None
        print(f"{Fore.GREEN}✅ venv создан: {venv_dir}")
        try:
            subprocess.run([venv_python, '-m', 'pip', 'install', '--upgrade', 'pip', '--quiet'],
                           capture_output=True, text=True, timeout=180,
                           stdin=subprocess.DEVNULL)
        except Exception:
            pass
        return venv_python
    except Exception as e:
        print(f"{Fore.RED}❌ Не удалось создать venv: {e}")
        log_error(f"venv creation failed: {e}")
        return None


def install_into_venv(venv_python, dir_path, filepath):
    """Устанавливает зависимости бота в venv."""
    req_file = os.path.join(dir_path, 'requirements.txt')

    if os.path.isfile(req_file):
        print(f"{Fore.YELLOW}Устанавливаю requirements.txt в venv...")
        try:
            r = subprocess.run(
                [venv_python, '-m', 'pip', 'install', '-r', req_file],
                cwd=dir_path, capture_output=True, text=True, timeout=1200,
                stdin=subprocess.DEVNULL
            )
            if r.returncode == 0:
                print(f"{Fore.GREEN}✅ Requirements установлены в venv.")
            else:
                print(f"{Fore.RED}⚠ pip -r fail: {(r.stderr or '')[-300:]}")
        except Exception as e:
            log_error(f"venv requirements fail: {e}")
        return

    imports = get_imports(filepath)
    if not imports:
        return

    print(f"{Fore.YELLOW}Проверяю зависимости в venv...")
    missing = []
    for module in sorted(imports):
        try:
            r = subprocess.run(
                [venv_python, '-c', f'import {module}'],
                capture_output=True, text=True, timeout=15,
                stdin=subprocess.DEVNULL
            )
            if r.returncode != 0:
                missing.append(module)
        except Exception:
            missing.append(module)

    if not missing:
        print(f"{Fore.GREEN}✅ Все зависимости в venv на месте.")
        return

    print(f"{Fore.YELLOW}Устанавливаю в venv: {Fore.LIGHTCYAN_EX}{', '.join(missing)}")
    for module in missing:
        pip_name = PIP_NAME_MAP.get(module, module)
        print(f"{Fore.YELLOW}→ venv: {Fore.LIGHTCYAN_EX}{pip_name}...")
        try:
            r = subprocess.run(
                [venv_python, '-m', 'pip', 'install', pip_name, '--quiet'],
                cwd=dir_path, capture_output=True, text=True, timeout=400,
                stdin=subprocess.DEVNULL
            )
            if r.returncode == 0:
                print(f"{Fore.GREEN}  ✅ {pip_name}")
            else:
                print(f"{Fore.RED}  ❌ {pip_name}")
                log_error(f"venv pip fail {pip_name}: {(r.stderr or '')[:300]}")
        except Exception as e:
            print(f"{Fore.RED}  ❌ {pip_name}: {e}")
            log_error(f"venv pip exception {pip_name}: {e}")


# ---------- Запуск бота (обычный) ----------
def launch_bot(filepath, num):
    abs_filepath = os.path.abspath(filepath)
    dir_path = os.path.dirname(abs_filepath)
    python_cmd = get_python_command(filepath)

    if not os.path.exists(abs_filepath):
        log_error(f"Файл {abs_filepath} не найден!")
        return None

    install_bot_dependencies(dir_path, python_cmd, abs_filepath)

    log_path = os.path.join(SETTINGS["log_dir"], f"bot_{num}.log")
    log_files[num] = log_path
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"=== Логи бота {num} ({filepath}) ===\n")
        f.write(f"Команда: {python_cmd} {abs_filepath}\n")
        f.write(f"Рабочая папка: {dir_path}\n")
        f.write("=" * 50 + "\n\n")

    try:
        if platform.system() == 'Windows':
            if python_cmd == 'py':
                cmd = f'py -3 "{abs_filepath}"'
            else:
                cmd = f'"{python_cmd}" "{abs_filepath}"'
            log_file = open(log_path, 'a', encoding='utf-8')
            proc = subprocess.Popen(cmd, shell=True, cwd=dir_path,
                                    stdin=subprocess.DEVNULL,
                                    stdout=log_file, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            real_cmd = python_cmd
            cmd = f'cd "{dir_path}" && "{real_cmd}" -u "{abs_filepath}"'
            log_file = open(log_path, 'a', encoding='utf-8')
            proc = subprocess.Popen(['bash', '-c', cmd],
                                    stdin=subprocess.DEVNULL,
                                    stdout=log_file, stderr=subprocess.STDOUT,
                                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None)

        time.sleep(0.7)
        if proc.poll() is not None:
            with open(log_path, 'r', encoding='utf-8') as f:
                last = f.readlines()[-25:]
            print(f"{Fore.RED}❌ Бот {num} завершился сразу! Логи:")
            for line in last:
                print(f"{Fore.YELLOW}{line.rstrip()}")
            return None

        return proc
    except Exception as e:
        log_error(f"Ошибка запуска бота {num}: {e}")
        return None


# ---------- Запуск бота в venv ----------
def launch_bot_venv(filepath, num):
    abs_filepath = os.path.abspath(filepath)
    dir_path = os.path.dirname(abs_filepath)

    if not os.path.exists(abs_filepath):
        log_error(f"Файл {abs_filepath} не найден!")
        return None

    venv_python = ensure_venv(dir_path)
    if not venv_python:
        print(f"{Fore.RED}❌ Не удалось подготовить venv.")
        return None

    install_into_venv(venv_python, dir_path, abs_filepath)

    log_path = os.path.join(SETTINGS["log_dir"], f"bot_{num}.log")
    log_files[num] = log_path
    with open(log_path, 'w', encoding='utf-8') as f:
        f.write(f"=== Логи бота {num} ({filepath}) [venv] ===\n")
        f.write(f"Команда: {venv_python} {abs_filepath}\n")
        f.write(f"Рабочая папка: {dir_path}\n")
        f.write("=" * 50 + "\n\n")

    try:
        if platform.system() == 'Windows':
            cmd = f'"{venv_python}" "{abs_filepath}"'
            log_file = open(log_path, 'a', encoding='utf-8')
            proc = subprocess.Popen(cmd, shell=True, cwd=dir_path,
                                    stdin=subprocess.DEVNULL,
                                    stdout=log_file, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            cmd = f'cd "{dir_path}" && "{venv_python}" -u "{abs_filepath}"'
            log_file = open(log_path, 'a', encoding='utf-8')
            proc = subprocess.Popen(['bash', '-c', cmd],
                                    stdin=subprocess.DEVNULL,
                                    stdout=log_file, stderr=subprocess.STDOUT,
                                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None)

        time.sleep(0.7)
        if proc.poll() is not None:
            with open(log_path, 'r', encoding='utf-8') as f:
                last = f.readlines()[-25:]
            print(f"{Fore.RED}❌ Бот {num} [venv] завершился сразу! Логи:")
            for line in last:
                print(f"{Fore.YELLOW}{line.rstrip()}")
            return None

        return proc
    except Exception as e:
        log_error(f"Ошибка запуска бота {num} [venv]: {e}")
        return None


def stop_process(proc, num=None):
    if proc is None:
        return True
    try:
        if platform.system() == 'Windows':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, check=False, stdin=subprocess.DEVNULL)
        else:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.4)
                os.killpg(pgid, signal.SIGKILL)
            except Exception:
                proc.terminate()
                time.sleep(0.4)
                if proc.poll() is None:
                    proc.kill()
        return True
    except Exception as e:
        log_error(f"Ошибка остановки: {e}")
        return False


def monitor_loop():
    while running:
        time.sleep(SETTINGS["monitor_interval"])
        if not running:
            break
        if not SETTINGS["auto_restart"]:
            continue
        for num in list(processes.keys()):
            proc = processes.get(num)
            if proc is None:
                continue
            if proc.poll() is not None:
                idx = num - 1
                if 0 <= idx < len(file_list):
                    filepath = file_list[idx]
                    print(f"\n{Fore.RED}⚠ Бот {num} ({filepath}) упал, перезапускаем...")
                    del processes[num]
                    new_proc = launch_bot(filepath, num)
                    if new_proc:
                        processes[num] = new_proc
                        print(f"{Fore.GREEN}✅ Бот {num} перезапущен (PID {new_proc.pid})")
                    save_state()


# ---------- Терминал ----------
def _make_terminal_cmd(bash_cmd):
    if shutil.which('gnome-terminal'):
        return ['gnome-terminal', '--', 'bash', '-c', bash_cmd]
    elif shutil.which('xterm'):
        return ['xterm', '-e', 'bash', '-c', bash_cmd]
    elif shutil.which('konsole'):
        return ['konsole', '-e', 'bash', '-c', bash_cmd]
    elif shutil.which('xfce4-terminal'):
        return ['xfce4-terminal', '-e', 'bash', '-c', bash_cmd]
    elif shutil.which('mate-terminal'):
        return ['mate-terminal', '-e', 'bash', '-c', bash_cmd]
    return None


# ---------- Дочерние терминалы ----------
def spawn_child_terminal(action):
    script_path = os.path.abspath(__file__)
    parent_pid = os.getpid()
    py = sys.executable
    args = [py, script_path, '--child', action, '--parent-pid', str(parent_pid)]
    save_state()
    try:
        if platform.system() == 'Windows':
            quoted = ' '.join(f'"{a}"' if ' ' in a else a for a in args)
            cmd = f'start "CHILD: {action}" cmd /k {quoted}'
            proc = subprocess.Popen(cmd, shell=True)
        else:
            import shlex
            quoted = ' '.join(shlex.quote(a) for a in args)
            term_cmd = _make_terminal_cmd(f'{quoted}; exec bash')
            if not term_cmd:
                print(f"{Fore.RED}Не найден терминал.")
                return None
            proc = subprocess.Popen(term_cmd)
        return proc
    except Exception as e:
        log_error(f"Ошибка запуска дочернего: {e}")
        return None


def close_child_terminal(action):
    if action in child_processes:
        proc = child_processes[action]
        try:
            if platform.system() == 'Windows':
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               capture_output=True, stdin=subprocess.DEVNULL)
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    time.sleep(0.3)
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.terminate()
            del child_processes[action]
            return True
        except Exception as e:
            log_error(f"Ошибка закрытия дочернего: {e}")
            return False
    return False


def cmd_ott_list():
    if not child_processes:
        print(f"{Fore.YELLOW}Нет открытых дочерних терминалов.")
        return
    print(f"\n{Fore.CYAN}=== Дочерние терминалы ({len(child_processes)}) ===\n")
    for i, (action, proc) in enumerate(child_processes.items(), 1):
        alive = proc.poll() is None
        status = f"{Fore.GREEN}РАБОТАЕТ" if alive else f"{Fore.RED}ЗАКРЫТ"
        print(f"  {Fore.WHITE}{i}. [{Fore.LIGHTCYAN_EX}{action}{Fore.WHITE}] PID {proc.pid}  {status}")
    print(f"\n{Fore.LIGHTBLACK_EX}Закрыть: {Fore.GREEN}ott -n <action>{Fore.LIGHTBLACK_EX}  |  "
          f"Закрыть все: {Fore.GREEN}ott -n all")


# ---------- Действия ----------
def action_list(state=None):
    if state is not None:
        files = state.get("file_list", [])
        procs = state.get("process_status", {})
    else:
        files = [f for f in glob.glob('*.py') if os.path.isfile(f)]
        script_name = os.path.basename(__file__)
        if script_name in files:
            files.remove(script_name)
        files.sort()
        procs = {str(num): (proc.poll() is None) for num, proc in processes.items()}

    print(f"\n{Fore.CYAN}=== Список файлов ({len(files)}) ===\n")
    if not files:
        print(f"{Fore.YELLOW}Нет .py файлов.")
        return
    for i, f in enumerate(files, 1):
        is_run = procs.get(str(i), False) if state is not None else (i in processes)
        status = f"{Fore.GREEN}[ЗАПУЩЕН]" if is_run else f"{Fore.RED}[ОСТАНОВЛЕН]"
        print(f"  {Fore.WHITE}{i}. {f} {status}")


def action_settings_show():
    print(f"\n{Fore.CYAN}=== Текущие настройки ===\n")
    for k, v in SETTINGS.items():
        desc = SETTINGS_DESCRIPTIONS.get(k, "")
        print(f"  {Fore.YELLOW}{k:<24}{Fore.WHITE}= {Fore.GREEN}{v}")
        if desc:
            print(f"      {Fore.LIGHTBLACK_EX}└─ {desc}")


def action_logs(parts):
    """Просмотр логов в текущей консоли (без окна)."""
    if len(parts) < 2:
        print(f"{Fore.RED}Синтаксис: logs <num> | logs all")
        print(f"{Fore.LIGHTBLACK_EX}Для живого просмотра: {Fore.GREEN}ott -y logs <num>")
        return

    if parts[1] == 'all':
        print(f"\n{Fore.CYAN}=== Логи всех ботов ===\n")
        if not log_files:
            print(f"{Fore.YELLOW}Нет логов. Сначала запустите ботов.")
            return
        for num in sorted(log_files.keys()):
            path = log_files[num]
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                print(f"{Fore.YELLOW}--- Бот {num} ({len(lines)} строк) ---")
                for line in lines[-15:]:
                    print(f"{Fore.WHITE}{line.rstrip()}")
                print()
    else:
        try:
            n = int(parts[1])
            path = log_files.get(n)
            if not path:
                candidate = os.path.join(SETTINGS["log_dir"], f"bot_{n}.log")
                if os.path.exists(candidate):
                    path = candidate
            if path and os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = f.readlines()
                print(f"\n{Fore.YELLOW}--- Бот {n} ({len(lines)} строк, последние 30) ---")
                for line in lines[-30:]:
                    print(f"{Fore.WHITE}{line.rstrip()}")
                print(f"\n{Fore.LIGHTBLACK_EX}Live-просмотр: {Fore.GREEN}ott -y logs {n}")
            else:
                print(f"{Fore.RED}Лог для бота {n} не найден.")
        except ValueError:
            print(f"{Fore.RED}Неверный номер.")


def action_info():
    print(f"\n{Fore.CYAN}=== ИНФОРМАЦИЯ О СИСТЕМЕ ===\n")
    print(f"  ОС:          {Fore.GREEN}{platform.system()} {platform.release()}")
    print(f"  Архитектура: {Fore.GREEN}{platform.machine()}")
    print(f"  Python:      {Fore.GREEN}{platform.python_version()}")
    print(f"  Имя узла:    {Fore.GREEN}{platform.node()}")
    print(f"  Процессор:   {Fore.GREEN}{psutil.cpu_count()} ядер ({psutil.cpu_percent(interval=0.3)}%)")
    mem = psutil.virtual_memory()
    print(f"  RAM:         {Fore.GREEN}{mem.used/(1024**3):.2f} / {mem.total/(1024**3):.2f} GB ({mem.percent}%)")
    try:
        d = psutil.disk_usage('.')
        print(f"  Диск (cwd):  {Fore.GREEN}{d.used/(1024**3):.2f} / {d.total/(1024**3):.2f} GB ({d.percent}%)")
    except Exception as e:
        log_error(f"Ошибка чтения диска: {e}")


def action_date():
    print(f"{Fore.LIGHTCYAN_EX}Дата/время: {Fore.GREEN}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def action_whoami():
    try:
        user = getpass.getuser()
    except Exception:
        user = os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'
    print(f"{Fore.LIGHTCYAN_EX}Пользователь: {Fore.GREEN}{user}")


def action_uptime():
    try:
        boot = datetime.fromtimestamp(psutil.boot_time())
        delta = datetime.now() - boot
        days = delta.days
        h, rem = divmod(delta.seconds, 3600)
        m, s = divmod(rem, 60)
        print(f"{Fore.LIGHTCYAN_EX}Uptime: {Fore.GREEN}{days}д {h}ч {m}м {s}с")
        print(f"{Fore.LIGHTCYAN_EX}Загрузка: {Fore.GREEN}{boot.strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        log_error(f"Ошибка uptime: {e}")


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


# ---------- Команда rename ----------
def cmd_rename(num_str, newname):
    """sudo rename <num> to <newname> — переименовать файл бота."""
    try:
        num = int(num_str)
    except ValueError:
        print(f"{Fore.RED}Неверный номер: {num_str}")
        return

    idx = num - 1
    if idx < 0 or idx >= len(file_list):
        print(f"{Fore.RED}Номер {num} вне списка (всего: {len(file_list)}).")
        return

    old_file = file_list[idx]
    old_abs = os.path.abspath(old_file)
    dir_path = os.path.dirname(old_abs)

    newname = newname.strip()
    if newname.endswith('.py'):
        newname = newname[:-3]
    if not newname:
        print(f"{Fore.RED}Пустое имя.")
        return
    bad = re.search(r'[\\/<>:"|?*]', newname)
    if bad:
        print(f"{Fore.RED}Имя содержит недопустимые символы.")
        return

    new_file = newname + '.py'
    new_abs = os.path.join(dir_path, new_file)

    if os.path.exists(new_abs):
        print(f"{Fore.RED}Файл {new_file} уже существует.")
        return

    if num in processes:
        print(f"{Fore.YELLOW}Останавливаю бота {num} перед переименованием...")
        stop_process(processes[num], num)
        del processes[num]

    try:
        os.rename(old_abs, new_abs)
        print(f"{Fore.GREEN}✅ Переименовано: {old_file} → {new_file}")
        scan_files()
        save_state()
    except Exception as e:
        print(f"{Fore.RED}❌ Ошибка переименования: {e}")
        log_error(f"rename fail: {e}")


# ---------- Системные команды ----------
def execute_system_cmd(cmd_parts):
    if len(cmd_parts) < 2:
        print(f"{Fore.RED}Укажите команду. Пример: sudo reboot")
        return
    cmd = ' '.join(cmd_parts[1:])
    print(f"{Fore.YELLOW}Выполняю: {cmd}")
    if SETTINGS["sudo_confirm"]:
        print(f"{Fore.RED}⚠ Системная команда!")
        _flush_stdin()
        try:
            confirm = input(f"{Fore.YELLOW}Продолжить? (y/N): ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            confirm = 'n'
        if confirm != 'y':
            print(f"{Fore.RED}Отменено.")
            return
    try:
        if platform.system() == 'Windows':
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        else:
            r = subprocess.run(['sudo'] + cmd_parts[1:], capture_output=True, text=True)
        if r.returncode == 0:
            print(f"{Fore.GREEN}✅ Выполнено")
            if r.stdout:
                print(r.stdout)
        else:
            print(f"{Fore.RED}❌ Ошибка (код {r.returncode})")
            if r.stderr:
                print(r.stderr)
            log_error(f"Системная команда '{cmd}' завершилась с кодом {r.returncode}")
    except Exception as e:
        log_error(f"Ошибка системной команды: {e}")


# ---------- Настройки ----------
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
        _flush_stdin()
        try:
            cmd = input(f"{Fore.YELLOW}settings> {Fore.WHITE}").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue
        if cmd.lower() == 'exit':
            break
        if cmd.lower() == 'save':
            if save_settings():
                print(f"{Fore.GREEN}✅ Сохранено в {SETTINGS_FILE}")
            time.sleep(0.8)
            continue
        if cmd.lower() == 'reset':
            for k, v in DEFAULT_SETTINGS.items():
                SETTINGS[k] = v
            save_settings()
            print(f"{Fore.GREEN}✅ Сброшено.")
            time.sleep(0.8)
            continue
        try:
            idx = int(cmd) - 1
            if 0 <= idx < len(items):
                key = items[idx]
                cur = SETTINGS[key]
                print(f"\n{Fore.LIGHTCYAN_EX}{key}: {Fore.LIGHTBLACK_EX}{SETTINGS_DESCRIPTIONS.get(key,'')}")
                print(f"{Fore.WHITE}Текущее: {Fore.GREEN}{cur}")
                if isinstance(cur, bool):
                    print(f"{Fore.LIGHTBLACK_EX}Введите true/false")
                elif isinstance(cur, int):
                    print(f"{Fore.LIGHTBLACK_EX}Введите целое число")
                _flush_stdin()
                nv = input(f"{Fore.YELLOW}Новое (Enter — отмена): {Fore.WHITE}").strip()
                if nv:
                    if isinstance(cur, bool):
                        SETTINGS[key] = nv.lower() in ('1','true','yes','y','on','вкл','да')
                    elif isinstance(cur, int):
                        SETTINGS[key] = int(nv)
                    else:
                        SETTINGS[key] = nv
                    save_settings()
                    print(f"{Fore.GREEN}✅ {key} = {SETTINGS[key]}")
                    time.sleep(0.8)
        except ValueError:
            print(f"{Fore.RED}Неверный ввод.")
            time.sleep(0.8)


# ---------- Справка ----------
def show_help():
    print(f"""
{Fore.LIGHTCYAN_EX}══════════ УПРАВЛЕНИЕ БОТАМИ ══════════
  {Fore.GREEN}list                    {Fore.WHITE}- список .py файлов
  {Fore.GREEN}run <num>               {Fore.WHITE}- запустить бота
  {Fore.GREEN}run <num> -venv-        {Fore.WHITE}- запустить в отдельном venv
  {Fore.GREEN}allrun                  {Fore.WHITE}- запустить всех
  {Fore.GREEN}stop <num>              {Fore.WHITE}- остановить бота
  {Fore.GREEN}stopall                 {Fore.WHITE}- остановить всех
  {Fore.GREEN}restart <num>           {Fore.WHITE}- перезапустить бота
  {Fore.GREEN}kill <num>              {Fore.WHITE}- убить принудительно
  {Fore.GREEN}sudo rename <num> to <name>  {Fore.WHITE}- переименовать файл бота

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

{Fore.LIGHTCYAN_EX}══════════ СИСТЕМНЫЕ КОМАНДЫ (через sudo) ══════════
  {Fore.GREEN}sudo reboot             {Fore.WHITE}- перезагрузить систему
  {Fore.GREEN}sudo shutdown now       {Fore.WHITE}- выключить сейчас
  {Fore.GREEN}sudo poweroff           {Fore.WHITE}- выключить
  {Fore.GREEN}sudo halt               {Fore.WHITE}- остановить
  {Fore.GREEN}sudo systemctl restart <svc>   {Fore.WHITE}- перезапустить сервис
  {Fore.GREEN}sudo apt update         {Fore.WHITE}- обновить список пакетов
  {Fore.GREEN}sudo chmod +x <file>    {Fore.WHITE}- сделать исполняемым

{Fore.LIGHTCYAN_EX}══════════ ИНТЕРФЕЙС ══════════
  {Fore.GREEN}settings                {Fore.WHITE}- меню настроек (сохраняются в {SETTINGS_FILE})
  {Fore.GREEN}clear / cls             {Fore.WHITE}- очистить экран (лого остаётся)
  {Fore.GREEN}help                    {Fore.WHITE}- эта справка
  {Fore.GREEN}exit                    {Fore.WHITE}- выход

{Fore.YELLOW}Логи ошибок: {ERROR_LOG_FILE}
{Fore.LIGHTCYAN_EX}═════════════════════════════════════════
""")


# ---------- Child mode ----------
def _follow_log_thread(log_path, bot_num, stop_event):
    """Фоновый поток для live-просмотра лога."""
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            lines = content.splitlines()
            tail = lines[-30:] if len(lines) > 30 else lines
            for line in tail:
                if stop_event.is_set():
                    return
                print(f"{Fore.LIGHTCYAN_EX}[bot {bot_num}]{Fore.WHITE} {line}")
            while not stop_event.is_set():
                line = f.readline()
                if line:
                    print(f"{Fore.LIGHTCYAN_EX}[bot {bot_num}]{Fore.WHITE} {line.rstrip()}")
                else:
                    time.sleep(0.3)
    except FileNotFoundError:
        print(f"{Fore.RED}Файл лога не найден: {log_path}")
    except Exception as e:
        print(f"{Fore.RED}Ошибка чтения лога: {e}")


def draw_child_header(action, parent_pid):
    clear_screen()
    print(f"""
{Fore.YELLOW}╔══════════════════════════════════════════════════════════════╗
{Fore.YELLOW}║{Fore.LIGHTRED_EX}          ДОЧЕРНИЙ ТЕРМИНАЛ — CHILD PROCESS               {Fore.YELLOW}║
{Fore.YELLOW}║{Fore.WHITE}  Родитель: {Fore.LIGHTGREEN_EX}{parent_pid:<10}{Fore.WHITE}  Мой PID: {Fore.LIGHTGREEN_EX}{os.getpid():<15}{Fore.YELLOW}║
{Fore.YELLOW}║{Fore.WHITE}  Действие: {Fore.LIGHTCYAN_EX}{action:<46}{Fore.YELLOW}║
{Fore.YELLOW}╚══════════════════════════════════════════════════════════════╝
{Fore.MAGENTA}  Состояние синхронизируется автоматически каждые {SETTINGS.get('state_sync_interval', 2)}с.
{Fore.MAGENTA}  Введите {Fore.GREEN}exit{Fore.MAGENTA} для закрытия.\n""")


def child_execute_action(action, state=None):
    parts = action.strip().split()
    if not parts:
        return
    cmd = parts[0].lower()

    if cmd == 'list':
        action_list(state)
    elif cmd == 'settings':
        action_settings_show()
    elif cmd == 'logs':
        action_logs(parts)
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


def run_child_mode():
    try:
        action = sys.argv[sys.argv.index('--child') + 1]
    except (ValueError, IndexError):
        action = 'help'
    try:
        parent_pid = int(sys.argv[sys.argv.index('--parent-pid') + 1])
    except (ValueError, IndexError):
        parent_pid = 0

    # --- Спец-режим: live-просмотр логов (ott -y logs <num>) ---
    is_logs_follow = False
    follow_log_path = None
    follow_bot_num = None

    parts = action.strip().split()
    if len(parts) == 2 and parts[0].lower() == 'logs':
        try:
            follow_bot_num = int(parts[1])
            follow_log_path = os.path.join(SETTINGS["log_dir"], f"bot_{follow_bot_num}.log")
            is_logs_follow = True
        except ValueError:
            pass

    if is_logs_follow:
        clear_screen()
        print(f"""{Fore.YELLOW}╔══════════════════════════════════════════════════════════════╗
{Fore.YELLOW} {Fore.LIGHTRED_EX}          ДОЧЕРНИЙ ТЕРМИНАЛ — LIVE LOGS                   {Fore.YELLOW}
{Fore.YELLOW} {Fore.WHITE}  Родитель: {Fore.LIGHTGREEN_EX}{parent_pid:<10}{Fore.WHITE}  Мой PID: {Fore.LIGHTGREEN_EX}{os.getpid():<15}{Fore.YELLOW}
{Fore.YELLOW} {Fore.WHITE}  Бот:      {Fore.LIGHTCYAN_EX}{follow_bot_num:<46}{Fore.YELLOW}
{Fore.YELLOW}╚══════════════════════════════════════════════════════════════╝
{Fore.MAGENTA}  Live-режим. Нажмите Ctrl+C чтобы выйти.
{Fore.MAGENTA}  Автоматически закроется при закрытии главного терминала.\n""")

        if not os.path.exists(follow_log_path):
            print(f"{Fore.RED}Лог-файл не найден: {follow_log_path}")
            print(f"{Fore.YELLOW}Сначала запустите бота {follow_bot_num} в главном терминале.")
            time.sleep(3)
            return

        stop_ev = threading.Event()
        reader = threading.Thread(
            target=_follow_log_thread,
            args=(follow_log_path, follow_bot_num, stop_ev),
            daemon=True
        )
        reader.start()

        check_interval = max(1, int(SETTINGS.get("child_check_interval", 3)))
        last_check = 0
        try:
            while True:
                now = time.time()
                if now - last_check >= check_interval:
                    last_check = now
                    if parent_pid and not psutil.pid_exists(parent_pid):
                        print(f"\n{Fore.RED}Родитель завершён. Закрываюсь...")
                        stop_ev.set()
                        time.sleep(0.5)
                        break
                time.sleep(0.3)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Выход из live-режима.")
            stop_ev.set()
        return

    # --- Обычный режим child ---
    state = load_state()

    draw_child_header(action, parent_pid)
    if state:
        action_list(state)
    child_execute_action(action, state)

    check_interval = max(1, int(SETTINGS.get("child_check_interval", 3)))
    sync_interval = max(1, int(SETTINGS.get("state_sync_interval", 2)))
    last_parent_check = 0
    last_state_sync = 0

    while True:
        now = time.time()

        if now - last_parent_check >= check_interval:
            last_parent_check = now
            if parent_pid and not psutil.pid_exists(parent_pid):
                print(f"\n{Fore.RED}Родитель завершён. Закрываюсь...")
                time.sleep(1)
                break

        if now - last_state_sync >= sync_interval:
            last_state_sync = now

        _flush_stdin()
        try:
            cmd = input(f"{Fore.YELLOW}child [{action}]> {Fore.WHITE}").strip()
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
            state = load_state()
            redraw_child(action, parent_pid, state)
            continue
        if low == 'refresh':
            state = load_state()
            redraw_child(action, parent_pid, state)
            print(f"{Fore.GREEN}✅ Состояние синхронизировано с главным терминалом.")
            continue
        if low == 'banner':
            show_banner()
            continue

        state = load_state()
        child_execute_action(cmd, state)

    print(f"\n{Fore.YELLOW}Дочерний терминал завершён.")
    time.sleep(0.5)


# ---------- Главная функция ----------
def main():
    if '--child' in sys.argv:
        run_child_mode()
        return

    global running, processes, file_list

    scan_files()
    show_logo_only()

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    def state_saver():
        while running:
            save_state()
            time.sleep(1)

    state_thread = threading.Thread(target=state_saver, daemon=True)
    state_thread.start()

    def cleanup():
        global running
        running = False
        try:
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
        except Exception as e:
            log_error(f"Не удалось удалить state: {e}")
        for action in list(child_processes.keys()):
            try:
                close_child_terminal(action)
            except Exception:
                pass
        child_processes.clear()
        for key in list(log_windows.keys()):
            try:
                if platform.system() == 'Windows':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(log_windows[key].pid)], capture_output=True)
                else:
                    os.killpg(os.getpgid(log_windows[key].pid), signal.SIGTERM)
            except:
                pass
        log_windows.clear()
        if processes:
            print(f"\n{Fore.RED}Останавливаем все процессы...")
            for idx in list(processes.keys()):
                stop_process(processes[idx], idx)
            processes.clear()
    atexit.register(cleanup)

    while running:
        # КРИТИЧНО: сбрасываем буфер stdin, чтобы мусор от подпроцессов
        # не «съедал» первый Enter пользователя.
        _flush_stdin()
        try:
            cmd = input(f"{Fore.YELLOW}Kail~Admin$: {Fore.WHITE}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.RED}Выход...")
            break

        if not cmd:
            continue

        command_history.append(cmd)
        parts = cmd.split()
        command = parts[0].lower()

        # ---- ИНТЕРФЕЙС ----
        if command in ('clear', 'cls'):
            show_logo_only()
            continue

        if command == 'help':
            print()
            show_help()
            continue

        if command == 'banner':
            show_banner()
            continue

        if command == 'settings':
            settings_menu()
            show_logo_only()
            continue

        if command == 'exit':
            print(f"{Fore.RED}Выход...")
            running = False
            break

        # ---- БОТЫ ----
        if command == 'list':
            action_list()
            continue

        if command == 'run':
            if len(parts) < 2:
                print(f"{Fore.RED}Пример: run 1  |  run 1 -venv-")
                continue
            use_venv = (len(parts) >= 3 and parts[2] == '-venv-')
            try:
                idx = int(parts[1]) - 1
                if idx < 0 or idx >= len(file_list):
                    print(f"{Fore.RED}Неверный номер.")
                    continue
                filepath = file_list[idx]
                num = idx + 1
                if num in processes:
                    print(f"{Fore.YELLOW}Перезапускаю бота {num}...")
                    stop_process(processes[num], num)
                    del processes[num]
                if use_venv:
                    print(f"{Fore.MAGENTA}Запуск {filepath} в изолированном venv...")
                    proc = launch_bot_venv(filepath, num)
                else:
                    print(f"{Fore.CYAN}Запуск {filepath}...")
                    proc = launch_bot(filepath, num)
                if proc:
                    processes[num] = proc
                    tag = " [venv]" if use_venv else ""
                    print(f"{Fore.GREEN}✅ Бот {num} запущен{tag} (PID {proc.pid})")
                    save_state()
                else:
                    print(f"{Fore.RED}❌ Ошибка запуска.")
            except ValueError:
                print(f"{Fore.RED}Номер — целое число.")
            continue

        if command == 'allrun':
            if not file_list:
                print(f"{Fore.RED}Нет файлов.")
                continue
            print(f"{Fore.CYAN}Запуск всех...")
            s = 0
            for i, filepath in enumerate(file_list, 1):
                if i in processes:
                    continue
                proc = launch_bot(filepath, i)
                if proc:
                    processes[i] = proc
                    print(f"{Fore.GREEN}✅ Бот {i} запущен (PID {proc.pid})")
                    s += 1
                else:
                    print(f"{Fore.RED}❌ Ошибка бота {i}")
                time.sleep(1)
            print(f"{Fore.GREEN}Запущено {s} из {len(file_list)}.")
            save_state()
            continue

        if command == 'stop':
            if len(parts) < 2:
                print(f"{Fore.RED}Пример: stop 1")
                continue
            try:
                num = int(parts[1])
                if num not in processes:
                    print(f"{Fore.RED}Бот {num} не запущен.")
                    continue
                print(f"{Fore.YELLOW}Останавливаю бота {num}...")
                if stop_process(processes[num], num):
                    del processes[num]
                    print(f"{Fore.GREEN}✅ Остановлен.")
                    save_state()
            except ValueError:
                print(f"{Fore.RED}Номер — целое число.")
            continue

        if command == 'stopall':
            if not processes:
                print(f"{Fore.RED}Нет ботов.")
                continue
            print(f"{Fore.YELLOW}Останавливаю всех...")
            for num in list(processes.keys()):
                stop_process(processes[num], num)
                print(f"  Бот {num} остановлен.")
            processes.clear()
            print(f"{Fore.GREEN}✅ Все остановлены.")
            save_state()
            continue

        if command == 'restart':
            if len(parts) < 2:
                print(f"{Fore.RED}Пример: restart 1")
                continue
            try:
                num = int(parts[1])
                if num not in processes:
                    print(f"{Fore.RED}Бот {num} не запущен.")
                    continue
                filepath = file_list[num-1]
                print(f"{Fore.YELLOW}Перезапуск {num}...")
                stop_process(processes[num], num)
                del processes[num]
                time.sleep(1)
                proc = launch_bot(filepath, num)
                if proc:
                    processes[num] = proc
                    print(f"{Fore.GREEN}✅ Бот {num} перезапущен (PID {proc.pid})")
                    save_state()
                else:
                    print(f"{Fore.RED}❌ Ошибка.")
            except ValueError:
                print(f"{Fore.RED}Номер — целое число.")
            continue

        if command == 'kill':
            if len(parts) < 2:
                print(f"{Fore.RED}Пример: kill 1")
                continue
            try:
                num = int(parts[1])
                if num not in processes:
                    print(f"{Fore.RED}Бот {num} не запущен.")
                    continue
                proc = processes[num]
                if platform.system() == 'Windows':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)], capture_output=True)
                else:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                del processes[num]
                print(f"{Fore.GREEN}✅ Бот {num} убит.")
                save_state()
            except ValueError:
                print(f"{Fore.RED}Номер — целое число.")
            continue

        # ---- ЛОГИ ----
        if command == 'logs':
            action_logs(parts)
            continue

        if command == 'logclose':
            print(f"{Fore.YELLOW}Окна логов открываются только в дочернем терминале (ott -y logs <num>).")
            continue

        # ---- ДОЧЕРНИЕ ТЕРМИНАЛЫ ----
        if command == 'ott':
            if len(parts) >= 2 and parts[1].lower() == 'list':
                cmd_ott_list()
                continue
            if len(parts) >= 3 and parts[1] == '-n' and parts[2].lower() == 'all':
                if not child_processes:
                    print(f"{Fore.YELLOW}Нет открытых дочерних.")
                    continue
                for action in list(child_processes.keys()):
                    close_child_terminal(action)
                print(f"{Fore.GREEN}✅ Все дочерние закрыты.")
                continue
            if len(parts) >= 3 and parts[1] == '-n':
                action = ' '.join(parts[2:])
                if close_child_terminal(action):
                    print(f"{Fore.GREEN}✅ Дочерний '{action}' закрыт.")
                else:
                    print(f"{Fore.RED}Не найден '{action}'.")
                continue
            if len(parts) >= 3 and parts[1] == '-y':
                action = ' '.join(parts[2:])
                if action in child_processes and child_processes[action].poll() is None:
                    print(f"{Fore.YELLOW}Уже открыт '{action}'.")
                    continue
                if action.startswith('logs '):
                    try:
                        ln = int(action.split()[1])
                        log_path = os.path.join(SETTINGS["log_dir"], f"bot_{ln}.log")
                        if not os.path.exists(log_path):
                            print(f"{Fore.RED}Лог бота {ln} ещё не создан. Запустите бота сначала.")
                            continue
                    except (ValueError, IndexError):
                        print(f"{Fore.RED}Синтаксис: ott -y logs <num>")
                        continue
                proc = spawn_child_terminal(action)
                if proc:
                    child_processes[action] = proc
                    print(f"{Fore.GREEN}✅ Дочерний '{action}' открыт (PID {proc.pid})")
                else:
                    print(f"{Fore.RED}❌ Не удалось открыть.")
                continue
            print(f"{Fore.RED}Синтаксис: ott list | ott -y <action> | ott -n <action> | ott -n all")
            print(f"{Fore.YELLOW}Пример: ott -y logs 4 | ott -y list | ott -y settings")
            continue

        # ---- СИСТЕМА ----
        if command == 'sudo':
            if (len(parts) >= 5 and parts[1].lower() == 'rename'
                    and parts[3].lower() == 'to'):
                cmd_rename(parts[2], parts[4])
                continue
            execute_system_cmd(parts)
            continue

        if command == 'info':
            action_info()
            continue
        if command == 'date':
            action_date()
            continue
        if command == 'whoami':
            action_whoami()
            continue
        if command == 'uptime':
            action_uptime()
            continue
        if command == 'history':
            action_history()
            continue
        if command == 'version':
            action_version()
            continue
        if command == 'echo':
            print(' '.join(parts[1:]))
            continue

        if command == 'refresh':
            action_refresh()
            print(f"{Fore.GREEN}Состояние синхронизировано с дочерними терминалами.")
            continue

        print(f"{Fore.RED}❌ Неизвестная команда: {command}. Введите help.")

    cleanup()


if __name__ == '__main__':
    main()