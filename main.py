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
import argparse

import psutil

import BotHandler
import AIHandler

TELEGRAMUS_VERSION = 'beta_1.1.1'

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


def parse_args():
    """
    Parses cli arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--open_ai_api_key', type=str, help='OpenAI API Key for DALL-E only',
                        default=os.getenv('TELEGRAMUS_OPEN_AI_API_KEY', None))

    parser.add_argument('--chatgpt_auth_email', type=str, help='OpenAI account login for ChatGPT',
                        default=os.getenv('TELEGRAMUS_CHATGPT_AUTH_EMAIL', None))
    parser.add_argument('--chatgpt_auth_password', type=str, help='OpenAI account password for ChatGPT',
                        default=os.getenv('TELEGRAMUS_CHATGPT_AUTH_PASSWORD', None))
    parser.add_argument('--chatgpt_auth_session_token', type=str, help='Comes from cookies on chat.openai.com as '
                                                                       '"__Secure-next-auth.session-token"',
                        default=os.getenv('TELEGRAMUS_CHATGPT_AUTH_EMAIL', None))
    parser.add_argument('--chatgpt_auth_access_token', type=str, help='https://chat.openai.com/api/auth/session',
                        default=os.getenv('TELEGRAMUS_CHATGPT_AUTH_PASSWORD', None))
    parser.add_argument('--chatgpt_auth_proxy', type=str,
                        help='Custom proxy for auth. See: https://github.com/acheong08/ChatGPT',
                        default=os.getenv('TELEGRAMUS_CHATGPT_AUTH_PROXY', None))

    parser.add_argument('--telegram_api_key', type=str, help='Telegram API Key',
                        default=os.getenv('TELEGRAMUS_TELEGRAM_API_KEY', None))
    parser.add_argument('--queue_max', type=int, help='Requests queue for chatgpt and dall-e (messages to bot queue)',
                        default=os.getenv('TELEGRAMUS_QUEUE_MAX', None))
    parser.add_argument('--image_size', type=str, help='DALL-E image size (256x256 or 512x512 or 1024x1024)',
                        default=os.getenv('TELEGRAMUS_IMAGE_SIZE', None))
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

    # Load settings and messages
    settings = load_json(SETTINGS_FILE)
    messages = load_json(MESSAGES_FILE)

    # Overwrite settings from JSON with CLI arguments
    args = parse_args()
    if args.open_ai_api_key is not None:
        settings['open_ai_api_key'] = args.open_ai_api_key
    if args.chatgpt_auth_email is not None:
        settings['chatgpt_auth_email'] = args.chatgpt_auth_email
    if args.chatgpt_auth_password is not None:
        settings['chatgpt_auth_password'] = args.chatgpt_auth_password
    if args.chatgpt_auth_session_token is not None:
        settings['chatgpt_auth_session_token'] = args.chatgpt_auth_session_token
    if args.chatgpt_auth_access_token is not None:
        settings['chatgpt_auth_access_token'] = args.chatgpt_auth_access_token
    if args.chatgpt_auth_proxy is not None:
        settings['chatgpt_auth_proxy'] = args.chatgpt_auth_proxy
    if args.telegram_api_key is not None:
        settings['telegram_api_key'] = args.telegram_api_key
    if args.queue_max is not None:
        settings['queue_max'] = args.queue_max
    if args.image_size is not None:
        settings['image_size'] = args.image_size

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
