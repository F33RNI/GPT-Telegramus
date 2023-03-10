"""
 Copyright (C) 2022 Fern Lane, GPT-telegramus
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
import signal
import sys

import psutil

import AIHandler
import Authenticator
import BotHandler
from JSONReaderWriter import load_json

TELEGRAMUS_VERSION = 'beta_2.0.0'

# Logging level (INFO for debug, WARN for release)
LOGGING_LEVEL = logging.INFO

# Files and directories
SETTINGS_FILE = 'settings.json'
MESSAGES_FILE = 'messages.json'
CHATS_FILE = 'chats.json'
LOGS_DIR = 'logs'


def logging_setup():
    """
    Sets up logging format and level
    :return:
    """
    # Create logs directory
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)

    # Create logs formatter
    log_formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Setup logging into file
    file_handler = logging.FileHandler(os.path.join(LOGS_DIR,
                                                    datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S') + '.log'),
                                       encoding='utf-8')
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
    logging.info('logging setup is complete')


def exit_(signum, frame):
    """
    Closes app
    :param signum:
    :param frame:
    :return:
    """
    logging.warning('Killing all threads...')
    current_system_pid = os.getpid()
    psutil.Process(current_system_pid).terminate()
    exit(0)


def parse_args():
    """
    Parses cli arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--settings', type=str, help='settings.json file location',
                        default=os.getenv('TELEGRAMUS_SETTINGS_FILE', SETTINGS_FILE))
    parser.add_argument('--messages', type=str, help='messages.json file location',
                        default=os.getenv('TELEGRAMUS_MESSAGES_FILE', MESSAGES_FILE))
    parser.add_argument('--chats', type=str, help='chats.json file location',
                        default=os.getenv('TELEGRAMUS_CHATS_FILE', CHATS_FILE))
    parser.add_argument('--version', action='version', version=TELEGRAMUS_VERSION)
    return parser.parse_args()


def main():
    """
    Main entry
    :return:
    """
    # Initialize logging
    logging_setup()

    # Connect interrupt signal
    signal.signal(signal.SIGINT, exit_)

    # Parse arguments and load settings and messages
    args = parse_args()
    settings = load_json(args.settings)
    messages = load_json(args.messages)

    # Initialize classes
    authenticator = Authenticator.Authenticator(settings)
    ai_handler = AIHandler.AIHandler(settings, args.chats, authenticator)
    bot_handler = BotHandler.BotHandler(settings, messages, args.chats, ai_handler)

    # Set requests_queue to ai_handler
    ai_handler.requests_queue = bot_handler.requests_queue

    # Initialize chatbot and start checker loop
    authenticator.start_chatbot()

    # Start AIHandler
    ai_handler.thread_start()

    # Start reply handler
    bot_handler.reply_thread_start()

    # Finally, start telegram bot
    bot_handler.bot_start()

    # Exit on error
    exit_(None, None)


if __name__ == '__main__':
    main()
