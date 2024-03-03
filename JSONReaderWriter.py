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


def load_json(file_name: str, logging_enabled=True):
    """
    Loads json from file_name
    :param file_name: filename to load
    :param logging_enabled: set True to have logs
    :return: json if loaded or None if not
    """
    try:
        if os.path.exists(file_name):
            if logging_enabled:
                logging.info("Loading {0}".format(file_name))

            messages_file = open(file_name, encoding="utf-8")
            json_content = json.load(messages_file)
            messages_file.close()

            if json_content is not None:
                if logging_enabled:
                    logging.info("Loaded json from {0}".format(file_name))
            else:
                if logging_enabled:
                    logging.error("Error loading json data from file {0}".format(file_name))
                return None
        else:
            if logging_enabled:
                logging.warning("No {0} file! Returning empty json".format(file_name))
            return None

    except Exception as e:
        if logging_enabled:
            logging.error("Error loading json data from file {0}".format(file_name), exc_info=e)
        return None

    return json_content


def save_json(file_name: str, content, logging_enabled=True):
    """
    Saves
    :param file_name: filename to save
    :param content: JSON dictionary
    :param logging_enabled: set True to have logs
    :return:
    """
    if logging_enabled:
        logging.info("Saving to {0}".format(file_name))
    file = open(file_name, "w")
    json.dump(content, file, indent=4)
    file.close()
