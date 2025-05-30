import os
import sqlite3
import time
from typing import Dict, List, Optional, Set, Tuple
import json
from contextlib import contextmanager
from sqlite3 import Error
import psutil
from utils import find_process_by_path

_cache = {
    "manager_dir": None,
    "profile_cashes": [],
    "is_empty_profiles": False,
    "profile_seen_paths": set(),
    "cash_registers": [],
    "external_cashes": []
}

EXCLUDED_DIRS = [
    "windows", "appdata", "programdata", "system32", "syswow64",
    "$recycle.bin", "recovery", "boot", "perflogs", "$getcurrent"
]

MANAGER_FOLDER_NAME = "checkbox.kasa.manager"

COMMON_PATHS = [
    r"C:\checkbox.kasa.manager",
    r"D:\checkbox.kasa.manager",
    r"C:\Program Files",
    r"C:\Program Files (x86)"
]

@contextmanager
def sqlite_connection(db_path: str):
    """
    Контекстний менеджер для створення та безпечного закриття з’єднання з SQLite базою даних у режимі лише для читання.

    Args:
        db_path (str): Шлях до файлу бази даних SQLite.

    Yields:
        sqlite3.Connection: Відкрите з’єднання з базою даних.

    Raises:
        sqlite3.Error: Якщо не вдалося підключитися до бази даних.
    """
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
        yield conn
    except Error:
        raise
    finally:
        if conn:
            conn.close()
            time.sleep(0.1)

def reset_cache():
    global _cache
    _cache = {
        "manager_dir": None,
        "profile_cashes": [],
        "is_empty_profiles": False,
        "profile_seen_paths": set(),
        "cash_registers": [],
        "external_cashes": []
    }

def is_hidden_folder(filepath: str) -> bool:
    if os.path.abspath(filepath) == os.path.abspath(os.path.dirname(filepath + os.sep)):
        return False
    try:
        attrs = os.stat(filepath).st_file_attributes
        return bool(attrs & 0x02)
    except (OSError, AttributeError):
        return False

def find_manager_by_exe(drives: list, max_depth: int = 4, use_cache: bool = True) -> Optional[str]:
    """
    Шукає директорію менеджера, знаходячи запущений процес 'kasa_manager.exe' або скануючи
    загальні шляхи та диски для папки 'checkbox.kasa.manager' із виконуваним файлом.

    Args:
        drives (list): Список шляхів до дисків для пошуку (наприклад, ['C:\\', 'D:\\']).
        max_depth (int): Максимальна глибина пошуку в дереві директорій. За замовчуванням 4.
        use_cache (bool): Чи використовувати кешовані результати. За замовчуванням True.

    Returns:
        Optional[str]: Шлях до директорії менеджера, якщо знайдено, або None.

    Raises:
        PermissionError: Якщо відсутні права доступу до директорій.
        OSError: Інші помилки файлової системи.
    """
    global _cache
    if use_cache and _cache["manager_dir"] is not None:
        return _cache["manager_dir"]

    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            if proc.name().lower() == "kasa_manager.exe":
                manager_path = os.path.normpath(os.path.abspath(os.path.dirname(proc.exe())))
                if not any(excluded in manager_path.lower() for excluded in EXCLUDED_DIRS):
                    _cache["manager_dir"] = manager_path
                    return manager_path
                time.sleep(0.001)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for common_path in COMMON_PATHS:
        if not os.path.exists(common_path):
            continue
        try:
            for root, dirs, files in os.walk(common_path, topdown=True):
                root_normalized = os.path.normpath(os.path.abspath(root))
                root_basename = os.path.basename(root_normalized).lower()

                if any(excluded in root_normalized.lower() for excluded in EXCLUDED_DIRS):
                    dirs[:] = []
                    continue

                if is_hidden_folder(root_normalized):
                    dirs[:] = []
                    continue

                depth = len(os.path.relpath(root_normalized, common_path).split(os.sep))
                if depth > max_depth:
                    dirs[:] = []
                    continue

                if root_basename == MANAGER_FOLDER_NAME.lower():
                    if "kasa_manager.exe" in files:
                        manager_path = root_normalized
                        _cache["manager_dir"] = manager_path
                        return manager_path
        except (PermissionError, OSError):
            continue

    drives = [os.path.normpath(os.path.abspath(drive)) for drive in drives]
    for drive in drives:
        try:
            for root, dirs, files in os.walk(drive, topdown=True):
                root_normalized = os.path.normpath(os.path.abspath(root))
                root_basename = os.path.basename(root_normalized).lower()

                if any(excluded in root_normalized.lower() for excluded in EXCLUDED_DIRS):
                    dirs[:] = []
                    continue

                if is_hidden_folder(root_normalized):
                    dirs[:] = []
                    continue

                depth = len(os.path.relpath(root_normalized, drive).split(os.sep))
                if depth > max_depth:
                    dirs[:] = []
                    continue

                if root_basename == MANAGER_FOLDER_NAME.lower():
                    if "kasa_manager.exe" in files:
                        manager_path = root_normalized
                        _cache["manager_dir"] = manager_path
                        return manager_path
        except (PermissionError, OSError):
            continue

    _cache["manager_dir"] = None
    return None

def find_cash_registers_by_profiles_json(manager_dir: str, use_cache: bool = True) -> Tuple[List[Dict], bool, Set[str]]:
    """
    Знаходить каси, аналізуючи файл 'profiles.json' у директорії менеджера.

    Args:
        manager_dir (str): Шлях до директорії менеджера, що містить 'profiles.json'.
        use_cache (bool): Чи використовувати кешовані результати. За замовчуванням True.

    Returns:
        Tuple[List[Dict], bool, Set[str]]: Кортеж, що містить:
            - Список словників із шляхами до кас та їх джерелом.
            - Логічне значення, що вказує, чи порожній файл profiles.json.
            - Множина нормалізованих шляхів, знайдених у profiles.json.

    Raises:
        json.JSONDecodeError: Якщо файл profiles.json некоректний.
        Exception: Інші помилки, пов’язані з читанням файлу.
    """
    global _cache
    if use_cache and _cache["profile_cashes"]:
        return _cache["profile_cashes"], _cache["is_empty_profiles"], _cache["profile_seen_paths"]

    manager_dir = os.path.normpath(os.path.abspath(manager_dir))
    profiles_json_path = os.path.normpath(os.path.join(manager_dir, "profiles.json"))
    cash_registers = []
    is_empty = False
    seen_paths = set()

    if not os.path.exists(profiles_json_path):
        _cache["profile_cashes"] = cash_registers
        _cache["is_empty_profiles"] = is_empty
        _cache["profile_seen_paths"] = seen_paths
        return cash_registers, is_empty, seen_paths

    try:
        with open(profiles_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profiles = data.get("profiles", {})
        if not profiles:
            is_empty = True
        else:
            for profile_id, profile in profiles.items():
                exec_path = profile.get("local", {}).get("paths", {}).get("exec_path", "")
                if exec_path:
                    exec_path_normalized = os.path.normpath(os.path.abspath(exec_path))
                    if not any(excluded in exec_path_normalized.lower() for excluded in EXCLUDED_DIRS):
                        cash_registers.append({
                            "path": exec_path_normalized,
                            "source": "profiles_json"
                        })
                        seen_paths.add(exec_path_normalized)
    except (json.JSONDecodeError, Exception):
        pass

    _cache["profile_cashes"] = cash_registers
    _cache["is_empty_profiles"] = is_empty
    _cache["profile_seen_paths"] = seen_paths
    return cash_registers, is_empty, seen_paths

def find_cash_registers_by_exe(manager_dir: Optional[str], drives: List[str], max_depth: int = 4, use_cache: bool = True) -> List[Dict]:
    """
    Шукає директорії кас, знаходячи запущені процеси 'checkbox_kasa.exe' або
    скануючи файлову систему на наявність цього виконуваного файлу.

    Args:
        manager_dir (Optional[str]): Шлях до директорії менеджера або None.
        drives (List[str]): Список дисків для пошуку.
        max_depth (int): Максимальна глибина пошуку в дереві директорій. За замовчуванням 4.
        use_cache (bool): Чи використовувати кешовані результати. За замовчуванням True.

    Returns:
        List[Dict]: Список словників із шляхами до кас та їх джерелом.

    Raises:
        PermissionError: Якщо відсутні права доступу до директорій.
        OSError: Інші помилки файлової системи.
    """
    global _cache
    if use_cache and (_cache["cash_registers"] or _cache["external_cashes"]):
        return _cache["cash_registers"] + _cache["external_cashes"]

    cash_registers = []
    external_cashes = []
    seen_paths = set(_cache["profile_seen_paths"])
    manager_dir_normalized = os.path.normpath(os.path.abspath(manager_dir)) if manager_dir else None

    for proc in psutil.process_iter(['pid', 'exe', 'cwd']):
        try:
            if proc.name().lower() == "checkbox_kasa.exe":
                cash_dir = os.path.normpath(os.path.abspath(proc.cwd()))
                if manager_dir_normalized and cash_dir == manager_dir_normalized:
                    continue
                if any(excluded in cash_dir.lower() for excluded in EXCLUDED_DIRS):
                    continue
                if cash_dir not in seen_paths:
                    cash_entry = {
                        "path": cash_dir,
                        "source": "process"
                    }
                    if cash_dir not in _cache["profile_seen_paths"]:
                        external_cashes.append(cash_entry)
                    else:
                        cash_registers.append(cash_entry)
                    seen_paths.add(cash_dir)
                time.sleep(0.001)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if cash_registers or external_cashes:
        _cache["cash_registers"] = cash_registers
        _cache["external_cashes"] = external_cashes
        return cash_registers + external_cashes

    search_dirs = [manager_dir] if manager_dir else drives
    search_dirs = [os.path.normpath(os.path.abspath(d)) for d in search_dirs]

    for search_dir in search_dirs:
        try:
            for root, dirs, files in os.walk(search_dir, topdown=True):
                root_normalized = os.path.normpath(os.path.abspath(root))

                if any(excluded in root_normalized.lower() for excluded in EXCLUDED_DIRS):
                    dirs[:] = []
                    continue

                if is_hidden_folder(root_normalized):
                    dirs[:] = []
                    continue

                depth = len(os.path.relpath(root_normalized, search_dir).split(os.sep))
                if depth > max_depth:
                    dirs[:] = []
                    continue

                if "checkbox_kasa.exe" in files:
                    cash_dir = root_normalized
                    if manager_dir_normalized and cash_dir == manager_dir_normalized:
                        continue
                    if cash_dir not in seen_paths:
                        cash_entry = {
                            "path": cash_dir,
                            "source": "filesystem"
                        }
                        if cash_dir not in _cache["profile_seen_paths"]:
                            external_cashes.append(cash_entry)
                        else:
                            cash_registers.append(cash_entry)
                        seen_paths.add(cash_dir)
        except (PermissionError, OSError):
            continue

    _cache["cash_registers"] = cash_registers
    _cache["external_cashes"] = external_cashes
    return cash_registers + external_cashes

def get_cash_register_info(cash_path: str, is_external: bool = False) -> Dict:
    """
    Отримує детальну інформацію про касу за його шляхом.

    Args:
        cash_path (str): Шлях до директорії каси.
        is_external (bool): Чи є каса зовнішньою (не в profiles.json). За замовчуванням False.

    Returns:
        Dict: Словник із інформацією про касу (назва, шлях, стан здоров’я, статус транзакцій, зміни, версія, фіскальний номер, статус запуску).

    Raises:
        sqlite3.Error: Якщо не вдалося підключитися до бази даних або виконати запит.
        Exception: Інші помилки, пов’язані з читанням файлів або доступом до бази даних.
    """
    cash_path = os.path.normpath(os.path.abspath(cash_path))
    db_path = os.path.normpath(os.path.join(cash_path, "agent.db"))
    version = "Unknown"
    fiscal_number = "Unknown"
    health = "BAD"
    trans_status = "ERROR"
    shift_status = "OPENED"
    is_running = bool(find_process_by_path("checkbox_kasa.exe", cash_path))

    try:
        version_path = os.path.normpath(os.path.join(cash_path, "version"))
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
    except Exception:
        pass

    if os.path.exists(db_path):
        try:
            with sqlite_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                result = cursor.fetchone()
                if result and result[0]:
                    fiscal_number = result[0]
        except Error:
            pass

        for attempt in range(3):
            try:
                with sqlite_connection(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check;")
                    result = cursor.fetchone()[0]
                    if result == "ok":
                        health = "OK"
                        cursor.execute("SELECT status FROM transactions;")
                        statuses = [row[0] for row in cursor.fetchall()]
                        if not statuses:
                            trans_status = "EMPTY"
                        elif any(s == "ERROR" for s in statuses):
                            trans_status = "ERROR"
                        elif any(s == "PENDING" for s in statuses):
                            trans_status = "PENDING"
                        else:
                            trans_status = "DONE"

                        cursor.execute("SELECT status FROM shifts WHERE id = (SELECT MAX(id) FROM shifts);")
                        shift_result = cursor.fetchone()
                        if shift_result:
                            shift_status = shift_result[0].upper()
                        else:
                            shift_status = "CLOSED"
                    break
            except Error:
                time.sleep(2)

    name = f"[Ext] {os.path.basename(cash_path)}" if is_external else os.path.basename(cash_path)
    return {
        "name": name,
        "path": cash_path,
        "health": health,
        "trans_status": trans_status,
        "shift_status": shift_status,
        "version": version,
        "fiscal_number": fiscal_number,
        "is_running": is_running,
        "is_external": is_external
    }