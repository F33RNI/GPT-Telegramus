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
import os
import uuid
from typing import List, Dict

from EdgeGPT.EdgeGPT import Chatbot
from EdgeGPT.conversation_style import ConversationStyle

import bot_handler
import users_handler
from request_response_container import RequestResponseContainer


class EdgeGPTModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: users_handler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.cancel_requested = multiprocessing.Value(ctypes.c_bool, False)
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes EdgeGPT bot using this API: https://github.com/acheong08/EdgeGPT
        :return:
        """
        self._enabled = False
        self._chatbot = None

        self.processing_flag.value = False
        self.cancel_requested.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["edgegpt"]["proxy"] and self.config["edgegpt"]["proxy"] != "auto":
                proxy = self.config["edgegpt"]["proxy"]

            # Log
            logging.info(f"Initializing EdgeGPT module with proxy {proxy}")

            # Read cookies file
            cookies = None
            if self.config["edgegpt"]["cookies_file"] and os.path.exists(self.config["edgegpt"]["cookies_file"]):
                logging.info(f"Loading cookies from {self.config['edgegpt']['cookies_file']}")
                cookies = json.loads(open(self.config["edgegpt"]["cookies_file"], encoding="utf-8").read())

            # Set enabled status
            self._enabled = self.config["modules"]["edgegpt"]
            if not self._enabled:
                logging.warning("EdgeGPT module disabled in config file!")
                raise Exception("EdgeGPT module disabled in config file!")

            # Initialize EdgeGPT chatbot
            if proxy and len(proxy) > 1 and proxy.strip().lower() != "auto":
                self._chatbot = asyncio.run(Chatbot.create(proxy=proxy, cookies=cookies))
            else:
                self._chatbot = asyncio.run(Chatbot.create(cookies=cookies))

            # Check
            if self._chatbot is not None:
                logging.info("EdgeGPT module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to EdgeGPT
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = request_response.user.get("lang", 0)

        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("EdgeGPT module not initialized!")
            request_response.response = (
                self.messages[lang]["response_error"].replace("\\n", "\n").format("EdgeGPT module not initialized!")
            )
            request_response.error = True
            return

        try:
            # Set flag that we are currently processing request
            self.processing_flag.value = True
            self.cancel_requested.value = False

            # Get user data
            conversation_id = request_response.user.get("edgegpt_conversation_id")
            conversation_style = request_response.user.get("edgegpt_style")

            # Set default conversation style
            if conversation_style is None:
                conversation_style = self.config["edgegpt"]["conversation_style_type_default"]

            # Extract conversation style
            if conversation_style == 0:
                conversation_style_ = ConversationStyle.precise
            elif conversation_style == 1:
                conversation_style_ = ConversationStyle.balanced
            else:
                conversation_style_ = ConversationStyle.creative

            async def async_ask_stream_():
                async for data in self._chatbot.ask_stream(
                    prompt=request_response.request, conversation_style=conversation_style_, raw=True
                ):
                    # Split response
                    is_done, json_data = data

                    # Response
                    text_response = None
                    response_sources = []

                    # Type 1
                    if not is_done:
                        if "arguments" in json_data:
                            arguments = json_data["arguments"]
                            if len(arguments) > 0 and "messages" in arguments[-1]:
                                messages = arguments[-1]["messages"]
                                if len(messages) > 0:
                                    message = messages[-1]
                                    # Parse text response
                                    if "text" in message:
                                        text_response = message["text"]

                    # Type 2
                    else:
                        if "item" in json_data:
                            item = json_data["item"]
                            if "messages" in item:
                                messages = item["messages"]
                                if len(messages) > 0:
                                    # Try to find message with sourceAttributions
                                    for message in messages:
                                        response_sources.clear()

                                        # Parse text response
                                        if "text" in message:
                                            text_response = message["text"]

                                        # Parse sources
                                        if "sourceAttributions" in message:
                                            source_attributions = message["sourceAttributions"]
                                            for source_attribution in source_attributions:
                                                if (
                                                    "providerDisplayName" in source_attribution
                                                    and "seeMoreUrl" in source_attribution
                                                ):
                                                    response_sources.append(
                                                        (
                                                            source_attribution["providerDisplayName"],
                                                            source_attribution["seeMoreUrl"],
                                                        )
                                                    )

                                        # We found it
                                        if len(response_sources) > 0 and text_response:
                                            break

                    # If we have text response
                    if text_response:
                        # Set to container
                        request_response.response = text_response

                        # Add sources
                        if len(response_sources) > 0:
                            request_response.response += "\n"
                        for response_source in response_sources:
                            request_response.response += (
                                self.messages[lang]["edgegpt_sources"]
                                .format(response_source[0], response_source[1])
                                .replace("\\n", "\n")
                            )

                        # Send message to user
                        await bot_handler.send_message_async(self.config, self.messages, request_response, end=False)

                    # Exit requested?
                    if self.cancel_requested.value:
                        logging.info("Exiting from loop")
                        break

            # Reset current conversation
            asyncio.run(self._chatbot.reset())

            # Try to load conversation
            if conversation_id:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info(f"Loading conversation from {conversation_file}")
                    asyncio.run(self._chatbot.load_conversation(conversation_file))
                else:
                    conversation_id = None

            # Start request handling
            asyncio.run(async_ask_stream_())

            # Generate new conversation id
            if not conversation_id:
                conversation_id = str(uuid.uuid4()) + "_edgegpt"

            # Save conversation
            logging.info(f"Saving conversation to {conversation_id}")
            asyncio.run(
                self._chatbot.save_conversation(
                    os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                )
            )

            # Save to user data
            request_response.user["edgegpt_conversation_id"] = conversation_id
            self.users_handler.save_user(request_response.user)

            # Check response
            if len(request_response.response) > 0:
                logging.info(
                    f"Response successfully processed for user "
                    f"{request_response.user['user_name']} ({request_response.user['user_id']})"
                )

            # No response
            else:
                logging.warning(
                    f"Empty response for user "
                    f"{request_response.user['user_name']} ({request_response.user['user_id']})!"
                )
                request_response.response = (
                    self.messages[lang]["response_error"].replace("\\n", "\n").format("Empty response!")
                )
                request_response.error = True

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # EdgeGPT or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True
            self.processing_flag.value = False

        # Finish message
        bot_handler.async_helper(bot_handler.send_message_async(self.config, self.messages, request_response, end=True))

        # Clear processing flag
        self.processing_flag.value = False

    def clear_conversation_for_user(self, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user:
        :return:
        """
        # Get conversation id
        edgegpt_conversation_id = user.get("edgegpt_conversation_id")

        # Check if we need to clear it
        if edgegpt_conversation_id:
            # Delete file
            try:
                conversation_file = os.path.join(
                    self.config["files"]["conversations_dir"], edgegpt_conversation_id + ".json"
                )
                if os.path.exists(conversation_file):
                    logging.info(f"Removing {conversation_file}")
                    os.remove(conversation_file)
            except Exception as e:
                logging.error("Error removing conversation file!", exc_info=e)

        # Reset user data
        user["edgegpt_conversation_id"] = None
        self.users_handler.save_user(user)

    def exit(self):
        """
        Aborts processing
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        if self._chatbot is not None:
            logging.warning("Closing EdgeGPT connection")
            try:
                async_helper(self._chatbot.close())
            except Exception as e:
                logging.error("Error closing EdgeGPT connection!", exc_info=e)
