"""
 Copyright (C) 2022 Fern Lane, GPT-telegramus
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
import copy
import logging
import multiprocessing
import os
import random
import threading
import time
from urllib import request

import useragents

PROXY_FROM_URL = 'http://free-proxy-list.net/'

TOO_MANY_REQUESTS_MESSAGE = 'Too many requests in 1 hour'


def kill_all_processes(processes_and_times):
    """
    Kills all processes
    :param processes_and_times: list of (process, time_started)
    :return:
    """
    for (process_, time_) in processes_and_times:
        if process_ is not None and time_ is not None and process_.is_alive():
            logging.info('Killing process with PID: ' + str(process_.pid))
            try:
                process_.kill()
                process_.join()
            except:
                logging.warning('Error killing process with PID: ' + str(process_.pid))


def initialize_chatbot(base_url, proxy, config, chatbots_and_proxies_queue):
    """
    Pops first proxy and tries to initialize chatbot
    :return:
    """
    try:
        # Get config
        config_ = copy.deepcopy(config)
        config_['proxy'] = proxy

        # Initialize chatbot
        if base_url is not None and len(str(base_url)) > 0:
            os.environ['CHATGPT_BASE_URL'] = str(base_url)
        from revChatGPT.V1 import Chatbot
        chatbot = Chatbot(config=config_)

        # Append working chatbot and proxy
        if chatbot is not None:
            chatbots_and_proxies_queue.put((chatbot, proxy))
    except:
        pass


class Authenticator:
    def __init__(self, settings):
        self.settings = settings

        self.api_type = 0
        self.chatbot = None
        self.chatbot_locked = False
        self.chatbot_too_many_requests = False
        self.chatbot_working = False
        self.chatbots_and_proxies_queue = multiprocessing.Queue(maxsize=int(self.settings['chatgpt_api_1']['proxy']
                                                                            ['max_number_of_processes']) * 2)
        self.current_proxy = None
        self.conversation_id = None
        self.proxy_list = []
        self.check_loop_running = False

    def start_check_loop(self):
        """
        Starts background thread
        :return:
        """
        # Official API
        if int(self.settings['modules']['chatgpt_api_type']) == 0:
            self.api_type = 0
            # Proxy
            proxy_ = str(self.settings['chatgpt_api_0']['proxy'])
            if len(proxy_) > 0:
                self.current_proxy = proxy_
            try:
                from revChatGPT.V0 import Chatbot
                # Initialize chatbot
                self.chatbot = Chatbot(str(self.settings['chatgpt_api_0']['open_ai_api_key']),
                                       engine=str(self.settings['chatgpt_api_0']['engine']),
                                       proxy=proxy_)
                self.chatbot_working = True

            # Error initializing chatbot
            except Exception as e:
                logging.warning('Error initializing chatbot!' + str(e))
                self.chatbot_working = False

        # revChatGPT API version 1
        elif int(self.settings['modules']['chatgpt_api_type']) == 1:
            self.api_type = 1
            # No proxy
            if int(self.settings['chatgpt_api_1']['proxy']['check_interval_seconds']) <= 0 \
                    or not self.settings['chatgpt_api_1']['proxy']['enabled']:
                logging.info('Proxy checks disabled. Initializing chatbot...')
                if self.chatbot is None:
                    try:
                        if len(str(self.settings['chatgpt_api_1']['chatgpt_auth']['base_url'])) > 0:
                            os.environ['CHATGPT_BASE_URL'] \
                                = str(self.settings['chatgpt_api_1']['chatgpt_auth']['base_url'])
                        from revChatGPT.V1 import Chatbot
                        self.chatbot = Chatbot(config=self.get_chatbot_config())
                        self.chatbot_working = True

                    # Error initializing chatbot
                    except Exception as e:
                        logging.warning('Error initializing chatbot!' + str(e))
                        self.chatbot_working = False
                return

            # Set flag
            self.check_loop_running = True

            # Start thread
            thread = threading.Thread(target=self.proxy_checker_loop)
            thread.start()
            logging.info('Checking thread: ' + thread.name)

        # Other than 0 or 1
        else:
            logging.error('Wrong chatgpt_api_type!')
            raise Exception('Wrong chatgpt_api_type')

    def proxy_get(self):
        """
        Retrieves proxy from auto_proxy_from url into self.proxy_list
        :return:
        """
        # Reset proxy list
        self.proxy_list = []

        # Try to get proxy
        try:
            logging.info('Trying to get proxy list from: ' + PROXY_FROM_URL)
            req = request.Request('%s' % PROXY_FROM_URL)
            req.add_header('User-Agent', random.choice(useragents.USERAGENTS))
            sourcecode = request.urlopen(req)
            part = str(sourcecode.read()).replace(' ', '')
            part = part.split('<tbody>')
            part = part[1].split('</tbody>')
            part = part[0].split('<tr><td>')
            for proxy_ in part:
                proxy_ = proxy_.split('/td><td')
                try:
                    # Get proxy parts
                    ip = proxy_[0].replace('>', '').replace('<', '').strip()
                    port = proxy_[1].replace('>', '').replace('<', '').strip()
                    is_https = 'yes' in proxy_[6].lower()

                    # Check data and append to list
                    if len(ip.split('.')) == 4 and len(port) > 1 and \
                            (is_https or not self.settings['chatgpt_api_1']['proxy']['https_only']):
                        # proxies_list.append(('https://' if is_https else 'http://') + ip + ':' + port)
                        self.proxy_list.append('http://' + ip + ':' + port)
                except:
                    pass
            if len(self.proxy_list) > 1:
                logging.info('Proxies downloaded successfully')
                logging.info(str(self.proxy_list))
            else:
                logging.warning('Proxies list is empty!')
        except Exception as e:
            logging.error('Error downloading proxy list! ' + str(e))

    def proxy_checker_loop(self):
        """
        Performs automatic connection and proxy checks
        :return:
        """
        while self.check_loop_running:
            # Clear chatbot_working flag
            self.chatbot_working = False

            # Perform chatbot check
            check_successful = False
            if self.chatbot is not None:
                try:
                    # Wait for response for previous question
                    while self.chatbot_locked:
                        time.sleep(1)

                    # Ask test message
                    logging.info('Asking test question: ' + str(self.settings['chatgpt_api_1']
                                                                ['proxy']['check_message']).strip())
                    chatbot_response = ''
                    for data in self.chatbot.ask(str(self.settings['chatgpt_api_1']['proxy']['check_message']).strip(),
                                                 conversation_id=self.conversation_id,
                                                 timeout=int(self.settings['chatgpt_api_1']
                                                             ['proxy']['check_message_timeout'])):
                        # Get response
                        chatbot_response = data['message']

                        # Store conversation_id
                        if data['conversation_id'] is not None:
                            self.conversation_id = data['conversation_id']

                    # Check response
                    if str(self.settings['chatgpt_api_1']['proxy']['check_reply_must_include']).strip() \
                            in chatbot_response:
                        check_successful = True
                        self.chatbot_too_many_requests = False
                    else:
                        raise Exception('No ' + self.settings['chatgpt_api_1']['proxy']['check_reply_must_include']
                                        + ' in response!')

                except Exception as e:
                    # Too many requests in 1 hour
                    if TOO_MANY_REQUESTS_MESSAGE in str(e):
                        logging.warning(str(e))

                        # Wait before next try
                        wait_seconds = int(self.settings['chatgpt_dialog']['too_many_requests_wait_time_seconds'])
                        logging.warning('Waiting ' + str(wait_seconds) + ' seconds...')
                        self.chatbot_too_many_requests = True
                        time.sleep(wait_seconds)

                    # Other error
                    else:
                        self.chatbot_too_many_requests = False
                        logging.warning('Error checking chatbot! ' + str(e))

            # Sleep for next cycle in check is successful
            if check_successful:
                # Set chatbot_working flag
                self.chatbot_working = True

                # Sleep for next check cycle
                logging.info('Check successful! Sleeping for next check...')

                # Sleep and check for self.chatbot_working
                sleep_started_time = time.time()
                while time.time() - sleep_started_time \
                        < int(self.settings['chatgpt_api_1']['proxy']['check_interval_seconds']):
                    if not self.chatbot_working:
                        logging.info('Sleep interrupted!')
                        break
                    time.sleep(1)

            # Check is not successful
            else:
                # Get proxy
                if self.settings['chatgpt_api_1']['proxy']['enabled']:
                    # Auto proxy
                    if self.settings['chatgpt_api_1']['proxy']['auto']:
                        # Get new proxy list
                        if len(self.proxy_list) <= 0:
                            self.proxy_get()
                    # Manual proxy
                    else:
                        self.proxy_list = [self.settings['chatgpt_api_1']['proxy']['manual_proxy']]
                # Proxy disabled
                else:
                    break

                # Remove old chatbot
                if self.chatbot is not None:
                    del self.chatbot
                    self.chatbot = None

                # Create list of processes and start times
                processes_and_times = []

                # Get default config
                default_config = self.get_chatbot_config()

                while True:
                    # Create and start processes
                    while len(self.proxy_list) > 0 \
                            and len(processes_and_times) \
                            < int(self.settings['chatgpt_api_1']['proxy']['max_number_of_processes']):
                        proxy = self.proxy_list.pop(0)
                        process = multiprocessing.Process(target=initialize_chatbot,
                                                          args=(str(self.settings['chatgpt_api_1']
                                                                    ['chatgpt_auth']['base_url']),
                                                                proxy,
                                                                default_config,
                                                                self.chatbots_and_proxies_queue,))
                        process.start()
                        time_started = time.time()
                        processes_and_times.append((process, time_started))
                        logging.info('Started new initialization process for proxy: ' + proxy + '. PID: '
                                     + str(process.pid) + ' Total: ' + str(len(processes_and_times)) + ' processes')

                        # Limit connection intervals
                        time.sleep(0.5)

                    # Wait some time each cycle
                    time.sleep(0.5)

                    # No more proxies
                    if len(self.proxy_list) == 0:
                        # Get new proxy list in auto mode
                        if self.settings['chatgpt_api_1']['proxy']['auto']:
                            self.proxy_get()

                        # Exit if manual mode and no more processes
                        elif len(processes_and_times) == 0:
                            logging.info('Cannot connect with manual proxy. Exiting loop...')
                            kill_all_processes(processes_and_times)
                            break

                    # Check chatbots
                    try:
                        # Get from queue
                        chatbot_, proxy_ = self.chatbots_and_proxies_queue.get(block=False)

                        # Found initialized one
                        if chatbot_ is not None and proxy_ is not None and len(proxy_) > 0:
                            self.chatbot = chatbot_
                            self.current_proxy = proxy_
                    except:
                        pass

                    # Kill all processes and exit from loop
                    if self.chatbot is not None and self.current_proxy is not None:
                        kill_all_processes(processes_and_times)
                        logging.info('Found working proxy: ' + self.current_proxy + ' exiting loop...')
                        break

                    # Check timeouts
                    for i in range(len(processes_and_times)):
                        process_, time_ = processes_and_times[i]
                        if process_ is not None and time_ is not None:
                            # Kill on timeout or exit
                            if time.time() - time_ \
                                    > int(self.settings['chatgpt_api_1']['proxy']['initialization_timeout']) \
                                    or not process_.is_alive():
                                if process_.is_alive():
                                    logging.info('Killing process with PID: ' + str(process_.pid) + ' due to timeout')
                                    try:
                                        process_.kill()
                                        process_.join()
                                    except:
                                        logging.warning('Error killing process with PID: ' + str(process_.pid))
                                processes_and_times[i] = (None, None)

                    # Remove Nones
                    processes_and_times = [i for i in processes_and_times if i[0] is not None]

                # Sleep 1 second to limit connections interval
                time.sleep(1)

        # Loop finished
        logging.warning('Proxy checker loop finished')
        self.check_loop_running = False

    def get_chatbot_config(self):
        """
        Constructs chatbot config
        See: https://github.com/acheong08/ChatGPT
        :return:
        """
        config = {}

        # Use email/password
        if len(self.settings['chatgpt_api_1']['chatgpt_auth']['email']) > 0 \
                and len(self.settings['chatgpt_api_1']['chatgpt_auth']['password']) > 0:
            config['email'] = self.settings['chatgpt_api_1']['chatgpt_auth']['email']
            config['password'] = self.settings['chatgpt_api_1']['chatgpt_auth']['password']

        # Use session_token
        elif len(self.settings['chatgpt_api_1']['chatgpt_auth']['session_token']) > 0:
            config['session_token'] = self.settings['chatgpt_api_1']['chatgpt_auth']['session_token']

        # Use access_token
        elif len(self.settings['chatgpt_api_1']['chatgpt_auth']['access_token']) > 0:
            config['access_token'] = self.settings['chatgpt_api_1']['chatgpt_auth']['access_token']

        # No credentials
        else:
            raise Exception('Error! No credentials to login!')

        return config
