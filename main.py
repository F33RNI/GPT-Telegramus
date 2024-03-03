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

import argparse
import logging
import multiprocessing
import os
import sys

from _version import __version__
import BingImageGenModule
import BotHandler
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import GoogleAIModule
import LoggingHandler
import ProxyAutomation
import QueueHandler
import users_handler
from JSONReaderWriter import load_json

# Logging level
LOGGING_LEVEL = logging.INFO

# Default config file
CONFIG_FILE = "config.json"


def parse_args():
    """
    Parses cli arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        help="config.json file location",
        default=os.getenv("TELEGRAMUS_CONFIG_FILE", CONFIG_FILE),
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args()


def main():
    """
    Main entry
    :return:
    """
    # Multiprocessing fix for Windows
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()

    # Parse arguments
    args = parse_args()

    # Initialize logging and start listener as process
    logging_handler = LoggingHandler.LoggingHandler()
    logging_handler_process = multiprocessing.Process(target=logging_handler.configure_and_start_listener)
    logging_handler_process.start()
    LoggingHandler.worker_configurer(logging_handler.queue)
    logging.info(f"LoggingHandler PID: {logging_handler_process.pid}")

    # Log software version and GitHub link
    logging.info(f"GPT-Telegramus version: {__version__}")
    logging.info("https://github.com/F33RNI/GPT-Telegramus")

    # Load config with multiprocessing support
    config = multiprocessing.Manager().dict(load_json(args.config))

    # Load messages from json file with multiprocessing support
    messages = multiprocessing.Manager().list(load_json(config["files"]["messages_file"]))

    # Check and create conversations directory
    if not os.path.exists(config["files"]["conversations_dir"]):
        logging.info(f"Creating directory: {config['files']['conversations_dir']}")
        os.makedirs(config["files"]["conversations_dir"])

    # Initialize UsersHandler and ProxyAutomation classes
    user_handler = users_handler.UsersHandler(config, messages)
    proxy_automation = ProxyAutomation.ProxyAutomation(config)

    # Pre-initialize modules
    chatgpt_module = ChatGPTModule.ChatGPTModule(config, messages, user_handler)
    dalle_module = DALLEModule.DALLEModule(config, messages, user_handler)
    edgegpt_module = EdgeGPTModule.EdgeGPTModule(config, messages, user_handler)
    bing_image_gen_module = BingImageGenModule.BingImageGenModule(config, messages, user_handler)
    gemini_module = GoogleAIModule.GoogleAIModule(config, "gemini", messages, user_handler)

    # Initialize QueueHandler class
    queue_handler = QueueHandler.QueueHandler(
        config,
        messages,
        logging_handler.queue,
        user_handler,
        proxy_automation,
        chatgpt_module,
        dalle_module,
        edgegpt_module,
        bing_image_gen_module,
        gemini_module,
    )

    # Initialize Telegram bot class
    bot_handler = BotHandler.BotHandler(
        config,
        args.config,
        messages,
        user_handler,
        queue_handler,
        proxy_automation,
        logging_handler.queue,
        chatgpt_module,
        edgegpt_module,
        gemini_module,
    )

    # Start proxy automation
    proxy_automation.start_automation_loop()

    # Start processing loop in thread
    queue_handler.start_processing_loop()

    # Finally, start telegram bot in main thread
    bot_handler.start_bot()

    # If we're here, exit requested
    proxy_automation.stop_automation_loop()
    queue_handler.stop_processing_loop()
    logging.info("GPT-Telegramus exited successfully")

    # Finally, stop logging loop
    logging_handler.queue.put(None)


if __name__ == "__main__":
    main()
