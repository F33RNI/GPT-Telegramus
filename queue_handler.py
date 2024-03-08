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
import datetime
import gc
import logging
import multiprocessing
import os
import threading
import time
from typing import Dict

import psutil
import requests

import messages
import users_handler
import request_response_container
from queue_container_helpers import put_container_to_queue, queue_to_list, remove_container_from_queue
from request_processor import request_processor
from async_helper import async_helper
from bot_sender import send_message_async


# After how long (seconds) clear self.prevent_shutdown_flag.value
CLEAR_PREVENT_SHUTDOWN_FLAG_AFTER = 5.0

# Default module timeout (if no config entry for specific module)
_TIMEOUT_DEFAULT = 120

# Minimal delay of _queue_processing_loop to prevent overloading
_QUEUE_PROCESSING_LOOP_DELAY = 0.1


class QueueHandler:
    def __init__(
        self,
        config: Dict,
        messages_: messages.Messages,
        users_handler_: users_handler.UsersHandler,
        logging_queue: multiprocessing.Queue,
        prevent_shutdown_flag: multiprocessing.Value,
        modules: Dict,
    ):
        """Initializes QueueHandler

        Args:
            config (Dict): global config
            messages_ (messages.Messages): initialized messages handler
            users_handler_ (users_handler.UsersHandler): initialized users handler
            logging_queue (multiprocessing.Queue): logging queue from logging handler
            prevent_shutdown_flag (multiprocessing.Value): value to prevent Telegram bot shutdown from bot handler
            modules (Dict): dictionary of all loaded modules from main
        """
        self.config = config
        self.messages = messages_
        self.users_handler = users_handler_
        self.logging_queue = logging_queue
        self.prevent_shutdown_flag = prevent_shutdown_flag
        self.modules = modules

        # Requests queue
        self.request_response_queue = multiprocessing.Queue(maxsize=-1)
        self.lock = multiprocessing.Lock()

        self._processing_loop_thread = None
        self._exit_flag = False
        self._prevent_shutdown_flag_clear_timer = 0
        self._log_filename = ""

    def start_processing_loop(self) -> None:
        """Starts _queue_processing_loop as background thread"""
        if self._processing_loop_thread is not None and self._processing_loop_thread.is_alive():
            logging.warning("Cannot start _queue_processing_loop thread. Thread already running")
            return
        logging.info("Starting _queue_processing_loop thread")
        self._processing_loop_thread = threading.Thread(target=self._queue_processing_loop)
        self._exit_flag = False
        self._processing_loop_thread.start()

    def stop_processing_loop(self) -> None:
        """Stops _queue_processing_loop thread"""
        if self._processing_loop_thread is None or not self._processing_loop_thread.is_alive():
            logging.info("_queue_processing_loop thread already stopped")
            self._processing_loop_thread = None
            return

        logging.info("Stopping _queue_processing_loop thread")
        self._exit_flag = True
        try:
            if self._processing_loop_thread.is_alive():
                self._processing_loop_thread.join()
        except Exception as e:
            logging.warning(f"Error joining _queue_processing_loop thread: {e}")
        self._processing_loop_thread = None

    def _queue_processing_loop(self) -> None:
        """Queue handling thread
        Gets request from self.requests_queue or self.responses_queue and processes it
        This must be separate thread
        """
        logging.info("_queue_processing_loop thread started")
        while not self._exit_flag:
            try:
                # Clear prevent shutdown flag
                if self.prevent_shutdown_flag is not None:
                    if (
                        self._prevent_shutdown_flag_clear_timer != 0
                        and time.time() - self._prevent_shutdown_flag_clear_timer > CLEAR_PREVENT_SHUTDOWN_FLAG_AFTER
                        and self.prevent_shutdown_flag
                    ):
                        logging.info("Clearing prevent_shutdown_flag")
                        with self.prevent_shutdown_flag.get_lock():
                            self.prevent_shutdown_flag.value = False
                        self._prevent_shutdown_flag_clear_timer = 0

                # Skip one cycle in queue is empty
                if self.request_response_queue.qsize() == 0:
                    time.sleep(0.1)
                    continue

                # Lock queue
                self.lock.acquire()

                # Convert queue to list
                queue_list = queue_to_list(self.request_response_queue)

                # Main loop
                # We check each container inside the queue and decide what we should with it
                for request_ in queue_list:
                    #################################################
                    # Not yet processed (PROCESSING_STATE_IN_QUEUE) #
                    #################################################
                    # Check if we're not processing this request yet
                    if request_.processing_state == request_response_container.PROCESSING_STATE_IN_QUEUE:
                        # Check if requested module's process is busy (only 1 request to each module as a time)
                        module_is_busy = False
                        for request__ in queue_list:
                            if (
                                request__.module_name == request_.module_name
                                and request__.pid != 0
                                and psutil.pid_exists(request__.pid)
                            ):
                                module_is_busy = True
                                break

                        # Ignore until module is no longer busy
                        if module_is_busy:
                            continue

                        # Set initializing state
                        request_.processing_state = request_response_container.PROCESSING_STATE_INITIALIZING

                        # Set current time (for timeout control)
                        request_.processing_start_timestamp = time.time()

                        # Log request
                        logging.info(f"Received request from user {request_.user_id}")
                        self._collect_data(request_, log_request=True)

                        # Create process from handling container
                        request_process = multiprocessing.Process(
                            target=request_processor,
                            args=(
                                self.config,
                                self.messages,
                                self.users_handler,
                                self.logging_queue,
                                self.request_response_queue,
                                self.lock,
                                request_.id,
                                self.modules.get(request_.module_name),
                            ),
                        )

                        # Start process
                        logging.info(f"Starting request_processor for {request_.module_name}")
                        request_process.start()

                        # Set process PID to the container
                        request_.pid = request_process.pid

                        # Update
                        put_container_to_queue(self.request_response_queue, None, request_)

                    ######################################
                    # Active (PROCESSING_STATE_IN_QUEUE) #
                    ######################################
                    # Request is currently processing -> check timeout
                    if request_.processing_state > request_response_container.PROCESSING_STATE_IN_QUEUE:
                        # Check timeout
                        timeout = self.config.get(request_.module_name).get("timeout_seconds", _TIMEOUT_DEFAULT)
                        if time.time() - request_.processing_start_timestamp > timeout:
                            # Log warning
                            logging.warning(
                                f"Request from user {request_.user_id} to {request_.module_name} timed out!"
                            )

                            # Set timeout status and message
                            request_.processing_state = request_response_container.PROCESSING_STATE_TIMED_OUT
                            request_.response_text = f"Timed out (>{timeout} s)"
                            request_.error = True

                            # Update
                            put_container_to_queue(self.request_response_queue, None, request_)

                            # Send timeout message
                            async_helper(send_message_async(self.config, self.messages, request_, end=True))

                    ##############################################
                    # Cancel requested (PROCESSING_STATE_CANCEL) #
                    ##############################################
                    # Cancel generating
                    if request_.processing_state == request_response_container.PROCESSING_STATE_CANCEL:
                        logging.info(f"Canceling {request_.module_name}")
                        self.modules.get(request_.module_name).stop_stream()

                        # Set canceling flag
                        request_.processing_state = request_response_container.PROCESSING_STATE_CANCELING

                        # Update
                        put_container_to_queue(self.request_response_queue, None, request_)

                    ####################################################################################
                    # Done / Timed out / abort requested (PROCESSING_STATE_DONE / _TIMED_OUT / _ABORT) #
                    ####################################################################################
                    if (
                        request_.processing_state == request_response_container.PROCESSING_STATE_DONE
                        or request_.processing_state == request_response_container.PROCESSING_STATE_TIMED_OUT
                        or request_.processing_state == request_response_container.PROCESSING_STATE_ABORT
                    ):
                        # Kill process if it is active
                        if request_.pid > 0 and psutil.pid_exists(request_.pid):
                            if self.prevent_shutdown_flag is not None:
                                logging.info("Setting prevent_shutdown_flag")
                                with self.prevent_shutdown_flag.get_lock():
                                    self.prevent_shutdown_flag.value = True
                                self._prevent_shutdown_flag_clear_timer = time.time()
                            try:
                                logging.info(f"Trying to kill {request_.module_name} process with PID {request_.pid}")
                                process = psutil.Process(request_.pid)

                                # Firstly try SIGTERM
                                process.terminate()
                                time.sleep(1)

                                # And only then SIGKILL
                                if process.is_running():
                                    process.kill()
                                    process.wait(timeout=5)
                            except Exception as e:
                                logging.error(f"Error killing process with PID {request_.pid}", exc_info=e)
                            logging.info(f"Killed? {not psutil.pid_exists(request_.pid)}")

                        # Format response timestamp (for data collecting)
                        response_timestamp = ""
                        if self.config.get("data_collecting").get("enabled"):
                            response_timestamp = datetime.datetime.now().strftime(
                                self.config.get("data_collecting").get("timestamp_format")
                            )
                        request_.response_timestamp = response_timestamp

                        # Log response
                        self._collect_data(request_, log_request=False)

                        # Remove from the queue
                        remove_container_from_queue(self.request_response_queue, None, request_.id)
                        logging.info(
                            f"Container with ID {request_.id} (PID {request_.pid}) was removed from the queue"
                        )

                        # Collect garbage (just in case)
                        gc.collect()

                # Unlock the queue
                self.lock.release()

                # Sleep some time before next cycle to prevent overloading
                time.sleep(_QUEUE_PROCESSING_LOOP_DELAY)

            # Exit requested
            except (SystemExit, KeyboardInterrupt):
                logging.warning("_queue_processing_loop interrupted")
                self._exit_flag = True

                # Kill and remove all active processes from the queue
                with self.lock:
                    queue_list = queue_to_list(self.request_response_queue)
                    for container in queue_list:
                        if container.pid > 0 and psutil.pid_exists(container.pid):
                            try:
                                logging.info(f"Trying to kill process with PID {container.pid}")
                                process = psutil.Process(container.pid)

                                # Firstly try SIGTERM
                                process.terminate()
                                time.sleep(1)

                                # And only then SIGKILL
                                if process.is_running():
                                    process.kill()
                                    process.wait(timeout=5)
                            except Exception as e:
                                logging.error(f"Error killing process with PID {container.pid}", exc_info=e)
                            logging.info(f"Killed? {not psutil.pid_exists(container.pid)}")

                        remove_container_from_queue(self.request_response_queue, None, container.id)

                # Collect garbage (just in case)
                gc.collect()

                # Exit from loop
                break

            # Oh no, error! Why?
            except Exception as e:
                logging.error("Error processing queue", exc_info=e)
                time.sleep(1)

        logging.info("_queue_processing_loop finished")

    def _collect_data(
        self,
        request_response: request_response_container.RequestResponseContainer,
        log_request: bool = True,
    ) -> None:
        """Logs requests and responses (collects data)
        NOTE: You should notify users if it's enabled!

        Args:
            request_response (request_response_container.RequestResponseContainer): container to log data from
            log_request (bool, optional): True to log request, False to log response. Defaults to True
        """
        if not self.config.get("data_collecting").get("enabled"):
            return

        data_collecting_config = self.config.get("data_collecting")

        # Create new filename
        if not self._log_filename or len(self._log_filename) < 1 or not os.path.exists(self._log_filename):
            data_collecting_dir = self.config.get("files").get("data_collecting_dir")
            if not os.path.exists(data_collecting_dir):
                logging.info(f"Creating {data_collecting_dir} directory")
                os.makedirs(data_collecting_dir)

            file_timestamp = datetime.datetime.now().strftime(data_collecting_config.get("filename_timestamp_format"))
            self._log_filename = os.path.join(
                data_collecting_dir, file_timestamp + data_collecting_config.get("filename_extension")
            )
            logging.info(f"New file for data collecting: {self._log_filename}")

        # Open log file for appending
        try:
            log_file = open(self._log_filename, "a+", encoding="utf8")
        except Exception as e:
            logging.error(f"Error opening {self._log_filename} file for appending: {e}")
            return

        user_id = request_response.user_id
        user_name = self.users_handler.get_key(user_id, "user_name", "")

        try:
            ###########
            # Request #
            ###########
            if log_request:
                request_format = data_collecting_config.get("request_format")

                # Log image request as base 64
                try:
                    if request_response.request_image is not None:
                        image_request = base64.b64encode(request_response.request_image).decode("utf-8")
                        log_file.write(
                            request_format.format(
                                timestamp=request_response.request_timestamp,
                                container_id=request_response.id,
                                user_name=user_name,
                                user_id=user_id,
                                module_name=request_response.module_name,
                                request=image_request,
                            )
                        )
                except Exception as e:
                    logging.warning(f"Error logging image request: {e}")

                # Log request text
                log_file.write(
                    request_format.format(
                        timestamp=request_response.request_timestamp,
                        container_id=request_response.id,
                        user_name=user_name,
                        user_id=user_id,
                        module_name=request_response.module_name,
                        request=request_response.request_text,
                    )
                )

            ############
            # Response #
            ############
            else:
                response_format = data_collecting_config.get("response_format")

                # Log response text
                if request_response.response_text:
                    log_file.write(
                        response_format.format(
                            timestamp=request_response.response_timestamp,
                            container_id=request_response.id,
                            user_name=user_name,
                            user_id=user_id,
                            module_name=request_response.module_name,
                            response=request_response.response_text,
                        )
                    )

                # Log response images as base64
                for image_url in request_response.response_images:
                    try:
                        response = base64.b64encode(requests.get(image_url, timeout=60).content).decode("utf-8")
                        log_file.write(
                            response_format.format(
                                timestamp=request_response.response_timestamp,
                                container_id=request_response.id,
                                user_name=user_name,
                                user_id=user_id,
                                module_name=request_response.module_name,
                                response=response,
                            )
                        )
                    except Exception as e:
                        logging.warning(f"Error logging image: {image_url}", exc_info=e)

            # Done
            logging.info(
                f"The {'request' if log_request else 'response'} was written to the file: {self._log_filename}"
            )
        except Exception as e:
            logging.error("Error collecting data", exc_info=e)

        # Close file
        if log_file:
            try:
                log_file.close()
            except Exception as e:
                logging.error("Error closing file for data collecting: {e}")

        # Start new file if length exceeded requested value
        if self._log_filename and os.path.exists(self._log_filename):
            file_size = os.path.getsize(self._log_filename)
            if file_size > data_collecting_config.get("max_size"):
                logging.info(
                    f"File {self._log_filename} has size {file_size} bytes which is more "
                    f"than {data_collecting_config.get('max_size')}. New file will be started"
                )
                self._log_filename = ""
