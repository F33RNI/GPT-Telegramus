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
import os
import queue
import threading
import time
import uuid

import openai

import Authenticator
import RequestResponseContainer
from JSONReaderWriter import load_json, save_json

EMPTY_RESPONSE_ERROR_MESSAGE = 'Empty response or unhandled error!'
ERROR_CHATGPT_DISABLED = 'ChatGPT module is disabled in settings.json'
ERROR_DALLE_DISABLED = 'DALL-E module is disabled in settings.json'

CONVERSATION_DIR_OR_FILE = 'conversations'


class AIHandler:
    def __init__(self, settings, chats_file, authenticator):
        self.settings = settings
        self.chats_file = chats_file
        self.authenticator = authenticator

        # Loop running flag
        self.loop_running = False

        # Responses queue
        self.responses_queue = None

        # Asking request
        self.processing_container = None

        # Requests queue
        self.requests_queue = None

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

    def get_chat(self, chat_id: int):
        """
        Retrieves conversation_id and parent_id for given chat_id or None if not exists
        :param chat_id:
        :return: (conversation_id, parent_id)
        """
        logging.info('Loading conversation_id for chat_id ' + str(chat_id))
        chats = load_json(self.chats_file)
        if chats is not None and str(chat_id) in chats:
            chat = chats[str(chat_id)]
            conversation_id = None
            parent_id = None
            if 'conversation_id' in chat:
                conversation_id = chat['conversation_id']
            if 'parent_id' in chat:
                parent_id = chat['parent_id']

            return conversation_id, parent_id
        else:
            return None, None

    def set_chat(self, chat_id: int, conversation_id=None, parent_id=None):
        """
        Saves conversation ID and parent ID or Nones to remove it
        :param chat_id:
        :param conversation_id:
        :param parent_id:
        :return:
        """
        logging.info('Saving conversation_id ' + str(conversation_id) + ' and parent_id '
                     + str(parent_id) + ' for chat_id ' + str(chat_id))
        chats = load_json(self.chats_file)
        if chats is not None:
            if str(chat_id) in chats:
                # Save or delete conversation_id
                if conversation_id is not None and len(conversation_id) > 0:
                    chats[str(chat_id)]['conversation_id'] = conversation_id
                elif 'conversation_id' in chats[str(chat_id)]:
                    del chats[str(chat_id)]['conversation_id']

                # Save or delete parent_id
                if parent_id is not None and len(parent_id) > 0:
                    chats[str(chat_id)]['parent_id'] = parent_id
                elif 'parent_id' in chats[str(chat_id)]:
                    del chats[str(chat_id)]['parent_id']

            # New chat
            else:
                chats[str(chat_id)] = {}
                if conversation_id is not None and len(conversation_id) > 0:
                    chats[str(chat_id)]['conversation_id'] = conversation_id
                if parent_id is not None and len(parent_id) > 0:
                    chats[str(chat_id)]['parent_id'] = parent_id
        else:
            chats = {}
        save_json(self.chats_file, chats)

    def save_conversation(self, chatbot_, conversation_id) -> None:
        """
        Saves conversation
        :param chatbot_:
        :param conversation_id:
        :return:
        """
        logging.info('Saving conversation ' + conversation_id)
        # API type 0
        if int(self.settings['modules']['chatgpt_api_type']) == 0:
            conversations_file = CONVERSATION_DIR_OR_FILE + '.json'
            chatbot_.conversations.save(conversations_file)

        # API type 3
        elif int(self.settings['modules']['chatgpt_api_type']) == 3:
            if not os.path.exists(CONVERSATION_DIR_OR_FILE):
                os.makedirs(CONVERSATION_DIR_OR_FILE)
            conversation_file = os.path.join(CONVERSATION_DIR_OR_FILE, conversation_id + '.json')
            chatbot_.save(conversation_file, conversation_id)

    def load_conversation(self, chatbot_, conversation_id) -> None:
        """
        Loads conversation
        :param chatbot_:
        :param conversation_id:
        :return:
        """
        logging.info('Loading conversation ' + conversation_id)
        try:
            # API type 0
            if int(self.settings['modules']['chatgpt_api_type']) == 0:
                conversations_file = CONVERSATION_DIR_OR_FILE + '.json'
                chatbot_.conversations.load(conversations_file)

            # API type 3
            elif int(self.settings['modules']['chatgpt_api_type']) == 3:
                conversation_file = os.path.join(CONVERSATION_DIR_OR_FILE, conversation_id + '.json')
                chatbot_.load(conversation_file, conversation_id)
        except Exception as e:
            logging.warning('Error loading conversation ' + conversation_id + ' ' + str(e))

    def delete_conversation(self, conversation_id) -> None:
        """
        Deletes conversation
        :param conversation_id:
        :return:
        """
        logging.info('Deleting conversation ' + conversation_id)
        try:
            # API type 0
            if int(self.settings['modules']['chatgpt_api_type']) == 0:
                self.authenticator.chatbot.reset()
                try:
                    conversations_file = CONVERSATION_DIR_OR_FILE + '.json'
                    self.authenticator.chatbot.conversations.remove_conversation(conversations_file)
                    self.authenticator.chatbot.conversations.save(conversations_file)
                except Exception as e:
                    logging.error('Error deleting conversation ' + conversation_id, e)

            # API type 1
            elif int(self.settings['modules']['chatgpt_api_type']) == 1:
                self.authenticator.chatbot.reset_chat()
                try:
                    self.authenticator.chatbot.delete_conversation(conversation_id)
                except Exception as e:
                    logging.error('Error deleting conversation ' + conversation_id, e)

            # API type 2
            elif int(self.settings['modules']['chatgpt_api_type']) == 2:
                self.authenticator.chatbot.reset_chat()
                try:
                    self.authenticator.chatbot.conversations.remove(conversation_id)
                except Exception as e:
                    logging.error('Error deleting conversation ' + conversation_id, e)

            # API type 3
            elif int(self.settings['modules']['chatgpt_api_type']) == 3:
                self.authenticator.chatbot.reset(conversation_id)

            # Wrong API type
            else:
                raise Exception('Wrong chatgpt_api_type')

            # Delete conversation file if exists
            try:
                conversation_file = os.path.join(CONVERSATION_DIR_OR_FILE, conversation_id + '.json')
                if os.path.exists(conversation_file):
                    os.remove(conversation_file)
            except Exception as e:
                logging.error('Error removing conversation file for conversation ' + conversation_id, e)
        except Exception as e:
            logging.warning('Error loading conversation ' + conversation_id + ' ' + str(e))

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

                    # Too many requests in 1 hour
                    if self.authenticator.chatbot_too_many_requests:
                        raise Exception(Authenticator.TOO_MANY_REQUESTS_MESSAGE)

                    # Wait for chatbot
                    chatbot = self.authenticator.chatbot
                    while not self.authenticator.chatbot_working or chatbot is None:
                        time.sleep(1)
                        chatbot = self.authenticator.chatbot

                        # Too many requests in 1 hour
                        if self.authenticator.chatbot_too_many_requests:
                            raise Exception(Authenticator.TOO_MANY_REQUESTS_MESSAGE)

                    # Lock chatbot
                    self.authenticator.chatbot_locked = True

                    # Get conversation_id and parent_id
                    conversation_id, parent_id = self.get_chat(container.chat_id)

                    # Log request
                    logging.info('Asking: ' + str(container.request)
                                 + ', conversation_id: ' + str(conversation_id) + ', parent_id: ' + str(parent_id))

                    # API type 0
                    if int(self.settings['modules']['chatgpt_api_type']) == 0:
                        # Reset current chat
                        chatbot.reset()

                        # Try to load conversation
                        if conversation_id is not None:
                            self.load_conversation(chatbot, conversation_id)

                        # Try to load conversation
                        if conversation_id is not None:
                            try:
                                chatbot.load_conversation(conversation_id)
                            except Exception as e:
                                logging.warning('Error loading conversation with id: ' + conversation_id + ' ' + str(e))

                        # Ask
                        for data in chatbot.ask_stream(str(container.request), conversation_id=conversation_id):
                            # Initialize response
                            if api_response is None:
                                api_response = ''

                            # Append response
                            api_response += str(data)

                        # Generate and save conversation ID
                        try:
                            if conversation_id is None:
                                conversation_id = str(uuid.uuid4())
                            chatbot.save_conversation(conversation_id)
                            self.save_conversation(chatbot, conversation_id)
                            self.set_chat(container.chat_id, conversation_id, parent_id)
                        except Exception as e:
                            logging.warning('Error saving conversation! ' + str(e))

                        # Remove tags
                        api_response = api_response.replace('<|im_end|>', '').replace('<|im_start|>', '')

                    # API type 1
                    elif int(self.settings['modules']['chatgpt_api_type']) == 1:
                        # Reset current chat
                        chatbot.reset_chat()

                        # Ask
                        for data in chatbot.ask(str(container.request),
                                                conversation_id=conversation_id,
                                                parent_id=parent_id):
                            # Get last response
                            api_response = data['message']

                            # Store conversation_id
                            if 'conversation_id' in data and data['conversation_id'] is not None:
                                conversation_id = data['conversation_id']

                            # Store parent_id
                            if 'parent_id' in data and data['parent_id'] is not None:
                                parent_id = data['parent_id']

                        # Log conversation id and parent id
                        logging.info('Current conversation_id: ' + str(conversation_id)
                                     + ', parent_id: ' + str(parent_id))

                        # Save conversation id
                        self.set_chat(container.chat_id, conversation_id, parent_id)

                    # API type 2
                    elif int(self.settings['modules']['chatgpt_api_type']) == 2:
                        # Make async function sync
                        api_responses_ = []
                        conversation_ids_ = []

                        async def ask_async(request_, conversation_id_):
                            async for data_ in chatbot.ask(request_, conversation_id=conversation_id_):
                                # Get last response
                                api_responses_.append(data_['message'])

                                # Store conversation_id
                                if 'conversation_id' in data_ and data_['conversation_id'] is not None:
                                    conversation_ids_.append(data_['conversation_id'])

                        # Ask
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(ask_async(str(container.request), conversation_id))

                        # Log conversation id and parent id
                        logging.info('Current conversation_id: ' + str(conversation_id)
                                     + ', parent_id: ' + str(parent_id))

                        # Save conversation id
                        self.set_chat(container.chat_id, conversation_id, parent_id)

                    # API type 3
                    elif int(self.settings['modules']['chatgpt_api_type']) == 3:
                        # Generate conversation ID
                        if conversation_id is None:
                            conversation_id = str(uuid.uuid4())

                        # Try to load conversation
                        else:
                            self.load_conversation(chatbot, conversation_id)

                        # Ask
                        for data in chatbot.ask(str(container.request), convo_id=conversation_id):
                            # Initialize response
                            if api_response is None:
                                api_response = ''

                            # Append response
                            api_response += str(data)

                        # Save conversation id
                        self.save_conversation(chatbot, conversation_id)
                        self.set_chat(container.chat_id, conversation_id)

                    # Wrong api type
                    else:
                        raise Exception('Wrong chatgpt_api_type')

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
                if not self.authenticator.chatbot_too_many_requests:
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

            # Release lock
            self.authenticator.chatbot_locked = False

        # Loop finished
        logging.warning('AIHandler loop finished')
        self.loop_running = False
