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

import EdgeGPT

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
    def __init__(self, config: dict, messages: dict, users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        self._enabled = False
        self._chatbot = None
        self._restart_attempts = 0

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

            # Initialize EdgeGPT chatbot
            self._chatbot = EdgeGPT.Chatbot()
            proxy = self.config["edgegpt"]["proxy"]
            if proxy and len(proxy) > 1 and proxy.strip().lower() != "auto":
                async_helper(self._chatbot.create(cookie_path=self.config["edgegpt"]["cookie_file"],
                                                  proxy=proxy))
            else:
                async_helper(self._chatbot.create(cookie_path=self.config["edgegpt"]["cookie_file"]))

            # Check
            if self._chatbot is not None:
                logging.info("EdgeGPT module initialized")

        # Error
        except Exception as e:
            logging.error("Error initializing EdgeGPT module!", exc_info=e)
            self._enabled = False

    def set_proxy(self, proxy: str) -> None:
        """
        Sets new proxy
        :param proxy: https proxy but in format http://IP:PORT
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        if self.config["edgegpt"]["proxy"].strip().lower() == "auto":
            logging.info("Setting proxy {0} for EdgeGPT module".format(proxy))
            self._chatbot.proxy = proxy

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
            self._restart_attempts = 0
            return

        try:
            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            edgegpt_response_raw = []

            async def async_wrapper(edgegpt_response_raw_):
                conversation_style = EdgeGPT.ConversationStyle.balanced
                if self.config["edgegpt"]["conversation_style_type"] == "creative":
                    conversation_style = EdgeGPT.ConversationStyle.creative
                elif self.config["edgegpt"]["conversation_style_type"] == "precise":
                    conversation_style = EdgeGPT.ConversationStyle.precise

                wss_link = self.config["edgegpt"]["wss_link"]
                logging.info("Asking EdgeGPT...")
                if len(wss_link) > 0:
                    edgegpt_response_raw_.append(await self._chatbot.ask(prompt=request_response.request,
                                                                         conversation_style=conversation_style,
                                                                         wss_link=wss_link))
                else:
                    edgegpt_response_raw_.append(await self._chatbot.ask(prompt=request_response.request,
                                                                         conversation_style=conversation_style))

            # Ask and parse
            async_helper(async_wrapper(edgegpt_response_raw))
            edgegpt_response_raw = edgegpt_response_raw[0]
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
                    sources_str += self.messages["edgegpt_sources"].format(i + 1,
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

            # Reset attempts counter
            self._restart_attempts = 0

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            self._restart_attempts = 0
            return

        # EdgeGPT or other error
        except Exception as e:
            # Try to restart
            self.restart()
            self._restart_attempts += 1

            # Try again 1 time
            if self._restart_attempts < 2:
                self.process_request(request_response)

            # Stop restarting and respond with error
            else:
                request_response.response = self.messages["response_error"].replace("\\n", "\n").format(str(e))
                request_response.error = True
                self._restart_attempts = 0

    def clear_conversation(self) -> None:
        """
        Clears conversation (chat history)
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        try:
            async_helper(self._chatbot.reset())
        except Exception as e:
            logging.error("Error clearing EdgeGPT history!", exc_info=e)

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

    def restart(self):
        """
        Restarts module and saves proxy
        :return:
        """
        if not self._enabled or self._chatbot is None:
            return
        logging.info("Restarting EdgeGPT module")

        # Save proxy
        proxy = self._chatbot.proxy

        # Restart
        self.exit()
        self.initialize()

        # Set proxy
        self._chatbot.proxy = proxy
