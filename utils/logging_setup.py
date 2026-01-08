import logging
import logging.handlers
import os

def setup_logging():
    log_dir = "./logging"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file_path = os.path.join(log_dir, "app.log")

    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path, maxBytes=5*1024*1024, backupCount=3
    )

    console_handler = logging.StreamHandler()

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)