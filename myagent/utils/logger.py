import logging
import os
from pathlib import Path
from datetime import datetime

# Define log file path
LOG_DIR = Path.home() / ".myagent"
LOG_FILE = LOG_DIR / "myagent_debug.log"

def setup_logger():
    """Configures the global logger to write to a file in the user's home directory."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Configure logging
    logger = logging.getLogger("myagent")
    logger.setLevel(logging.DEBUG)
    
    # Create file handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    
    # Create formatter: [TIMESTAMP] [LEVEL] [MODULE] - Message
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s] - %(message)s'
    )
    file_handler.setFormatter(formatter)
    
    # Add handler to logger
    if not logger.handlers:
        logger.addHandler(file_handler)
    
    return logger

# Initialize the global logger instance
log = setup_logger()

def log_error(msg: str, exc: Exception = None):
    """Convenience helper for logging errors with stack traces."""
    if exc:
        log.exception(f"{msg}: {str(exc)}")
    else:
        log.error(msg)
