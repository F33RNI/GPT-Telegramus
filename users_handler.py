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
import os
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

    def read_database(self) -> List[Dict] or None:
        """Tries to read and parse database

        Returns:
            List[Dict] or None: list of users or None in case of error
        """
        try:
            database_file = self.config.get("files").get("users_database")

            # Create empty file
            if not os.path.exists(database_file):
                logging.info(f"Creating database file {database_file}")
                with self._lock:
                    with open(database_file, "w+", encoding="utf-8") as file_:
                        json.dump([], file_, ensure_ascii=False, indent=4)

            # Read and parse
            logging.info(f"Reading users database from {database_file}")
            with self._lock:
                with open(database_file, "r", encoding="utf-8") as file_:
                    database = json.loads(file_.read())
            return database
        except Exception as e:
            logging.error("Error reading users database", exc_info=e)
        return None

    def get_user(self, id_: int) -> Dict or None:
        """Tries to find user in database

        Args:
            id_ (int): ID of user to find

        Returns:
            Dict or None: user's data as dictionary as is (without replacing any keys) or None if not found
        """
        try:
            # Read database
            database = self.read_database()
            if database is None:
                return None

            # Find user
            user = None
            for user_ in database:
                if user_["user_id"] == id_:
                    user = user_
                    break

            # Check if we found them
            if user:
                return user

            # No user
            else:
                logging.warning(f"No user {id_}")
                return None

        except Exception as e:
            logging.error(f"Error finding user {id_} in database", exc_info=e)
        return None

    def get_key(self, id_: int, key: str, default_value: Any = None, user: Dict or None = None) -> Any:
        """Tries to read key value of user and handles previous formats (legacy)
        It's possible to use pre-loaded dictionary as user argument (ex. from get_user() function)
        If user argument is specified, id_ argument doesn't matter

        Args:
            id_ (int): ID of user
            key (str): target key
            default_value (Any, optional): fallback value. Defaults to None
            user (Dict or None, optional): None to load from file, or Dict to use pre-loaded one. Defaults to None

        Returns:
            Any: key's value or default_value
        """
        # Find user
        if user is None:
            user = self.get_user(id_)

        # Check
        if user is None:
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
                if lang_index is None:
                    return default_value
                if lang_index == 0:
                    return "eng"
                if lang_index == 1:
                    return "rus"
                if lang_index == 2:
                    return "tof"
                if lang_index == 3:
                    return "ind"
                if lang_index == 4:
                    return "zho"
                if lang_index == 5:
                    return "bel"
                if lang_index == 6:
                    return "ukr"
                if lang_index == 7:
                    return "fas"
                if lang_index == 8:
                    return "spa"
                return default_value

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
                    return "lmao_chatgpt"
                if module == 1:
                    return "dalle"
                if module == 2:
                    return "ms_copilot"
                if module == 3:
                    return "gemini"
                if module == 4:
                    return "ms_copilot_image_creator"
                if module == 5:
                    return "gemini"
                return self.config.get("modules").get("default", default_value)

            return default_value if module is None else module

        ####################
        # MS Copilot style #
        ####################
        elif key == "ms_copilot_style":
            # Try current format
            ms_copilot_style = user.get("ms_copilot_style")

            # Old format
            if ms_copilot_style is None and format_version is None:
                edgegpt_style = user.get("edgegpt_style")
                if edgegpt_style is None:
                    return default_value
                if edgegpt_style == 0:
                    return "precise"
                if edgegpt_style == 1:
                    return "balanced"
                if edgegpt_style == 2:
                    return "creative"
                return default_value

            return default_value if ms_copilot_style is None else ms_copilot_style

        # Return key value or default value
        return user.get(key, default_value)

    def set_key(self, id_: int, key: str, value: Any) -> None:
        """Sets key's value of user and saves it to database or creates a new user

        Args:
            id_ (int): ID of user
            key (str): key to set
            value (Any): value of the key
        """
        try:
            # Read database
            database = self.read_database()
            if database is None:
                return

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
                database_file = self.config.get("files").get("users_database")
                logging.info(f"Saving users database to {database_file}")
                with self._lock:
                    with open(database_file, "w+", encoding="utf-8") as file_:
                        json.dump(database, file_, ensure_ascii=False, indent=4)

            # No user -> create a new one
            else:
                self.create_user(id_, key_values=[(key, value)])

        except Exception as e:
            logging.error(f"Error setting value of key {key} for user {id_}", exc_info=e)

    def read_request_image(self, id_: int, user: Dict or None = None) -> bytes or None:
        """Tries to load user's last request image

        Args:
            id_ (int): ID of user
            user (Dict or None, optional): None to load from file, or Dict to use pre-loaded one. Defaults to None

        Returns:
            bytes or None: image as bytes or None if not exists / error
        """
        # Find user
        if user is None:
            user = self.get_user(id_)
        if user is None:
            return None

        # Try to get image path
        request_last_image = user.get("request_last_image")

        # No image
        if request_last_image is None or not os.path.exists(request_last_image):
            return None

        # Read
        try:
            logging.info(f"Reading user's last request image from {request_last_image}")
            image_bytes = None
            with open(request_last_image, "rb") as file:
                image_bytes = file.read()
            return image_bytes
        except Exception as e:
            logging.error("Error retrieving user's last request image", exc_info=e)

        return None

    def save_request_image(self, id_: int, image_bytes: bytes or None) -> None:
        """Saves user's last request image into file and it's path into users database

        Args:
            id_ (int): ID of user
            image_bytes (bytes or None): image to save as bytes or None to delete existing one
        """
        try:
            # Read database
            database = self.read_database()
            if database is None:
                return

            # Find user
            user_index = -1
            for i, user_ in enumerate(database):
                if user_["user_id"] == id_:
                    user_index = i
                    break

            # Create directories if not exists
            user_images_dir = self.config.get("files").get("user_images_dir")
            if not os.path.exists(user_images_dir):
                logging.info(f"Creating {user_images_dir} directory")
                os.makedirs(user_images_dir)

            request_last_image = os.path.join(user_images_dir, str(id_))

            # Save image
            if request_last_image is not None:
                logging.info(f"Saving user's last request image to {request_last_image}")
                with open(request_last_image, "wb+") as file:
                    file.write(image_bytes)

            # Delete if exists
            else:
                if os.path.exists(request_last_image):
                    logging.info(f"Deleting user's last request image {request_last_image}")
                    os.remove(request_last_image)
                request_last_image = None

            # User exists
            if user_index != -1:
                # Set the key
                database[user_index]["request_last_image"] = request_last_image

                # Save database
                database_file = self.config.get("files").get("users_database")
                logging.info(f"Saving users database to {database_file}")
                with self._lock:
                    with open(database_file, "w+", encoding="utf-8") as file_:
                        json.dump(database, file_, ensure_ascii=False, indent=4)

            # No user -> create a new one
            else:
                self.create_user(id_, key_values=[("request_last_image", request_last_image)])

        except Exception as e:
            logging.error("Error saving user's last request image", exc_info=e)

    def create_user(self, id_: int, key_values: List[Tuple[str, Any]] or None = None) -> Dict or None:
        """Creates a new user with default data and saves it to the database

        Args:
            id_ (int): ID of new user
            key_values (List[Tuple[str, Any]]orNone, optional): list of (key, value) to set to a new user

        Returns:
            Dict or None: user's dictionary or None in case of error
        """
        try:
            # Create a new user with default params
            logging.info(f"Creating a new user {id_}")
            telegram_config = self.config.get("telegram")
            user = {
                "format_version": version_major(),
                "user_id": id_,
                "user_name": DEFAULT_USER_NAME,
                "admin": True if id_ in telegram_config.get("admin_ids") else False,
                "banned": (
                    False if id_ in telegram_config.get("admin_ids") else telegram_config.get("ban_by_default")
                ),
                "module": self.config.get("modules").get("default"),
                "requests_total": 0,
            }

            # Set additional keys
            if key_values is not None:
                for key, value in key_values:
                    user[key] = value

            # Read database
            database = self.read_database()
            if database is None:
                return None

            # Check if user exists
            for user_ in database:
                if user_["user_id"] == id_:
                    raise Exception("User already exists")

            # Append
            database.append(user)

            # Save database
            database_file = self.config.get("files").get("users_database")
            logging.info(f"Saving users database to {database_file}")
            with self._lock:
                with open(database_file, "w+", encoding="utf-8") as file_:
                    json.dump(database, file_, ensure_ascii=False, indent=4)

            # Done -> return created user
            return user

        except Exception as e:
            logging.error(f"Error creating user {id_}", exc_info=e)
        return None
