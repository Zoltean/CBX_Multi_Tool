# -*- coding: utf-8 -*-
import logging
import sys
import os

# Константа для включения записи логов в файл
LOG_TO_FILE = True

# Константа для включения вывода логов в консоль
CONSOLE_LOG_ENABLED = True  # Новая константа

# Константа для включения пауз после консольных логов
CONSOLE_LOG_WITH_PAUSE = False

# Глобальная переменная для проверки инициализации логгера
_logger_initialized = False

def setup_logging():
    """Настройка логирования."""
    global _logger_initialized
    if _logger_initialized:
        return logging.getLogger()

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    logger.handlers.clear()

    # Файловый обработчик
    if LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler("cbx.log", encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)
            logger.info("File logging enabled")
        except Exception as e:
            logger.error(f"Failed to setup file logging: {e}")

    # Консольный обработчик
    if CONSOLE_LOG_ENABLED:
        if CONSOLE_LOG_WITH_PAUSE:
            class PauseHandler(logging.StreamHandler):
                def emit(self, record):
                    super().emit(record)
                    input("Press any key to continue...")

            console_handler = PauseHandler()
            console_handler.setFormatter(formatter)
            console_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)
            logger.info("Console logging with pause enabled")
        else:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            console_handler.setStream(open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1))
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)
            logger.info("Console logging enabled")

    _logger_initialized = True
    return logger