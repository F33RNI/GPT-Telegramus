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

import logging
import json
import multiprocessing
from typing import Any, Dict, List, Tuple

from _version import version_major

# Default name for new users
DEFAULT_USER_NAME = "-"


class UsersHandler:
    def __init__(self, config: Dict) -> None:
        self.config = config

        self._lock = multiprocessing.Lock()

    def get_user(self, id_: str) -> Dict or None:
        """Tries to find user in database

        Args:
            id_ (str): ID of user to find

        Returns:
            Dict or None: user's data as dictionary or None if not found
        """
        try:
            # Read database
            database_file = self.config["files"]["users_database"]
            logging.info(f"Reading users database from {database_file}")
            with self._lock:
                with open(database_file, "r", encoding="utf-8") as file_:
                    database = json.loads(file_.read())

            # Find user
            user = None
            for user_ in database:
                if user_["user_id"] == id_:
                    user = user_
                    break

            # Check if we found them
            if user:
                return user
            else:
                logging.warning(f"No user {id_}")
                return None

        except Exception as e:
            logging.error(f"Error finding user {id_} in database", exc_info=e)
        return None

    def get_key(self, id_: str, key: str, default_value: Any) -> Any:
        """Tries to read key value of user and handles previous formats (legacy)

        Args:
            id_ (str): ID of user
            key (str): target key
            default_value (Any): fallback value

        Returns:
            Any: key's value or default_value
        """
        # Find user
        user = self.get_user(id_)

        # Check
        if not user:
            return default_value

        # Get user's format version
        format_version = user.get("format_version")

        ############
        # Language #
        ############
        if key == "lang_id":
            # Try current format
            lang_id = user.get("lang_id")

            # Old format
            if lang_id is None and format_version is None:
                lang_index = user.get("lang")
                if lang_index == 0:
                    lang_id = "eng"
                elif lang_index == 1:
                    lang_id = "rus"
                elif lang_index == 2:
                    lang_id = "tof"
                elif lang_index == 3:
                    lang_id = "ind"
                elif lang_index == 4:
                    lang_id = "zho"
                elif lang_index == 5:
                    lang_id = "bel"
                elif lang_index == 6:
                    lang_id = "ukr"
                elif lang_index == 7:
                    lang_id = "fas"
                elif lang_index == 8:
                    lang_id = "spa"

            # Still None?
            return default_value if lang_id is None else lang_id

        ##########
        # Module #
        ##########
        elif key == "module":
            # Try current format
            module = user.get("module")

            # Old format
            if module is not None and isinstance(module, int):
                if module == 0:
                    module = "chatgpt"
                elif module == 1:
                    module = "dalle"
                elif lang_index == 2:
                    module = "copilot"
                elif lang_index == 3:
                    module = "bard"
                elif lang_index == 4:
                    module = "copilot_image_creator"
                elif lang_index == 5:
                    module = "gemini"
                else:
                    module = "chatgpt"

            return default_value if module is None else module

        # Return key value or default value
        return user.get(key, default_value)

    def set_key(self, id_: str, key: str, value: Any) -> None:
        """Sets key's value of user and saves it to database or creates a new user

        Args:
            id_ (str): ID of user
            key (str): key to set
            value (Any): value of the key
        """
        try:
            # Read database
            database_file = self.config["files"]["users_database"]
            logging.info(f"Reading users database from {database_file}")
            with self._lock:
                with open(database_file, "r", encoding="utf-8") as file_:
                    database = json.loads(file_.read())

            # Find user
            user_index = -1
            for i, user_ in enumerate(database):
                if user_["user_id"] == id_:
                    user_index = i
                    break

            # User exists
            if user_index != -1:
                # Set the key
                database[user_index][key] = value

                # Save database
                logging.info(f"Saving users database to {database_file}")
                with self._lock:
                    with open(database_file, "w+", encoding="utf-8") as file_:
                        json.dump(database, file_, ensure_ascii=False, indent=4)

            # No user -> create a new one
            else:
                self.create_user(id_, key_values=[(key, value)])

        except Exception as e:
            logging.error(f"Error setting value of key {key} for user {id_}", exc_info=e)

    def create_user(self, id_: str, key_values: List[Tuple[str, Any]] or None = None) -> Dict or None:
        """Creates a new user with default data and saves it to the database

        Args:
            id_ (str): ID of new user
            key_values (List[Tuple[str, Any]]orNone, optional): list of (key, value) to set to a new user

        Returns:
            Dict or None: user's dictionary or None in case of error
        """
        try:
            # Create a new user with default params
            logging.info(f"Creating a new user {id_}")
            user = {
                "user_id": id_,
                "user_name": DEFAULT_USER_NAME,
                "admin": True if id_ in self.config["telegram"]["admin_ids"] else False,
                "banned": (
                    False if id_ in self.config["telegram"]["admin_ids"] else self.config["telegram"]["ban_by_default"]
                ),
                "module": self.config["modules"]["default_module"],
                "requests_total": 0,
                "format_version": version_major(),
            }

            # Set additional keys
            if key_values is not None:
                for key, value in key_values:
                    user[key] = value

            # Read database
            database_file = self.config["files"]["users_database"]
            logging.info(f"Reading users database from {database_file}")
            with self._lock:
                with open(database_file, "r", encoding="utf-8") as file_:
                    database = json.loads(file_.read())

            # Check if user exists
            for user_ in database:
                if user_["user_id"] == id_:
                    raise Exception("User already exists")

            # Append
            database.append(user)

            # Save database
            logging.info(f"Saving users database to {database_file}")
            with self._lock:
                with open(database_file, "w+", encoding="utf-8") as file_:
                    json.dump(database, file_, ensure_ascii=False, indent=4)

            # Done -> return created user
            return user

        except Exception as e:
            logging.error(f"Error creating user {id_}", exc_info=e)
        return None
