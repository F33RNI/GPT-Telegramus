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

import json
import logging
import os
import signal

import psutil

import BotHandler
import AIHandler

TELEGRAMUS_VERSION = 'beta_0.4.4'

# Logging level (INFO for debug, WARN for release)
LOGGING_LEVEL = logging.INFO

# JSON Files
SETTINGS_FILE = 'settings.json'
MESSAGES_FILE = 'messages.json'


def logging_setup():
    """
    Sets up logging format and level
    :return:
    """
    logging.basicConfig(encoding='utf-8', format='%(asctime)s %(levelname)-8s %(message)s',
                        level=LOGGING_LEVEL,
                        datefmt='%Y-%m-%d %H:%M:%S')
    logging.info('logging setup is complete')


def load_json(file_name: str):
    """
    Loads settings from file_name
    :return: json if loaded or None if not
    """
    try:
        logging.info('Loading ' + file_name + '...')
        messages_file = open(file_name, encoding='utf-8')
        json_content = json.load(messages_file)
        messages_file.close()
        if json_content is not None and len(str(json_content)) > 0:
            logging.info('Loaded json: ' + str(json_content))
        else:
            json_content = None
            logging.error('Error loading json data from file ' + file_name)
    except Exception as e:
        json_content = None
        logging.error(e, exc_info=True)

    return json_content


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


def main():
    """
    Main entry
    :return:
    """
    # Initialize logging
    logging_setup()

    # Connect interrupt signal
    signal.signal(signal.SIGINT, exit_)

    # Load settings and messages
    settings = load_json(SETTINGS_FILE)
    messages = load_json(MESSAGES_FILE)

    # Initialize BotHandler and AIHandler classes
    ai_handler = AIHandler.AIHandler(settings)
    bot_handler = BotHandler.BotHandler(settings, messages, ai_handler)

    # Set requests_queue to ai_handler
    ai_handler.requests_queue = bot_handler.requests_queue

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
