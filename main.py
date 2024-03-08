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
import json
import logging
import multiprocessing
import os
import sys
from typing import Dict


from _version import __version__
import logging_handler
import messages
import users_handler
import queue_handler
import bot_handler
import module_wrapper_global

# Default config file
CONFIG_FILE = "config.json"
CONFIG_COMPATIBLE_VERSIONS = [5]


def load_and_parse_config(config_file: str) -> Dict:
    """Loads and parses config from main file and from module's config files
    This is separate because of /restart command

    Args:
        config_file (str): path to main config file

    Raises:
        Exception: loading / parsing / version error

    Returns:
        Dict: loaded and parsed config
    """
    logging.info(f"Loading config file {config_file}")
    with open(config_file, "r", encoding="utf-8") as file:
        config = json.loads(file.read())

    # Check config version
    config_version = config.get("config_version")
    if config_version is None:
        raise Exception("No config_version key! Please update your config file")
    if not config_version in CONFIG_COMPATIBLE_VERSIONS:
        raise Exception(
            f"Your config version ({config_version}) is not compatible! "
            f"Compatible versions: {', '.join(str(version) for version in CONFIG_COMPATIBLE_VERSIONS)}"
        )

    # List of enabled modules
    enabled_modules = config.get("modules").get("enabled")
    if len(enabled_modules) == 0:
        raise Exception("No modules enabled")
    logging.info(f"Enabled modules: {', '.join(enabled_modules)}")

    # Load config of enabled modules and merge it into global config
    module_configs_dir = config.get("files").get("module_configs_dir")
    logging.info(f"Parsing {module_configs_dir} directory")
    for file in os.listdir(module_configs_dir):
        # Parse only .json files
        if file.lower().endswith(".json"):
            # Check if need to load it
            module_name_from_file = os.path.splitext(os.path.basename(file))[0]
            if module_name_from_file not in enabled_modules:
                continue

            # Parse and merge
            logging.info(f"Adding config of {module_name_from_file} module")
            with open(os.path.join(module_configs_dir, file), "r", encoding="utf-8") as file_:
                module_config = json.loads(file_.read())
            config[module_name_from_file] = module_config

    return config


def parse_args() -> argparse.Namespace:
    """Parses cli arguments

    Returns:
        argparse.Namespace: parsed arguments
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default=os.getenv("TELEGRAMUS_CONFIG_FILE", CONFIG_FILE),
        required=False,
        help=f"path to config.json file (Default: {os.getenv('TELEGRAMUS_CONFIG_FILE', CONFIG_FILE)})",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    return parser.parse_args()


def main():
    """Main entry"""
    # Multiprocessing fix for Windows
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()

    # Parse arguments
    args = parse_args()

    # Initialize logging and start logging listener as process
    logging_handler_ = logging_handler.LoggingHandler()
    logging_handler_process = multiprocessing.Process(target=logging_handler_.configure_and_start_listener)
    logging_handler_process.start()
    logging_handler.worker_configurer(logging_handler_.queue, log_test_message=False)

    # Log software version and GitHub link
    logging.info(f"GPT-Telegramus version: {__version__}")
    logging.info("https://github.com/F33RNI/GPT-Telegramus")

    modules = {}

    # Catch errors during initialization process
    initialization_ok = False
    try:
        # Load config
        config = multiprocessing.Manager().dict(load_and_parse_config(args.config))

        # Create conversations and user images dirs (it's not necessary but just in case)
        conversations_dir = config.get("files").get("conversations_dir")
        if not os.path.exists(conversations_dir):
            logging.info(f"Creating {conversations_dir} directory")
            os.makedirs(conversations_dir)
        user_images_dir = config.get("files").get("user_images_dir")
        if not os.path.exists(user_images_dir):
            logging.info(f"Creating {user_images_dir} directory")
            os.makedirs(user_images_dir)

        # Initialize users and messages handlers
        users_handler_ = users_handler.UsersHandler(config)
        messages_ = messages.Messages(users_handler_)

        # Load messages
        messages_.langs_load(config.get("files").get("messages_dir"))

        # modules = {} is a dictionary of ModuleWrapperGlobal (each enabled module)
        # {
        #   "module_name": ModuleWrapperGlobal,
        #   ...
        # }
        for module_name in config.get("modules").get("enabled"):
            logging.info(f"Trying to load and initialize {module_name} module")
            try:
                module = module_wrapper_global.ModuleWrapperGlobal(
                    module_name, config, messages_, users_handler_, logging_handler_.queue
                )
                modules[module_name] = module
            except Exception as e:
                logging.error(f"Error initializing {module_name} module: {e} Module will be ignored")

        # Initialize main classes
        queue_handler_ = queue_handler.QueueHandler(
            config, messages_, users_handler_, logging_handler_.queue, None, modules
        )
        bot_handler_ = bot_handler.BotHandler(
            config, args.config, messages_, users_handler_, logging_handler_.queue, queue_handler_, modules
        )
        queue_handler_.prevent_shutdown_flag = bot_handler_.prevent_shutdown_flag

        # At least, initialization did not raised any error
        initialization_ok = True
    except Exception as e:
        logging.error("Initialization error", exc_info=e)

    # Finally, start queue handler and bot polling (blocking)
    if initialization_ok:
        queue_handler_.start_processing_loop()
        bot_handler_.start_bot()

    # Stop queue handler
    queue_handler_.stop_processing_loop()

    # Close (stop) each module
    for module_name, module in modules.items():
        logging.info(f"Trying to close and unload {module_name} module")
        try:
            module.on_exit()
        except Exception as e:
            logging.error(f"Error closing {module_name} module", exc_info=e)

    # Finally, stop logging loop
    logging.info("GPT-Telegramus exited")
    logging_handler_.queue.put(None)


if __name__ == "__main__":
    main()
