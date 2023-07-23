"""
 Copyright (C) 2023 Fern Lane, GPT-Telegramus
 Licensed under the GNU Affero General Public License, Version 3.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
       https://www.gnu.org/licenses/agpl-3.0.en.html
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR
 OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
 ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import base64
import datetime
import gc
import logging
import multiprocessing
import os
import random
import threading
import time
from typing import List, Dict

import psutil
import requests

import BotHandler
import LoggingHandler
import ProxyAutomation
import RequestResponseContainer
import UsersHandler


def get_container_from_queue(request_response_queue: multiprocessing.Queue, lock: multiprocessing.Lock,
                             container_id: int) -> RequestResponseContainer.RequestResponseContainer | None:
    """
    Retrieves request_response_container from queue by ID without removing it
    :param request_response_queue: multiprocessing Queue to get container from
    :param lock: multiprocessing lock to prevent errors while updating the queue
    :param container_id: requested container ID
    :return: RequestResponseContainer or None if not exists
    """

    def get_container_from_queue_() -> RequestResponseContainer.RequestResponseContainer | None:
        # Convert entire queue to list
        queue_list = queue_to_list(request_response_queue)

        # Search container in list
        container = None
        for container__ in queue_list:
            if container__.id == container_id:
                container = container__
        return container

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            container_ = get_container_from_queue_()
        return container_

    # Get without lock
    else:
        return get_container_from_queue_()


def put_container_to_queue(request_response_queue: multiprocessing.Queue,
                           lock: multiprocessing.Lock,
                           request_response_container: RequestResponseContainer.RequestResponseContainer) -> int:
    """
    Generates unique container ID (if needed) and puts container to the queue (deletes previous one if exists)
    :param request_response_queue: multiprocessing Queue into which put the container
    :param lock: multiprocessing lock to prevent errors while updating the queue
    :param request_response_container: container to put into the queue
    :return: container ID
    """

    def put_container_to_queue_() -> int:
        # Delete previous one
        if request_response_container.id >= 0:
            remove_container_from_queue(request_response_queue, None, request_response_container.id)

        # Convert queue to lost
        queue_list = queue_to_list(request_response_queue)

        # Check if we need to generate a new ID for the container
        if request_response_container.id < 0:
            # Generate unique ID
            while True:
                container_id = random.randint(0, 2147483647)
                unique = True
                for container in queue_list:
                    if container.id == container_id:
                        unique = False
                        break
                if unique:
                    break

            # Set container id
            request_response_container.id = container_id

        # Add our container to the queue
        request_response_queue.put(request_response_container)

        return request_response_container.id

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            id_ = put_container_to_queue_()
        return id_

    # Put without lock
    else:
        return put_container_to_queue_()


def remove_container_from_queue(request_response_queue: multiprocessing.Queue,
                                lock: multiprocessing.Lock,
                                container_id: int) -> bool:
    """
    Tries to remove container by specific ID from the queue
    :param request_response_queue: multiprocessing Queue to remove container from
    :param lock: multiprocessing lock to prevent errors while updating the queue
    :param container_id: ID of container to remove from the queue
    :return: True if removed successfully, False if not
    """

    def remove_container_from_queue_() -> bool:
        # Convert entire queue to list
        queue_list = []
        while not request_response_queue.empty():
            queue_list.append(request_response_queue.get())

        # Flag to return
        removed = False

        # Convert list back to the queue without our container
        for container_ in queue_list:
            if container_.id != container_id:
                request_response_queue.put(container_)
            else:
                removed = True

        return removed

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            removed_ = remove_container_from_queue_()
        return removed_

    # Remove without lock
    else:
        return remove_container_from_queue_()


def queue_to_list(request_response_queue: multiprocessing.Queue) -> list:
    """
    Retrieves all elements from queue and returns them as list
    NOTE: THIS FUNCTION MUST BE CALLED INSIDE LOCK
    :param request_response_queue: multiprocessing Queue to convert to list
    :return: list of queue elements
    """
    queue_list = []

    # Convert entire queue to list
    while request_response_queue.qsize() > 0:
        container = request_response_queue.get()
        if container not in queue_list:
            queue_list.append(container)

    # Convert list back to the queue
    for container_ in queue_list:
        request_response_queue.put(container_)

    # Return list
    return queue_list


def _user_module_cooldown(config: dict,
                          messages: List[Dict],
                          request: RequestResponseContainer,
                          time_left_seconds: int) -> None:
    """
    Sends cooldown message to the user
    :param config:
    :param messages:
    :param request:
    :param time_left_seconds:
    :return:
    """
    # Get user language
    lang = UsersHandler.get_key_or_none(request.user, "lang", 0)

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
        time_left_str += str(time_left_hours) + messages[lang]["hours"]
    if time_left_minutes > 0:
        if len(time_left_str) > 0:
            time_left_str += " "
        time_left_str += str(time_left_minutes) + messages[lang]["minutes"]
    if time_left_seconds > 0:
        if len(time_left_str) > 0:
            time_left_str += " "
        time_left_str += str(time_left_seconds) + messages[lang]["seconds"]
    if time_left_str == "":
        time_left_str = "0" + messages[lang]["seconds"]

    # Generate cooldown message
    request.response = messages[lang]["user_cooldown_error"].replace("\\n", "\n") \
        .format(time_left_str,
                messages[lang]["modules"][request.request_type])

    # Send this message
    BotHandler.async_helper(BotHandler.send_message_async(config, messages, request, end=True))


def _request_processor(config: dict,
                       messages: List[Dict],
                       logging_queue: multiprocessing.Queue,
                       users_handler: UsersHandler,
                       request_response_queue: multiprocessing.Queue,
                       lock: multiprocessing.Lock,
                       request_id: int,
                       proxy: str,
                       chatgpt_module, dalle_module, bard_module, edgegpt_module, bing_image_gen_module) -> None:
    """
    Processes request to any module
    This method should be called from multiprocessing as process
    :return:
    """
    # Setup logging for current process
    LoggingHandler.worker_configurer(logging_queue)

    # Get request
    request_ = get_container_from_queue(request_response_queue, lock, request_id)

    # Check request
    if request_ is None:
        logging.error("Error retrieving container from the queue!")
        return

    try:
        # Set active state
        request_.processing_state = RequestResponseContainer.PROCESSING_STATE_ACTIVE

        # Increment requests_total for statistics
        request_.user["requests_total"] += 1

        # Save request data (for regenerate function)
        request_.user["request_last"] = request_.request
        request_.user["reply_message_id_last"] = request_.reply_message_id

        # Save user
        users_handler.save_user(request_.user)

        # Update container in the queue
        put_container_to_queue(request_response_queue, lock, request_)

        # ChatGPT
        if request_.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
            chatgpt_user_last_request_timestamp = UsersHandler.get_key_or_none(request_.user, "timestamp_chatgpt", 0)
            time_passed_seconds = int(time.time()) - chatgpt_user_last_request_timestamp
            if time_passed_seconds < config["chatgpt"]["user_cooldown_seconds"]:
                request_.error = True
                logging.warning("User {0} sends ChatGPT requests too quickly!".format(request_.user["user_id"]))
                _user_module_cooldown(config, messages, request_,
                                      config["chatgpt"]["user_cooldown_seconds"] - time_passed_seconds)
            else:
                request_.user["timestamp_chatgpt"] = int(time.time())
                users_handler.save_user(request_.user)
                proxy_ = None
                if proxy and config["chatgpt"]["proxy"] == "auto":
                    proxy_ = proxy
                chatgpt_module.initialize(proxy_)
                chatgpt_module.process_request(request_)
                chatgpt_module.exit()

        # DALL-E
        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_DALLE:
            dalle_user_last_request_timestamp = UsersHandler.get_key_or_none(request_.user, "timestamp_dalle", 0)
            time_passed_seconds = int(time.time()) - dalle_user_last_request_timestamp
            if time_passed_seconds < config["dalle"]["user_cooldown_seconds"]:
                request_.error = True
                logging.warning("User {0} sends DALL-E requests too quickly!".format(request_.user["user_id"]))
                _user_module_cooldown(config, messages, request_,
                                      config["dalle"]["user_cooldown_seconds"] - time_passed_seconds)
            else:
                request_.user["timestamp_dalle"] = int(time.time())
                users_handler.save_user(request_.user)
                proxy_ = None
                if proxy and config["dalle"]["proxy"] == "auto":
                    proxy_ = proxy
                dalle_module.initialize(proxy_)
                dalle_module.process_request(request_)

        # EdgeGPT
        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT:
            edgegpt_user_last_request_timestamp = UsersHandler.get_key_or_none(request_.user, "timestamp_edgegpt", 0)
            time_passed_seconds = int(time.time()) - edgegpt_user_last_request_timestamp
            if time_passed_seconds < config["edgegpt"]["user_cooldown_seconds"]:
                request_.error = True
                logging.warning("User {0} sends EdgeGPT requests too quickly!".format(request_.user["user_id"]))
                _user_module_cooldown(config, messages, request_,
                                      config["edgegpt"]["user_cooldown_seconds"] - time_passed_seconds)
            else:
                request_.user["timestamp_edgegpt"] = int(time.time())
                users_handler.save_user(request_.user)
                proxy_ = None
                if proxy and config["edgegpt"]["proxy"] == "auto":
                    proxy_ = proxy
                edgegpt_module.initialize(proxy_)
                edgegpt_module.process_request(request_)
                edgegpt_module.exit()

        # Bard
        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_BARD:
            bard_user_last_request_timestamp = UsersHandler.get_key_or_none(request_.user, "timestamp_bard", 0)
            time_passed_seconds = int(time.time()) - bard_user_last_request_timestamp
            if time_passed_seconds < config["bard"]["user_cooldown_seconds"]:
                request_.error = True
                logging.warning("User {0} sends Bard requests too quickly!".format(request_.user["user_id"]))
                _user_module_cooldown(config, messages, request_,
                                      config["bard"]["user_cooldown_seconds"] - time_passed_seconds)
            else:
                request_.user["timestamp_bard"] = int(time.time())
                users_handler.save_user(request_.user)
                proxy_ = None
                if proxy and config["bard"]["proxy"] == "auto":
                    proxy_ = proxy
                bard_module.initialize(proxy_)
                bard_module.process_request(request_)
                bard_module.exit()

        # Bing ImageGen
        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_BING_IMAGEGEN:
            bing_imagegen_user_last_request_timestamp \
                = UsersHandler.get_key_or_none(request_.user, "timestamp_bing_imagegen", 0)
            time_passed_seconds = int(time.time()) - bing_imagegen_user_last_request_timestamp
            if time_passed_seconds < config["bing_imagegen"]["user_cooldown_seconds"]:
                request_.error = True
                logging.warning("User {0} sends BingImageGen requests too quickly!".format(request_.user["user_id"]))
                _user_module_cooldown(config, messages, request_,
                                      config["bing_imagegen"]["user_cooldown_seconds"] - time_passed_seconds)
            else:
                request_.user["timestamp_bing_imagegen"] = int(time.time())
                users_handler.save_user(request_.user)
                proxy_ = None
                if proxy and config["bing_imagegen"]["proxy"] == "auto":
                    proxy_ = proxy
                bing_image_gen_module.initialize(proxy_)
                bing_image_gen_module.process_request(request_)

        # Wrong API type
        else:
            raise Exception("Wrong request type: {0}".format(request_.request_type))

    # Error during processing request
    except Exception as e:
        request_.error = True
        lang = UsersHandler.get_key_or_none(request_.user, "lang", 0)
        request_.response = messages[lang]["response_error"].replace("\\n", "\n").format(str(e))
        BotHandler.async_helper(BotHandler.send_message_async(config, messages, request_, end=True))
        logging.error("Error processing request!", exc_info=e)

    # Set done state
    request_.processing_state = RequestResponseContainer.PROCESSING_STATE_DONE

    # Finally, update container in the queue
    put_container_to_queue(request_response_queue, lock, request_)


class QueueHandler:
    def __init__(self, config: dict,
                 messages: List[Dict],
                 logging_queue: multiprocessing.Queue,
                 users_handler: UsersHandler,
                 proxy_automation: ProxyAutomation.ProxyAutomation,
                 chatgpt_module, dalle_module, bard_module, edgegpt_module, bing_image_gen_module):
        self.config = config
        self.messages = messages
        self.logging_queue = logging_queue
        self.users_handler = users_handler
        self.proxy_automation = proxy_automation
        self.bing_image_gen_module = bing_image_gen_module

        # Modules
        self.chatgpt_module = chatgpt_module
        self.dalle_module = dalle_module
        self.bard_module = bard_module
        self.edgegpt_module = edgegpt_module

        # Requests queue
        self.request_response_queue = multiprocessing.Queue(maxsize=-1)
        self.lock = multiprocessing.Lock()

        self._exit_flag = False
        self._processing_loop_thread = None
        self._log_filename = ""

    def start_processing_loop(self) -> None:
        """
        Starts _queue_processing_loop and _process_monitor_loop as new threads
        :return:
        """
        self._processing_loop_thread = threading.Thread(target=self._queue_processing_loop)
        self._processing_loop_thread.start()
        logging.info("queue_processing_loop thread: {0}".format(self._processing_loop_thread.name))

    def stop_processing_loop(self) -> None:
        """
        Stops _queue_processing_loop and _process_monitor_loop
        :return:
        """
        if self._processing_loop_thread and self._processing_loop_thread.is_alive():
            logging.warning("Stopping queue_processing_loop")
            self._exit_flag = True
            self._processing_loop_thread.join()

    def _queue_processing_loop(self) -> None:
        """
        Gets request or response from self.requests_queue or self.responses_queue and processes it
        :return:
        """
        logging.info("Starting queue_processing_loop")
        self._exit_flag = False
        while not self._exit_flag:
            try:
                # Skip one cycle in queue is empty
                if self.request_response_queue.qsize() == 0:
                    time.sleep(0.1)
                    continue

                # Lock queue
                self.lock.acquire()

                # Convert queue to list
                queue_list = queue_to_list(self.request_response_queue)

                # Look in entire queue (list)
                for request_ in queue_list:
                    # Check if we're not processing this request yet
                    if request_.processing_state == RequestResponseContainer.PROCESSING_STATE_IN_QUEUE:
                        # Check if requested module is busy
                        module_busy = False
                        for request__ in queue_list:
                            if request__.request_type == request_.request_type \
                                    and request__.pid > 0 and psutil.pid_exists(request__.pid):
                                module_busy = True
                                break

                        # Module is available. We can process this request
                        if not module_busy:
                            # Set initializing state
                            request_.processing_state = RequestResponseContainer.PROCESSING_STATE_INITIALIZING

                            # Set current time (for timout control)
                            request_.processing_start_timestamp = time.time()

                            # Log request
                            logging.info("New request from user: {0} ({1})".format(request_.user["user_name"],
                                                                                   request_.user["user_id"]))
                            self._collect_data(request_, log_request=True)

                            # Create process for queue object
                            request_process = multiprocessing.Process(target=_request_processor,
                                                                      args=(self.config,
                                                                            self.messages,
                                                                            self.logging_queue,
                                                                            self.users_handler,
                                                                            self.request_response_queue,
                                                                            self.lock,
                                                                            request_.id,
                                                                            self.proxy_automation.working_proxy,
                                                                            self.chatgpt_module,
                                                                            self.dalle_module,
                                                                            self.bard_module,
                                                                            self.edgegpt_module,
                                                                            self.bing_image_gen_module,))

                            # Start process
                            request_process.start()

                            # Set process PID to the container
                            request_.pid = request_process.pid

                            # Update
                            put_container_to_queue(self.request_response_queue, None, request_)

                    # Request is currently processing -> check timeout
                    if request_.processing_state > RequestResponseContainer.PROCESSING_STATE_IN_QUEUE:
                        # Get maximum time from config
                        timeout_seconds = 0
                        if request_.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
                            timeout_seconds = self.config["chatgpt"]["timeout_seconds"]
                        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT:
                            timeout_seconds = self.config["edgegpt"]["timeout_seconds"]
                        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_DALLE:
                            timeout_seconds = self.config["dalle"]["timeout_seconds"]
                        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_BARD:
                            timeout_seconds = self.config["bard"]["timeout_seconds"]
                        elif request_.request_type == RequestResponseContainer.REQUEST_TYPE_BING_IMAGEGEN:
                            timeout_seconds = self.config["bing_imagegen"]["timeout_seconds"]

                        # Check timeout
                        if time.time() - request_.processing_start_timestamp > timeout_seconds:
                            # Log warning
                            logging.warning("Request from user {0} to {1} timed out!"
                                            .format(request_.user["user_id"],
                                                    RequestResponseContainer.REQUEST_NAMES[request_.request_type]))

                            # Set timeout status and message
                            request_.processing_state = RequestResponseContainer.PROCESSING_STATE_TIMED_OUT
                            request_.response = "Timed out (>{} s)".format(timeout_seconds)
                            request_.error = True

                            # Update
                            put_container_to_queue(self.request_response_queue, None, request_)

                            # Send timeout message
                            BotHandler.async_helper(BotHandler.send_message_async(self.config,
                                                                                  self.messages,
                                                                                  request_,
                                                                                  end=True))

                    # Cancel generating
                    if request_.processing_state == RequestResponseContainer.PROCESSING_STATE_CANCEL:
                        # Request ChatGPT module exit
                        if request_.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
                            logging.info("Canceling ChatGPT module")
                            self.chatgpt_module.cancel_requested.value = True

                        # Request EdgeGPT module exit
                        if request_.request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT:
                            logging.info("Canceling EdgeGPT module")
                            self.edgegpt_module.cancel_requested.value = True

                        # Set canceling flag
                        request_.processing_state = RequestResponseContainer.PROCESSING_STATE_CANCELING

                        # Update
                        put_container_to_queue(self.request_response_queue, None, request_)

                    # Done processing / Timed out -> log data and finally remove it
                    if request_.processing_state == RequestResponseContainer.PROCESSING_STATE_DONE \
                            or request_.processing_state == RequestResponseContainer.PROCESSING_STATE_TIMED_OUT:
                        # Kill process if it is active
                        if request_.pid > 0 and psutil.pid_exists(request_.pid):
                            logging.info("Trying to kill process with PID {}".format(request_.pid))
                            try:
                                process = psutil.Process(request_.pid)
                                process.terminate()
                                process.kill()
                                process.wait(timeout=5)
                            except Exception as e:
                                logging.error("Error killing process with PID {}".format(request_.pid), exc_info=e)
                            logging.info("Killed? {}".format(not psutil.pid_exists(request_.pid)))

                        # Set response timestamp (for data collecting)
                        response_timestamp = ""
                        if self.config["data_collecting"]["enabled"]:
                            response_timestamp = datetime.datetime.now() \
                                .strftime(self.config["data_collecting"]["timestamp_format"])
                        request_.response_timestamp = response_timestamp

                        # Log response
                        self._collect_data(request_, log_request=False)

                        # Remove from queue
                        logging.info("Container with id {0} (PID {1}) was removed from the queue"
                                     .format(request_.id, request_.pid))
                        remove_container_from_queue(self.request_response_queue, None, request_.id)

                        # Collect garbage
                        gc.collect()

                # Unlock the queue
                self.lock.release()

                # Sleep 100ms before next cycle
                time.sleep(0.1)

            # Exit requested
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt @ queue_processing_loop")
                self._exit_flag = True

                # Kill all active processes
                with self.lock:
                    queue_list = queue_to_list(self.request_response_queue)
                    for container in queue_list:
                        if container.pid > 0 and psutil.pid_exists(container.pid):
                            logging.info("Trying to kill process with PID {}".format(container.pid))
                            try:
                                process = psutil.Process(container.pid)
                                process.terminate()
                                process.kill()
                                process.wait(timeout=5)
                            except Exception as e:
                                logging.error("Error killing process with PID {}".format(container.pid), exc_info=e)
                            logging.info("Killed? {}".format(not psutil.pid_exists(container.pid)))

                        remove_container_from_queue(self.request_response_queue, None, container.id)

                # Collect garbage
                gc.collect()

                # Exit from loop
                break

            # Oh no, error! Why?
            except Exception as e:
                logging.error("Error processing queue!", exc_info=e)
                time.sleep(1)

        logging.warning("queue_processing_loop finished")

    def _collect_data(self, request_response: RequestResponseContainer, log_request=True):
        """
        Logs requests and responses (collects data)
        :param request_response: container to log data from
        :param log_request: True to log request, False to log response
        :return:
        """
        # Skip data collecting
        if not self.config["data_collecting"]["enabled"]:
            return

        # Create new filename
        if not self._log_filename or len(self._log_filename) < 1 or not os.path.exists(self._log_filename):
            if not os.path.exists(self.config["files"]["data_collecting_dir"]):
                os.makedirs(self.config["files"]["data_collecting_dir"])

            file_timestamp = datetime.datetime.now() \
                .strftime(self.config["data_collecting"]["filename_timestamp_format"])
            self._log_filename = os.path.join(self.config["files"]["data_collecting_dir"],
                                              file_timestamp + self.config["data_collecting"]["filename_extension"])
            logging.info("New file for data collecting: {0}".format(self._log_filename))

        # Open log file for appending
        log_file = open(self._log_filename, "a", encoding="utf8")

        try:
            # Log request
            if log_request:
                request_str_to_format = self.config["data_collecting"]["request_format"].replace("\\n", "\n") \
                    .replace("\\t", "\t").replace("\\r", "\r")
                log_file.write(request_str_to_format.format(request_response.request_timestamp,
                                                            request_response.id,
                                                            request_response.user["user_name"],
                                                            request_response.user["user_id"],
                                                            RequestResponseContainer
                                                            .REQUEST_NAMES[request_response.request_type],
                                                            request_response.request))

            # Log response
            else:
                # DALL-E or BingImageGen response without error
                if (request_response.request_type == RequestResponseContainer.REQUEST_TYPE_DALLE
                    or request_response.request_type == RequestResponseContainer.REQUEST_TYPE_BING_IMAGEGEN) \
                        and not request_response.error:
                    response = base64.b64encode(requests.get(request_response.response, timeout=120).content) \
                        .decode("utf-8")

                # Text response (ChatGPT, EdgeGPT, Bard)
                else:
                    response = request_response.response

                # Log response
                response_str_to_format = self.config["data_collecting"]["response_format"].replace("\\n", "\n") \
                    .replace("\\t", "\t").replace("\\r", "\r")
                log_file.write(response_str_to_format.format(request_response.response_timestamp,
                                                             request_response.id,
                                                             request_response.user["user_name"],
                                                             request_response.user["user_id"],
                                                             RequestResponseContainer
                                                             .REQUEST_NAMES[request_response.request_type],
                                                             response))

            # Log confirmation
            logging.info("The {0} were written to the file: {1}".format("request" if log_request else "response",
                                                                        self._log_filename))

        # Error processing or logging data
        except Exception as e:
            logging.error("Error collecting data!", exc_info=e)

        # Close file
        if log_file:
            try:
                log_file.close()
            except Exception as e:
                logging.error("Error closing file for data collecting!", exc_info=e)

        # Start new file if length exceeded requested value
        if self._log_filename and os.path.exists(self._log_filename):
            file_size = os.path.getsize(self._log_filename)
            if file_size > self.config["data_collecting"]["max_size"]:
                logging.info("File {0} has size {1} bytes which is more than {2}. New file will be started!"
                             .format(self._log_filename, file_size, self.config["data_collecting"]["max_size"]))
                self._log_filename = ""
