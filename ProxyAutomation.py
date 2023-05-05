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
import multiprocessing
import random
import threading
import time
from queue import Empty
from urllib import request

import requests

import BardModule
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import useragents

PROXY_FROM_URL = "http://free-proxy-list.net/"


def proxy_tester_process(test_proxy_queue: multiprocessing.Queue,
                         working_proxy_queue: multiprocessing.Queue,
                         check_url: str, timeout) -> None:
    """
    multiprocessing process to test proxy
    :param test_proxy_queue:
    :param working_proxy_queue:
    :param check_url:
    :param timeout:
    :return:
    """
    # Initialize session object
    session = requests.Session()
    session.headers.update({"User-agent": "Mozilla/5.0"})

    try:
        # Test all proxies until there is no more proxies to test
        while not test_proxy_queue.empty():
            # Get proxy to test
            proxy_to_test = test_proxy_queue.get(block=True, timeout=1)

            # Is it correct proxy?
            if proxy_to_test:
                # Set proxies
                session.proxies.update({"http": proxy_to_test,
                                        "https": proxy_to_test})
                try:
                    # Try to send GET request to https google
                    response = session.get(check_url, timeout=timeout)

                    # Check result
                    if len(str(response.headers)) > 1:
                        # Put working proxy to the queue
                        working_proxy_queue.put(proxy_to_test, block=True, timeout=1)

                # Ignore error
                except:
                    pass

    # Just exit on interrupt or error
    except KeyboardInterrupt:
        pass
    except Exception:
        pass

    # Close current session
    session.close()


def clear_queue(queue: multiprocessing.Queue) -> None:
    """
    Clears multiprocessing queue
    :param queue:
    :return:
    """
    # Clear queue
    try:
        while True:
            queue.get_nowait()
    except Empty:
        pass


class ProxyAutomation:
    def __init__(self, config,
                 chatgpt_module: ChatGPTModule.ChatGPTModule,
                 dalle_module: DALLEModule.DALLEModule,
                 edgegpt_module: EdgeGPTModule.EdgeGPTModule,
                 bard_module: BardModule.BardModule) -> None:
        self.config = config

        self.chatgpt_module = chatgpt_module
        self.dalle_module = dalle_module
        self.edgegpt_module = edgegpt_module
        self.bard_module = bard_module

        self.working_proxy = ""

        self._proxy_list = []
        self._test_proxy_queue = multiprocessing.Queue()
        self._working_proxy_queue = multiprocessing.Queue()
        self._processes = []
        self._exit_flag = False
        self._automation_loop_thread = None

    def start_automation_loop(self) -> None:
        """
        Starts _automation_loop as new thread
        :return:
        """
        if self.config["proxy_automation"]["enabled"]:
            self._automation_loop_thread = threading.Thread(target=self._automation_loop)
            self._automation_loop_thread.start()
            logging.info("automation_loop thread: {0}".format(self._automation_loop_thread.name))

    def stop_automation_loop(self) -> None:
        """
        Stops _automation_loop_loop
        :return:
        """
        if self._automation_loop_thread and self._automation_loop_thread.is_alive():
            logging.warning("Stopping automation_loop")
            self._exit_flag = True
            self._automation_loop_thread.join()

    def _automation_loop(self) -> None:
        """
        Continuously tries to search for a new working proxy
        :return:
        """
        # Time of last proxy check
        last_check_time = 0

        logging.info("Starting proxy automation loop")
        self._exit_flag = False
        while not self._exit_flag:
            try:
                # Clear current working proxy
                self.working_proxy = ""

                # Get list of proxies
                self._proxy_get()

                # Clear queues
                clear_queue(self._test_proxy_queue)
                clear_queue(self._working_proxy_queue)

                # Add proxies to text
                for proxy in self._proxy_list:
                    self._test_proxy_queue.put(proxy, block=True)

                # Start checkers
                self._processes = []
                for i in range(min(multiprocessing.cpu_count(), len(self._proxy_list))):
                    process = multiprocessing.Process(target=proxy_tester_process,
                                                      args=(self._test_proxy_queue,
                                                            self._working_proxy_queue,
                                                            self.config["proxy_automation"]["check_url"],
                                                            self.config["proxy_automation"]["check_timeout_seconds"]))
                    self._processes.append(process)
                    process.start()
                logging.info("Total processes: {0}".format(len(self._processes)))

                # Get first working proxy
                logging.info("Trying to find working proxy")
                while True:
                    try:
                        # Remove finished processes
                        for process in self._processes:
                            if not process or not process.is_alive():
                                self._processes.remove(process)

                        # Exit form waiting loop if no more processes or exit_flag
                        if len(self._processes) == 0 or self._exit_flag:
                            break

                        # Try to get first working proxy
                        working_proxy = None
                        try:
                            working_proxy = self._working_proxy_queue.get(block=True, timeout=0.1)
                        except Empty:
                            pass

                        # Check it
                        if working_proxy:
                            self.working_proxy = working_proxy
                            logging.info("Found working proxy: {0}".format(self.working_proxy))

                            # Stop checkers
                            self._kill_processes()

                            # Set last check time
                            last_check_time = time.time()

                            # Run callback function
                            self._apply_new_proxy()

                            # Exit from waiting loop
                            break

                    # Exit requested
                    except KeyboardInterrupt:
                        # Stop checkers
                        self._kill_processes()

                        # Exit from waiting loop
                        break

                # Exit from main loop if requested
                if self._exit_flag:
                    break

                # Loop for checking if proxy is still working, or we need to find a new one
                while True:
                    # Exit from current loop if requested
                    if self._exit_flag:
                        break

                    # Sleep until we need to check
                    if time.time() - last_check_time < self.config["proxy_automation"]["check_interval_seconds"]:
                        time.sleep(1)
                        continue

                    # Check current proxy
                    logging.info("Checking current proxy: {0}".format(self.working_proxy))
                    is_proxy_working = False
                    session = requests.Session()
                    session.headers.update({"User-agent": "Mozilla/5.0"})
                    session.proxies.update({"http": self.working_proxy,
                                            "https": self.working_proxy})
                    try:
                        response = session.get(self.config["proxy_automation"]["check_url"],
                                               timeout=self.config["proxy_automation"]["check_timeout_seconds"])
                        is_proxy_working = len(str(response.headers)) > 1
                    except Exception as e:
                        logging.error("Error checking proxy: {0}".format(str(e)))
                    session.close()

                    # OK?
                    if is_proxy_working:
                        last_check_time = time.time()
                        logging.info("Proxy checked successfully")

                    # We need to find a new proxy
                    else:
                        break

                # Exit from main loop if requested
                if self._exit_flag:
                    break

            # Exit requested
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt @ automation_loop")
                break

            # Oh no, error! Why?
            except Exception as e:
                logging.error("Error searching for a working proxy!", exc_info=e)
                time.sleep(1)

        # Kill background processes
        self._kill_processes()

        # Done
        logging.warning("queue_processing_loop finished")

    def _apply_new_proxy(self) -> None:
        """
        This function will be called if a new working proxy (self.working_proxy) is found
        :return:
        """
        self.chatgpt_module.set_proxy(self.working_proxy)
        self.dalle_module.set_proxy(self.working_proxy)
        self.edgegpt_module.set_proxy(self.working_proxy)
        self.bard_module.set_proxy(self.working_proxy)

    def _kill_processes(self) -> None:
        """
        Kills all processes by their PIDs
        :return:
        """
        for process in self._processes:
            if process is not None and process.is_alive():
                logging.info("Killing process with PID: " + str(process.pid))
                try:
                    process.kill()
                    process.join()
                except Exception as e:
                    logging.warning("Error killing process with PID: {0}".format(process.pid), exc_info=e)

    def _proxy_get(self) -> None:
        """
        Retrieves proxy from auto_proxy_from url into self.proxy_list
        :return:
        """
        # Reset proxy list
        self._proxy_list = []

        # Try to get proxy
        try:
            logging.info("Trying to get proxy list from: {0}".format(PROXY_FROM_URL))
            req = request.Request("%s" % PROXY_FROM_URL)
            req.add_header("User-Agent", random.choice(useragents.USERAGENTS))
            sourcecode = request.urlopen(req)
            part = str(sourcecode.read()).replace(" ", "")
            part = part.split("<tbody>")
            part = part[1].split("</tbody>")
            part = part[0].split("<tr><td>")
            for proxy_ in part:
                proxy_ = proxy_.split("/td><td")
                try:
                    # Get proxy parts
                    ip = proxy_[0].replace(">", "").replace("<", "").strip()
                    port = proxy_[1].replace(">", "").replace("<", "").strip()
                    is_https = "yes" in proxy_[6].lower()

                    # Check data and append to list
                    if len(ip.split(".")) == 4 and len(port) > 1 and is_https:
                        self._proxy_list.append("http://" + ip + ":" + port)
                except:
                    pass
            if len(self._proxy_list) > 1:
                logging.info("Proxies downloaded successfully")
            else:
                logging.warning("Proxies list is empty!")
        except Exception as e:
            logging.error("Error downloading proxy list!", exc_info=e)
