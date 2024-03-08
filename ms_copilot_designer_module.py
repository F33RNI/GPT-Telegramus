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
from typing import Dict

from BingImageCreator import ImageGen

import messages
import users_handler
import bot_sender
from async_helper import async_helper
from request_response_container import RequestResponseContainer


# Self name
_NAME = "ms_copilot_designer"


class MSCopilotDesignerModule:
    def __init__(
        self,
        config: Dict,
        messages_: messages.Messages,
        users_handler_: users_handler.UsersHandler,
    ) -> None:
        """Initializes class variables (must be done in main process)

        Args:
            config (Dict): global config
            messages_ (messages.Messages): initialized messages handler
            users_handler_ (users_handler.UsersHandler): initialized users handler
        """
        self.config = config
        self.messages = messages_
        self.users_handler = users_handler_

        # Don't use this variables outside the module's process
        self._image_generator = None

    def initialize(self) -> None:
        """Initializes Bing ImageGen API

        Raises:
            Exception: in case of error
        """
        self._image_generator = None

        # Get module's config
        module_config = self.config.get(_NAME)

        # Use proxy
        proxy = None
        if module_config.get("proxy") and module_config.get("proxy") != "auto":
            proxy = module_config.get("proxy")
            logging.info(f"Initializing MS Copilot Designer module with proxy {proxy}")
        else:
            logging.info("Initializing MS Copilot Designer module without proxy")

        # Read cookies file
        cookies = None
        if module_config.get("cookies_file") and os.path.exists(module_config.get("cookies_file")):
            logging.info(f"Loading cookies from {module_config.get('cookies_file')}")
            cookies = json.loads(open(module_config.get("cookies_file"), "r", encoding="utf-8").read())

        # Parse cookies
        auth_cookie = ""
        auth_cookie_SRCHHPGUSR = ""
        if cookies:
            logging.info("Parsing cookies")
            try:
                for cookie in cookies:
                    if cookie.get("name") == "_U":
                        auth_cookie = cookie.get("value")
                    elif cookie.get("name") == "SRCHHPGUSR":
                        auth_cookie_SRCHHPGUSR = cookie.get("value")
                if not auth_cookie:
                    raise Exception("No _U cookie")
                if not auth_cookie_SRCHHPGUSR:
                    raise Exception("No SRCHHPGUSR cookie")
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

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """Processes request to Bing ImageGen

        Args:
            request_response (RequestResponseContainer): container from the queue
        """
        # Check if we are initialized
        if self._image_generator is None:
            logging.error("MS Copilot Designer module not initialized")
            request_response.response_text = self.messages.get_message(
                "response_error", user_id=request_response.user_id
            ).format(error_text="MS Copilot Designer module not initialized")
            request_response.error = True
            return

        try:
            # Generate images
            logging.info("Requesting images from Bing ImageGen")
            response_urls = self._image_generator.get_images(request_response.request_text)

            # Check response
            if not response_urls or len(response_urls) == 0:
                raise Exception("Wrong Bing ImageGen response")

            # Use all generated images
            logging.info(f"Response successfully processed for user {request_response.user_id})")
            request_response.response_images = response_urls

        # Exit requested
        except (SystemExit, KeyboardInterrupt):
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # DALL-E or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response_text = self.messages.get_message(
                "response_error", user_id=request_response.user_id
            ).format(error_text=error_text)
            request_response.error = True

        # Finish message
        async_helper(
            bot_sender.send_message_async(self.config.get("telegram"), self.messages, request_response, end=True)
        )
