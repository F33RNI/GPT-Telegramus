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
from typing import List, Dict

from BingImageCreator import ImageGen

import BotHandler
import UsersHandler
from JSONReaderWriter import load_json
from RequestResponseContainer import RequestResponseContainer


class BingImageGenModule:
    def __init__(self, config: dict, messages: List[Dict], users_handler: UsersHandler.UsersHandler) -> None:
        self.config = config
        self.messages = messages
        self.users_handler = users_handler

        # All variables here must be multiprocessing
        self.processing_flag = multiprocessing.Value(ctypes.c_bool, False)

    def initialize(self, proxy=None) -> None:
        """
        Initializes Bing ImageGen API
        :return:
        """
        self._enabled = False
        self._image_generator = None

        self.processing_flag.value = False

        try:
            # Use manual proxy
            if not proxy and self.config["bing_imagegen"]["proxy"] and self.config["bing_imagegen"]["proxy"] != "auto":
                proxy = self.config["bing_imagegen"]["proxy"]

            # Log
            logging.info("Initializing Bing ImageGen module with proxy {}".format(proxy))

            # Set enabled status
            self._enabled = self.config["modules"]["bing_imagegen"]
            if not self._enabled:
                logging.warning("Bing ImageGen module disabled in config file!")
                raise Exception("Bing ImageGen module disabled in config file!")

            # Parse cookies
            auth_cookie = ""
            auth_cookie_SRCHHPGUSR = ""
            try:
                cookies = load_json(self.config["bing_imagegen"]["cookies_file"])
                if not cookies or len(cookies) < 1:
                    raise "Error reading bing cookies!"
                for cookie in cookies:
                    if cookie["name"] == "_U":
                        auth_cookie = cookie["value"]
                    elif cookie["name"] == "SRCHHPGUSR":
                        auth_cookie_SRCHHPGUSR = cookie["value"]
                if not auth_cookie:
                    raise "No _U cookie!"
                if not auth_cookie_SRCHHPGUSR:
                    raise "No SRCHHPGUSR cookie!"
            except Exception as e:
                raise e

            # Initialize Bing ImageGen
            self._image_generator = ImageGen(auth_cookie=auth_cookie,
                                             auth_cookie_SRCHHPGUSR=auth_cookie_SRCHHPGUSR,
                                             quiet=True,
                                             all_cookies=cookies)

            # Set proxy
            if proxy:
                self._image_generator.session.proxies = {"http": proxy, "https": proxy}

            # Check
            if self._image_generator is not None:
                logging.info("Bing ImageGen module initialized")

        # Error
        except Exception as e:
            self._enabled = False
            raise e

    def process_request(self, request_response: RequestResponseContainer) -> None:
        """
        Processes request to Bing ImageGen
        :param request_response: RequestResponseContainer object
        :return:
        """
        # Get user language
        lang = UsersHandler.get_key_or_none(request_response.user, "lang", 0)

        # Check if we are initialized
        if not self._enabled:
            logging.error("Bing ImageGen module not initialized!")
            request_response.response = self.messages[lang]["response_error"].replace("\\n", "\n") \
                .format("Bing ImageGen module not initialized!")
            request_response.error = True
            return

        try:
            # Increment requests_total for statistics
            request_response.user["requests_total"] += 1
            self.users_handler.save_user(request_response.user)

            # Generate images
            logging.info("Requesting images from Bing ImageGen")
            response_urls = self._image_generator.get_images(request_response.request)

            # Check response
            if not response_urls or len(response_urls) < 1:
                raise Exception("Wrong Bing ImageGen response!")

            # Use all generated images
            logging.info("Response successfully processed for user {0} ({1})"
                         .format(request_response.user["user_name"], request_response.user["user_id"]))
            request_response.response_images = response_urls

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
