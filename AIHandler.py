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
import logging
import queue
import threading

import openai
from revChatGPT.V1 import Chatbot

import RequestResponseContainer

EMPTY_RESPONSE_ERROR_MESSAGE = 'Empty response'
NO_AUTH_GPT_ERROR_MESSAGE = 'Auth error or no email or password provided!'
NO_AUTH_DALLE_ERROR_MESSAGE = 'No OpenAI API key provided!'


class AIHandler:
    def __init__(self, settings):
        self.settings = settings

        # Loop running flag
        self.gpt_loop_running = False

        # OpenAI API
        self.chatbot = None

        # Responses queue
        self.responses_queue = None

        # Asking request
        self.processing_container = None

        # Requests queue
        self.requests_queue = None

        # Check settings
        if self.settings is not None:
            # Initialize queue
            self.responses_queue = queue.Queue(maxsize=self.settings['queue_max'])

    def thread_start(self):
        """
        Starts background thread
        :return:
        """
        # Set flag
        self.gpt_loop_running = True

        # Start thread
        thread = threading.Thread(target=self.gpt_loop)
        thread.start()
        logging.info('AIHandler thread: ' + thread.name)

    def gpt_loop(self):
        """
        Background loop for handling requests
        :return:
        """
        # Initialize ChatGPT
        if (len(self.settings['chatgpt_auth_email']) > 0 and len(self.settings['chatgpt_auth_password']) > 0) \
                or len(self.settings['chatgpt_auth_session_token']) > 0 \
                or len(self.settings['chatgpt_auth_access_token']) > 0:

            # Initialize ChatGPT
            try:
                config = {}
                if 'chatgpt_auth_email' in self.settings and 'chatgpt_auth_password' in self.settings:
                    config['email'] = self.settings['chatgpt_auth_email']
                    config['password'] = self.settings['chatgpt_auth_password']
                elif 'chatgpt_auth_session_token' in self.settings:
                    config['session_token'] = self.settings['chatgpt_auth_session_token']
                elif 'chatgpt_auth_access_token' in self.settings:
                    config['access_token'] = self.settings['chatgpt_auth_access_token']

                if 'chatgpt_auth_proxy' in self.settings:
                    config['proxy'] = self.settings['chatgpt_auth_proxy']

                self.chatbot = Chatbot(config=config)

            except Exception as e:
                self.chatbot = None
                logging.warning(e, exc_info=True)
                logging.warning('Error initializing ChatGPT. ChatGPT functions will be disabled')

        # No login details
        else:
            self.chatbot = None
            logging.warning('No login details provided! ChatGPT functions will be disabled')

        # No API Key
        if len(self.settings['open_ai_api_key']) <= 0:
            logging.warning('No OpenAI API key for DALL-E provided. DALL-E functions will be disabled')

        while self.gpt_loop_running and self.requests_queue is not None:
            # Get request
            container = self.requests_queue.get(block=True)
            self.processing_container = RequestResponseContainer.RequestResponseContainer(container.chat_id,
                                                                                          container.user_name,
                                                                                          container.message_id,
                                                                                          container.request,
                                                                                          request_type=container
                                                                                          .request_type)

            # Error message
            error_message = ''

            # Ask API
            api_response = None
            try:
                # ChatGPT
                if container.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
                    if self.chatbot is not None:
                        # Log request
                        logging.info('Asking: ' + str(container.request))

                        # Add response
                        for data in self.chatbot.ask(str(container.request)):
                            api_response = data['message']

                        # Log response
                        logging.info(str(api_response))

                    # ChatGPT is not initialized
                    else:
                        api_response = None
                        raise Exception(NO_AUTH_GPT_ERROR_MESSAGE)

                # ALLE
                else:
                    if len(self.settings['open_ai_api_key']) > 0:
                        # Log request
                        logging.info('Drawing: ' + str(container.request))

                        # Send request
                        openai.api_key = self.settings['open_ai_api_key']
                        image_response = openai.Image.create(
                            prompt=str(container.request),
                            n=1,
                            size=self.settings['image_size'],
                        )
                        response_url = image_response['data'][0]['url']

                        # Log response
                        logging.info(str(response_url))

                        # Add response
                        api_response = str(response_url)

                    # No API key provided
                    else:
                        api_response = None
                        raise Exception(NO_AUTH_DALLE_ERROR_MESSAGE)

            except Exception as e:
                error_message = str(e)
                logging.error(e, exc_info=True)

            # Check error
            if len(error_message) == 0:
                # Check response
                if api_response is not None and len(api_response) > 0:
                    container.response = api_response
                    container.error = False

                # Empty response
                else:
                    container.response = EMPTY_RESPONSE_ERROR_MESSAGE
                    container.error = True

            # Error
            else:
                container.response = error_message
                container.error = True

            # Add response to queue
            logging.info('Adding response to request: ' + str(container.request) + ' to the queue')
            self.responses_queue.put(container)

            # Clear processing container
            self.processing_container = None

        # Loop finished
        logging.warning('AIHandler loop finished')
        self.gpt_loop_running = False
