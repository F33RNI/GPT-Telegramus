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
import queue
import threading
import time

import openai

import RequestResponseContainer

EMPTY_RESPONSE_ERROR_MESSAGE = 'Empty response or unhandled error!'
ERROR_CHATGPT_DISABLED = 'ChatGPT module is disabled in settings.json'
ERROR_DALLE_DISABLED = 'DALL-E module is disabled in settings.json'


class AIHandler:
    def __init__(self, settings, authenticator):
        self.settings = settings
        self.authenticator = authenticator

        # Loop running flag
        self.loop_running = False

        # Responses queue
        self.responses_queue = None

        # Asking request
        self.processing_container = None

        # Requests queue
        self.requests_queue = None

        # Conversation id and parent id to continue dialog
        self.conversation_id = None
        self.parent_id = None

        # Check settings
        if self.settings is not None:
            # Initialize queue
            self.responses_queue = queue.Queue(maxsize=self.settings['telegram']['queue_max'])

    def thread_start(self):
        """
        Starts background thread
        :return:
        """
        # Set flag
        self.loop_running = True

        # Start thread
        thread = threading.Thread(target=self.gpt_loop)
        thread.start()
        logging.info('AIHandler thread: ' + thread.name)

    def gpt_loop(self):
        """
        Background loop for handling requests
        :return:
        """
        while self.loop_running and self.requests_queue is not None:
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
                    # Check if ChatGPT is enabled
                    if not self.settings['modules']['chatgpt']:
                        logging.warning(ERROR_CHATGPT_DISABLED)
                        api_response = None
                        raise Exception(ERROR_CHATGPT_DISABLED)

                    # Wait for chatbot
                    chatbot = self.authenticator.chatbot
                    while not self.authenticator.chatbot_working or chatbot is None:
                        time.sleep(1)
                        chatbot = self.authenticator.chatbot

                    # Log request
                    logging.info('Asking: ' + str(container.request))

                    # Initialize conversation_id and parent_id
                    if self.conversation_id is None:
                        self.conversation_id = str(self.settings['chatgpt_dialog']['conversation_id']) if \
                            len(str(self.settings['chatgpt_dialog']['conversation_id'])) > 0 else None
                        logging.info('Initial conversation id: ' + str(self.conversation_id))
                    if self.parent_id is None:
                        self.parent_id = str(self.settings['chatgpt_dialog']['parent_id']) if \
                            len(str(self.settings['chatgpt_dialog']['parent_id'])) > 0 else None
                        logging.info('Initial parent id: ' + str(self.parent_id))

                    # Ask
                    for data in chatbot.ask(str(container.request),
                                            conversation_id=self.conversation_id,
                                            parent_id=self.parent_id):
                        # Get last response
                        api_response = data['message']

                        # Store conversation_id
                        if data['conversation_id'] is not None:
                            self.conversation_id = data['conversation_id']

                    # Log conversation id and parent id
                    logging.info('Current conversation id: ' + str(self.conversation_id)
                                 + '\tParent id: ' + str(self.parent_id))

                    # Log response
                    logging.info(str(api_response))

                # DALL-E
                else:
                    # Check if ChatGPT is enabled
                    if not self.settings['modules']['dalle'] or len(self.settings['dalle']['open_ai_api_key']) <= 0:
                        logging.warning(ERROR_DALLE_DISABLED)
                        api_response = None
                        raise Exception(ERROR_DALLE_DISABLED)

                    # Log request
                    logging.info('Drawing: ' + str(container.request))

                    # Set Key
                    openai.api_key = self.settings['dalle']['open_ai_api_key']

                    # Proxy for DALL-E
                    if self.settings['dalle']['use_proxy']:
                        proxy = self.authenticator.current_proxy
                        if proxy is not None and len(proxy) > 0:
                            openai.proxy = proxy

                    # Send request
                    image_response = openai.Image.create(
                        prompt=str(container.request),
                        n=1,
                        size=self.settings['dalle']['image_size'],
                    )
                    response_url = image_response['data'][0]['url']

                    # Log response
                    logging.info(str(response_url))

                    # Add response
                    api_response = str(response_url)

            # Error
            except Exception as e:
                # Wake up authenticator check loop from sleep
                self.authenticator.chatbot_working = False

                # Print error message
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
        self.loop_running = False
