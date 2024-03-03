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
import os.path
from typing import Dict, List


def load_json(file_name: str, logging_enabled=True) -> Dict or List or None:
    """Loads json from file_name

    Args:
        file_name (str): filename to load
        logging_enabled (bool, optional): set True to print logs. Defaults to True.

    Returns:
        Dict or List or None: json if loaded or None if not
    """
    try:
        if os.path.exists(file_name):
            if logging_enabled:
                logging.info(f"Loading {file_name}")

            with open(file_name, "r", encoding="utf-8") as file:
                json_content = json.load(file)

            if json_content is not None:
                if logging_enabled:
                    logging.info(f"Loaded json from {file_name}")
            else:
                if logging_enabled:
                    logging.error(f"Error loading json data from file {file_name}")
                return None
        else:
            if logging_enabled:
                logging.warning(f"No {file_name} file! Returning empty json")
            return None

    except Exception as e:
        if logging_enabled:
            logging.error(f"Error loading json data from file {file_name}", exc_info=e)
        return None

    return json_content


def save_json(file_name: str, content, logging_enabled=True):
    """Saves json file

    Args:
        file_name (str): filename to save
        content (Dict or List): JSON content
        logging_enabled (bool, optional): set True to print logs. Defaults to True.
    """
    if logging_enabled:
        logging.info(f"Saving to {file_name}")
    with open(file_name, "w", encoding="utf-8") as file:
        json.dump(content, file, indent=4, ensure_ascii=False)
