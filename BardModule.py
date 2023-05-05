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

import Bard

import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class BardModule:
    def __init__(self, config: dict, messages: dict, users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        self._enabled = False
        self._chatbot = None

    def initialize(self) -> None:
        """
        Initializes Bard bot using this API: https://github.com/acheong08/Bard
        :return:
        """
        try:
            # Set enabled status
            self._enabled = self.config["modules"]["bard"]
            if not self._enabled:
                logging.warning("Bard module disabled in config file!")
                return

            # Initialize chatbot
            self._chatbot = Bard.Chatbot(self.config["bard"]["token"])

            # Set proxy
            proxy = self.config["bard"]["proxy"]
            if proxy and len(proxy) > 1 and proxy.strip().lower() != "auto":
                self._chatbot.session.proxies.update({"http": proxy,
                                                      "https": proxy})

            # Done?
            if self._chatbot is not None:
                logging.info("Bard module initialized")
            else:
                self._enabled = False

        # Error
        except Exception as e:
            logging.error("Error initializing Bard module!", exc_info=e)
            self._enabled = False

    def set_proxy(self, proxy: str) -> None:
        """
        Sets new proxy
        :param proxy: https proxy but in format http://IP:PORT
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        if self.config["bard"]["proxy"].strip().lower() == "auto":
            logging.info("Setting proxy {0} for Bard module".format(proxy))
            self._chatbot.session.proxies.update({"http": proxy,
                                                  "https": proxy})

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Bard
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("Bard module not initialized!")
            request_response.response = self.messages["response_error"].replace("\\n", "\n") \
                .format("Bard module not initialized!")
            request_response.error = True
            return

        try:
            # Get user data
            bard_conversation_id = UsersHandler.get_key_or_none(request_response.user, "bard_conversation_id")
            bard_response_id = UsersHandler.get_key_or_none(request_response.user, "bard_response_id")
            bard_choice_id = UsersHandler.get_key_or_none(request_response.user, "bard_choice_id")

            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            # Set conversation id, response id and choice id
            if bard_conversation_id and bard_response_id and bard_choice_id:
                self._chatbot.conversation_id = bard_conversation_id
                self._chatbot.response_id = bard_response_id
                self._chatbot.choice_id = bard_choice_id
            else:
                self._chatbot.conversation_id = ""
                self._chatbot.response_id = ""
                self._chatbot.choice_id = ""

            # Ask Bard
            logging.info("Asking Bard...")
            bard_response = self._chatbot.ask(request_response.request)

            # Check response
            if not bard_response or len(bard_response) < 1 or "content" not in bard_response:
                raise Exception("Wrong Bard response!")

            # OK?
            logging.info("Response successfully processed for user {0} ({1})"
                         .format(request_response.user["user_name"], request_response.user["user_id"]))
            request_response.response = bard_response["content"]

            # Save user data
            if self._chatbot.conversation_id and self._chatbot.response_id and self._chatbot.choice_id:
                request_response.user["bard_conversation_id"] = self._chatbot.conversation_id
                request_response.user["bard_response_id"] = self._chatbot.response_id
                request_response.user["bard_choice_id"] = self._chatbot.choice_id
                self.users_handler.save_user(request_response.user)
                self._chatbot.conversation_id = ""
                self._chatbot.response_id = ""
                self._chatbot.choice_id = ""

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # Bard or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            request_response.response = self.messages["response_error"].replace("\\n", "\n").format(str(e))
            request_response.error = True

    def clear_conversation_for_user(self, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user:
        :return: True if cleared successfully
        """
        if not self._enabled or self._chatbot is None:
            return

        # Reset user data
        user["bard_conversation_id"] = ""
        user["bard_response_id"] = ""
        user["bard_choice_id"] = ""

        # Save user
        self.users_handler.save_user(user)

    def exit(self):
        """
        Aborts connection
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        self._chatbot.session.close()
