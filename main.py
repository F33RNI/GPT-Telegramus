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
import asyncio
import datetime
import logging
import os
import sys

import BotHandler
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import QueueHandler
import UsersHandler
from JSONReaderWriter import load_json

# GPT-Telegramus version
__version__ = "beta_3.0.0"

# Logging level
LOGGING_LEVEL = logging.INFO

# Files and directories
SETTINGS_FILE = "settings.json"
MESSAGES_FILE = "messages.json"
LOGS_DIR = "logs"


def logging_setup(directory: str):
    """
    Sets up logging format and level
    :param directory: Directory where to save logs
    :return:
    """
    # Create logs directory
    if not os.path.exists(directory):
        os.makedirs(directory)

    # Create logs formatter
    log_formatter = logging.Formatter("%(asctime)s %(threadName)s %(levelname)-8s %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S")

    # Setup logging into file
    file_handler = logging.FileHandler(os.path.join(directory,
                                                    datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".log"),
                                       encoding="utf-8")
    file_handler.setFormatter(log_formatter)

    # Setup logging into console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)

    # Add all handlers and setup level
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(LOGGING_LEVEL)

    # Log test message
    logging.info("logging setup is complete")


def parse_args():
    """
    Parses cli arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", type=str, help="settings.json file location",
                        default=os.getenv("TELEGRAMUS_SETTINGS_FILE", SETTINGS_FILE))
    parser.add_argument("--messages", type=str, help="messages.json file location",
                        default=os.getenv("TELEGRAMUS_MESSAGES_FILE", MESSAGES_FILE))
    parser.add_argument("--logs", type=str, help="logs directory",
                        default=os.getenv("TELEGRAMUS_LOGS_DIR", LOGS_DIR))
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args()


def main():
    """
    Main entry
    :return:
    """
    # Parse arguments
    args = parse_args()

    # Initialize logging
    logging_setup(args.logs)

    # Load settings and messages from json files
    settings = load_json(args.settings)
    messages = load_json(args.messages)

    # Initialize classes
    user_handler = UsersHandler.UsersHandler(settings, messages)

    chatgpt_module = ChatGPTModule.ChatGPTModule(settings, messages, user_handler)
    dalle_module = DALLEModule.DALLEModule(settings, messages, user_handler)
    edgegpt_module = EdgeGPTModule.EdgeGPTModule(settings, messages, user_handler)

    queue_handler = QueueHandler.QueueHandler(settings, chatgpt_module, dalle_module, edgegpt_module)
    bot_handler = BotHandler.BotHandler(settings, messages, user_handler, queue_handler,
                                        chatgpt_module, edgegpt_module)

    # Initialize modules
    chatgpt_module.initialize()
    dalle_module.initialize()
    edgegpt_module.initialize()

    # Start processing loop in thread
    queue_handler.start_processing_loop()

    # Finally, start telegram bot in main thread
    bot_handler.start_bot()

    # If we're here, exit requested
    chatgpt_module.exit()
    queue_handler.stop_processing_loop()
    logging.info("GPT-Telegramus exited successfully")


if __name__ == "__main__":
    main()
