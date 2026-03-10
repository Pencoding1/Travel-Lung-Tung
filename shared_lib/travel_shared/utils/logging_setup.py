import logging
import logging.handlers
from pathlib import Path

def setup_logging(service_name: str, log_dir: Path):
    """
    Standardizes logging across all microservices.
    """
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = log_dir / f"{service_name}.log"

    # 1. File Handler (Rotating)
    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=5*1024*1024, backupCount=3
    )

    # 2. Console Handler
    console_handler = logging.StreamHandler()

    # 3. Formatting
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 4. Root Logger Setup
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Avoid adding handlers multiple times if the function is called twice
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    return logging.getLogger(service_name)