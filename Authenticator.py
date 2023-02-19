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

import logging
import random
import threading
import time
from urllib import request

from revChatGPT.V1 import Chatbot

import useragents

PROXY_FROM_URL = 'http://free-proxy-list.net/'


class Authenticator:
    def __init__(self, settings):
        self.settings = settings

        self.chatbot = None
        self.chatbot_working = False
        self.current_proxy = None
        self.conversation_id = None
        self.proxy_list = []
        self.proxy_list_index = 0
        self.check_loop_running = False

    def start_check_loop(self):
        """
        Starts background thread
        :return:
        """
        # No proxy
        if int(self.settings['proxy']['check_interval_seconds']) <= 0 or not self.settings['proxy']['enabled']:
            logging.info('Proxy checks disabled. Initializing chatbot...')
            if self.chatbot is None:
                try:
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

    def proxy_get(self):
        """
        Retrieves proxy from auto_proxy_from url into self.proxy_list
        :return:
        """
        # Reset proxy list
        self.proxy_list = []
        self.proxy_list_index = 0

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
                    # Ask test message
                    logging.info('Asking test question: ' + str(self.settings['proxy']['check_message']).strip())
                    chatbot_response = ''
                    for data in self.chatbot.ask(str(self.settings['proxy']['check_message']).strip(),
                                                 conversation_id=self.conversation_id,
                                                 timeout=int(self.settings['proxy']['check_message_timeout'])):
                        # Get response
                        chatbot_response = data['message']

                        # Store conversation_id
                        if data['conversation_id'] is not None:
                            self.conversation_id = data['conversation_id']

                    # Check response
                    if str(self.settings['proxy']['check_reply_must_include']).strip() in chatbot_response:
                        check_successful = True
                    else:
                        raise Exception('No ' + self.settings['proxy']['check_reply_must_include'] + ' in response!')

                except Exception as e:
                    logging.warning('Error checking chatbot! ' + str(e))

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

            # Check is not successful
            else:
                # Get config
                config = self.get_chatbot_config()

                # Get proxy
                if self.settings['proxy']['enabled']:
                    proxy = None
                    # Auto proxy
                    if self.settings['proxy']['auto']:
                        # Already have proxy_list -> get new proxy from it
                        if self.proxy_list_index < len(self.proxy_list) - 1:
                            self.proxy_list_index += 1
                            logging.info('Loading next proxy: ' + str(self.proxy_list_index + 1) + '/'
                                         + str(len(self.proxy_list)))
                            proxy = self.proxy_list[self.proxy_list_index]

                        # No proxy or all checked
                        else:
                            # Get new proxy list
                            self.proxy_get()

                            # Get proxy from list
                            if len(self.proxy_list) > 0:
                                proxy = self.proxy_list[0]

                    # Manual proxy
                    else:
                        proxy = self.settings['proxy']['manual_proxy']

                    # Add proxy to config
                    self.current_proxy = proxy
                    if proxy is not None:
                        logging.info('Using proxy: ' + proxy)
                        config['proxy'] = proxy

                # Remove old chatbot
                if self.chatbot is not None:
                    del self.chatbot
                    self.chatbot = None

                # Initialize new chatbot
                logging.info('Initializing new chatbot with config: ' + str(config))
                try:
                    self.chatbot = Chatbot(config=config)
                # Error initializing chatbot
                except Exception as e:
                    logging.warning('Error initializing chatbot! ' + str(e))

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
        if len(self.settings['chatgpt_auth']['email']) > 0 and len(self.settings['chatgpt_auth']['password']) > 0:
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
