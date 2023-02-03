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

import asyncio
import logging
import queue
import threading

import telegram
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import RequestResponseContainer
from AIHandler import AIHandler
from main import TELEGRAMUS_VERSION

BOT_COMMAND_START = 'start'
BOT_COMMAND_HELP = 'help'
BOT_COMMAND_QUEUE = 'queue'
BOT_COMMAND_RESET = 'reset'
BOT_COMMAND_GPT = 'gpt'
BOT_COMMAND_DRAW = 'draw'

# List of markdown chars to escape with \\
MARKDOWN_ESCAPE = ['_', '*', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']


class BotHandler:
    def __init__(self, settings, messages, ai_handler: AIHandler):
        self.settings = settings
        self.messages = messages
        self.ai_handler = ai_handler

        # Response loop running flag
        self.response_loop_running = False

        # Requests queue
        self.requests_queue = None

        # Responses queue for AIHandler class
        self.responses_queue = self.ai_handler.responses_queue

        # Check settings and messages
        if self.settings is not None and self.messages is not None:
            # Initialize queue
            self.requests_queue = queue.Queue(maxsize=self.settings['queue_max'])

        # Settings or messages are None
        else:
            logging.error('Error starting BotHandler class due to wrong settings or messages')

    def bot_start(self):
        """
        Starts bot (blocking)
        :return:
        """
        try:
            # Build bot
            application = ApplicationBuilder().token(self.settings['telegram_api_key']) \
                .write_timeout(30).read_timeout(30).build()
            application.add_handler(CommandHandler(BOT_COMMAND_START, self.bot_command_start))
            application.add_handler(CommandHandler(BOT_COMMAND_HELP, self.bot_command_help))
            application.add_handler(CommandHandler(BOT_COMMAND_QUEUE, self.bot_command_queue))
            application.add_handler(CommandHandler(BOT_COMMAND_RESET, self.bot_command_reset))
            application.add_handler(CommandHandler(BOT_COMMAND_GPT, self.bot_command_gpt))
            application.add_handler(CommandHandler(BOT_COMMAND_DRAW, self.bot_command_draw))
            application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.bot_read_message))

            # Start bot
            application.run_polling()
        except Exception as e:
            logging.error(e)

    def reply_thread_start(self):
        """
        Starts background reply handler thread
        :return:
        """
        # Set flag
        self.response_loop_running = True

        # Start thread
        thread = threading.Thread(target=self.response_loop)
        thread.start()
        logging.info('Responses handler background thread: ' + thread.name)

    async def create_request(self, request: str, update: Update, context: ContextTypes.DEFAULT_TYPE, request_type: int):
        """
        Creates request to chatGPT
        :param request:
        :param update:
        :param context:
        :param request_type:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id

        # Check queue length
        if not self.requests_queue.full():
            # Add request to queue
            container = RequestResponseContainer.RequestResponseContainer(chat_id, user.full_name,
                                                                          update.message.message_id, request=request,
                                                                          request_type=request_type)
            self.requests_queue.put(container)

            # Send confirmation message
            await context.bot.send_message(chat_id=chat_id, text=str(self.messages['queue_accepted'])
                                           .format(user.full_name,
                                                   str(self.requests_queue.qsize()
                                                       + (1 if self.ai_handler.
                                                          processing_container is not None else 0)),
                                                   str(self.settings['queue_max'])).replace('\\n', '\n'))
        # Queue overflow
        else:
            await context.bot.send_message(chat_id=chat_id,
                                           text=str(self.messages['queue_overflow']).replace('\\n', '\n'))

    async def bot_command_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /reset command
        :param update:
        :param context:
        :return:
        """
        chat_id = update.effective_chat.id
        if self.ai_handler.chatbot is not None:
            self.ai_handler.chatbot.reset()
            await context.bot.send_message(chat_id=chat_id, text=str(self.messages['reset']).replace('\\n', '\n'))

    async def bot_read_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Read message from user
        :param update:
        :param context:
        :return:
        """
        chat_id = update.effective_chat.id
        message = update.message.text.strip()

        if len(message) > 0:
            await self.create_request(message, update, context, RequestResponseContainer.REQUEST_TYPE_CHATGPT)
        # No message
        else:
            await context.bot.send_message(chat_id=chat_id,
                                           text=str(self.messages['gpt_no_message']).replace('\\n', '\n'))

    async def bot_command_draw(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /draw command
        :param update:
        :param context:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id
        logging.info('/draw command from user ' + str(user.full_name) + ' request: ' + ' '.join(context.args))

        if len(context.args) > 0:
            # Combine all arguments to text
            request = str(' '.join(context.args)).strip()
            if len(request) > 0:
                await self.create_request(request, update, context, RequestResponseContainer.REQUEST_TYPE_DALLE)
            # No text
            else:
                await context.bot.send_message(chat_id=chat_id,
                                               text=str(self.messages['draw_no_text']).replace('\\n', '\n'))
        # No text
        else:
            await context.bot.send_message(chat_id=chat_id,
                                           text=str(self.messages['draw_no_text']).replace('\\n', '\n'))

    async def bot_command_gpt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /gpt command
        :param update:
        :param context:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id
        logging.info('/gpt command from user ' + str(user.full_name) + ' request: ' + ' '.join(context.args))

        if len(context.args) > 0:
            # Combine all arguments to text
            request = str(' '.join(context.args)).strip()
            if len(request) > 0:
                await self.create_request(request, update, context, RequestResponseContainer.REQUEST_TYPE_CHATGPT)
            # No text
            else:
                await context.bot.send_message(chat_id=chat_id,
                                               text=str(self.messages['gpt_no_text']).replace('\\n', '\n'))
        # No text
        else:
            await context.bot.send_message(chat_id=chat_id,
                                           text=str(self.messages['gpt_no_text']).replace('\\n', '\n'))

    async def bot_command_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /queue command
        :param update:
        :param context:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id
        processing_container = self.ai_handler.processing_container
        logging.info('/queue command from user ' + str(user.full_name))

        # Queue is empty
        if self.requests_queue.empty() and processing_container is None:
            await context.bot.send_message(chat_id=chat_id, text=str(self.messages['queue_empty']).replace('\\n', '\n'))
        else:
            i = 0
            message = ''

            # From queue
            if not self.requests_queue.empty():
                for i in range(self.requests_queue.qsize()):
                    container = self.requests_queue.queue[i]
                    text_request = container.request
                    text_from = container.user_name
                    message += str(i + 1) + '. ' + ('ChatGPT: ' if container.request_type == RequestResponseContainer
                                                    .REQUEST_TYPE_CHATGPT else 'DALLE: ') \
                               + text_from + ': ' + text_request + '\n\n'

            # Current request
            if processing_container is not None:
                if len(message) > 0:
                    i += 1
                message += str(i + 1) + '. ' + ('ChatGPT: ' if processing_container.request_type
                                                               == RequestResponseContainer
                                                .REQUEST_TYPE_CHATGPT else 'DALLE: ') \
                           + processing_container.user_name + ': ' + processing_container.request + '\n\n'

            # Send queue stats
            await context.bot.send_message(chat_id=chat_id, text=str(self.messages['queue_stats'])
                                           .format(message).replace('\\n', '\n'))

    async def bot_command_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /help command
        :param update:
        :param context:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id
        logging.info('/help command from user ' + str(user.full_name))

        # Send help message
        await context.bot.send_message(chat_id=chat_id, text=str(self.messages['help_message']).replace('\\n', '\n'))

    async def bot_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /start command
        :param update:
        :param context:
        :return:
        """
        user = update.message.from_user
        chat_id = update.effective_chat.id
        logging.info('/start command from user ' + str(user.full_name))

        # Send start message
        await context.bot.send_message(chat_id=chat_id, text=str(self.messages['start_message'])
                                       .format(TELEGRAMUS_VERSION).replace('\\n', '\n'))

        # Send help message
        await self.bot_command_help(update, context)

    async def send_reply(self, chat_id: int, message: str, reply_to_message_id: int, markdown=False):
        """
        Sends reply to chat
        :param chat_id: Chat id to send to
        :param message: Message to send
        :param reply_to_message_id: Message ID to reply on
        :param markdown: parse as markdown
        :return:
        """
        if markdown:
            # Try parse markdown
            try:
                # Escape all chars with \\
                for i in range(len(MARKDOWN_ESCAPE)):
                    escape_char = MARKDOWN_ESCAPE[i]
                    message = message.replace(escape_char, '\\' + escape_char)

                await telegram.Bot(self.settings['telegram_api_key']).sendMessage(chat_id=chat_id,
                                                                                  text=message,
                                                                                  reply_to_message_id=
                                                                                  reply_to_message_id,
                                                                                  parse_mode='MarkdownV2')

            # Error parsing markdown
            except Exception as e:
                logging.info(e)
                await telegram.Bot(self.settings['telegram_api_key']).sendMessage(chat_id=chat_id,
                                                                                  text=message.replace('\\n', '\n'),
                                                                                  reply_to_message_id=
                                                                                  reply_to_message_id)
        else:
            await telegram.Bot(self.settings['telegram_api_key']).sendMessage(chat_id=chat_id,
                                                                              text=message.replace('\\n', '\n'),
                                                                              reply_to_message_id=reply_to_message_id)

    def response_loop(self):
        """
        Background loop for handling responses
        :return:
        """
        while self.response_loop_running and self.responses_queue is not None:
            # Get response
            response = self.responses_queue.get(block=True)

            # Send reply
            if not response.error:
                # ChatGPT
                if response.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
                    asyncio.run(self.send_reply(response.chat_id, response.response, response.message_id, True))

                # DALLE
                else:
                    asyncio.run(telegram.Bot(self.settings['telegram_api_key']).sendPhoto(chat_id=response.chat_id,
                                                                                          photo=response.response))
            else:
                asyncio.run(self.send_reply(response.chat_id,
                                            str(self.messages['gpt_error']).format(response.response)
                                            .replace('\\n', '\n'),
                                            response.message_id, False))

        # Loop finished
        logging.warning('Response loop finished')
        self.response_loop_running = False
