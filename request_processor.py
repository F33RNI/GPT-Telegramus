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

import base64
import logging
import multiprocessing
from typing import Dict

import logging_handler
import messages
import users_handler
import request_response_container
import module_wrapper_global
from async_helper import async_helper
from bot_sender import send_message_async
from queue_container_helpers import get_container_from_queue, put_container_to_queue


def request_processor(
    config: Dict,
    messages_: messages.Messages,
    users_handler_: users_handler.UsersHandler,
    logging_queue: multiprocessing.Queue,
    request_response_queue: multiprocessing.Queue,
    lock: multiprocessing.Lock,
    request_id: int,
    module: module_wrapper_global.ModuleWrapperGlobal,
) -> None:
    """Processes request to any module
    This method should be called from multiprocessing as process

    Args:
        config (Dict): global config
        messages_ (messages.Messages): initialized messages handler
        users_handler_ (users_handler.UsersHandler): initialized users handler
        logging_queue (multiprocessing.Queue): logging queue from logging handler
        request_response_queue (multiprocessing.Queue): queue of request-response containers
        lock (multiprocessing.Lock): lock from queue handler
        request_id (int): ID of container
        module (module_wrapper_global.ModuleWrapperGlobal): requested module
    """
    # Setup logging for current process
    logging_handler.worker_configurer(logging_queue)
    logging.info("request_processor started")

    # Get request
    request_ = get_container_from_queue(request_response_queue, lock, request_id)
    user_id = request_.user_id

    # Check request
    if request_ is None:
        logging.error("Error retrieving container from the queue")
        return

    try:
        # Send initial message
        if config.get("telegram").get("response_initial_message"):
            request_.response_text = config.get("telegram").get("response_initial_message")
            async_helper(send_message_async(config.get("telegram"), messages_, request_, end=False))

        request_.response_text = ""

        # Set active state
        request_.processing_state = request_response_container.PROCESSING_STATE_ACTIVE

        user = users_handler_.get_user(user_id)

        # Increment number of requests for statistics
        users_handler_.set_key(
            user_id, f"requests_{module.name}", users_handler_.get_key(0, f"requests_{module.name}", 0, user=user) + 1
        )
        users_handler_.set_key(
            user_id, "requests_total", users_handler_.get_key(0, "requests_total", 0, user=user) + 1
        )

        # Save request data (for regenerate function)
        users_handler_.set_key(user_id, "request_last", request_.request_text)
        if request_.request_image:
            users_handler_.set_key(
                user_id,
                "request_last_image",
                base64.urlsafe_b64encode(request_.request_image).decode(),
            )
        else:
            users_handler_.set_key(user_id, "request_last_image", None)
        users_handler_.set_key(user_id, "reply_message_id_last", request_.reply_message_id)

        # Update container in the queue
        put_container_to_queue(request_response_queue, lock, request_)

        # Process request
        module.process_request(request_)

    # Error during processing request
    except Exception as e:
        request_.error = True
        lang_id = users_handler_.get_key(user_id, "lang_id", "eng")
        request_.response_text = messages_.get_message("response_error", lang_id=lang_id).format(error_text=str(e))
        async_helper(send_message_async(config.get("telegram"), messages_, request_, end=True))
        logging.error("Error processing request", exc_info=e)

    # Set done state
    request_.processing_state = request_response_container.PROCESSING_STATE_DONE

    # Finally, update container in the queue
    put_container_to_queue(request_response_queue, lock, request_)
