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

import time
import uuid
import json
import os
import multiprocessing
import ctypes
import logging
from typing import Dict, Type

# pylint: disable=no-name-in-module
from google.generativeai.client import _ClientManager
import google.generativeai as genai
from google.ai.generativelanguage import Part, Content

import messages
import users_handler
from async_helper import async_helper
from bot_sender import send_message_async
from request_response_container import RequestResponseContainer

# Self name
_NAME = "gemini"


class GoogleAIModule:
    def __init__(
        self,
        config: Dict,
        messages_: Type[messages.Messages],
        users_handler_: Type[users_handler.UsersHandler],
    ) -> None:
        """Initializes class variables (must be done in main process)

        Args:
            config (Dict): global config
            messages_ (Type[messages.Messages]): initialized messages handler
            users_handler_ (Type[users_handler.UsersHandler]): initialized users handler
        """
        self.config = config
        self.messages = messages_
        self.users_handler = users_handler_

        # All variables here must be multiprocessing
        self.cancel_requested = multiprocessing.Value(ctypes.c_bool, False)
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)
        self._last_request_time = multiprocessing.Value(ctypes.c_double, 0.0)

        # Don't use this variables outside the module's process
        self._model = None
        self._vision_model = None

    def initialize(self) -> None:
        """Initializes Google AI module using the generative language API: https://ai.google.dev/api
        This method must be called from another process

        Raises:
            Exception: initialization error
        """
        # Internal variables for current process
        self._model = None
        try:
            self.processing_flag.value = False
            self.cancel_requested.value = False

            # Get module's config
            module_config = self.config.get(_NAME)

            # Use proxy
            if module_config.get("proxy") and module_config.get("proxy") != "auto":
                proxy = module_config.get("proxy")
                os.environ["http_proxy"] = proxy
                logging.info(f"Initializing Google AI module with proxy {proxy}")
            else:
                logging.info("Initializing Google AI module without proxy")

            # Set up the model
            generation_config = {
                "temperature": module_config.get("temperature", 0.9),
                "top_p": module_config.get("top_p", 1),
                "top_k": module_config.get("top_k", 1),
                "max_output_tokens": module_config.get("max_output_tokens", 2048),
            }
            safety_settings = []
            self._model = genai.GenerativeModel(
                model_name="gemini-pro",
                generation_config=generation_config,
                safety_settings=safety_settings,
            )
            self._vision_model = genai.GenerativeModel(
                model_name="gemini-pro-vision",
                generation_config=generation_config,
                safety_settings=safety_settings,
            )

            client_manager = _ClientManager()
            client_manager.configure(api_key=module_config.get("api_key"))
            # pylint: disable=protected-access
            self._model._client = client_manager.get_default_client("generative")
            self._vision_model._client = client_manager.get_default_client("generative")
            # pylint: enable=protected-access
            logging.info("Google AI module initialized")

        # Reset module and re-raise the error
        except Exception as e:
            self._model = None
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Google AI
        :param request_response: RequestResponseContainer object
        :return:
        """
        conversations_dir = self.config.get("files").get("conversations_dir")
        conversation_id = self.users_handler.get_key(request_response.user_id, f"{_NAME}_conversation_id")

        # Check if we are initialized
        if self._model is None:
            logging.error("Google AI module not initialized")
            request_response.response_text = self.messages.get_message(
                "response_error", user_id=request_response.user_id
            ).format(error_text="Google AI module not initialized")
            request_response.error = True
            self.processing_flag.value = False
            return

        try:
            # Set flag that we are currently processing request
            self.processing_flag.value = True

            # Get module's config
            module_config = self.config.get(_NAME)

            # Cool down
            if time.time() - self._last_request_time.value <= module_config.get("cooldown_seconds"):
                time_to_wait = module_config.get("cooldown_seconds") - (time.time() - self._last_request_time.value)
                logging.warning(f"Too frequent requests. Waiting {time_to_wait} seconds...")
                time.sleep(self._last_request_time.value + module_config.get("cooldown_seconds") - time.time())
            self._last_request_time.value = time.time()

            response = None
            conversation = []

            # Gemini vision
            if request_response.request_image:
                logging.info("Asking Gemini...")
                response = self._vision_model.generate_content(
                    [
                        Part(
                            inline_data={
                                "mime_type": "image/jpeg",
                                "data": request_response.request_image,
                            }
                        ),
                        Part(text=request_response.request_text),
                    ],
                    stream=True,
                )

            # Gemini (text)
            else:
                # Try to load conversation
                conversation = _load_conversation(conversations_dir, conversation_id) or []
                # Generate new random conversation ID
                if conversation_id is None:
                    conversation_id = str(uuid.uuid4())

                conversation.append(
                    Content.to_json(Content(role="user", parts=[Part(text=request_response.request_text)]))
                )

                logging.info("Asking Gemini...")
                response = self._model.generate_content(
                    [Content.from_json(content) for content in conversation],
                    stream=True,
                )

            for chunk in response:
                if self.cancel_requested.value:
                    break
                if len(chunk.parts) < 1 or "text" not in chunk.parts[0]:
                    continue

                # Append and send response
                request_response.response_text += chunk.parts[0].text
                async_helper(
                    send_message_async(self.config.get("telegram"), self.messages, request_response, end=False)
                )

            # Canceled, don't save conversation
            if self.cancel_requested.value:
                logging.info("Gemini module canceled")

            # Save conversation if not gemini-vision
            elif not request_response.request_image:
                # Try to save conversation
                conversation.append(Content.to_json(Content(role="model", parts=response.parts)))
                if not _save_conversation(conversations_dir, conversation_id, conversation):
                    conversation_id = None

                # Save conversation ID
                self.users_handler.set_key(request_response.user_id, f"{_NAME}_conversation_id", conversation_id)

        # Error
        except Exception as e:
            raise e

        finally:
            self.processing_flag.value = False

        # Finish
        async_helper(send_message_async(self.config.get("telegram"), self.messages, request_response, end=True))

    def clear_conversation_for_user(self, user_id: int) -> None:
        """Clears conversation (chat history) for selected user"""
        # Get current conversation_id
        conversation_id = self.users_handler.get_key(user_id, f"{_NAME}_conversation_id")
        if conversation_id is None:
            return

        # Delete from API
        _delete_conversation(self.config.get("files").get("conversations_dir"), conversation_id)

        # Delete from user
        self.users_handler.set_key(user_id, f"{_NAME}_conversation_id", None)


def _load_conversation(conversations_dir, conversation_id):
    """Tries to load conversation

    Args:
        conversations_dir (_type_): _description_
        conversation_id (_type_): _description_

    Returns:
        _type_: content of conversation, None if error
    """
    logging.info(f"Loading conversation {conversation_id}")
    try:
        if conversation_id is None:
            logging.info("conversation_id is None. Skipping loading")
            return None

        # API type 3
        conversation_file = os.path.join(conversations_dir, conversation_id + ".json")
        if os.path.exists(conversation_file):
            # Load from json file
            with open(conversation_file, "r", encoding="utf-8") as json_file:
                return json.load(json_file)
        else:
            logging.warning(f"File {conversation_file} not exists")

    except Exception as e:
        logging.warning(f"Error loading conversation {conversation_id}", exc_info=e)

    return None


def _save_conversation(conversations_dir, conversation_id, conversation) -> bool:
    """Tries to save conversation without raising any error

    Args:
        conversations_dir (_type_): _description_
        conversation_id (_type_): _description_
        conversation (_type_): _description_

    Returns:
        bool: True if no error
    """
    logging.info(f"Saving conversation {conversation_id}")
    try:
        if conversation_id is None:
            logging.info("conversation_id is None. Skipping saving")
            return False

        # Create conversation dir
        if not os.path.exists(conversations_dir):
            logging.info(f"Creating {conversations_dir} directory")
            os.makedirs(conversations_dir)

        # Save as json file
        conversation_file = os.path.join(conversations_dir, conversation_id + ".json")
        with open(conversation_file, "w+", encoding="utf-8") as json_file:
            json.dump(conversation, json_file, indent=4)

    except Exception as e:
        logging.error(f"Error saving conversation {conversation_id}", exc_info=e)
        return False

    return True


def _delete_conversation(conversations_dir, conversation_id) -> bool:
    """Tries to delete conversation without raising any error

    Args:
        conversations_dir (_type_): _description_
        conversation_id (_type_): _description_

    Returns:
        bool: True if no error
    """
    logging.info(f"Deleting conversation {conversation_id}")
    # Delete conversation file if exists
    try:
        conversation_file = os.path.join(conversations_dir, conversation_id + ".json")
        if os.path.exists(conversation_file):
            logging.info(f"Deleting {conversation_file} file")
            os.remove(conversation_file)
        return True

    except Exception as e:
        logging.error(
            f"Error removing conversation file for conversation {conversation_id}",
            exc_info=e,
        )

    return False
