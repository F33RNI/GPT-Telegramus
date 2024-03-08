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
import queue
import time
import multiprocessing
from ctypes import c_bool, c_int32
from typing import Dict

from lmao.module_wrapper import STATUS_NOT_INITIALIZED, STATUS_IDLE, STATUS_BUSY, STATUS_FAILED
from lmao.module_wrapper import MODULES as LMAO_MODULES

from google_ai_module import GoogleAIModule
from ms_copilot_module import MSCopilotModule
from ms_copilot_designer_module import MSCopilotDesignerModule

import messages
import users_handler
import request_response_container
from async_helper import async_helper
from bot_sender import send_message_async
from lmao_process_loop import LMAO_LOOP_DELAY, lmao_process_loop


# List of available modules (their names)
# LlM-Api-Open (LMAO) modules should start with lmao_
# See <https://github.com/F33RNI/LlM-Api-Open> for more info
MODULES = ["lmao_chatgpt", "chatgpt", "dalle", "ms_copilot", "ms_copilot_designer", "gemini"]

# Names of modules with conversation history (clearable)
MODULES_WITH_HISTORY = ["lmao_chatgpt", "chatgpt", "ms_copilot", "gemini"]

# Maximum time (in seconds) to wait for LMAO module to close before killing it's process
_LMAO_STOP_TIMEOUT = 10


class ModuleWrapperGlobal:
    def __init__(
        self,
        name: str,
        config: Dict,
        messages_: messages.Messages,
        users_handler_: users_handler.UsersHandler,
        logging_queue: multiprocessing.Queue,
    ) -> None:
        """Module's class initialization here (and LMAO process initialization)
        This is called from main process. Some other functions (see below) will be called from another processes

        Args:
            name (str): name of module to initialize (from MODULES)
            config (Dict): global config
            messages_ (messages.Messages): initialized messages wrapper
            users_handler_ (users_handler.UsersHandler): initialized users handler
            logging_queue (multiprocessing.Queue): initialized logging queue to handle logs from separate processes

        Raises:
            Exception: no module or module class __init__ error
        """
        if name not in MODULES:
            raise Exception(f"No module named {name}")
        self.name = name
        self.config = config
        self.messages = messages_
        self.users_handler = users_handler_
        self.logging_queue = logging_queue

        self.module = None

        ################
        # LMAO modules #
        ################
        # Use LMAO ModuleWrapper (initialization will be handled inside _lmao_process)
        # All crap below is to adopt non-multiprocessing LMAO
        # This will change if I switch LMAO to use multiprocessing instead of multithreading
        if name.startswith("lmao_"):
            self.name_lmao = name[5:]
            if self.name_lmao not in LMAO_MODULES:
                raise Exception(f"No lmao module named {self.name_lmao}")

            # LMAO process variables
            self._lmao_process_running = multiprocessing.Value(c_bool, False)
            self._lmao_stop_stream = multiprocessing.Value(c_bool, False)
            self._lmao_module_status = multiprocessing.Value(c_int32, STATUS_NOT_INITIALIZED)

            # Queue of user_id (int) to clear conversation
            self._lmao_delete_conversation_request_queue = multiprocessing.Queue(1)

            # Queue of Exception or user_id (same as for requests) as a result of deleting conversation
            self._lmao_delete_conversation_response_queue = multiprocessing.Queue(1)

            # Queue of RequestResponseContainer for LMAO modules
            self._lmao_request_queue = multiprocessing.Queue(1)
            self._lmao_response_queue = multiprocessing.Queue(1)

            # Queue of lmao Exceptions
            self._lmao_exceptions_queue = multiprocessing.Queue(-1)

            # Start LMAO process (LMAO modules needs to be loaded constantly so we need all that stuff at least for now)
            logging.info("Starting _lmao_process_loop as process")
            self._lmao_process = multiprocessing.Process(
                target=lmao_process_loop,
                args=(
                    self.name,
                    self.name_lmao,
                    self.config,
                    self.messages,
                    self.users_handler,
                    self.logging_queue,
                    self._lmao_process_running,
                    self._lmao_stop_stream,
                    self._lmao_module_status,
                    self._lmao_delete_conversation_request_queue,
                    self._lmao_delete_conversation_response_queue,
                    self._lmao_request_queue,
                    self._lmao_response_queue,
                    self._lmao_exceptions_queue,
                ),
            )
            with self._lmao_process_running.get_lock():
                self._lmao_process_running.value = True
            self._lmao_process.start()

            # Wait to initialize or error
            logging.info(f"Waiting for {self.name} initialization to finish")
            while True:
                try:
                    with self._lmao_module_status.get_lock():
                        module_status = self._lmao_module_status.value
                    if module_status == STATUS_IDLE or module_status == STATUS_FAILED:
                        logging.info(f"{self.name} initialization finished")
                        break
                    with self._lmao_process_running.get_lock():
                        process_running = self._lmao_process_running.value
                    if not process_running:
                        logging.info(f"{self.name} process finished")
                        break
                    time.sleep(LMAO_LOOP_DELAY)
                except (SystemExit, KeyboardInterrupt):
                    logging.warning("Interrupted")
                    break
                except Exception as e:
                    logging.error(f"Error waiting for {self.name} to initialize", exc_info=e)
                    break

        ##########
        # Gemini #
        ##########
        elif name == "gemini":
            self.module = GoogleAIModule(config, self.messages, self.users_handler)

        ##############
        # MS Copilot #
        ##############
        elif name == "ms_copilot":
            self.module = MSCopilotModule(config, self.messages, self.users_handler)

        #######################
        # MS Copilot Designer #
        #######################
        elif name == "ms_copilot_designer":
            self.module = MSCopilotDesignerModule(config, self.messages, self.users_handler)

    def process_request(self, request_response: request_response_container.RequestResponseContainer) -> None:
        """Processes request
        This is called from separate queue process (non main)

        Args:
            request_response (request_response_container.RequestResponseContainer): container from the queue

        Raises:
            Exception: process state / status or any other error
        """
        user_id = request_response.user_id
        lang_id = self.users_handler.get_key(user_id, "lang_id", "eng")

        # Read user's last timestamp (integer) and module's cooldown
        user_last_request_timestamp = self.users_handler.get_key(user_id, f"timestamp_{self.name}")
        user_cooldown_seconds = self.config.get(self.name).get("user_cooldown_seconds")

        # Check timeout
        if user_last_request_timestamp is not None and user_cooldown_seconds is not None:
            time_passed_seconds = int(time.time()) - user_last_request_timestamp

            # Send timeout message and exit
            if time_passed_seconds < user_cooldown_seconds:
                request_response.error = True
                logging.warning(f"User {user_id} sends {self.name} requests too quickly!")
                self._user_module_cooldown(
                    request_response, user_id, lang_id, user_cooldown_seconds - time_passed_seconds
                )
                return

        # Save current timestamp as integer
        self.users_handler.set_key(user_id, f"timestamp_{self.name}", int(time.time()))

        ################
        # LMAO modules #
        ################
        # Redirect request to LMAO process and wait
        if self.name.startswith("lmao_"):
            # Check status
            with self._lmao_process_running.get_lock():
                process_running = self._lmao_process_running.value
            if not process_running:
                raise Exception(f"{self.name} process is not running")
            with self._lmao_module_status.get_lock():
                module_status = self._lmao_module_status.value
            if module_status != STATUS_IDLE:
                raise Exception(f"{self.name} status is not idle")

            # Put to the queue
            self._lmao_request_queue.put(request_response)

            # Wait until it's processed or failed
            logging.info(f"Waiting for {self.name} request to be processed")
            time.sleep(1)
            while True:
                # Check process
                with self._lmao_process_running.get_lock():
                    process_running = self._lmao_process_running.value
                if not process_running:
                    raise Exception(f"{self.name} process stopped")

                # Check error and re-raise exception
                lmao_exception = None
                try:
                    lmao_exception = self._lmao_exceptions_queue.get(block=False)
                except queue.Empty:
                    pass
                if lmao_exception is not None:
                    raise lmao_exception

                # Check status
                with self._lmao_module_status.get_lock():
                    module_status = self._lmao_module_status.value
                if module_status == STATUS_IDLE:
                    break

                time.sleep(LMAO_LOOP_DELAY)

            # Update container
            # TODO: Optimize this
            response_ = None
            try:
                response_ = self._lmao_response_queue.get(block=True, timeout=1)
            except queue.Empty:
                logging.warning(f"Cannot get container back from {self.name} process")
            if response_:
                request_response.response_text = response_.response_text
                for response_image in response_.response_images:
                    request_response.response_images.append(response_image)
                request_response.response_timestamp = response_.response_timestamp
                request_response.response_send_timestamp_last = response_.response_send_timestamp_last
                request_response.processing_state = response_.processing_state
                request_response.message_id = response_.message_id
                request_response.reply_markup = response_.reply_markup
                request_response.processing_start_timestamp = response_.processing_start_timestamp
                request_response.error = response_.error
                request_response.response_next_chunk_start_index = response_.response_next_chunk_start_index
                request_response.response_sent_len = response_.response_sent_len

        ##########
        # Gemini #
        ##########
        elif self.name == "gemini":
            self.module.initialize()
            self.module.process_request(request_response)

        ##############
        # MS Copilot #
        ##############
        elif self.name == "ms_copilot":
            self.module.initialize()
            self.module.process_request(request_response)
            self.module.exit()

        #######################
        # MS Copilot Designer #
        #######################
        elif self.name == "ms_copilot_designer":
            self.module.initialize()
            self.module.process_request(request_response)

        # Done
        logging.info(f"{self.name} request processing finished")

    def _user_module_cooldown(
        self,
        request: request_response_container.RequestResponseContainer,
        user_id: int,
        lang_id: str,
        time_left_seconds: int,
    ) -> None:
        """Sends cooldown message to the user

        Args:
            request (request_response_container.RequestResponseContainer): container from the queue
            user_id (int): ID of user (to not get it from container again)
            lang_id (str): user's language (to not get it from container again)
            time_left_seconds (int): how much user needs to wait
        """
        # Calculate time left
        if time_left_seconds < 0:
            time_left_seconds = 0
        time_left_hours = time_left_seconds // 3600
        time_left_minutes = (time_left_seconds - (time_left_hours * 3600)) // 60
        time_left_seconds = time_left_seconds - (time_left_hours * 3600) - (time_left_minutes * 60)

        # Convert to string (ex. 1h 20m 9s)
        time_left_str = ""
        if time_left_hours > 0:
            if len(time_left_str) > 0:
                time_left_str += " "
            time_left_str += str(time_left_hours) + self.messages.get_message("hours", lang_id=lang_id)
        if time_left_minutes > 0:
            if len(time_left_str) > 0:
                time_left_str += " "
            time_left_str += str(time_left_minutes) + self.messages.get_message("minutes", lang_id=lang_id)
        if time_left_seconds > 0:
            if len(time_left_str) > 0:
                time_left_str += " "
            time_left_str += str(time_left_seconds) + self.messages.get_message("seconds", lang_id=lang_id)
        if time_left_str == "":
            time_left_str = "0" + self.messages.get_message("seconds", lang_id=lang_id)

        # Generate cooldown message
        module_id = self.users_handler.get_key(user_id, "module", self.config.get("modules").get("default"))
        module_icon_name = self.messages.get_message("modules", lang_id=lang_id).get(module_id)
        module_name = f"{module_icon_name.get('icon')} {module_icon_name.get('name')}"
        request.response_text = self.messages.get_message("user_cooldown_error", lang_id=lang_id).format(
            time_formatted=time_left_str, module_name=module_name
        )

        # Send this message
        async_helper(send_message_async(self.config.get("telegram"), self.messages, request, end=True))

    def stop_stream(self) -> None:
        """Stops response
        This is called from main process and it must NOT raise any errors
        """
        # Redirect to LMAO process
        if self.name.startswith("lmao_"):
            with self._lmao_stop_stream.get_lock():
                self._lmao_stop_stream.value = True

        # Gemini
        elif self.name == "gemini":
            with self.module.cancel_requested.get_lock():
                self.module.cancel_requested.value = True

        # MS Copilot
        elif self.name == "ms_copilot":
            with self.module.cancel_requested.get_lock():
                self.module.cancel_requested.value = True

    def delete_conversation(self, user_id: int) -> None:
        """Deletes module's conversation history
        This is called from main process and it MUST finish in a reasonable time
        So it's good to start processes here to make sure they finished in case of some 3rd party API needs heavy work

        Args:
            user_id (int): ID or user to delete conversation for

        Raises:
            Exception: process state / status or any other error
        """
        # Redirect to LMAO process and wait
        if self.name.startswith("lmao_"):
            # Check status
            with self._lmao_process_running.get_lock():
                process_running = self._lmao_process_running.value
            if not process_running:
                raise Exception(f"{self.name} process is not running")
            with self._lmao_module_status.get_lock():
                module_status = self._lmao_module_status.value
            if module_status != STATUS_IDLE:
                raise Exception(f"{self.name} status is not idle")

            # Put to the queue
            self._lmao_delete_conversation_request_queue.put(user_id)

            # Wait until it's processed or failed
            logging.info(f"Waiting for {self.name} to delete conversation")
            time.sleep(1)
            while True:
                # Check process
                with self._lmao_process_running.get_lock():
                    process_running = self._lmao_process_running.value
                if not process_running:
                    raise Exception(f"{self.name} process stopped")

                # Check error and re-raise exception
                delete_conversation_result = None
                try:
                    delete_conversation_result = self._lmao_delete_conversation_response_queue.get(block=False)
                except queue.Empty:
                    pass
                if delete_conversation_result is not None:
                    # OK
                    if isinstance(delete_conversation_result, int):
                        break

                    # Error -> re-raise exception
                    else:
                        raise delete_conversation_result

                time.sleep(LMAO_LOOP_DELAY)

        # Gemini
        elif self.name == "gemini":
            self.module.clear_conversation_for_user(user_id)

        # MS Copilot
        elif self.name == "ms_copilot":
            self.module.clear_conversation_for_user(user_id)

    def on_exit(self) -> None:
        """Calls module's post-stop actions (and closes LMAO module)
        This is called from main process

        Raises:
            Exception: process kill error
        """
        # Close LMAO module and stop it's process
        if self.name.startswith("lmao_"):
            # We don't need to do anything if process is not running
            with self._lmao_process_running.get_lock():
                process_running = self._lmao_process_running.value
            if not process_running:
                return

            # Read current status
            with self._lmao_module_status.get_lock():
                module_status = self._lmao_module_status.value

            # Request stream stop and wait a bit
            if module_status == STATUS_BUSY:
                with self._lmao_stop_stream.get_lock():
                    self._lmao_stop_stream.value = True
                time.sleep(1)

            # Ask for process to stop
            with self._lmao_process_running.get_lock():
                self._lmao_process_running.value = False

            # Wait or timeout
            logging.info(f"Waiting for {self.name} process to stop")
            time_started = time.time()
            while self._lmao_process.is_alive():
                if time.time() - time_started > _LMAO_STOP_TIMEOUT:
                    logging.info(f"Trying to kill {self.name} process")
                    self._lmao_process.kill()
                    break
                time.sleep(LMAO_LOOP_DELAY)
