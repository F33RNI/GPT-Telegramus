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
import datetime
import logging
import os
import sys

import BardModule
import BotHandler
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import ProxyAutomation
import QueueHandler
import UsersHandler
from JSONReaderWriter import load_json

# GPT-Telegramus version
__version__ = "2.1.4"

# Logging level
LOGGING_LEVEL = logging.INFO

# Default config file
CONFIG_FILE = "config.json"


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

    # Load config
    config = load_json(args.config, logging_enabled=False)

    # Initialize logging
    logging_setup(config["files"]["logs_dir"])

    # Load messages from json file
    messages = load_json(config["files"]["messages_file"])

    # Initialize classes
    user_handler = UsersHandler.UsersHandler(config, messages)

    chatgpt_module = ChatGPTModule.ChatGPTModule(config, messages, user_handler)
    dalle_module = DALLEModule.DALLEModule(config, messages, user_handler)
    edgegpt_module = EdgeGPTModule.EdgeGPTModule(config, messages, user_handler)
    bard_module = BardModule.BardModule(config, messages, user_handler)

    proxy_automation = ProxyAutomation.ProxyAutomation(config,
                                                       chatgpt_module, dalle_module, edgegpt_module, bard_module)

    queue_handler = QueueHandler.QueueHandler(config, chatgpt_module, dalle_module, edgegpt_module, bard_module)
    bot_handler = BotHandler.BotHandler(config, messages, user_handler, queue_handler, proxy_automation,
                                        chatgpt_module, edgegpt_module, dalle_module, bard_module)

    # Initialize modules
    chatgpt_module.initialize()
    dalle_module.initialize()
    edgegpt_module.initialize()
    bard_module.initialize()

    # Start proxy automation
    proxy_automation.start_automation_loop()

    # Start processing loop in thread
    queue_handler.start_processing_loop()

    # Finally, start telegram bot in main thread
    bot_handler.start_bot()

    # If we're here, exit requested
    proxy_automation.stop_automation_loop()
    chatgpt_module.exit()
    bard_module.exit()
    edgegpt_module.exit()
    queue_handler.stop_processing_loop()
    logging.info("GPT-Telegramus exited successfully")


if __name__ == "__main__":
    main()
