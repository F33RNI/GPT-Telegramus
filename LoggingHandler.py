"""
Copyright (C) 2023-2024 Fern Lane

This file is part of the GPT-Telegramus distribution
(see <https://github.com/F33RNI/GPT-Telegramus>)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

import datetime
import logging
import logging.handlers
import multiprocessing
import os

# Logging level
LOGGING_LEVEL = logging.INFO

# Where to save log files
LOGS_DIR = "logs"

# Will ignore logs from python-telegram-bot that start with this message
TELEGRAM_LOGS_IGNORE_PREFIX = "HTTP Request: POST https://api.telegram.org/bot"


def worker_configurer(queue: multiprocessing.Queue):
    """
    Call this method in your process
    :param queue:
    :return:
    """
    # Setup queue handler
    queue_handler = logging.handlers.QueueHandler(queue)
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            root_logger.removeHandler(handler)
    root_logger.addHandler(queue_handler)
    root_logger.setLevel(logging.INFO)

    # Log test message
    logging.info("Logging setup is complete for current process")


class LoggingHandler:
    def __init__(self):
        # Logging queue
        self.queue = multiprocessing.Queue(-1)

    def configure_and_start_listener(self):
        """
        Initializes logging and starts listening. Send None to queue to stop it
        :return:
        """
        # Create logs directory is not exists
        if not os.path.exists(LOGS_DIR):
            os.makedirs(LOGS_DIR)

        # Create logs formatter
        log_formatter = logging.Formatter(
            "[%(asctime)s] [%(process)-8d] [%(levelname)-8s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Setup logging into file
        file_handler = logging.FileHandler(
            os.path.join(LOGS_DIR, datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".log"), encoding="utf-8"
        )
        file_handler.setFormatter(log_formatter)

        # Setup logging into console
        import sys

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)

        # Add all handlers and setup level
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.setLevel(LOGGING_LEVEL)

        # Start queue listener
        while True:
            try:
                # Get logging record
                record = self.queue.get()

                # Ignore python-telegram-bot logs
                if (
                    record is not None
                    and record.message
                    and str(record.message).startswith(TELEGRAM_LOGS_IGNORE_PREFIX)
                ):
                    continue

                # Send None to exit
                if record is None:
                    break

                # Handle current logging record
                logger = logging.getLogger(record.name)
                logger.handle(record)

            # Ignore Ctrl+C (call queue.put(None) to stop this listener)
            except KeyboardInterrupt:
                pass

            # Error! WHY???
            except Exception:
                import sys, traceback

                print("Logging error: ", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
