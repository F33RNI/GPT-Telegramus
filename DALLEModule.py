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
from typing import List, Dict

import httpx
from openai import OpenAI

import BotHandler
import UsersHandler
from RequestResponseContainer import RequestResponseContainer


class DALLEModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler
        self.client = None

    def initialize(self, proxy=None) -> None:
        """
        Initializes DALL-E official API
        :return:
        """
        self._enabled = False

        try:
            # Use manual proxy
            if not proxy and self.config["dalle"]["proxy"] and self.config["dalle"]["proxy"] != "auto":
                proxy = self.config["dalle"]["proxy"]

            # Log
            logging.info("Initializing DALL-E module with proxy {}".format(proxy))

            # Set enabled status
            self._enabled = self.config["modules"]["dalle"]
            if not self._enabled:
                logging.warning("DALL-E module disabled in config file!")
                raise Exception("DALL-E module disabled in config file!")

            # Set Key
            api_key = self.config["dalle"]["open_ai_api_key"]

            http_client = None
            # Set proxy
            if proxy:
                http_client = httpx.Client(proxies=proxy)

            self.client = OpenAI(api_key=api_key, http_client=http_client)

            # Done?
            logging.info("DALL-E module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to DALL-E
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)

        # Check if we are initialized
        if not self._enabled:
            logging.error("DALL-E module not initialized!")
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                .format("DALL-E module not initialized!")
            request_response.error = True
            return

        try:
            # Set Key
            openai.api_key = self.config["dalle"]["open_ai_api_key"]

            # Generate image
            logging.info("Requesting image from DALL-E")
            image_response = self.client.images.generate(prompt=request_response.request,
                                                 n=1,
                                                 size=self.config["dalle"]["image_size"])
            response_url = image_response.data[0].url

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
            error_text = str(e)
            if len(error_text) > 100:
                error_text = error_text[:100] + "..."

            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n").format(error_text)
            request_response.error = True

        # Finish message
        BotHandler.async_helper(BotHandler.send_message_async(self.config, self.messages, request_response, end=True))
