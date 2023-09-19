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

import argparse
import logging
import multiprocessing
import os
import sys

import BardModule
import BingImageGenModule
import BotHandler
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import LoggingHandler
import ProxyAutomation
import QueueHandler
import UsersHandler
from JSONReaderWriter import load_json

# GPT-Telegramus version
__version__ = "3.4.5"

# Logging level
LOGGING_LEVEL = logging.INFO

# Default config file
CONFIG_FILE = "config.json"


def parse_args():
    """
    Parses cli arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, help="config.json file location",
                        default=os.getenv("TELEGRAMUS_CONFIG_FILE", CONFIG_FILE))
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args()


def main():
    """
    Main entry
    :return:
    """
    # Parse arguments
    args = parse_args()

    # Multiprocessing fix for Windows
    if sys.platform.startswith("win"):
        multiprocessing.freeze_support()

    # Initialize logging and start listener as process
    logging_handler = LoggingHandler.LoggingHandler()
    logging_handler_process = multiprocessing.Process(target=logging_handler.configure_and_start_listener)
    logging_handler_process.start()
    LoggingHandler.worker_configurer(logging_handler.queue)
    logging.info("LoggingHandler PID: " + str(logging_handler_process.pid))

    # Log software version and GitHub link
    logging.info("GPT-Telegramus version: " + str(__version__))
    logging.info("https://github.com/F33RNI/GPT-Telegramus")

    # Load config with multiprocessing support
    config = multiprocessing.Manager().dict(load_json(args.config))

    # Load messages from json file with multiprocessing support
    messages = multiprocessing.Manager().list(load_json(config["files"]["messages_file"]))

    # Check and create conversations directory
    if not os.path.exists(config["files"]["conversations_dir"]):
        logging.info("Creating directory: {0}".format(config["files"]["conversations_dir"]))
        os.makedirs(config["files"]["conversations_dir"])

    # Initialize UsersHandler and ProxyAutomation classes
    user_handler = UsersHandler.UsersHandler(config, messages)
    proxy_automation = ProxyAutomation.ProxyAutomation(config)

    # Pre-initialize modules
    chatgpt_module = ChatGPTModule.ChatGPTModule(config, messages, user_handler)
    dalle_module = DALLEModule.DALLEModule(config, messages, user_handler)
    bard_module = BardModule.BardModule(config, messages, user_handler)
    edgegpt_module = EdgeGPTModule.EdgeGPTModule(config, messages, user_handler)
    bing_image_gen_module = BingImageGenModule.BingImageGenModule(config, messages, user_handler)

    # Initialize QueueHandler class
    queue_handler = QueueHandler.QueueHandler(config, messages, logging_handler.queue, user_handler, proxy_automation,
                                              chatgpt_module,
                                              dalle_module,
                                              bard_module,
                                              edgegpt_module,
                                              bing_image_gen_module)

    # Initialize Telegram bot class
    bot_handler = BotHandler.BotHandler(config, messages, user_handler, queue_handler, proxy_automation,
                                        logging_handler.queue,
                                        chatgpt_module, bard_module, edgegpt_module)

    # Start proxy automation
    proxy_automation.start_automation_loop()

    # Start processing loop in thread
    queue_handler.start_processing_loop()

    # Finally, start telegram bot in main thread
    bot_handler.start_bot()

    # If we're here, exit requested
    proxy_automation.stop_automation_loop()
    queue_handler.stop_processing_loop()
    logging.info("GPT-Telegramus exited successfully")

    # Finally, stop logging loop
    logging_handler.queue.put(None)


if __name__ == "__main__":
    main()
