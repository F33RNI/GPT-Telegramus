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

import json
import logging
import os.path
import time
import uuid

import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class ChatGPTModule:
    def __init__(self, config: dict, messages: dict, users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        self._conversations_dir = ""
        self._enabled = False
        self._api_type = 0
        self._cooldown_seconds = 0
        self._last_request_time = 0
        self._chatbot = None
        self._exit_flag = False
        self._processing_flag = False

    def initialize(self) -> None:
        """
        Initializes ChatGPT bot using this API: https://github.com/acheong08/ChatGPT
        :return:
        """
        self._exit_flag = False
        try:
            # Set enabled status
            self._enabled = self.config["modules"]["chatgpt"]
            if not self._enabled:
                logging.warning("ChatGPT module disabled in config file!")
                return

            # Get API type from config
            self._api_type = int(self.config["modules"]["chatgpt_api_type"])

            # Get conversations directory
            self._conversations_dir = self.config["files"]["conversations_dir"]

            # Get cooldown delay
            self._cooldown_seconds = self.config["chatgpt"]["cooldown_seconds"]

            # Set chatbot object to None (reset it)
            self._chatbot = None

            # API type 1
            if self._api_type == 1:
                logging.info("Initializing ChatGPT module with API type 1")
                from revChatGPT.V1 import Chatbot
                self._chatbot = Chatbot(config=self._get_chatbot_config())

            # API type 3
            elif self._api_type == 3:
                logging.info("Initializing ChatGPT module with API type 3")
                from revChatGPT.V3 import Chatbot
                engine = str(self.config["chatgpt"]["engine"])
                proxy = str(self.config["chatgpt"]["proxy"])
                if proxy.strip().lower() == "auto":
                    proxy = ""

                if len(engine) > 0:
                    self._chatbot = Chatbot(str(self.config["chatgpt"]["api_key"]),
                                            proxy=proxy,
                                            engine=engine)
                else:
                    self._chatbot = Chatbot(str(self.config["chatgpt"]["api_key"]),
                                            proxy=proxy)

            # Wrong API type
            else:
                raise Exception("Wrong API type: {0}".format(self._api_type))

            # Check
            if self._chatbot is not None:
                logging.info("ChatGPT module initialized")

        # Error
        except Exception as e:
            logging.error("Error initializing ChatGPT module!", exc_info=e)
            self._enabled = False

    def set_proxy(self, proxy: str) -> None:
        """
        Sets new proxy
        :param proxy: https proxy but in format http://IP:PORT
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        if self.config["chatgpt"]["proxy"].strip().lower() == "auto":
            logging.info("Setting proxy {0} for ChatGPT module".format(proxy))
            self._chatbot.proxy = proxy

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to ChatGPT
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("ChatGPT module not initialized!")
            request_response.response = self.messages["response_error"].replace("\\n", "\n")\
                .format("ChatGPT module not initialized!")
            request_response.error = True
            self._processing_flag = False
            return

        try:
            # Set flag that we are currently processing request
            self._processing_flag = True

            # Temp response variable
            chatgpt_response = None

            # Get user data
            conversation_id = UsersHandler.get_key_or_none(request_response.user, "conversation_id")
            parent_id = UsersHandler.get_key_or_none(request_response.user, "parent_id")

            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            # Cooldown to prevent 429 Too Many Requests
            if time.time() - self._last_request_time <= self._cooldown_seconds:
                logging.warning("Too frequent requests. Waiting {0} seconds..."
                                .format(int(self._cooldown_seconds - (time.time() - self._last_request_time))))
                while time.time() - self._last_request_time <= self._cooldown_seconds:
                    time.sleep(0.1)
                    if self._exit_flag:
                        logging.warning("Exiting process_request")
                        self._processing_flag = False
                        return
            self._last_request_time = time.time()

            # API type 1
            if self._api_type == 1:
                # Reset current chat
                self._chatbot.reset_chat()

                # Ask
                logging.info("Asking ChatGPT (API type 1)...")
                for data in self._chatbot.ask(request_response.request,
                                              conversation_id=conversation_id,
                                              parent_id=parent_id if parent_id is not None else ""):
                    # Get last response
                    chatgpt_response = data["message"]

                    # Store conversation_id
                    if "conversation_id" in data and data["conversation_id"] is not None:
                        conversation_id = data["conversation_id"]

                    # Store parent_id
                    if "parent_id" in data and data["parent_id"] is not None:
                        parent_id = data["parent_id"]

                    # Exit?
                    if self._exit_flag:
                        break

                # Log conversation id and parent id
                logging.info("Current conversation_id: {0}, parent_id: {1}".format(conversation_id, parent_id))

                # Save conversation id and parent id
                request_response.user["conversation_id"] = conversation_id
                request_response.user["parent_id"] = parent_id

            # API type 3
            if self._api_type == 3:
                # Try to load conversation
                if not self._load_conversation(conversation_id):
                    conversation_id = None

                # Generate new random conversation ID
                if conversation_id is None:
                    conversation_id = str(uuid.uuid4())

                # Ask
                logging.info("Asking ChatGPT (API type 3)...")
                for data in self._chatbot.ask(request_response.request, convo_id=conversation_id):
                    # Initialize response
                    if chatgpt_response is None:
                        chatgpt_response = ""

                    # Append response
                    chatgpt_response += str(data)

                    # Exit?
                    if self._exit_flag:
                        break

                # Save conversation id
                if not self._save_conversation(conversation_id):
                    conversation_id = None
                request_response.user["conversation_id"] = conversation_id

                # Reset conversation
                if conversation_id is not None:
                    self._chatbot.reset(conversation_id)
                    try:
                        del self._chatbot.conversation[conversation_id]
                    except Exception as e:
                        logging.warning("Error deleting key {0} from chatbot.conversation".format(conversation_id),
                                        exc_info=e)

            # Wrong API type
            else:
                self._processing_flag = False
                raise Exception("Wrong API type: {0}".format(self._api_type))

            # Save user data to database
            self.users_handler.save_user(request_response.user)

            # Check response
            if chatgpt_response is not None and len(chatgpt_response) > 0:
                logging.info("Response successfully processed for user {0} ({1})"
                             .format(request_response.user["user_name"], request_response.user["user_id"]))
                request_response.response = chatgpt_response

            # No response
            else:
                logging.warning("Empty response for user {0} ({1})!"
                                .format(request_response.user["user_name"], request_response.user["user_id"]))
                request_response.response = self.messages["response_error"].replace("\\n", "\n")\
                    .format("Empty response!")
                request_response.error = True

            # Clear processing flag
            self._processing_flag = False

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            self._processing_flag = False
            return

        # ChatGPT or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            request_response.response = self.messages["response_error"].replace("\\n", "\n").format(str(e))
            request_response.error = True
            self._processing_flag = False

    def clear_conversation_for_user(self, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user:
        :return: True if cleared successfully
        """
        if not self._enabled or self._chatbot is None:
            return
        conversation_id = UsersHandler.get_key_or_none(user, "conversation_id")
        if conversation_id is None:
            return
        self._delete_conversation(conversation_id)

    def exit(self):
        """
        Aborts processing
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        self._exit_flag = True

        # Wait until aborted
        while self._processing_flag:
            time.sleep(0.1)

    def _save_conversation(self, conversation_id) -> bool:
        """
        Saves conversation (only for API type 3)
        :param conversation_id:
        :return: True if no error
        """
        logging.info("Saving conversation {0}".format(conversation_id))
        try:
            if conversation_id is None:
                logging.info("conversation_id is None. Skipping saving")
                return False

            # API type 3
            if self._api_type == 3:
                # Check conversations directory
                if not os.path.exists(self._conversations_dir):
                    logging.info("Creating directory: {0}".format(self._conversations_dir))
                    os.makedirs(self._conversations_dir)

                # Save as json file
                conversation_file = os.path.join(self._conversations_dir, conversation_id + ".json")
                with open(conversation_file, "w", encoding="utf-8") as json_file:
                    json.dump(self._chatbot.conversation, json_file, indent=4)
                    json_file.close()

        except Exception as e:
            logging.error("Error saving conversation {0}".format(conversation_id), exc_info=e)
            return False

        return True

    def _load_conversation(self, conversation_id) -> bool:
        """
        Loads conversation (only for API type 3)
        :param conversation_id:
        :return: True if no error
        """
        logging.info("Loading conversation {0}".format(conversation_id))
        try:
            if conversation_id is None:
                logging.info("conversation_id is None. Skipping loading")
                return False

            # API type 3
            if self._api_type == 3:
                conversation_file = os.path.join(self._conversations_dir, conversation_id + ".json")
                if os.path.exists(conversation_file):
                    # Load from json file
                    with open(conversation_file, "r", encoding="utf-8") as json_file:
                        self._chatbot.conversation = json.load(json_file)
                        json_file.close()
                else:
                    logging.warning("File {0} not exists!".format(conversation_file))

        except Exception as e:
            logging.warning("Error loading conversation {0}".format(conversation_id), exc_info=e)
            return False

        return True

    def _delete_conversation(self, conversation_id) -> bool:
        """
        Deletes conversation
        :param conversation_id:
        :return:
        """
        logging.info("Deleting conversation " + conversation_id)
        try:
            deleted = False

            # API type 1
            if self._api_type == 1:
                self._chatbot.reset_chat()
                try:
                    self._chatbot.delete_conversation(conversation_id)
                    deleted = True
                except Exception as e:
                    logging.error("Error deleting conversation {0}".format(conversation_id), exc_info=e)

            # API type 3
            elif self._api_type == 3:
                self._chatbot.reset(conversation_id)
                deleted = True

            # Wrong API type
            else:
                raise Exception("Wrong API type: {0}".format(self._api_type))

            # Delete conversation file if exists
            try:
                conversation_file = os.path.join(self._conversations_dir, conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info("Deleting {0} file".format(conversation_file))
                    os.remove(conversation_file)
                return deleted

            except Exception as e:
                logging.error("Error removing conversation file for conversation {0}".format(conversation_id),
                              exc_info=e)

        except Exception as e:
            logging.warning("Error loading conversation {0}".format(conversation_id),
                            exc_info=e)
        return False

    def _get_chatbot_config(self) -> dict:
        """
        Constructs chatbot config for API type 1
        See: https://github.com/acheong08/ChatGPT
        :return:
        """
        config = {}

        # Use email/password
        if len(self.config["chatgpt"]["email"]) > 0 \
                and len(self.config["chatgpt"]["password"]) > 0:
            config["email"] = self.config["chatgpt"]["email"]
            config["password"] = self.config["chatgpt"]["password"]

        # Use session_token
        elif len(self.config["chatgpt"]["session_token"]) > 0:
            config["session_token"] = self.config["chatgpt"]["session_token"]

        # Use access_token
        elif len(self.config["chatgpt"]["access_token"]) > 0:
            config["access_token"] = self.config["chatgpt"]["access_token"]

        # No credentials
        else:
            raise Exception("Error! No credentials to login!")

        # Add proxy
        if len(self.config["chatgpt"]["proxy"]) > 0 and self.config["chatgpt"]["proxy"].strip().lower() != "auto":
            config["proxy"] = self.config["chatgpt"]["proxy"]

        # Paid?
        config["paid"] = self.config["chatgpt"]["paid"]

        return config
