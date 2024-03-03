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
import multiprocessing
from typing import List, Dict

import JSONReaderWriter

DEFAULT_USER_NAME = "Noname"


def get_key_or_none(dictionary: dict, key, default_value=None):
    """
    Safely gets value of key from dictionary
    :param dictionary:
    :param key:
    :param default_value: default value if key not found
    :return: key value or default_value if not found
    """
    if key is None:
        return default_value

    if key in dictionary:
        if dictionary[key] is None:
            return default_value
        else:
            return dictionary[key]

    return default_value


class UsersHandler:
    def __init__(self, config: dict, messages: List[Dict]):
        self.config = config
        self.messages = messages

        self.lock = multiprocessing.Lock()

    def read_users(self) -> list:
        """
        Reads users data from database
        :return: users as list of dictionaries or [] if not found
        """
        with self.lock:
            users = JSONReaderWriter.load_json(self.config["files"]["users_database"])
            if users is None:
                return []
            return users

    def get_user_by_id(self, user_id: int) -> dict:
        """
        Returns user (or create new one) as dictionary from database using user_id
        :param user_id:
        :return: dictionary
        """
        users = self.read_users()
        for user in users:
            if user["user_id"] == user_id:
                return user

        # If we are here then user doesn't exist
        return self._create_user(user_id)

    def save_user(self, user_data: dict) -> None:
        """
        Saves user_data to database
        :param user_data:
        :return:
        """
        if user_data is None:
            return

        users = self.read_users()

        with self.lock:
            user_index = -1
            for i in range(len(users)):
                if users[i]["user_id"] == user_data["user_id"]:
                    user_index = i
                    break

            # User exists
            if user_index >= 0:
                new_keys = user_data.keys()
                for new_key in new_keys:
                    users[user_index][new_key] = user_data[new_key]

            # New user
            else:
                users.append(user_data)

            # Save to database
            JSONReaderWriter.save_json(self.config["files"]["users_database"], users)

    def _create_user(self, user_id: int) -> dict:
        """
        Creates and saves new user
        :return:
        """
        logging.info("Creating new user with id: {0}".format(user_id))
        user = {
            "user_id": user_id,
            "user_name": DEFAULT_USER_NAME,
            "user_type": "",
            "admin": True if user_id in self.config["telegram"]["admin_ids"] else False,
            "banned": False if user_id in self.config["telegram"]["admin_ids"] else self.config["telegram"]["ban_by_default"],
            "ban_reason": self.messages[0]["ban_reason_default"].replace("\\n", "\n"),
            "module": self.config["modules"]["default_module"],
            "requests_total": 0,
            "reply_message_id_last": -1
        }
        self.save_user(user)
        return user
