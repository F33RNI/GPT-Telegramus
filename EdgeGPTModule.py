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
import logging
from asyncio import AbstractEventLoop

import EdgeGPT

import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class EdgeGPTModule:
    def __init__(self, config: dict, messages: dict, users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        self._enabled = False
        self._chatbot = None

    def initialize(self) -> None:
        """
        Initializes EdgeGPT bot using this API: https://github.com/acheong08/EdgeGPT
        :return:
        """
        try:
            # Set enabled status
            self._enabled = self.config["modules"]["edgegpt"]
            if not self._enabled:
                logging.warning("EdgeGPT module disabled in config file!")
                return

            # Create asyncio event loop
            if asyncio.get_event_loop() is None:
                asyncio.set_event_loop(asyncio.new_event_loop())

            # Initialize EdgeGPT chatbot
            self._chatbot = EdgeGPT.Chatbot()
            proxy = self.config["edgegpt"]["proxy"]
            if len(proxy) > 0:
                asyncio.create_task(self._chatbot.create(cookie_path=self.config["edgegpt"]["cookie_file"],
                                                         proxy=proxy))
            else:
                asyncio.create_task(self._chatbot.create(cookie_path=self.config["edgegpt"]["cookie_file"]))

            # Check
            if self._chatbot is not None:
                logging.info("EdgeGPT module initialized")

        # Error
        except Exception as e:
            logging.error("Error initializing EdgeGPT module!", exc_info=e)
            self._enabled = False

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to EdgeGPT
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled or self._chatbot is None:
            logging.error("EdgeGPT module not initialized!")
            request_response.response = self.messages["response_error"].replace("\\n", "\n") \
                .format("EdgeGPT module not initialized!")
            request_response.error = True
            return

        try:
            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            async def async_wrapper():
                conversation_style = EdgeGPT.ConversationStyle.balanced
                if self.config["edgegpt"]["conversation_style_type"] == "creative":
                    conversation_style = EdgeGPT.ConversationStyle.creative
                elif self.config["edgegpt"]["conversation_style_type"] == "precise":
                    conversation_style = EdgeGPT.ConversationStyle.precise

                wss_link = self.config["edgegpt"]["wss_link"]
                logging.info("Asking EdgeGPT...")
                if len(wss_link) > 0:
                    return await self._chatbot.ask(prompt=request_response.request,
                                                   conversation_style=conversation_style,
                                                   wss_link=wss_link)
                else:
                    return await self._chatbot.ask(prompt=request_response.request,
                                                   conversation_style=conversation_style)

            # Ask and parse
            edgegpt_response_raw = asyncio.run(async_wrapper())
            edgegpt_response = ""
            try:
                edgegpt_response = edgegpt_response_raw["item"]["messages"][-1]["text"]
            except Exception as e:
                logging.error("Error parsing EdgeGPT response!", exc_info=e)

            # Add sources
            sources_str = ""
            try:
                sources = edgegpt_response_raw["item"]["messages"][-1]["sourceAttributions"]
                for i in range(len(sources)):
                    sources_str += "[{0}] {1} ({2})\n".format(i + 1,
                                                                 sources[i]["providerDisplayName"],
                                                                 sources[i]["seeMoreUrl"])
            except:
                pass
            if sources_str and len(sources_str) > 0:
                edgegpt_response += "\n\n" + sources_str

            # Check response
            if len(edgegpt_response) > 0:
                logging.info("Response successfully processed for user {0} ({1})"
                             .format(request_response.user["user_name"], request_response.user["user_id"]))
                request_response.response = edgegpt_response

            # No response
            else:
                logging.warning("Empty response for user {0} ({1})!"
                                .format(request_response.user["user_name"], request_response.user["user_id"]))
                request_response.response = self.messages["response_error"].replace("\\n", "\n") \
                    .format("Empty response!")
                request_response.error = True

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # EdgeGPT or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)
            request_response.response = self.messages["response_error"].replace("\\n", "\n").format(str(e))
            request_response.error = True

    def clear_conversation(self) -> None:
        """
        Clears conversation (chat history)
        :return:
        """
        try:
            asyncio.create_task(self._chatbot.reset())
        except Exception as e:
            logging.error("Error clearing EdgeGPT history!", exc_info=e)

    def exit(self):
        """
        Aborts processing
        :return:
        """
        if self._chatbot is not None:
            logging.warning("Closing EdgeGPT connection")
            try:
                asyncio.create_task(self._chatbot.close())
            except Exception as e:
                logging.error("Error closing EdgeGPT connection!", exc_info=e)
