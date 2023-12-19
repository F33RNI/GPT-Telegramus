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
import ctypes
import logging
import multiprocessing
import os
from typing import List, Dict

import requests
from bardapi import Bard

import BotHandler
import UsersHandler
from JSONReaderWriter import load_json, save_json
from RequestResponseContainer import RequestResponseContainer


class BardModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes Bard bot using this API: https://github.com/acheong08/Bard
        :return:
        """
        self._enabled = False
        self._chatbot = None
        self.processing_flag.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["bard"]["proxy"] and self.config["bard"]["proxy"] != "auto":
                proxy = self.config["bard"]["proxy"]

            # Log
            logging.info("Initializing Bard module with proxy {}".format(proxy))

            # Set enabled status
            self._enabled = self.config["modules"]["bard"]
            if not self._enabled:
                logging.warning("Bard module disabled in config file!")
                raise Exception("Bard module disabled in config file!")

            # Load cookies and secure_1psid
            secure_1psid = None
            session = requests.Session()
            session_cookies = load_json(self.config["bard"]["cookies_file"], logging_enabled=True)
            for i in range(len(session_cookies)):
                session.cookies.set(session_cookies[i]["name"],
                                    session_cookies[i]["value"],
                                    domain=session_cookies[i]["domain"],
                                    path=session_cookies[i]["path"])
                if secure_1psid is None and session_cookies[i]["name"] == "__Secure-1PSID":
                    secure_1psid = session_cookies[i]["value"]

            # Set headers
            session.headers = {
                "Host": "bard.google.com",
                "X-Same-Domain": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/91.4472.114 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": "https://bard.google.com",
                "Referer": "https://bard.google.com/",
            }

            # Initialize chatbot
            if proxy:
                self._chatbot = Bard(token=secure_1psid, proxies={"https": proxy, "http": proxy}, session=session)
            else:
                self._chatbot = Bard(token=secure_1psid, session=session)

            # Done?
            if self._chatbot is not None:
                logging.info("Bard module initialized")
            else:
                self._enabled = False

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Bard
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("Bard module not initialized!")
            lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                .format("Bard module not initialized!")
            request_response.error = True
            self.processing_flag.value = False
            return

        try:
            # Set processing flag
            self.processing_flag.value = True

            # Get user data
            conversation_id = UsersHandler.get_key_or_none(request_response.user, "bard_conversation_id")
            response_id = UsersHandler.get_key_or_none(request_response.user, "bard_response_id")
            choice_id = UsersHandler.get_key_or_none(request_response.user, "bard_choice_id")

            # Try to load conversation
            if conversation_id and response_id and choice_id:
                logging.info("Using conversation_id: {}, response_id: {} and choice_id: {}".format(conversation_id,
                                                                                                   response_id,
                                                                                                   choice_id))
                self._chatbot.conversation_id = conversation_id
                self._chatbot.response_id = response_id
                self._chatbot.choice_id = choice_id

            # Try to download image
            image_bytes = None
            if request_response.image_url:
                logging.info("Downloading user image")
                image_bytes = requests.get(request_response.image_url, timeout=120).content

            # Ask Bard
            logging.info("Asking Bard...")
            bard_response = self._chatbot.get_answer(request_response.request, image=image_bytes)

            # Check response
            if not bard_response or len(bard_response) < 1 or "content" not in bard_response:
                raise Exception("Wrong Bard response!")

            # OK?
            logging.info("Response successfully processed for user {0} ({1})"
                         .format(request_response.user["user_name"], request_response.user["user_id"]))
            request_response.response = bard_response["content"]
            if "images" in bard_response and len(bard_response["images"]) > 0:
                request_response.response_images = bard_response["images"]

            # Save conversation
            logging.info("Saving conversation_id as {} and response_id as {} and choice_id as {}".
                         format(self._chatbot.conversation_id, self._chatbot.response_id, self._chatbot.choice_id))
            request_response.user["bard_conversation_id"] = self._chatbot.conversation_id
            request_response.user["bard_response_id"] = self._chatbot.response_id
            request_response.user["bard_choice_id"] = self._chatbot.choice_id
            self.users_handler.save_user(request_response.user)

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # Bard or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True

        # Try to save cookies
        try:
            if self._chatbot and self._chatbot.session and self._chatbot.session.cookies:
                session_cookies = load_json(self.config["bard"]["cookies_file"], logging_enabled=True)
                for i in range(len(session_cookies)):
                    session_cookies[i]["value"] = self._chatbot.session.cookies.get(session_cookies[i]["name"],
                                                                                    domain=session_cookies[i]["domain"],
                                                                                    path=session_cookies[i]["path"])
                save_json(self.config["bard"]["cookies_file"], session_cookies, True)
        except Exception as e:
            logging.error("Error saving cookies!", exc_info=e)

        # Finish message
        BotHandler.async_helper(BotHandler.send_message_async(self.config, self.messages, request_response, end=True))

        # Clear processing flag
        self.processing_flag.value = False

    def clear_conversation_for_user(self, user: dict) -> None:
        """
        Clears conversation (chat history) for selected user
        :param user:
        :return:
        """
        # Get conversation id
        bard_conversation_id = UsersHandler.get_key_or_none(user, "bard_conversation_id")

        # Check if we need to clear it
        if bard_conversation_id:
            # Delete file
            try:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"],
                                                 bard_conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info("Removing {}".format(conversation_file))
                    os.remove(conversation_file)
            except Exception as e:
                logging.error("Error removing conversation file!", exc_info=e)

        # Reset user data
        user["bard_conversation_id"] = None
        user["bard_response_id"] = None
        user["bard_choice_id"] = None
        self.users_handler.save_user(user)

    def exit(self):
        """
        Aborts connection
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
