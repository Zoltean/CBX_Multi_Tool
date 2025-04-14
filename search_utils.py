# -*- coding: utf-8 -*-
import os
import sqlite3
import time
import logging
from typing import Dict, List, Optional, Set, Tuple
import json
from contextlib import contextmanager
from sqlite3 import Error

import psutil
from utils import find_process_by_path

# Настройка логирования
#logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Глобальный кэш для хранения путей
_cache = {
    "manager_dir": None,
    "profile_cashes": [],
    "is_empty_profiles": False,
    "profile_seen_paths": set(),
    "cash_registers": [],
    "external_cashes": []
}

@contextmanager
def sqlite_connection(db_path: str):
    """Контекстный менеджер для безопасного подключения к SQLite."""
    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5, check_same_thread=False)
        yield conn
    except Error as e:
        logging.error(f"SQLite error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            time.sleep(0.1)

def reset_cache():
    """Сбрасывает кэш для повторного сканирования."""
    global _cache
    _cache = {
        "manager_dir": None,
        "profile_cashes": [],
        "is_empty_profiles": False,
        "profile_seen_paths": set(),
        "cash_registers": [],
        "external_cashes": []
    }
    logging.info("Cache reset")

def find_manager_by_exe(drives: list, max_depth: int = 3, use_cache: bool = True) -> Optional[str]:
    """
    Ищет kasa_manager.exe сначала в запущенных процессах, затем в файловой системе.
    Возвращает путь к папке, где найден файл, или None, если не найден.
    """
    global _cache
    if use_cache and _cache["manager_dir"] is not None:
        logging.debug("Returning manager_dir from cache")
        return _cache["manager_dir"]

    logging.info("Checking running processes for kasa_manager.exe...")
    for proc in psutil.process_iter(['pid', 'exe']):
        try:
            if proc.name().lower() == "kasa_manager.exe":
                manager_path = os.path.normpath(os.path.abspath(os.path.dirname(proc.exe())))
                logging.info(f"Found kasa_manager.exe in processes: {manager_path}")
                _cache["manager_dir"] = manager_path
                return manager_path
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    logging.warning("No kasa_manager.exe in processes, switching to filesystem search")

    drives = [os.path.normpath(os.path.abspath(drive)) for drive in drives]

    for drive in drives:
        logging.info(f"Scanning drive: {drive}")
        try:
            for root, dirs, files in os.walk(drive, topdown=True):
                root_normalized = os.path.normpath(os.path.abspath(root))
                if any(excluded in root_normalized.lower() for excluded in ["windows", "appdata", "programdata"]):
                    logging.debug(f"Skipping system folder: {root_normalized}")
                    dirs[:] = []
                    continue

                depth = len(os.path.relpath(root_normalized, drive).split(os.sep))
                logging.debug(f"Checking folder: {root_normalized} (depth: {depth})")

                if depth > max_depth:
                    logging.debug(f"Skipping {root_normalized} (exceeds max depth {max_depth})")
                    dirs[:] = []
                    continue

                if "kasa_manager.exe" in files:
                    manager_path = root_normalized
                    logging.info(f"Found kasa_manager.exe in filesystem: {manager_path}")
                    _cache["manager_dir"] = manager_path
                    return manager_path
                elif files:
                    logging.debug(f"Files in {root_normalized}: {', '.join(files)}")
                else:
                    logging.debug(f"No files in {root_normalized}")

        except PermissionError as e:
            logging.error(f"Permission denied for {root_normalized}: {e}")
            continue
        except OSError as e:
            logging.error(f"OS error for {root_normalized}: {e}")
            continue

    logging.error("kasa_manager.exe not found after scanning all drives")
    _cache["manager_dir"] = None
    return None

def find_cash_registers_by_profiles_json(manager_dir: str, use_cache: bool = True) -> Tuple[List[Dict], bool, Set[str]]:
    """
    Читает profiles.json для поиска касс.
    Возвращает список касс, флаг пустого файла и множество путей.
    """
    global _cache
    if use_cache and _cache["profile_cashes"]:
        logging.debug("Returning profile_cashes from cache")
        return _cache["profile_cashes"], _cache["is_empty_profiles"], _cache["profile_seen_paths"]

    manager_dir = os.path.normpath(os.path.abspath(manager_dir))
    profiles_json_path = os.path.normpath(os.path.join(manager_dir, "profiles.json"))
    cash_registers = []
    is_empty = False
    seen_paths = set()

    logging.info(f"Attempting to read profiles.json at {profiles_json_path}")

    if not os.path.exists(profiles_json_path):
        logging.warning(f"profiles.json not found at {profiles_json_path}")
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
            logging.warning("profiles.json is empty")
        else:
            for profile_id, profile in profiles.items():
                exec_path = profile.get("local", {}).get("paths", {}).get("exec_path", "")
                if exec_path:
                    exec_path_normalized = os.path.normpath(os.path.abspath(exec_path))
                    cash_registers.append({
                        "path": exec_path_normalized,
                        "source": "profiles_json"
                    })
                    seen_paths.add(exec_path_normalized)
                    logging.info(f"Found cash register in profiles.json: {exec_path_normalized}")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse profiles.json: {e}")
    except Exception as e:
        logging.error(f"Unexpected error reading profiles.json: {e}")

    _cache["profile_cashes"] = cash_registers
    _cache["is_empty_profiles"] = is_empty
    _cache["profile_seen_paths"] = seen_paths
    return cash_registers, is_empty, seen_paths

def find_cash_registers_by_exe(manager_dir: Optional[str], drives: List[str], max_depth: int = 4, use_cache: bool = True) -> List[Dict]:
    """
    Ищет checkbox_kasa.exe сначала в запущенных процессах, затем в файловой системе.
    Если manager_dir задан, ищет в этой папке с глубиной max_depth.
    Если manager_dir не задан, ищет по всем дискам из drives с глубиной max_depth.
    Возвращает список словарей с путями к кассам.
    """
    global _cache
    if use_cache and (_cache["cash_registers"] or _cache["external_cashes"]):
        logging.debug("Returning cash_registers and external_cashes from cache")
        return _cache["cash_registers"] + _cache["external_cashes"]

    cash_registers = []
    external_cashes = []
    seen_paths = set(_cache["profile_seen_paths"])  # Учитываем пути из profiles.json
    manager_dir_normalized = os.path.normpath(os.path.abspath(manager_dir)) if manager_dir else None

    logging.info("Checking running processes for checkbox_kasa.exe...")
    for proc in psutil.process_iter(['pid', 'exe', 'cwd']):
        try:
            if proc.name().lower() == "checkbox_kasa.exe":
                cash_dir = os.path.normpath(os.path.abspath(proc.cwd()))
                # Пропускаем, если путь совпадает с папкой менеджера
                if manager_dir_normalized and cash_dir == manager_dir_normalized:
                    logging.debug(f"Skipping cash_dir {cash_dir} as it matches manager_dir")
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
                    logging.info(f"Found checkbox_kasa.exe in processes: {cash_dir} (external={cash_dir not in _cache['profile_seen_paths']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if cash_registers or external_cashes:
        logging.info("Cash registers found in processes, skipping filesystem search")
        _cache["cash_registers"] = cash_registers
        _cache["external_cashes"] = external_cashes
        return cash_registers + external_cashes

    search_dirs = [manager_dir] if manager_dir else drives
    search_dirs = [os.path.normpath(os.path.abspath(d)) for d in search_dirs]

    for search_dir in search_dirs:
        logging.info(f"Scanning directory for checkbox_kasa.exe: {search_dir}")
        try:
            for root, dirs, files in os.walk(search_dir, topdown=True):
                root_normalized = os.path.normpath(os.path.abspath(root))
                if any(excluded in root_normalized.lower() for excluded in ["windows", "appdata", "programdata"]):
                    logging.debug(f"Skipping system folder: {root_normalized}")
                    dirs[:] = []
                    continue

                depth = len(os.path.relpath(root_normalized, search_dir).split(os.sep))
                logging.debug(f"Checking folder: {root_normalized} (depth: {depth})")

                if depth > max_depth:
                    logging.debug(f"Skipping {root_normalized} (exceeds max depth {max_depth})")
                    dirs[:] = []
                    continue

                if "checkbox_kasa.exe" in files:
                    cash_dir = root_normalized
                    # Пропускаем, если путь совпадает с папкой менеджера
                    if manager_dir_normalized and cash_dir == manager_dir_normalized:
                        logging.debug(f"Skipping cash_dir {cash_dir} as it matches manager_dir")
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
                        logging.info(f"Found checkbox_kasa.exe in filesystem: {cash_dir} (external={cash_dir not in _cache['profile_seen_paths']})")
                elif files:
                    logging.debug(f"Files in {root_normalized}: {', '.join(files)}")
                else:
                    logging.debug(f"No files in {root_normalized}")

        except PermissionError as e:
            logging.error(f"Permission denied for {root_normalized}: {e}")
            continue
        except OSError as e:
            logging.error(f"OS error for {root_normalized}: {e}")
            continue

    if not (cash_registers or external_cashes):
        logging.error("checkbox_kasa.exe not found after scanning")

    _cache["cash_registers"] = cash_registers
    _cache["external_cashes"] = external_cashes
    return cash_registers + external_cashes

def get_cash_register_info(cash_path: str, is_external: bool = False) -> Dict:
    """
    Получает информацию о кассе по её пути.
    """
    cash_path = os.path.normpath(os.path.abspath(cash_path))
    db_path = os.path.normpath(os.path.join(cash_path, "agent.db"))
    version = "Unknown"
    fiscal_number = "Unknown"
    health = "BAD"
    trans_status = "ERROR"
    shift_status = "OPENED"
    is_running = bool(find_process_by_path("checkbox_kasa.exe", cash_path))

    logging.info(f"Retrieving info for cash register at {cash_path} (is_external={is_external})")
    try:
        version_path = os.path.normpath(os.path.join(cash_path, "version"))
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
                logging.debug(f"Version found: {version}")
        else:
            logging.debug(f"No version file found at {version_path}")
    except Exception as e:
        logging.error(f"Error reading version file at {version_path}: {e}")

    if os.path.exists(db_path):
        try:
            with sqlite_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT fiscal_number FROM cash_register LIMIT 1;")
                result = cursor.fetchone()
                if result and result[0]:
                    fiscal_number = result[0]
                    logging.debug(f"Fiscal number found: {fiscal_number}")
                else:
                    logging.debug(f"No fiscal number found in {db_path}")
        except Error as e:
            logging.error(f"Error querying fiscal number from {db_path}: {e}")

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
                        logging.debug(f"Health: {health}, Transactions: {trans_status}, Shift: {shift_status}")
                    break
            except Error as e:
                logging.error(f"Attempt {attempt + 1} failed for {db_path}: {e}")
                time.sleep(2)
                if attempt == 2:
                    logging.error(f"All attempts to query database {db_path} failed")
    else:
        logging.debug(f"No database found at {db_path}")

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