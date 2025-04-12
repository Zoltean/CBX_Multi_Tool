# -*- coding: utf-8 -*-
import logging
import sys

import requests
from datetime import datetime
import platform
import psutil

from config import VPS_CONFIG_URL

def fetch_config():
    temp_logger = logging.getLogger(__name__)
    temp_logger.setLevel(logging.INFO)
    temp_handler = logging.StreamHandler()
    temp_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    temp_logger.addHandler(temp_handler)

    temp_logger.info(f"Fetching config from {VPS_CONFIG_URL}")
    try:
        response = requests.get(VPS_CONFIG_URL, timeout=5)
        response.raise_for_status()
        config = response.json()
        temp_logger.info(f"Config fetched: {config}")
        return config.get("LOG_TO_FILE", False)
    except requests.RequestException as e:
        temp_logger.error(f"Failed to fetch config: {e}. Using default: LOG_TO_FILE=False")
        return False
    finally:
        temp_logger.removeHandler(temp_handler)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    logger.handlers.clear()

    iteration_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    LOG_TO_FILE = fetch_config()

    system_info = []
    try:
        os_name = platform.system()
        os_version = platform.release()
        os_build = platform.version()
        system_info.append(f"Operating System: {os_name} {os_version} (Build {os_build})")
        cpu_info = platform.processor() or "Unknown CPU"
        cpu_cores = psutil.cpu_count(logical=False) or "?"
        cpu_threads = psutil.cpu_count(logical=True) or "?"
        system_info.append(f"Processor: {cpu_info}, {cpu_cores} cores, {cpu_threads} threads")
        ram = psutil.virtual_memory()
        total_ram = ram.total / (1024 ** 3)
        system_info.append(f"RAM: {total_ram:.2f} GB total")
    except Exception as e:
        system_info.append(f"Failed to gather system info: {str(e)}")

    # Консольный обработчик с utf-8
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
    logger.addHandler(console_handler)

    if LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler("cbx.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            logger.info("Logging to file 'cbx.log' enabled")
        except Exception as e:
            logger.error(f"Failed to setup file logging: {e}")

    logger.info("System Information:")
    for info_line in system_info:
        logger.info(info_line)