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

import openai

import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class DALLEModule:
    def __init__(self, config: dict, messages: dict, users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        self._enabled = False
        self._restart_attempts = 0

    def initialize(self) -> None:
        """
        Initializes DALL-E official API
        :return:
        """
        try:
            # Set enabled status
            self._enabled = self.config["modules"]["dalle"]
            if not self._enabled:
                logging.warning("DALL-E module disabled in config file!")
                return

            # Set Key
            openai.api_key = self.config["dalle"]["open_ai_api_key"]

            # Proxy for DALL-E
            proxy = self.config["dalle"]["proxy"]
            if proxy and len(proxy) > 1 and proxy.strip().lower() != "auto":
                openai.proxy = proxy

            # Done?
            logging.info("DALL-E module initialized")

        # Error
        except Exception as e:
            logging.error("Error initializing DALL-E module!", exc_info=e)
            self._enabled = False

    def set_proxy(self, proxy: str) -> None:
        """
        Sets new proxy
        :param proxy: https proxy but in format http://IP:PORT
        :return:
        """
        if not self._enabled:
            return
        if self.config["dalle"]["proxy"].strip().lower() == "auto":
            logging.info("Setting proxy {0} for DALL-E module".format(proxy))
            openai.proxy = proxy

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to DALL-E
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Check if we are initialized
        if not self._enabled:
            logging.error("DALL-E module not initialized!")
            request_response.response = self.messages["response_error"].replace("\\n", "\n") \
                .format("DALL-E module not initialized!")
            request_response.error = True
            return

        try:
            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            # Set Key
            openai.api_key = self.config["dalle"]["open_ai_api_key"]

            # Generate image
            logging.info("Requesting image from DALL-E")
            image_response = openai.Image.create(prompt=request_response.request,
                                                 n=1,
                                                 size=self.config["dalle"]["image_size"])
            response_url = image_response["data"][0]["url"]

            # Check response
            if not response_url or len(response_url) < 1:
                raise Exception("Wrong DALL-E response!")

            # OK?
            logging.info("Response successfully processed for user {0} ({1})"
                         .format(request_response.user["user_name"], request_response.user["user_id"]))
            request_response.response = response_url

        # Exit requested
        except KeyboardInterrupt:
            logging.warning("KeyboardInterrupt @ process_request")
            return

        # DALL-E or other error
        except Exception as e:
            logging.error("Error processing request!", exc_info=e)

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

    def restart(self):
        """
        Restarts module and saves proxy
        :return:
        """
        if not self._enabled:
            return
        logging.info("Restarting DALL-E module")

        # Save proxy
        proxy = openai.proxy

        # Restart
        self.initialize()

        # Set proxy
        openai.proxy = proxy
