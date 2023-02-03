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

from revChatGPT.Official import Chatbot

EMPTY_RESPONSE_ERROR_MESSAGE = 'Empty response'


class GPTHandler:
    def __init__(self, settings):
        self.settings = settings

        # Loop running flag
        self.gpt_loop_running = False

        # OpenAI API
        self.chatbot = None

        # Responses queue
        self.responses_queue = None

        # Asking flag
        self.is_processing = False

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
        logging.info('GPTHandler thread: ' + thread.name)

    def gpt_loop(self):
        """
        Background loop for handling requests
        :return:
        """
        # Initialize OpenAI API
        self.chatbot = Chatbot(api_key=self.settings['open_ai_api_key'])

        while self.gpt_loop_running and self.requests_queue is not None:
            # Get request
            container = self.requests_queue.get(block=True)
            self.is_processing = True

            if self.chatbot is not None:
                # Error message
                error_message = ''

                # Ask API
                chatbot_response = None
                try:
                    # Log request
                    logging.info('Asking: ' + str(container.request))

                    # Send request
                    chatbot_response_raw = self.chatbot.ask(str(container.request))

                    # Log response
                    logging.info(str(chatbot_response_raw))

                    # Add all choices
                    chatbot_response = ''
                    for choice in chatbot_response_raw['choices']:
                        chatbot_response += choice['text'] + '\n'
                except Exception as e:
                    error_message = str(e)
                    logging.error(e, exc_info=True)

                # Check error
                if len(error_message) == 0:
                    # Check response
                    if chatbot_response is not None and len(chatbot_response) > 0:
                        container.response = chatbot_response
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

                # Clear processing flag
                self.is_processing = False

        # Loop finished
        logging.warning('GPTHandler loop finished')
        self.gpt_loop_running = False
