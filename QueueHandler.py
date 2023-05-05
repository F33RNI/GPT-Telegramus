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

import logging
import queue
import threading
import time

import BardModule
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import RequestResponseContainer


class QueueHandler:
    def __init__(self, config: dict,
                 chatgpt_module: ChatGPTModule.ChatGPTModule,
                 dalle_module: DALLEModule.DALLEModule,
                 edgegpt_module: EdgeGPTModule.EdgeGPTModule,
                 bard_module: BardModule.BardModule):
        self.config = config
        self.chatgpt_module = chatgpt_module
        self.dalle_module = dalle_module
        self.edgegpt_module = edgegpt_module
        self.bard_module = bard_module

        self.requests_queue = queue.Queue(maxsize=self.config["telegram"]["queue_max"])
        self.responses_queue = queue.Queue(maxsize=self.config["telegram"]["queue_max"])

        self._exit_flag = False
        self._processing_loop_thread = None
        self._request_response = None

    def start_processing_loop(self) -> None:
        """
        Starts _queue_processing_loop as new thread
        :return:
        """
        self._processing_loop_thread = threading.Thread(target=self._queue_processing_loop)
        self._processing_loop_thread.start()
        logging.info("queue_processing_loop thread: {0}".format(self._processing_loop_thread.name))

    def stop_processing_loop(self) -> None:
        """
        Stops _queue_processing_loop
        :return:
        """
        if self._processing_loop_thread and self._processing_loop_thread.is_alive():
            logging.warning("Stopping queue_processing_loop")
            self._exit_flag = True
            self._processing_loop_thread.join()

    def get_queue_list(self) -> list:
        """
        Gets queue including currently processing request
        :return:
        """
        queue_list = []
        try:
            for i in range(self.requests_queue.qsize()):
                queue_list.append(self.requests_queue.queue[i])
        except:
            pass

        if self._request_response is not None:
            queue_list.insert(0, self._request_response)

        return queue_list

    def _queue_processing_loop(self) -> None:
        """
        Loop that gets containers from requests_queue, processes them and puts into responses_queue
        :return:
        """
        logging.info("Starting queue_processing_loop")
        self._exit_flag = False
        while not self._exit_flag:
            try:
                # Wait until request and get it or exit
                request_response = None
                while True:
                    try:
                        request_response = self.requests_queue.get(block=True, timeout=1)
                        break
                    except queue.Empty:
                        if self._exit_flag:
                            break
                    except KeyboardInterrupt:
                        self._exit_flag = True
                        break
                if self._exit_flag or request_response is None:
                    break

                # Set currently processing container
                self._request_response = request_response

                # Log request
                logging.info("New request from user: {0} ({1})".format(request_response.user["user_name"],
                                                                       request_response.user["user_id"]))

                # ChatGPT
                if request_response.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
                    self.chatgpt_module.process_request(request_response)

                # DALL-E
                elif request_response.request_type == RequestResponseContainer.REQUEST_TYPE_DALLE:
                    self.dalle_module.process_request(request_response)

                # EdgeGPT
                elif request_response.request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT:
                    self.edgegpt_module.process_request(request_response)

                # Bard
                elif request_response.request_type == RequestResponseContainer.REQUEST_TYPE_BARD:
                    self.bard_module.process_request(request_response)

                # Wrong API type
                else:
                    request_response.error = True
                    request_response.response = "Wrong request type: {0}".format(request_response.request_type)
                    logging.warning("Wrong request type: {0}".format(request_response.request_type))

                # Put into responses_queue
                self.responses_queue.put(request_response)

                # Clear currently processing container
                self._request_response = None

            # Exit requested
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt @ queue_processing_loop")
                break

            # Oh no, error! Why?
            except Exception as e:
                logging.error("Error processing queue!", exc_info=e)
                time.sleep(1)

        logging.warning("queue_processing_loop finished")
