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
from typing import Dict

from EdgeGPT.EdgeGPT import Chatbot
from EdgeGPT.conversation_style import ConversationStyle

import messages
import users_handler
import bot_sender
from async_helper import async_helper
from request_response_container import RequestResponseContainer

# Self name
_NAME = "ms_copilot"


class MSCopilotModule:
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

        # All variables here must be multiprocessing
        self.cancel_requested = multiprocessing.Value(ctypes.c_bool, False)
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

        # Don't use this variables outside the module's process
        self._chatbot = None

    def initialize(self) -> None:
        """Initializes MS Copilot (aka EdgeGPT)
        https://github.com/F33RNI/EdgeGPT
        """
        self._chatbot = None

        with self.processing_flag.get_lock():
            self.processing_flag.value = False
        with self.cancel_requested.get_lock():
            self.cancel_requested.value = False

        # Get module's config
        module_config = self.config.get(_NAME)

        # Use proxy
        proxy = None
        if module_config.get("proxy") and module_config.get("proxy") != "auto":
            proxy = module_config.get("proxy")
            logging.info(f"Initializing MS Copilot (aka EdgeGPT) module with proxy {proxy}")
        else:
            logging.info("Initializing MS Copilot (aka EdgeGPT) module without proxy")

        # Read cookies file
        cookies = None
        if module_config.get("cookies_file") and os.path.exists(module_config.get("cookies_file")):
            logging.info(f"Loading cookies from {module_config.get('cookies_file')}")
            cookies = json.loads(open(module_config.get("cookies_file"), "r", encoding="utf-8").read())

        # Initialize EdgeGPT chatbot
        if proxy:
            self._chatbot = asyncio.run(Chatbot.create(proxy=proxy, cookies=cookies))
        else:
            self._chatbot = asyncio.run(Chatbot.create(cookies=cookies))

        # Check
        if self._chatbot is not None:
            logging.info("MS Copilot (aka EdgeGPT) module initialized")

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """Processes request to MS Copilot

        Args:
            request_response (RequestResponseContainer): container from the queue

        Raises:
            Exception: in case of error
        """
        # Check if module is initialized
        if self._chatbot is None:
            logging.error("MS Copilot (aka EdgeGPT) module not initialized")
            request_response.response_text = self.messages.get_message(
                "response_error", user_id=request_response.user_id
            ).format(error_text="MS Copilot (aka EdgeGPT) module not initialized")
            request_response.error = True
            return

        try:
            # Set flag that we are currently processing request
            with self.processing_flag.get_lock():
                self.processing_flag.value = True
            with self.cancel_requested.get_lock():
                self.cancel_requested.value = False

            # Get user data
            conversation_id = self.users_handler.get_key(request_response.user_id, f"{_NAME}_conversation_id")
            style_default = self.config.get(_NAME).get("conversation_style_type_default")
            conversation_style = self.users_handler.get_key(
                request_response.user_id, "ms_copilot_style", style_default
            )

            async def async_ask_stream_():
                async for finished, data in self._chatbot.ask_stream(
                    prompt=request_response.request_text,
                    conversation_style=getattr(ConversationStyle, conversation_style),
                    raw=True,
                ):
                    if not data:
                        continue

                    # Response
                    text_response = None
                    response_sources = []

                    type_ = data.get("type", -1)

                    # Type 1
                    if not finished and type_ == 1:
                        arguments = data.get("arguments")
                        if arguments is None or len(arguments) == 0:
                            continue
                        messages_ = arguments[-1].get("messages")
                        if messages_ is None or len(messages_) == 0:
                            continue
                        text = messages_[-1].get("text")
                        if not text:
                            continue
                        text_response = text

                    # Type 2
                    elif finished and type_ == 2:
                        item = data.get("item")
                        if item is None:
                            continue
                        messages_ = item.get("messages")
                        if messages_ is None or len(messages_) == 0:
                            continue
                        for message in messages_:
                            # Check author
                            author = message.get("author")
                            if author is None or author != "bot":
                                continue

                            # Text response
                            text = message.get("text")
                            if text:
                                text_response = text

                            # Sources
                            source_attributions = message.get("sourceAttributions")
                            if source_attributions is None or len(source_attributions) == 0:
                                continue
                            response_sources.clear()
                            for source_attribution in source_attributions:
                                provider_display_name = source_attribution.get("providerDisplayName")
                                see_more_url = source_attribution.get("seeMoreUrl")
                                if not provider_display_name or not see_more_url:
                                    continue
                                response_sources.append((provider_display_name, see_more_url))

                    # Unknown
                    else:
                        continue

                    # Check response
                    if not text_response:
                        continue

                    # Set to container
                    request_response.response_text = text_response

                    # Add sources
                    if len(response_sources) != 0:
                        request_response.response_text += "\n"
                        response_link_format = self.messages.get_message(
                            "response_link_format", user_id=request_response.user_id
                        )
                        for response_source in response_sources:
                            request_response.response_text += response_link_format.format(
                                source_name=response_source[0], link=response_source[1]
                            )

                    # Send message to user
                    await bot_sender.send_message_async(
                        self.config.get("telegram"), self.messages, request_response, end=False
                    )

                    # Exit requested?
                    with self.cancel_requested.get_lock():
                        cancel_requested = self.cancel_requested.value
                    if cancel_requested:
                        logging.info("Exiting from loop")
                        break

            # Reset current conversation
            asyncio.run(self._chatbot.reset())

            # Try to load conversation
            if conversation_id:
                conversation_file = os.path.join(
                    self.config.get("files").get("conversations_dir"), conversation_id + ".json"
                )
                if os.path.exists(conversation_file):
                    logging.info(f"Loading conversation from {conversation_file}")
                    asyncio.run(self._chatbot.load_conversation(conversation_file))
                else:
                    conversation_id = None

            # Start request handling
            asyncio.run(async_ask_stream_())

            # Generate new conversation id
            if not conversation_id:
                conversation_id = f"{_NAME}_{uuid.uuid4()}"

            # Save conversation
            logging.info(f"Saving conversation to {conversation_id}")
            asyncio.run(
                self._chatbot.save_conversation(
                    os.path.join(self.config.get("files").get("conversations_dir"), conversation_id + ".json")
                )
            )

            # Save to user data
            self.users_handler.set_key(request_response.user_id, f"{_NAME}_conversation_id", conversation_id)

            # Check response
            if len(request_response.response_text) != 0:
                logging.info(f"Response successfully processed for user {request_response.user_id}")

            # No response
            else:
                logging.warning(f"Empty response for user {request_response.user_id}")
                request_response.response_text = self.messages.get_message(
                    "response_error", user_id=request_response.user_id
                ).format(error_text="Empty response")
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

            request_response.response_text = self.messages.get_message(
                "response_error", user_id=request_response.user_id
            ).format(error_text=error_text)
            request_response.error = True
            with self.processing_flag.get_lock():
                self.processing_flag.value = False

        # Finish message
        async_helper(
            bot_sender.send_message_async(self.config.get("telegram"), self.messages, request_response, end=True)
        )

        # Clear processing flag
        with self.processing_flag.get_lock():
            self.processing_flag.value = False

    def clear_conversation_for_user(self, user_id: int) -> None:
        """Clears conversation (chat history) for selected user
        This can be called from any process

        Args:
            user_id (int): ID of user
        """
        conversation_id = self.users_handler.get_key(user_id, f"{_NAME}_conversation_id")

        # Check if we need to clear it
        if conversation_id:
            # Delete file
            try:
                conversation_file = os.path.join(
                    self.config.get("files").get("conversations_dir"), conversation_id + ".json"
                )
                if os.path.exists(conversation_file):
                    logging.info(f"Removing {conversation_file}")
                    os.remove(conversation_file)
            except Exception as e:
                logging.error("Error removing conversation file!", exc_info=e)

        # Reset user data
        self.users_handler.set_key(user_id, f"{_NAME}_conversation_id", None)

    def exit(self) -> None:
        """Aborts processing (closes chatbot)"""
        if self._chatbot is None:
            return
        if self._chatbot is not None:
            logging.warning("Closing MS Copilot (aka EdgeGPT) connection")
            try:
                async_helper(self._chatbot.close())
            except Exception as e:
                logging.error("Error closing MS Copilot (aka EdgeGPT) connection!", exc_info=e)
