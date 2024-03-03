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

import json
import logging
import os
from multiprocessing import Manager
from typing import Any

from users_handler import UsersHandler

# Required language file keys
_LANG_FILE_KEYS = [
    "language_name",
    "language_icon",
    "language_select_error",
    "language_select",
    "language_changed",
    "start_message",
    "help_message",
    "help_message_admin",
    "empty_request_module_changed",
    "media_group_response",
    "permissions_deny",
    "queue_overflow",
    "queue_empty",
    "queue_accepted",
    "response_error",
    "empty_message",
    "regenerate_error_not_last",
    "regenerate_error_empty",
    "continue_error_not_last",
    "stop_error_not_last",
    "stop_error",
    "edgegpt_sources",
    "users_admin",
    "restarting",
    "restarting_done",
    "chat_cleared",
    "clear_error",
    "clear_select_module",
    "module_select_module",
    "user_cooldown_error",
    "hours",
    "minutes",
    "seconds",
    "ban_message_admin",
    "ban_no_user_id",
    "ban_message_user",
    "ban_reason_default",
    "unban_message_admin",
    "broadcast_no_message",
    "broadcast",
    "broadcast_initiated",
    "broadcast_done",
    "style_changed",
    "style_change_error",
    "style_select",
    "style_precise",
    "style_balanced",
    "style_creative",
    "button_stop_generating",
    "button_continue",
    "button_regenerate",
    "button_clear",
    "button_module",
    "button_style_change",
    "modules",
    "module_icons",
]


class Messages:
    def __init__(self, users_handler: UsersHandler) -> None:
        self.users_handler = users_handler

        self._manager = Manager()
        self._langs = self._manager.dict()

    def langs_load(self, langs_dir: str) -> None:
        """Loads and parses languages from json files into multiprocessing dictionary

        Args:
            langs_dir (str): path to directory with language files

        Raises:
            Exception: file read error / parse error / no keys
        """
        logging.info(f"Parsing {langs_dir} directory")
        for file in os.listdir(langs_dir):
            # Parse only .json files
            if file.lower().endswith(".json"):
                # Read file
                lang_id = os.path.splitext(os.path.basename(file))[0]
                logging.info(f"Loading file {file} as language with ID {lang_id}")
                file_path = os.path.join(langs_dir, file)
                with open(file_path, "r", encoding="utf-8") as file_:
                    lang_dict = json.loads(file_.read())

                # Check keys (just a basic file validation)
                keys = lang_dict.keys()
                for key in _LANG_FILE_KEYS:
                    if key not in keys:
                        raise Exception(f"No {key} key in {file} language file")

                # Append to loaded languages
                self._langs[lang_id] = lang_dict

        # Print final number of languages
        logging.info(f"Loaded {len(self._langs)} languages")

    def message_get(
        self,
        message_key: str,
        lang_id: str or None = None,
        user_id: str or None = None,
        default_value: Any = None,
    ) -> Any:
        """Retrieves message from language

        Args:
            message_key (str): key from lang file
            lang_id (str or None, optional): ID of language or None to retrieve from user. Defaults to None.
            user_id (str or None, optional): ID of user to retrieve lang_id. Defaults to None.
            default_value (Any, optional): fallback value in case of no message_key. Defaults to None.

        Returns:
            Any: values of message_key or default_value
        """
        # Retrieve lang_id from user
        if lang_id is None and user_id is not None:
            lang_id = self.users_handler.get_key(user_id, "user_id", "eng")

        # Fallback to English
        elif lang_id is None and user_id is None:
            lang_id = "eng"

        # Get messages
        messages = self._langs.get(lang_id)

        # Check if lang_id exists and fallback to English
        if messages is None:
            logging.warning(f"No language with ID {lang_id}")
            messages = self._langs.get("eng")

        return messages.get(message_key, default_value)
