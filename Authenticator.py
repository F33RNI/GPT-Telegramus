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
import asyncio
import copy
import logging
import multiprocessing
import os
import random
import threading
import time
import uuid
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
            except Exception as e:
                logging.warning('Error killing process with PID: ' + str(process_.pid) + ' ' + str(e))


def initialize_chatbot(chatgpt_api_type, proxy, config, openai_api_key, engine, chatbots_and_proxies_queue):
    """
    Tries to initialize chatbot in background process
    :param chatgpt_api_type: int(self.settings['modules']['chatgpt_api_type'])
    :param proxy: proxy prom list
    :param config: self.get_chatbot_config()
    :param openai_api_key: str(self.settings['chatgpt_auth']['api_key'])
    :param engine: str(self.settings['chatgpt_auth']['engine'])
    :param chatbots_and_proxies_queue: multiprocessing queue
    :return:
    """
    try:
        # API type 0
        if chatgpt_api_type == 0:
            from revChatGPT.V0 import Chatbot
            if engine is not None and len(engine) > 0:
                chatbot = Chatbot(openai_api_key, engine=engine, proxy=proxy)
            else:
                chatbot = Chatbot(openai_api_key, proxy=proxy)

        # API type 1
        elif chatgpt_api_type == 1:
            config_ = copy.deepcopy(config)
            config_['proxy'] = proxy
            from revChatGPT.V1 import Chatbot
            chatbot = Chatbot(config=config_)

        # API type 2
        elif chatgpt_api_type == 2:
            from revChatGPT.V2 import Chatbot
            chatbot = Chatbot(openai_api_key, proxy=proxy)

        # API type 3
        elif chatgpt_api_type == 3:
            from revChatGPT.V3 import Chatbot
            if engine is not None and len(engine) > 0:
                chatbot = Chatbot(openai_api_key, engine=engine, proxy=proxy)
            else:
                chatbot = Chatbot(openai_api_key, proxy=proxy)

        # Other api type
        else:
            chatbot = None

        # Append working chatbot and proxy
        if chatbot is not None:
            chatbots_and_proxies_queue.put((chatbot, proxy))
    except:
        pass


class Authenticator:
    def __init__(self, settings):
        self.settings = settings

        self.chatbot = None
        self.chatbot_locked = False
        self.chatbot_too_many_requests = False
        self.chatbot_working = False
        self.chatbots_and_proxies_queue = multiprocessing.Queue(maxsize=int(self.settings['proxy']
                                                                            ['max_number_of_processes']) * 2)
        self.current_proxy = None
        self.conversation_id = None
        self.proxy_list = []
        self.check_loop_running = False
        self.engine = None

    def start_chatbot(self):
        """
        Initializes chatbot and starts background proxy checker thread if needed
        :return:
        """
        # Set base url
        base_url = None
        if int(self.settings['modules']['chatgpt_api_type']) == 1:
            base_url = str(self.settings['chatgpt_auth']['base_url'])
        if base_url is not None and len(base_url) > 0:
            os.environ['CHATGPT_BASE_URL'] = base_url

        # Set engine name
        self.engine = str(self.settings['chatgpt_auth']['engine'])
        if self.engine is not None and len(self.engine) <= 0:
            self.engine = None

        # Initialize proxy
        proxy_ = None
        if self.settings['proxy']['enabled']:
            logging.info('Proxy is set to enabled!')

            # Get proxy checks enabled flag
            proxy_checks_enabled = self.settings['proxy']['proxy_checks_enabled']
            if int(self.settings['proxy']['check_interval_seconds']) <= 0:
                proxy_checks_enabled = False

            # Start thread if proxy checks is set to true
            if proxy_checks_enabled:
                # Set flag
                self.check_loop_running = True

                # Start thread
                thread = threading.Thread(target=self.proxy_checker_loop)
                thread.start()
                logging.info('Proxy checking thread: ' + thread.name)
                return

            # No checks
            else:
                # Auto proxy -> get first proxy
                if self.settings['proxy']['auto']:
                    self.proxy_get()
                    proxy_ = self.proxy_list[0]
                # Manual proxy
                else:
                    proxy_ = str(self.settings['proxy']['manual_proxy'])

        # Initialize chatbot
        try:
            # API type 0
            if int(self.settings['modules']['chatgpt_api_type']) == 0:
                from revChatGPT.V0 import Chatbot
                if self.engine is None:
                    self.chatbot = Chatbot(str(self.settings['chatgpt_auth']['api_key']),
                                           proxy=proxy_)
                else:
                    self.chatbot = Chatbot(str(self.settings['chatgpt_auth']['api_key']),
                                           engine=self.engine,
                                           proxy=proxy_)
                self.chatbot_working = True

            # API type 1
            elif int(self.settings['modules']['chatgpt_api_type']) == 1:
                from revChatGPT.V1 import Chatbot
                self.chatbot = Chatbot(config=self.get_chatbot_config())
                self.chatbot_working = True

            # API type 2
            elif int(self.settings['modules']['chatgpt_api_type']) == 2:
                from revChatGPT.V2 import Chatbot
                self.chatbot = Chatbot(str(self.settings['chatgpt_auth']['api_key']), proxy=proxy_)
                self.chatbot_working = True

            # API type 3
            elif int(self.settings['modules']['chatgpt_api_type']) == 3:
                from revChatGPT.V3 import Chatbot
                if self.engine is None:
                    self.chatbot = Chatbot(str(self.settings['chatgpt_auth']['api_key']),
                                           proxy=proxy_)
                else:
                    self.chatbot = Chatbot(str(self.settings['chatgpt_auth']['api_key']),
                                           engine=self.engine,
                                           proxy=proxy_)
                self.chatbot_working = True

            # Other api type
            else:
                logging.error('Wrong chatgpt_api_type!')
                raise Exception('Wrong chatgpt_api_type')

        # Error initializing chatbot
        except Exception as e:
            logging.error('Error initializing chatbot!', e)
            self.chatbot_working = False

    def stop_chatbot(self):
        """
        Stops background handler and removes chatbot
        :return:
        """
        logging.info('Stopping chatbot...')
        # Clear loop flag
        self.check_loop_running = False
        self.chatbot_working = False

        # Sleep some time
        time.sleep(10)

        # Remove old chatbot
        try:
            if self.chatbot is not None:
                del self.chatbot
                self.chatbot = None
        except Exception as e:
            logging.warning('Error clearing chatbot! ' + str(e))

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
                            (is_https or not self.settings['proxy']['https_only']):
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
                    logging.info('Asking test question: ' + str(self.settings['proxy']['check_message']).strip())
                    chatbot_response = ''

                    # API type 0
                    if int(self.settings['modules']['chatgpt_api_type']) == 0:
                        # Reset current chat
                        self.chatbot.reset()

                        # Ask
                        for data in self.chatbot.ask_stream(str(self.settings['proxy']['check_message']).strip()):
                            # Initialize response
                            if chatbot_response is None:
                                chatbot_response = ''

                            # Append response
                            chatbot_response += str(data)

                    # API type 1
                    elif int(self.settings['modules']['chatgpt_api_type']) == 1:
                        # Reset current chat
                        self.chatbot.reset_chat()

                        # Ask
                        for data in self.chatbot.ask(str(self.settings['proxy']['check_message']).strip(),
                                                     conversation_id=self.conversation_id):
                            # Get last response
                            chatbot_response = data['message']

                            # Store conversation_id
                            if 'conversation_id' in data and data['conversation_id'] is not None:
                                self.conversation_id = data['conversation_id']

                    # API type 2
                    elif int(self.settings['modules']['chatgpt_api_type']) == 2:
                        # Make async function sync
                        api_responses_ = []
                        conversation_ids_ = []

                        async def ask_async(request_, conversation_id_):
                            async for data_ in self.chatbot.ask(request_, conversation_id=conversation_id_):
                                # Get last response
                                api_responses_.append(data_['message'])

                                # Store conversation_id
                                if 'conversation_id' in data_ and data_['conversation_id'] is not None:
                                    conversation_ids_.append(data_['conversation_id'])

                        # Ask
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(ask_async(str(self.settings['proxy']['check_message']).strip(),
                                                          self.conversation_id))

                    # API type 3
                    elif int(self.settings['modules']['chatgpt_api_type']) == 3:
                        # Generate conversation ID
                        if self.conversation_id is None:
                            self.conversation_id = str(uuid.uuid4())

                        # Ask
                        for data in self.chatbot.ask(str(self.settings['proxy']['check_message']).strip(),
                                                     convo_id=self.conversation_id):
                            # Initialize response
                            if chatbot_response is None:
                                chatbot_response = ''

                            # Append response
                            chatbot_response += str(data)

                    # Wrong api type
                    else:
                        raise Exception('Wrong chatgpt_api_type')

                    # Check response
                    if str(self.settings['proxy']['check_reply_must_include']).strip() in chatbot_response:
                        check_successful = True
                        self.chatbot_too_many_requests = False
                    else:
                        raise Exception('No ' + self.settings['proxy']['check_reply_must_include'] + ' in response!')

                except Exception as e:
                    # Too many requests in 1 hour
                    if TOO_MANY_REQUESTS_MESSAGE in str(e):
                        logging.warning(str(e))

                        # Wait before next try
                        wait_seconds = int(self.settings['proxy']['too_many_requests_wait_time_seconds'])
                        logging.warning('Waiting ' + str(wait_seconds) + ' seconds...')
                        self.chatbot_too_many_requests = True
                        time.sleep(wait_seconds)

                    # Other error
                    else:
                        self.chatbot_too_many_requests = False
                        logging.error('Error checking chatbot! ' + str(e))

            # Sleep for next cycle in check is successful
            if check_successful:
                # Set chatbot_working flag
                self.chatbot_working = True

                # Sleep for next check cycle
                logging.info('Check successful! Sleeping for next check...')

                # Sleep and check for self.chatbot_working
                sleep_started_time = time.time()
                while time.time() - sleep_started_time < int(self.settings['proxy']['check_interval_seconds']):
                    if not self.chatbot_working:
                        logging.info('Sleep interrupted!')
                        break
                    time.sleep(1)

                # Exit if thread stopped
                if not self.check_loop_running:
                    break

            # Check is not successful
            else:
                # Get proxy
                if self.settings['proxy']['enabled']:
                    # Auto proxy
                    if self.settings['proxy']['auto']:
                        # Get new proxy list
                        if len(self.proxy_list) <= 0:
                            self.proxy_get()
                    # Manual proxy
                    else:
                        self.proxy_list = [self.settings['proxy']['manual_proxy']]
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
                if int(self.settings['modules']['chatgpt_api_type']) == 1:
                    default_config = self.get_chatbot_config()
                else:
                    default_config = None

                while True:
                    # Exit if thread stopped
                    if not self.check_loop_running:
                        kill_all_processes(processes_and_times)
                        break

                    # Create and start processes
                    while len(self.proxy_list) > 0 \
                            and len(processes_and_times) \
                            < int(self.settings['proxy']['max_number_of_processes']):
                        proxy = self.proxy_list.pop(0)
                        process = multiprocessing.Process(target=initialize_chatbot,
                                                          args=(int(self.settings['modules']['chatgpt_api_type']),
                                                                proxy,
                                                                default_config,
                                                                str(self.settings['chatgpt_auth']['api_key']),
                                                                str(self.settings['chatgpt_auth']['engine']),
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
                        if self.settings['proxy']['auto']:
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
                                    > int(self.settings['proxy']['initialization_timeout']) or not process_.is_alive():
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
        Constructs chatbot config for api type 1
        See: https://github.com/acheong08/ChatGPT
        :return:
        """
        config = {}

        # Use email/password
        if len(self.settings['chatgpt_auth']['email']) > 0 \
                and len(self.settings['chatgpt_auth']['password']) > 0:
            config['email'] = self.settings['chatgpt_auth']['email']
            config['password'] = self.settings['chatgpt_auth']['password']

        # Use session_token
        elif len(self.settings['chatgpt_auth']['session_token']) > 0:
            config['session_token'] = self.settings['chatgpt_auth']['session_token']

        # Use access_token
        elif len(self.settings['chatgpt_auth']['access_token']) > 0:
            config['access_token'] = self.settings['chatgpt_auth']['access_token']

        # No credentials
        else:
            raise Exception('Error! No credentials to login!')

        return config
