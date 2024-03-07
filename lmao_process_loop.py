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
import multiprocessing
import queue
import threading
import time
from typing import Dict

from lmao.module_wrapper import (
    ModuleWrapper,
    STATUS_INITIALIZING,
    STATUS_BUSY,
    STATUS_FAILED,
)

import logging_handler
import messages
import users_handler
from bot_sender import send_message_async
from async_helper import async_helper

# lmao process loop delay during idle
LMAO_LOOP_DELAY = 0.5


def lmao_process_loop(
    name: str,
    name_lmao: str,
    config: Dict,
    messages_: messages.Messages,
    users_handler_: users_handler.UsersHandler,
    logging_queue: multiprocessing.Queue,
    lmao_process_running: multiprocessing.Value,
    lmao_stop_stream_value: multiprocessing.Value,
    lmao_module_status: multiprocessing.Value,
    lmao_delete_conversation_request_queue: multiprocessing.Queue,
    lmao_delete_conversation_response_queue: multiprocessing.Queue,
    lmao_request_queue: multiprocessing.Queue,
    lmao_response_queue: multiprocessing.Queue,
    lmao_exceptions_queue: multiprocessing.Queue,
) -> None:
    """Handler for lmao's ModuleWrapper
    (see module_wrapper_global.py for more info)
    """
    # Setup logging for current process
    logging_handler.worker_configurer(logging_queue)
    logging.info("_lmao_process_loop started")

    # Initialize module
    try:
        logging.info(f"Initializing {name}")
        with lmao_module_status.get_lock():
            lmao_module_status.value = STATUS_INITIALIZING
        module = ModuleWrapper(name_lmao, config.get(name))
        module.initialize(blocking=True)
        with lmao_module_status.get_lock():
            lmao_module_status.value = module.status
        logging.info(f"{name} initialization finished")
    except Exception as e:
        logging.error(f"{name} initialization error", exc_info=e)
        with lmao_module_status.get_lock():
            lmao_module_status.value = STATUS_FAILED
        with lmao_process_running.get_lock():
            lmao_process_running.value = False
        return

    # Main loop container
    request_response = None

    def _lmao_stop_stream_loop() -> None:
        """Background thread that handles stream stop signal"""
        logging.info("_lmao_stop_stream_loop started")
        while True:
            # Exit from loop
            with lmao_process_running.get_lock():
                if not lmao_process_running.value:
                    logging.warning("Exit from _lmao_stop_stream_loop requested")
                    break

            try:
                # Wait a bit to prevent overloading
                # We need to wait at the beginning to enable delay even after exception
                # But inside try-except to catch interrupts
                time.sleep(LMAO_LOOP_DELAY)

                # Get stop request
                lmao_stop_stream = False
                with lmao_stop_stream_value.get_lock():
                    if lmao_stop_stream_value.value:
                        lmao_stop_stream = True
                        lmao_stop_stream_value.value = False

                # Stop was requested
                if lmao_stop_stream:
                    module.response_stop()

            # Catch process interrupts just in case
            except (SystemExit, KeyboardInterrupt):
                logging.warning("Exit from _lmao_stop_stream_loop requested")
                break

            # Stop loop error
            except Exception as e:
                logging.error("_lmao_stop_stream_loop error", exc_info=e)

        # Done
        logging.info("_lmao_stop_stream_loop finished")

    # Start stream stop signal handler
    stop_handler_thread = threading.Thread(target=_lmao_stop_stream_loop)
    stop_handler_thread.start()

    # Main loop
    while True:
        # Exit from loop
        with lmao_process_running.get_lock():
            lmao_process_running_value = lmao_process_running.value
        if not lmao_process_running_value:
            logging.warning(f"Exit from {name} loop requested")
            break

        try:
            # Wait a bit to prevent overloading
            # We need to wait at the beginning to enable delay even after exception
            # But inside try-except to catch interrupts
            time.sleep(LMAO_LOOP_DELAY)

            # Non-blocking get of request-response container
            request_response = None
            try:
                request_response = lmao_request_queue.get(block=False)
            except queue.Empty:
                pass

            # Read module's status
            with lmao_module_status.get_lock():
                lmao_module_status.value = module.status

            # New request
            if request_response:
                logging.info(f"Received new request to {name}")
                with lmao_module_status.get_lock():
                    lmao_module_status.value = STATUS_BUSY

                # Currently LMAO API can only handle text requests
                prompt_text = request_response.request_text

                # Check prompt
                if not prompt_text:
                    raise Exception("No text request")
                else:
                    # Extract conversation ID
                    conversation_id = users_handler_.get_key(request_response.user_id, name + "_conversation_id")

                    # Build request
                    module_request = {"prompt": prompt_text, "convert_to_markdown": True}
                    if conversation_id:
                        module_request["conversation_id"] = conversation_id

                    # Ask and read stream
                    for response in module.ask(module_request):
                        finished = response.get("finished")
                        conversation_id = response.get("conversation_id")
                        request_response.response_text = response.get("response")

                        # Read module's status
                        with lmao_module_status.get_lock():
                            lmao_module_status.value = module.status

                        # Check if exit was requested
                        with lmao_process_running.get_lock():
                            lmao_process_running_value = lmao_process_running.value
                        if not lmao_process_running_value:
                            finished = True

                        # Send response to the user
                        async_helper(
                            send_message_async(config.get("telegram"), messages_, request_response, end=finished)
                        )

                        # Exit from stream reader
                        if not lmao_process_running_value:
                            break

                    # Save conversation ID
                    users_handler_.set_key(request_response.user_id, name + "_conversation_id", conversation_id)

                    # Return container
                    lmao_response_queue.put(request_response)

            # Non-blocking get of user_id to clear conversation for
            delete_conversation_user_id = None
            try:
                delete_conversation_user_id = lmao_delete_conversation_request_queue.get(block=False)
            except queue.Empty:
                pass

            # Get and delete conversation
            if delete_conversation_user_id is not None:
                with lmao_module_status.get_lock():
                    lmao_module_status.value = STATUS_BUSY
                conversation_id = users_handler_.get_key(delete_conversation_user_id, name + "_conversation_id")
                try:
                    if conversation_id:
                        module.delete_conversation({"conversation_id": conversation_id})
                        users_handler_.set_key(delete_conversation_user_id, name + "_conversation_id", None)
                    lmao_delete_conversation_response_queue.put(delete_conversation_user_id)
                except Exception as e:
                    logging.error(f"Error deleting conversation for {name}", exc_info=e)
                    lmao_delete_conversation_response_queue.put(e)

        # Catch process interrupts just in case
        except (SystemExit, KeyboardInterrupt):
            logging.warning(f"Exit from {name} loop requested")
            break

        # Main loop error
        except Exception as e:
            logging.error(f"{name} error", exc_info=e)
            lmao_exceptions_queue.put(e)

    # Wait for stop handler to finish
    if stop_handler_thread and stop_handler_thread.is_alive():
        logging.info("Waiting for _lmao_stop_stream_loop")
        try:
            stop_handler_thread.join()
        except Exception as e:
            logging.warning(f"Error joining _lmao_stop_stream_loop: {e}")

    # Try to close module
    try:
        logging.info(f"Trying to close {name}")
        module.close(blocking=True)
        with lmao_module_status.get_lock():
            lmao_module_status.value = module.status
        logging.info(f"{name} closing finished")
    except Exception as e:
        logging.error(f"Error closing {name}", exc_info=e)

    # Done
    with lmao_process_running.get_lock():
        lmao_process_running.value = False
    logging.info("_lmao_process_loop finished")
