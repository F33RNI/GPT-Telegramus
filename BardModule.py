"""
Copyright (C) 2023-2024 Fern Lane, Hanssen

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
import os
from typing import List, Dict

import requests
from bardapi import Bard

import BotHandler
import UsersHandler
from JSONReaderWriter import load_json, save_json
from RequestResponseContainer import RequestResponseContainer


class BardModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes Bard bot using this API: https://github.com/acheong08/Bard
        :return:
        """
        self._enabled = False
        self._chatbot = None
        self.processing_flag.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["bard"]["proxy"] and self.config["bard"]["proxy"] != "auto":
                proxy = self.config["bard"]["proxy"]

            # Log
            logging.info(f"Initializing Bard module with proxy {proxy}")

            # Set enabled status
            self._enabled = self.config["modules"]["bard"]
            if not self._enabled:
                logging.warning("Bard module disabled in config file!")
                raise Exception("Bard module disabled in config file!")

            # Load cookies and secure_1psid
            secure_1psid = None
            session = requests.Session()
            session_cookies = load_json(self.config["bard"]["cookies_file"], logging_enabled=True)
            for session_cookie in session_cookies:
                session.cookies.set(
                    session_cookie["name"],
                    session_cookie["value"],
                    domain=session_cookie["domain"],
                    path=session_cookie["path"],
                )
                if secure_1psid is None and session_cookie["name"] == "__Secure-1PSID":
                    secure_1psid = session_cookie["value"]

            # Set headers
            session.headers = {
                "Host": "bard.google.com",
                "X-Same-Domain": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.4472.114 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": "https://bard.google.com",
                "Referer": "https://bard.google.com/",
            }

            # Initialize chatbot
            if proxy:
                self._chatbot = Bard(token=secure_1psid, proxies={"https": proxy, "http": proxy}, session=session)
            else:
                self._chatbot = Bard(token=secure_1psid, session=session)

            # Done?
            if self._chatbot is not None:
                logging.info("Bard module initialized")
            else:
                self._enabled = False

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Bard
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("Bard module not initialized!")
            lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)
            request_response.response = (
                self.messages[lang]["response_error"].replace("\\n", "\n").format("Bard module not initialized!")
            )
            request_response.error = True
            self.processing_flag.value = False
            return

        try:
            # Set processing flag
            self.processing_flag.value = True

            # Get user data
            conversation_id = UsersHandler.get_key_or_none(request_response.user, "bard_conversation_id")
            response_id = UsersHandler.get_key_or_none(request_response.user, "bard_response_id")
            choice_id = UsersHandler.get_key_or_none(request_response.user, "bard_choice_id")

            # Try to load conversation
            if conversation_id and response_id and choice_id:
                logging.info(
                    f"Using conversation_id: {conversation_id}, response_id: {response_id} and choice_id: {choice_id}"
                )
                self._chatbot.conversation_id = conversation_id
                self._chatbot.response_id = response_id
                self._chatbot.choice_id = choice_id

            # Try to download image
            image_bytes = None
            if request_response.image_url:
                logging.info("Downloading user image")
                image_bytes = requests.get(request_response.image_url, timeout=120).content

            # Ask Bard
            logging.info("Asking Bard...")
            bard_response = self._chatbot.get_answer(request_response.request, image=image_bytes)

            # Check response
            if not bard_response or len(bard_response) < 1 or "content" not in bard_response:
                raise Exception("Wrong Bard response!")

            # OK?
            logging.info(
                f"Response successfully processed for user {request_response.user['user_name']} "
                f"({request_response.user['user_id']})"
            )
            request_response.response = bard_response["content"]
            if "images" in bard_response and len(bard_response["images"]) > 0:
                request_response.response_images = bard_response["images"]

            # Save conversation
            logging.info(
                f"Saving conversation_id as {self._chatbot.conversation_id} and response_id as "
                f"{self._chatbot.response_id} and choice_id as {self._chatbot.choice_id}"
            )
            request_response.user["bard_conversation_id"] = self._chatbot.conversation_id
            request_response.user["bard_response_id"] = self._chatbot.response_id
            request_response.user["bard_choice_id"] = self._chatbot.choice_id
            self.users_handler.save_user(request_response.user)

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # Bard or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True

        # Try to save cookies
        try:
            if self._chatbot and self._chatbot.session and self._chatbot.session.cookies:
                session_cookies = load_json(self.config["bard"]["cookies_file"], logging_enabled=True)
                for session_cookie in session_cookies:
                    session_cookie["value"] = self._chatbot.session.cookies.get(
                        session_cookie["name"],
                        domain=session_cookie["domain"],
                        path=session_cookie["path"],
                    )
                save_json(self.config["bard"]["cookies_file"], session_cookies, True)
        except Exception as e:
            logging.error("Error saving cookies!", exc_info=e)

        # Finish message
        BotHandler.async_helper(BotHandler.send_message_async(self.config, self.messages, request_response, end=True))

        # Clear processing flag
        self.processing_flag.value = False

    def clear_conversation_for_user(self, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user:
        :return:
        """
        # Get conversation id
        bard_conversation_id = UsersHandler.get_key_or_none(user, "bard_conversation_id")

        # Check if we need to clear it
        if bard_conversation_id:
            # Delete file
            try:
                conversation_file = os.path.join(
                    self.config["files"]["conversations_dir"], bard_conversation_id + ".json"
                )
                if os.path.exists(conversation_file):
                    logging.info(f"Removing {conversation_file}")
                    os.remove(conversation_file)
            except Exception as e:
                logging.error("Error removing conversation file!", exc_info=e)

        # Reset user data
        user["bard_conversation_id"] = None
        user["bard_response_id"] = None
        user["bard_choice_id"] = None
        self.users_handler.save_user(user)

    def exit(self):
        """
        Aborts connection
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
