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

import ctypes
import logging
import multiprocessing
from typing import List, Dict

from BingImageCreator import ImageGen

import BotHandler
import users_handler
from JSONReaderWriter import load_json
from RequestResponseContainer import RequestResponseContainer


class BingImageGenModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: users_handler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes Bing ImageGen API
        :return:
        """
        self._enabled = False
        self._image_generator = None

        self.processing_flag.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["bing_imagegen"]["proxy"] and self.config["bing_imagegen"]["proxy"] != "auto":
                proxy = self.config["bing_imagegen"]["proxy"]

            # Log
            logging.info(f"Initializing Bing ImageGen module with proxy {proxy}")

            # Set enabled status
            self._enabled = self.config["modules"]["bing_imagegen"]
            if not self._enabled:
                logging.warning("Bing ImageGen module disabled in config file!")
                raise Exception("Bing ImageGen module disabled in config file!")

            # Parse cookies
            auth_cookie = ""
            auth_cookie_SRCHHPGUSR = ""
            try:
                cookies = load_json(self.config["bing_imagegen"]["cookies_file"])
                if not cookies or len(cookies) < 1:
                    raise Exception("Error reading bing cookies!")
                for cookie in cookies:
                    if cookie["name"] == "_U":
                        auth_cookie = cookie["value"]
                    elif cookie["name"] == "SRCHHPGUSR":
                        auth_cookie_SRCHHPGUSR = cookie["value"]
                if not auth_cookie:
                    raise Exception("No _U cookie!")
                if not auth_cookie_SRCHHPGUSR:
                    raise Exception("No SRCHHPGUSR cookie!")
            except Exception as e:
                raise e

            # Initialize Bing ImageGen
            self._image_generator = ImageGen(
                auth_cookie=auth_cookie,
                auth_cookie_SRCHHPGUSR=auth_cookie_SRCHHPGUSR,
                quiet=True,
                all_cookies=cookies,
            )

            # Set proxy
            if proxy:
                self._image_generator.session.proxies = {"http": proxy, "https": proxy}

            # Check
            if self._image_generator is not None:
                logging.info("Bing ImageGen module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Bing ImageGen
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = request_response.user.get("lang", 0)

        # Check if we are initialized
        if not self._enabled:
            logging.error("Bing ImageGen module not initialized!")
            request_response.response = (
                self.messages[lang]["response_error"]
                .replace("\\n", "\n")
                .format("Bing ImageGen module not initialized!")
            )
            request_response.error = True
            return

        try:
            # Generate images
            logging.info("Requesting images from Bing ImageGen")
            response_urls = self._image_generator.get_images(request_response.request)

            # Check response
            if not response_urls or len(response_urls) < 1:
                raise Exception("Wrong Bing ImageGen response!")

            # Use all generated images
            logging.info(
                f"Response successfully processed for user {request_response.user['user_name']} "
                f"({request_response.user['user_id']})"
            )
            request_response.response_images = response_urls

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
