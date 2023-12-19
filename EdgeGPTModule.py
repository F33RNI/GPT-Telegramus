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

import asyncio
import ctypes
import json
import logging
import multiprocessing
import os
import uuid
from typing import List, Dict

from EdgeGPT.EdgeGPT import Chatbot
from EdgeGPT.conversation_style import ConversationStyle

import BotHandler
import UsersHandler
from RequestResponseContainer import RequestResponseContainer


def async_helper(awaitable_) -> None:
    """
    Runs async function inside sync
    :param awaitable_:
    :return:
    """
    # Try to get current event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    # Check it
    if loop and loop.is_running():
        loop.create_task(awaitable_)

    # We need new event loop
    else:
        asyncio.run(awaitable_)


class EdgeGPTModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.cancel_requested = multiprocessing.Value(ctypes.c_bool, False)
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes EdgeGPT bot using this API: https://github.com/acheong08/EdgeGPT
        :return:
        """
        self._enabled = False
        self._chatbot = None

        self.processing_flag.value = False
        self.cancel_requested.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["edgegpt"]["proxy"] and self.config["edgegpt"]["proxy"] != "auto":
                proxy = self.config["edgegpt"]["proxy"]

            # Log
            logging.info("Initializing EdgeGPT module with proxy {}".format(proxy))

            # Read cookies file
            cookies = None
            if self.config["edgegpt"]["cookies_file"] and os.path.exists(self.config["edgegpt"]["cookies_file"]):
                logging.info("Loading cookies from {}".format(self.config["edgegpt"]["cookies_file"]))
                cookies = json.loads(open(self.config["edgegpt"]["cookies_file"], encoding="utf-8").read())

            # Set enabled status
            self._enabled = self.config["modules"]["edgegpt"]
            if not self._enabled:
                logging.warning("EdgeGPT module disabled in config file!")
                raise Exception("EdgeGPT module disabled in config file!")

            # Initialize EdgeGPT chatbot
            if proxy and len(proxy) > 1 and proxy.strip().lower() != "auto":
                self._chatbot = asyncio.run(Chatbot.create(proxy=proxy, cookies=cookies))
            else:
                self._chatbot = asyncio.run(Chatbot.create(cookies=cookies))

            # Check
            if self._chatbot is not None:
                logging.info("EdgeGPT module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to EdgeGPT
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)

        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("EdgeGPT module not initialized!")
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                .format("EdgeGPT module not initialized!")
            request_response.error = True
            return

        try:
            # Set flag that we are currently processing request
            self.processing_flag.value = True
            self.cancel_requested.value = False

            # Get user data
            conversation_id = UsersHandler.get_key_or_none(request_response.user, "edgegpt_conversation_id")
            conversation_style = UsersHandler.get_key_or_none(request_response.user, "edgegpt_style")

            # Set default conversation style
            if conversation_style is None:
                conversation_style = self.config["edgegpt"]["conversation_style_type_default"]

            # Extract conversation style
            if conversation_style == 0:
                conversation_style_ = ConversationStyle.precise
            elif conversation_style == 1:
                conversation_style_ = ConversationStyle.balanced
            else:
                conversation_style_ = ConversationStyle.creative

            async def async_ask_stream_():
                async for data in self._chatbot.ask_stream(prompt=request_response.request,
                                                           conversation_style=conversation_style_,
                                                           raw=True):
                    # Split response
                    is_done, json_data = data

                    # Response
                    text_response = None
                    response_sources = []

                    # Type 1
                    if not is_done:
                        if "arguments" in json_data:
                            arguments = json_data["arguments"]
                            if len(arguments) > 0 and "messages" in arguments[-1]:
                                messages = arguments[-1]["messages"]
                                if len(messages) > 0:
                                    message = messages[-1]
                                    # Parse text response
                                    if "text" in message:
                                        text_response = message["text"]

                    # Type 2
                    else:
                        if "item" in json_data:
                            item = json_data["item"]
                            if "messages" in item:
                                messages = item["messages"]
                                if len(messages) > 0:
                                    # Try to find message with sourceAttributions
                                    for message in messages:
                                        response_sources.clear()

                                        # Parse text response
                                        if "text" in message:
                                            text_response = message["text"]

                                        # Parse sources
                                        if "sourceAttributions" in message:
                                            source_attributions = message["sourceAttributions"]
                                            for source_attribution in source_attributions:
                                                if "providerDisplayName" in source_attribution \
                                                        and "seeMoreUrl" in source_attribution:
                                                    response_sources.append((source_attribution["providerDisplayName"],
                                                                             source_attribution["seeMoreUrl"]))

                                        # We found it
                                        if len(response_sources) > 0 and text_response:
                                            break

                    # If we have text response
                    if text_response:
                        # Set to container
                        request_response.response = text_response

                        # Add sources
                        if len(response_sources) > 0:
                            request_response.response += "\n"
                        for response_source in response_sources:
                            request_response.response += self.messages[lang]["edgegpt_sources"]\
                                .format(response_source[0],
                                        response_source[1]).replace("\\n", "\n")

                        # Send message to user
                        await BotHandler.send_message_async(self.config, self.messages, request_response, end=False)

                    # Exit requested?
                    if self.cancel_requested.value:
                        logging.info("Exiting from loop")
                        break

            # Reset current conversation
            asyncio.run(self._chatbot.reset())

            # Try to load conversation
            if conversation_id:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"], conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info("Loading conversation from {}".format(conversation_file))
                    asyncio.run(self._chatbot.load_conversation(conversation_file))
                else:
                    conversation_id = None

            # Start request handling
            asyncio.run(async_ask_stream_())

            # Generate new conversation id
            if not conversation_id:
                conversation_id = str(uuid.uuid4()) + "_edgegpt"

            # Save conversation
            logging.info("Saving conversation to {}".format(conversation_id))
            asyncio.run(self._chatbot.save_conversation(os.path.join(self.config["files"]["conversations_dir"],
                                                                     conversation_id + ".json")))

            # Save to user data
            request_response.user["edgegpt_conversation_id"] = conversation_id
            self.users_handler.save_user(request_response.user)

            # Check response
            if len(request_response.response) > 0:
                logging.info("Response successfully processed for user {0} ({1})"
                             .format(request_response.user["user_name"], request_response.user["user_id"]))

            # No response
            else:
                logging.warning("Empty response for user {0} ({1})!"
                                .format(request_response.user["user_name"], request_response.user["user_id"]))
                request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                    .format("Empty response!")
                request_response.error = True

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # EdgeGPT or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True
            self.processing_flag.value = False

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
        edgegpt_conversation_id = UsersHandler.get_key_or_none(user, "edgegpt_conversation_id")

        # Check if we need to clear it
        if edgegpt_conversation_id:
            # Delete file
            try:
                conversation_file = os.path.join(self.config["files"]["conversations_dir"],
                                                 edgegpt_conversation_id + ".json")
                if os.path.exists(conversation_file):
                    logging.info("Removing {}".format(conversation_file))
                    os.remove(conversation_file)
            except Exception as e:
                logging.error("Error removing conversation file!", exc_info=e)

        # Reset user data
        user["edgegpt_conversation_id"] = None
        self.users_handler.save_user(user)

    def exit(self):
        """
        Aborts processing
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        if self._chatbot is not None:
            logging.warning("Closing EdgeGPT connection")
            try:
                async_helper(self._chatbot.close())
            except Exception as e:
                logging.error("Error closing EdgeGPT connection!", exc_info=e)
