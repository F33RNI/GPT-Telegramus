"""
 Copyright (C) 2022 Fern Lane, GPT-Telegramus
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
import time

import telegram
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

import BardModule
import ChatGPTModule
import DALLEModule
import EdgeGPTModule
import ProxyAutomation
import QueueHandler
import RequestResponseContainer
import UsersHandler
from main import __version__

# User commands
BOT_COMMAND_START = "start"
BOT_COMMAND_HELP = "help"
BOT_COMMAND_CHATGPT = "chatgpt"
BOT_COMMAND_EDGEGPT = "edgegpt"
BOT_COMMAND_DALLE = "dalle"
BOT_COMMAND_BARD = "bard"
BOT_COMMAND_CLEAR = "clear"
BOT_COMMAND_CHAT_ID = "chatid"

# Admin-only commands
BOT_COMMAND_ADMIN_QUEUE = "queue"
BOT_COMMAND_ADMIN_RESTART = "restart"
BOT_COMMAND_ADMIN_USERS = "users"
BOT_COMMAND_ADMIN_BAN = "ban"
BOT_COMMAND_ADMIN_UNBAN = "unban"
BOT_COMMAND_ADMIN_BROADCAST = "broadcast"

# List of markdown chars to escape with \\
MARKDOWN_ESCAPE = ["_", "*", "[", "]", "(", ")", "~", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
MARKDOWN_ESCAPE_MINIMUM = ["_", "[", "]", "(", ")", "~", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
MARKDOWN_MODE_ESCAPE_NONE = 0
MARKDOWN_MODE_ESCAPE_MINIMUM = 1
MARKDOWN_MODE_ESCAPE_ALL = 2
MARKDOWN_MODE_NO_MARKDOWN = 3

# After how many seconds restart bot polling if error occurs
RESTART_ON_ERROR_DELAY = 30


async def _send_safe(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends message without raising any error
    :param chat_id:
    :param context:
    :return:
    """
    try:
        await context.bot.send_message(chat_id=chat_id,
                                       text=text.replace("\\n", "\n").replace("\\t", "\t"))
    except Exception as e:
        logging.error("Error sending {0} to {1}!".format(text.replace("\\n", "\n").replace("\\t", "\t"), chat_id),
                      exc_info=e)


class BotHandler:
    def __init__(self, config: dict, messages: dict,
                 users_handler: UsersHandler.UsersHandler,
                 queue_handler: QueueHandler.QueueHandler,
                 proxy_automation: ProxyAutomation.ProxyAutomation,
                 chatgpt_module: ChatGPTModule.ChatGPTModule,
                 edgegpt_module: EdgeGPTModule.EdgeGPTModule,
                 dalle_module: DALLEModule.DALLEModule,
                 bard_module: BardModule.BardModule):
        self.config = config
        self.messages = messages
        self.users_handler = users_handler
        self.queue_handler = queue_handler
        self.proxy_automation = proxy_automation

        self.chatgpt_module = chatgpt_module
        self.edgegpt_module = edgegpt_module
        self.dalle_module = dalle_module
        self.bard_module = bard_module

        self._application = None
        self._event_loop = None
        self._restart_requested_flag = False
        self._exit_flag = False
        self._response_loop_thread = None

    def start_bot(self):
        """
        Starts bot (blocking)
        :return:
        """
        # Start response_loop as thread
        self._response_loop_thread = threading.Thread(target=self._response_loop)
        self._response_loop_thread.start()
        logging.info("response_loop thread: {0}".format(self._response_loop_thread.name))

        # Start telegram bot polling
        logging.info("Starting telegram bot")
        while True:
            try:
                # Build bot
                builder = ApplicationBuilder().token(self.config["telegram"]["api_key"])
                builder.write_timeout(self.config["telegram"]["write_read_timeout"])
                builder.read_timeout(self.config["telegram"]["write_read_timeout"])
                self._application = builder.build()

                # User commands
                self._application.add_handler(CommandHandler(BOT_COMMAND_START, self.bot_command_start))
                self._application.add_handler(CommandHandler(BOT_COMMAND_HELP, self.bot_command_help))
                self._application.add_handler(CommandHandler(BOT_COMMAND_CHATGPT, self.bot_command_chatgpt))
                self._application.add_handler(CommandHandler(BOT_COMMAND_EDGEGPT, self.bot_command_edgegpt))
                self._application.add_handler(CommandHandler(BOT_COMMAND_DALLE, self.bot_command_dalle))
                self._application.add_handler(CommandHandler(BOT_COMMAND_BARD, self.bot_command_bard))
                self._application.add_handler(CommandHandler(BOT_COMMAND_CLEAR, self.bot_command_clear))
                self._application.add_handler(CommandHandler(BOT_COMMAND_CHAT_ID, self.bot_command_chatid))
                self._application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.bot_message))

                # Admin commands
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_QUEUE, self.bot_command_queue))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_RESTART, self.bot_command_restart))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_USERS, self.bot_command_users))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_BAN, self.bot_command_ban))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_UNBAN, self.bot_command_unban))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_BROADCAST, self.bot_command_broadcast))

                # Unknown command -> send help
                self._application.add_handler(MessageHandler(filters.COMMAND, self.bot_command_help))

                # Start bot
                self._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._event_loop)
                self._event_loop.run_until_complete(self._application.run_polling())

            # Exit requested
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt @ bot_start")
                break

            # Bot error?
            except Exception as e:
                if "Event loop is closed" in str(e):
                    if not self._restart_requested_flag:
                        logging.warning("Stopping telegram bot")
                        break
                else:
                    logging.error("Telegram bot error!", exc_info=e)

            # Wait before restarting if needed
            if not self._restart_requested_flag:
                logging.info("Restarting bot polling after {0} seconds".format(RESTART_ON_ERROR_DELAY))
                try:
                    time.sleep(RESTART_ON_ERROR_DELAY)
                # Exit requested while waiting for restart
                except KeyboardInterrupt:
                    logging.warning("KeyboardInterrupt @ bot_start")
                    break

            # Restart bot
            logging.info("Restarting bot polling")
            self._restart_requested_flag = False

        # If we're here, exit requested
        self._stop_response_loop()
        logging.warning("Telegram bot stopped")

    async def bot_command_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /broadcast command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/broadcast command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check for admin rules
        if not user["admin"]:
            await _send_safe(user["user_id"], self.messages["permissions_deny"], context)
            return

        # Check for message
        if not context.args or len(context.args) < 1:
            await _send_safe(user["user_id"], self.messages["broadcast_no_message"], context)
            return

        # Get message
        broadcast_message = str(" ".join(context.args)).strip()

        # Get list of users
        users = self.users_handler.read_users()

        # Broadcast to non-banned users
        for broadcast_user in users:
            if not broadcast_user["banned"]:
                try:
                    logging.info("broadcasting to: {0} ({1})".format(broadcast_user["user_name"],
                                                                     broadcast_user["user_id"]))
                    await telegram.Bot(self.config["telegram"]["api_key"]) \
                        .sendMessage(chat_id=broadcast_user["user_id"],
                                     text=self.messages["broadcast"].replace("\\n", "\n").format(broadcast_message))
                except Exception as e:
                    logging.error("Error sending message!", exc_info=e)

    async def bot_command_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.bot_command_ban_unban(True, update, context)

    async def bot_command_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.bot_command_ban_unban(False, update, context)

    async def bot_command_ban_unban(self, ban: bool, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /ban, /unban commands
        :param ban: True to ban, False to unban
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/{0} command from {1} ({2})".format("ban" if ban else "unban",
                                                          user["user_name"],
                                                          user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check for admin rules
        if not user["admin"]:
            await _send_safe(user["user_id"], self.messages["permissions_deny"], context)
            return

        # Check user_id to ban
        if not context.args or len(context.args) < 1:
            await _send_safe(user["user_id"], self.messages["ban_no_user_id"], context)
            return
        try:
            ban_user_id = int(str(context.args[0]).strip())
        except Exception as e:
            await _send_safe(user["user_id"], str(e), context)
            return

        # Get ban reason
        reason = self.messages["ban_reason_default"].replace("\\n", "\n")
        if len(context.args) > 1:
            reason = str(" ".join(context.args[1:])).strip()

        # Get user to ban
        banned_user = self.users_handler.get_user_by_id(ban_user_id)

        # Ban / unban
        banned_user["banned"] = ban
        banned_user["ban_reason"] = reason

        # Save user
        self.users_handler.save_user(banned_user)

        # Send confirmation
        if ban:
            await _send_safe(user["user_id"],
                             self.messages["ban_message_admin"].format("{0} ({1})"
                                                                       .format(banned_user["user_name"],
                                                                               banned_user["user_id"]), reason),
                             context)
        else:
            await _send_safe(user["user_id"],
                             self.messages["unban_message_admin"].format("{0} ({1})"
                                                                         .format(banned_user["user_name"],
                                                                                 banned_user["user_id"])),
                             context)

    async def bot_command_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /users command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/users command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check for admin rules
        if not user["admin"]:
            await _send_safe(user["user_id"], self.messages["permissions_deny"], context)
            return

        # Get list of users
        users = self.users_handler.read_users()

        # Add them to message
        message = ""
        for user_info in users:
            message += "{0} ({1})\t{2}\t{3}\t{4}\n".format(user_info["user_id"],
                                                           user_info["user_name"],
                                                           user_info["admin"],
                                                           user_info["banned"],
                                                           user_info["requests_total"])

        # Send list of users
        await _send_safe(user["user_id"], self.messages["users_admin"].format(message), context)

    async def bot_command_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /restart command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/restart command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check for admin rules
        if not user["admin"]:
            await _send_safe(user["user_id"], self.messages["permissions_deny"], context)
            return

        # Send restarting message
        logging.info("Restarting")
        await _send_safe(user["user_id"], self.messages["restarting"], context)

        # Stop proxy automation
        logging.info("Stopping ProxyAutomation")
        self.proxy_automation.stop_automation_loop()

        # Restart ChatGPT module
        self.chatgpt_module.restart()

        # Restart EdgeGPT module
        self.edgegpt_module.restart()

        # Restart DALL-E module
        self.dalle_module.restart()

        # Restart Bard module
        self.bard_module.restart()

        # Start proxy automation
        logging.info("Starting back ProxyAutomation")
        self.proxy_automation.start_automation_loop()

        # Restart telegram bot
        self._restart_requested_flag = True
        self._event_loop.stop()
        try:
            self._event_loop.close()
        except:
            pass

        def send_message_after_restart():
            # Sleep while restarting
            while self._restart_requested_flag:
                time.sleep(1)

            # Done?
            logging.info("Restarting done")
            try:
                asyncio.run(telegram.Bot(self.config["telegram"]["api_key"])
                            .sendMessage(chat_id=user["user_id"],
                                         text=self.messages["restarting_done"].replace("\\n", "\n")))
            except Exception as e:
                logging.error("Error sending message!", exc_info=e)

        threading.Thread(target=send_message_after_restart).start()

    async def bot_command_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /queue command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/queue command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check for admin rules
        if not user["admin"]:
            await _send_safe(user["user_id"], self.messages["permissions_deny"], context)
            return

        # Get queue as list
        queue_list = self.queue_handler.get_queue_list()

        # Queue is empty
        if len(queue_list) == 0:
            await _send_safe(user["user_id"], self.messages["queue_empty"], context)
        else:
            message = ""
            for i in range(len(queue_list)):
                container = queue_list[i]
                text_request = container.request
                text_from = container.user["user_name"] + " (" + str(container.user["user_id"]) + ")"
                message += str(i + 1) + ". " + text_from + ", "
                message += RequestResponseContainer.REQUEST_NAMES[container.request_type]
                message += ": " + text_request + "\n"

            # Send queue stats
            await _send_safe(user["user_id"], message, context)

    async def bot_command_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /chatid command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/chatid command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Send chat id and not exit if banned
        await _send_safe(user["user_id"], str(user["user_id"]), context)

    async def bot_command_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /clear command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/clear command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Check requested module
        if not context.args or len(context.args) < 1:
            await _send_safe(user["user_id"], self.messages["clear_no_module"], context)
            return

        # Get requested module
        requested_module = context.args[0].strip().lower()

        # Check again
        if requested_module != "chatgpt" and requested_module != "edgegpt" and requested_module != "bard":
            await _send_safe(user["user_id"], self.messages["clear_no_module"], context)
            return

        # Clear ChatGPT
        if requested_module == "chatgpt":
            self.chatgpt_module.clear_conversation_for_user(user)

        # Clear EdgeGPT
        elif requested_module == "edgegpt":
            self.edgegpt_module.clear_conversation()

        # Clear Bard
        elif requested_module == "bard":
            self.bard_module.clear_conversation_for_user(user)

        # Wrong module
        else:
            await _send_safe(user["user_id"], self.messages["clear_no_module"], context)
            return

        # Send confirmation
        await _send_safe(user["user_id"], self.messages["chat_cleared"].format(requested_module), context)

    async def bot_command_chatgpt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_command_or_message_request(RequestResponseContainer.REQUEST_TYPE_CHATGPT, update, context)

    async def bot_command_edgegpt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_command_or_message_request(RequestResponseContainer.REQUEST_TYPE_EDGEGPT, update, context)

    async def bot_command_dalle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_command_or_message_request(RequestResponseContainer.REQUEST_TYPE_DALLE, update, context)

    async def bot_command_bard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_command_or_message_request(RequestResponseContainer.REQUEST_TYPE_BARD, update, context)

    async def bot_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.bot_command_or_message_request(-1, update, context)

    async def bot_command_or_message_request(self, request_type: int,
                                             update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /chatgpt, /edgegpt, /dalle or message request
        :param request_type: -1 for message, or RequestResponseContainer.REQUEST_TYPE_...
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command or message
        if request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT:
            logging.info("/chatgpt command from {0} ({1})".format(user["user_name"], user["user_id"]))
        elif request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT:
            logging.info("/edgegpt command from {0} ({1})".format(user["user_name"], user["user_id"]))
        elif request_type == RequestResponseContainer.REQUEST_TYPE_DALLE:
            logging.info("/dalle command from {0} ({1})".format(user["user_name"], user["user_id"]))
        elif request_type == RequestResponseContainer.REQUEST_TYPE_BARD:
            logging.info("/bard command from {0} ({1})".format(user["user_name"], user["user_id"]))
        else:
            logging.info("Text message from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Extract request
        if request_type >= 0:
            if context.args:
                request_message = str(" ".join(context.args)).strip()
            else:
                request_message = ""
        else:
            request_message = update.message.text.strip()

        # Set default user module
        if request_type >= 0:
            user["module"] = request_type
            self.users_handler.save_user(user)

        else:
            # Automatically adjust message module
            if self.config["modules"]["auto_module"]:
                request_type = user["module"]

            # Always use default module
            else:
                request_type = self.config["modules"]["default_module"]

        # Check request
        if not request_message or len(request_message) <= 0:
            await _send_safe(user["user_id"], self.messages["empty_request"], context)
            return

        # Check queue
        if self.queue_handler.requests_queue.full():
            await _send_safe(user["user_id"], self.messages["queue_overflow"], context)
            return

        # Create request
        request_response = RequestResponseContainer.RequestResponseContainer(user, update.message.message_id,
                                                                             request=request_message,
                                                                             request_type=request_type)

        # Add request to the queue
        logging.info("Adding new {0} request from {1} ({2}) to the queue".format(request_type,
                                                                                 user["user_name"],
                                                                                 user["user_id"]))
        self.queue_handler.requests_queue.put(request_response, block=True)

        # Send confirmation
        if self.config["telegram"]["show_queue_message"]:
            await _send_safe(user["user_id"],
                             self.messages["queue_accepted"].format(
                                 RequestResponseContainer.REQUEST_NAMES[request_type],
                                 len(self.queue_handler.get_queue_list()),
                                 self.config["telegram"]["queue_max"]), context)

    async def bot_command_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /help command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/help command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Send default help message
        await _send_safe(user["user_id"], self.messages["help_message"], context)

        # Send admin help message
        if user["admin"]:
            await _send_safe(user["user_id"], self.messages["help_message_admin"], context)

    async def bot_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        /start command
        :param update:
        :param context:
        :return:
        """
        # Get user
        user = await self._user_check_get(update, context)

        # Log command
        logging.info("/start command from {0} ({1})".format(user["user_name"], user["user_id"]))

        # Exit if banned
        if user["banned"]:
            return

        # Send start message
        await _send_safe(user["user_id"], self.messages["start_message"].format(__version__), context)

        # Send help message
        await self.bot_command_help(update, context)

    async def _user_check_get(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict:
        """
        Gets (or creates) user based on update.effective_chat.id and update.message.from_user.full_name
        and checks if they are banned or not
        :param update:
        :param context:
        :return: user as dictionary
        """
        # Get user (or create a new one)
        telegram_user_name = update.message.from_user.full_name if update.message is not None else None
        telegram_chat_id = update.effective_chat.id
        user = self.users_handler.get_user_by_id(telegram_chat_id)

        # Update user name
        if telegram_user_name is not None:
            user["user_name"] = str(telegram_user_name)
            self.users_handler.save_user(user)

        # Send banned info
        if user["banned"]:
            await _send_safe(telegram_chat_id, self.messages["ban_message_user"].format(user["ban_reason"]), context)

        return user

    async def _send_parse(self, chat_id: int, message: str, reply_to_message_id: int, escape_mode: int) -> bool:
        """
        Parses message and sends it as reply
        :param chat_id:
        :param message:
        :param reply_to_message_id:
        :param escape_mode:
        :return: True if sent correctly
        """
        try:
            # Escape some chars
            if escape_mode == MARKDOWN_MODE_ESCAPE_MINIMUM:
                for i in range(len(MARKDOWN_ESCAPE_MINIMUM)):
                    escape_char = MARKDOWN_ESCAPE_MINIMUM[i]
                    message = message.replace(escape_char, "\\" + escape_char)

            # Escape all chars
            elif escape_mode == MARKDOWN_MODE_ESCAPE_ALL:
                for i in range(len(MARKDOWN_ESCAPE)):
                    escape_char = MARKDOWN_ESCAPE[i]
                    message = message.replace(escape_char, "\\" + escape_char)

            # Send as markdown
            if escape_mode == MARKDOWN_MODE_ESCAPE_NONE \
                    or escape_mode == MARKDOWN_MODE_ESCAPE_MINIMUM \
                    or escape_mode == MARKDOWN_MODE_ESCAPE_ALL:
                await telegram.Bot(self.config["telegram"]["api_key"]).sendMessage(chat_id=chat_id,
                                                                                   text=message.replace("\\n", "\n"),
                                                                                   reply_to_message_id=
                                                                                   reply_to_message_id,
                                                                                   parse_mode="MarkdownV2")
            # Send as plain text
            else:
                await telegram.Bot(self.config["telegram"]["api_key"]).sendMessage(chat_id=chat_id,
                                                                                   text=message.replace("\\n", "\n"),
                                                                                   reply_to_message_id=
                                                                                   reply_to_message_id)

            # Seems OK
            return True

        except:
            logging.warning("Error sending reply with eascape_mode {0}".format(escape_mode))
            return False

    async def _send_reply(self, chat_id: int, message: str, reply_to_message_id: int, markdown=False) -> None:
        """
        Sends reply to chat
        :param chat_id: Chat id to send to
        :param message: Message to send
        :param reply_to_message_id: Message ID to reply on
        :param markdown: parse as markdown
        :return:
        """
        # Send as markdown
        if markdown:
            # Try everything
            if not await self._send_parse(chat_id, message, reply_to_message_id, MARKDOWN_MODE_ESCAPE_NONE):
                if not await self._send_parse(chat_id, message, reply_to_message_id, MARKDOWN_MODE_ESCAPE_MINIMUM):
                    if not await self._send_parse(chat_id, message, reply_to_message_id, MARKDOWN_MODE_ESCAPE_ALL):
                        if not await self._send_parse(chat_id, message, reply_to_message_id, MARKDOWN_MODE_NO_MARKDOWN):
                            logging.error("Unable to send message in any markdown escape mode!")

        # Markdown parsing is disabled - send as plain message
        else:
            await self._send_parse(chat_id, message, reply_to_message_id, MARKDOWN_MODE_NO_MARKDOWN)

    def _stop_response_loop(self) -> None:
        """
        Stops response_loop thread
        :return:
        """
        if self._response_loop_thread and self._response_loop_thread.is_alive():
            logging.warning("Stopping response_loop")
            self._exit_flag = True
            self._response_loop_thread.join()

    def _response_loop(self) -> None:
        """
        Background loop for handling responses
        :return:
        """
        logging.info("Starting response_loop")
        self._exit_flag = False
        while not self._exit_flag:
            try:
                # Wait until response and get it or exit
                request_response = None
                while True:
                    try:
                        request_response = self.queue_handler.responses_queue.get(block=True, timeout=1)
                        break
                    except queue.Empty:
                        if self._exit_flag:
                            break
                    except KeyboardInterrupt:
                        self._exit_flag = True
                        break
                if self._exit_flag or request_response is None:
                    break

                # Send reply
                if not request_response.error:
                    # Text response (ChatGPT, EdgeGPT, Bard)
                    if request_response.request_type == RequestResponseContainer.REQUEST_TYPE_CHATGPT \
                            or request_response.request_type == RequestResponseContainer.REQUEST_TYPE_EDGEGPT \
                            or request_response.request_type == RequestResponseContainer.REQUEST_TYPE_BARD:
                        asyncio.run(self._send_reply(request_response.user["user_id"],
                                                     request_response.response,
                                                     request_response.message_id,
                                                     markdown=True))

                    # Image response (DALL-E)
                    else:
                        asyncio.run(telegram.Bot(self.config["telegram"]["api_key"])
                                    .sendPhoto(chat_id=request_response.user["user_id"],
                                               photo=request_response.response,
                                               reply_to_message_id=request_response.message_id))

                # Response error
                else:
                    asyncio.run(self._send_reply(request_response.user["user_id"],
                                                 str(request_response.response),
                                                 request_response.message_id, False))
            # Exit requested
            except KeyboardInterrupt:
                logging.warning("KeyboardInterrupt @ response_loop")
                break

            # Oh no, error! Why?
            except Exception as e:
                logging.error("Error in response_loop!", exc_info=e)
                time.sleep(1)

        logging.warning("response_loop finished")
