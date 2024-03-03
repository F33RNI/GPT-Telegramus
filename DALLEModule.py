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
from typing import List, Dict

import openai

import BotHandler
import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class DALLEModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

    def initialize(self, proxy=None) -> None:
        """
        Initializes DALL-E official API
        :return:
        """
        self._enabled = False

        try:
            # Use manual proxy
            if not proxy and self.config["dalle"]["proxy"] and self.config["dalle"]["proxy"] != "auto":
                proxy = self.config["dalle"]["proxy"]

            # Log
            logging.info("Initializing DALL-E module with proxy {}".format(proxy))

            # Set enabled status
            self._enabled = self.config["modules"]["dalle"]
            if not self._enabled:
                logging.warning("DALL-E module disabled in config file!")
                raise Exception("DALL-E module disabled in config file!")

            # Set Key
            openai.api_key = self.config["dalle"]["open_ai_api_key"]

            # Set proxy
            if proxy:
                openai.proxy = proxy

            # Done?
            logging.info("DALL-E module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to DALL-E
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)

        # Check if we are initialized
        if not self._enabled:
            logging.error("DALL-E module not initialized!")
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                .format("DALL-E module not initialized!")
            request_response.error = True
            return

        try:
            # Set Key
            openai.api_key = self.config["dalle"]["open_ai_api_key"]

            # Generate image
            logging.info("Requesting image from DALL-E")
            image_response = openai.Image.create(prompt=request_response.request,
                                                 n=1,
                                                 size=self.config["dalle"]["image_size"])
            response_url = image_response["data"][0]["url"]

            # Check response
            if not response_url or len(response_url) < 1:
                raise Exception("Wrong DALL-E response!")

            # OK?
            logging.info("Response successfully processed for user {0} ({1})"
                         .format(request_response.user["user_name"], request_response.user["user_id"]))
            request_response.response = response_url

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # DALL-E or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True

        # Finish message
        BotHandler.async_helper(BotHandler.send_message_async(self.config, self.messages, request_response, end=True))
