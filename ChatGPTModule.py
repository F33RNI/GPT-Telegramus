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

import asyncio
import ctypes
import json
import logging
import multiprocessing
import os.path
import time
import uuid
from typing import List, Dict

import BotHandler
import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class ChatGPTModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.cancel_requested = multiprocessing.Value(ctypes.c_bool, False)
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)
        self._last_request_time = multiprocessing.Value(ctypes.c_double, 0.0)

    def initialize(self, proxy=None) -> None:
        """
        Initializes ChatGPT bot using this API: https://github.com/acheong08/ChatGPT
        This method must be called from another process
        :return:
        """
        # Internal variables for current process
        self._enabled = False
        self._chatbot = None
        self._exit_flag = False

        self.processing_flag.value = False
        self.cancel_requested.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["chatgpt"]["proxy"] and self.config["chatgpt"]["proxy"] != "auto":
                proxy = self.config["chatgpt"]["proxy"]

            # Log
            logging.info(f"Initializing ChatGPT module with proxy {proxy}")

            # Set enabled status
            self._enabled = self.config["modules"]["chatgpt"]
            if not self._enabled:
                logging.warning("ChatGPT module disabled in config file!")
                raise Exception("ChatGPT module disabled in config file!")

            # Set chatbot object to None (reset it)
            self._chatbot = None

            # API type 1
            if self.config["chatgpt"]["api_type"] == 1:
                logging.info("Initializing ChatGPT module with API type 1")

                # Set CHATGPT_BASE_URL
                if self.config["chatgpt"]["base_url"]:
                    os.environ["CHATGPT_BASE_URL"] = self.config["chatgpt"]["base_url"]

                from revChatGPT.V1 import Chatbot

                self._chatbot = Chatbot(config=self._get_chatbot_config(proxy))

            # API type 3
            elif self.config["chatgpt"]["api_type"] == 3:
                logging.info("Initializing ChatGPT module with API type 3")
                from revChatGPT.V3 import Chatbot

                engine = str(self.config["chatgpt"]["engine"])

                # Check proxy
                if not proxy or len(proxy) <= 0:
                    proxy = ""

                # Initialize chatbot
                if len(engine) > 0:
                    self._chatbot = Chatbot(str(self.config["chatgpt"]["api_key"]), proxy=proxy, engine=engine)
                else:
                    self._chatbot = Chatbot(str(self.config["chatgpt"]["api_key"]), proxy=proxy)

            # Wrong API type
            else:
                raise Exception(f"Wrong API type: {self.config['chatgpt']['api_type']}")

            # Check
            if self._chatbot is not None:
                logging.info("ChatGPT module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to ChatGPT
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)

        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("ChatGPT module not initialized!")
            request_response.response = (
                self.messages[lang]["response_error"].replace("\\n", "\n").format("ChatGPT module not initialized!")
            )
            request_response.error = True
            self.processing_flag.value = False
            return

        try:
            # Set flag that we are currently processing request
            self.processing_flag.value = True
            self.cancel_requested.value = False

            # Get user data
            conversation_id = UsersHandler.get_key_or_none(request_response.user, "conversation_id")
            parent_id = UsersHandler.get_key_or_none(request_response.user, "parent_id")

            # Cooldown to prevent 429 Too Many Requests
            if time.time() - self._last_request_time.value <= self.config["chatgpt"]["cooldown_seconds"]:
                time_to_wait = int(
                    self.config["chatgpt"]["cooldown_seconds"] - (time.time() - self._last_request_time.value)
                )
                logging.warning(f"Too frequent requests. Waiting {time_to_wait} seconds...")
                while time.time() - self._last_request_time.value <= self.config["chatgpt"]["cooldown_seconds"]:
                    time.sleep(0.1)
                    # Exit requested?
                    if self.cancel_requested.value:
                        self._exit_flag = True

                    # Exit?
                    if self._exit_flag:
                        logging.warning("Exiting process_request")
                        self.processing_flag.value = False
                        return
            self._last_request_time.value = time.time()

            # API type 1
            if self.config["chatgpt"]["api_type"] == 1:
                # Reset current chat
                self._chatbot.reset_chat()

                # Ask
                logging.info("Asking ChatGPT (API type 1)...")
                for data in self._chatbot.ask(
                    request_response.request,
                    conversation_id=conversation_id,
                    parent_id=parent_id if parent_id is not None else "",
                ):
                    # Get last response
                    request_response.response = str(data["message"])

                    # Send message to user
                    asyncio.run(BotHandler.send_message_async(self.config, self.messages, request_response, end=False))

                    # Store conversation_id
                    if "conversation_id" in data and data["conversation_id"] is not None:
                        conversation_id = data["conversation_id"]

                    # Store parent_id
                    if "parent_id" in data and data["parent_id"] is not None:
                        parent_id = data["parent_id"]

                    # Cancel requested?
                    if self.cancel_requested.value:
                        break

                    # Exit?
                    if self._exit_flag:
                        break

                # Log conversation id and parent id
                logging.info(f"Current conversation_id: {conversation_id}, parent_id: {parent_id}")

                # Save conversation id and parent id
                request_response.user["conversation_id"] = conversation_id
                request_response.user["parent_id"] = parent_id

            # API type 3
            elif self.config["chatgpt"]["api_type"] == 3:
                # Try to load conversation
                if not self._load_conversation(conversation_id):
                    conversation_id = None

                # Generate new random conversation ID
                if conversation_id is None:
                    conversation_id = str(uuid.uuid4())

                # Ask
                logging.info("Asking ChatGPT (API type 3)...")
                for data in self._chatbot.ask(request_response.request, convo_id=conversation_id):
                    # Append response
                    request_response.response += str(data)

                    # Send message to user
                    asyncio.run(BotHandler.send_message_async(self.config, self.messages, request_response, end=False))

                    # Cancel requested?
                    if self.cancel_requested.value:
                        logging.info("Exiting from loop")
                        break

                    # Exit?
                    if self._exit_flag:
                        break

                # Save conversation id
                if not self._save_conversation(conversation_id):
                    conversation_id = None
                request_response.user["conversation_id"] = conversation_id

                # Reset conversation
                if conversation_id is not None:
                    self._chatbot.reset(conversation_id)
                    try:
                        del self._chatbot.conversation[conversation_id]
                    except Exception as e:
                        logging.warning("Error deleting key {conversation_id} from chatbot.conversation", exc_info=e)

            # Wrong API type
            else:
                self.processing_flag.value = False
                raise Exception(f"Wrong API type: {self.config['chatgpt']['api_type']}")

            # Save user data to database
            self.users_handler.save_user(request_response.user)

            # Check response
            if request_response.response:
                logging.info(
                    f"Response successfully processed for user "
                    f"{request_response.user['user_name']} ({request_response.user['user_id']})"
                )

            # No response
            else:
                logging.warning(
                    f"Empty response for user {request_response.user['user_name']} "
                    f"({request_response.user['user_id']})!"
                )
                request_response.response = (
                    self.messages[lang]["response_error"].replace("\\n", "\n").format("Empty response!")
                )
                request_response.error = True

            # Clear processing flag
            self.processing_flag.value = False

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            self.processing_flag.value = False
            return

        # ChatGPT or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True
            self.processing_flag.value = False

        # Finish message
        asyncio.run(BotHandler.send_message_async(self.config, self.messages, request_response, end=True))

    def clear_conversation_for_user(self, user_handler: UsersHandler.UsersHandler, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user_handler:
        :param user:
        :return: True if cleared successfully
        """
        if not self._enabled or self._chatbot is None:
            return
        conversation_id = UsersHandler.get_key_or_none(user, "conversation_id")
        if conversation_id is None:
            return

        # Delete from API
        self._delete_conversation(conversation_id)

        # Delete from user
        user["conversation_id"] = None
        user["parent_id"] = None

        # Save user
        user_handler.save_user(user)

    def exit(self):
        """
        Aborts processing
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        self._exit_flag = True

        # Try to close session
        try:
            if self._chatbot.session:
                logging.info("Trying to close ChatGPT session")
                self._chatbot.session.close()
        except Exception as e:
            logging.warning("Error closing ChatGPT session", exc_info=e)

        # Wait until aborted
        while self.processing_flag.value:
            time.sleep(0.1)

        # Print log
        logging.info("ChatGPT module exited")

    def _save_conversation(self, conversation_id) -> bool:
        """
        Saves conversation (only for API type 3)
        :param conversation_id:
        :return: True if no error
        """
        logging.info(f"Saving conversation {conversation_id}")
        try:
            if conversation_id is None:
                logging.info("conversation_id is None. Skipping saving")
                return False

            # API type 3
            if self.config["chatgpt"]["api_type"] == 3:
                # Save as json file
                conversation_file = os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                with open(conversation_file, "w", encoding="utf-8") as json_file:
                    json.dump(self._chatbot.conversation, json_file, indent=4)
                    json_file.close()

        except Exception as e:
            logging.error(f"Error saving conversation {conversation_id}", exc_info=e)
            return False

        return True

    def _load_conversation(self, conversation_id) -> bool:
        """
        Loads conversation (only for API type 3)
        :param conversation_id:
        :return: True if no error
        """
        logging.info(f"Loading conversation {conversation_id}")
        try:
            if conversation_id is None:
                logging.info("conversation_id is None. Skipping loading")
                return False

            # API type 3
            if self.config["chatgpt"]["api_type"] == 3:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                if os.path.exists(conversation_file):
                    # Load from json file
                    with open(conversation_file, "r", encoding="utf-8") as json_file:
                        self._chatbot.conversation = json.load(json_file)
                        json_file.close()
                else:
                    logging.warning(f"File {conversation_file} not exists!")

        except Exception as e:
            logging.warning(f"Error loading conversation {conversation_id}", exc_info=e)
            return False

        return True

    def _delete_conversation(self, conversation_id) -> bool:
        """
        Deletes conversation
        :param conversation_id:
        :return:
        """
        logging.info(f"Deleting conversation {conversation_id}")
        try:
            deleted = False

            # API type 1
            if self.config["chatgpt"]["api_type"] == 1:
                self._chatbot.reset_chat()
                try:
                    self._chatbot.delete_conversation(conversation_id)
                    deleted = True
                except Exception as e:
                    logging.error(f"Error deleting conversation {conversation_id}", exc_info=e)

            # API type 3
            elif self.config["chatgpt"]["api_type"] == 3:
                self._chatbot.reset(conversation_id)
                deleted = True

            # Wrong API type
            else:
                raise Exception(f"Wrong API type: {self.config['chatgpt']['api_type']}")

            # Delete conversation file if exists
            try:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info("Deleting {conversation_file} file")
                    os.remove(conversation_file)
                return deleted

            except Exception as e:
                logging.error(f"Error removing conversation file for conversation {conversation_id}", exc_info=e)

        except Exception as e:
            logging.warning(f"Error loading conversation {conversation_id}", exc_info=e)
        return False

    def _get_chatbot_config(self, proxy: str) -> dict:
        """
        Constructs chatbot config for API type 1
        See: https://github.com/acheong08/ChatGPT
        :param proxy:
        :return:
        """
        config = {}

        # Use email/password
        if len(self.config["chatgpt"]["email"]) > 0 and len(self.config["chatgpt"]["password"]) > 0:
            config["email"] = self.config["chatgpt"]["email"]
            config["password"] = self.config["chatgpt"]["password"]

        # Use session_token
        elif len(self.config["chatgpt"]["session_token"]) > 0:
            config["session_token"] = self.config["chatgpt"]["session_token"]

        # Use access_token
        elif len(self.config["chatgpt"]["access_token"]) > 0:
            config["access_token"] = self.config["chatgpt"]["access_token"]

        # No credentials
        else:
            raise Exception("Error! No credentials to login!")

        # Add proxy
        if proxy and len(proxy) > 1:
            config["proxy"] = proxy

        # Paid?
        config["paid"] = self.config["chatgpt"]["paid"]

        return config
