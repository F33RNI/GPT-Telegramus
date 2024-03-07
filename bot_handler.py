"""
Copyright (C) 2023-2024 Fern Lane, Hanssen

This file is part of the GPT-Telegramus distribution
(see <https://github.com/F33RNI/GPT-Telegramus>)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import asyncio
import base64
from ctypes import c_bool
import datetime
import functools
import gc
import logging
import multiprocessing
import time
from math import sqrt
from typing import Dict, Tuple

import telegram
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
import requests

from _version import __version__
from main import load_and_parse_config
import bot_sender
import users_handler
import messages
import request_response_container
import queue_handler
import module_wrapper_global
from caption_command_handler import CaptionCommandHandler

# User commands
BOT_COMMAND_START = "start"
BOT_COMMAND_HELP = "help"
BOT_COMMAND_CHAT = "chat"
BOT_COMMAND_MODULE = "module"
BOT_COMMAND_STYLE = "style"
BOT_COMMAND_CLEAR = "clear"
BOT_COMMAND_LANG = "lang"
BOT_COMMAND_CHAT_ID = "chatid"

# Admin-only commands
BOT_COMMAND_ADMIN_QUEUE = "queue"
BOT_COMMAND_ADMIN_RESTART = "restart"
BOT_COMMAND_ADMIN_USERS = "users"
BOT_COMMAND_ADMIN_BAN = "ban"
BOT_COMMAND_ADMIN_UNBAN = "unban"
BOT_COMMAND_ADMIN_BROADCAST = "broadcast"

# After how many seconds restart bot polling if error occurs
RESTART_ON_ERROR_DELAY = 10


async def _send_safe(
    chat_id: int,
    text: str,
    context: ContextTypes.DEFAULT_TYPE,
    reply_to_message_id: int or None = None,
    reply_markup: InlineKeyboardMarkup or None = None,
):
    """Sends message without raising any error

    Args:
        chat_id (int): ID of user (or chat)
        text (str): text to send
        context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        reply_to_message_id (int or None, optional): ID of message to reply on. Defaults to None
        reply_markup (InlineKeyboardMarkup or None, optional): buttons. Defaults to None
    """
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logging.error(f"Error sending {text} to {chat_id}", exc_info=e)


class BotHandler:
    def __init__(
        self,
        config: Dict,
        config_file: str,
        messages_: messages.Messages,
        users_handler_: users_handler.UsersHandler,
        logging_queue: multiprocessing.Queue,
        queue_handler_: queue_handler.QueueHandler,
        modules: Dict,
    ):
        self.config = config
        self.config_file = config_file
        self.messages = messages_
        self.users_handler = users_handler_
        self.logging_queue = logging_queue
        self.queue_handler = queue_handler_
        self.modules = modules

        self.prevent_shutdown_flag = multiprocessing.Value(c_bool, False)

        self._application = None
        self._event_loop = None

    def start_bot(self):
        """
        Starts bot (blocking)
        :return:
        """
        while True:
            try:
                # Close previous event loop
                # Maybe we should optimize this and everything asyncio below (inside start_bot)
                try:
                    loop = asyncio.get_running_loop()
                    if loop and loop.is_running():
                        logging.info("Stopping current event loop before starting a new one")
                        loop.stop()
                except Exception as e:
                    logging.warning(f"Error stopping current event loop: {e}")

                # Create new event loop
                logging.info("Creating a new event loop")
                self._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._event_loop)

                # Build bot
                telegram_config = self.config.get("telegram")
                builder = ApplicationBuilder().token(telegram_config.get("api_key"))
                self._application = builder.build()

                # Set commands description
                if telegram_config.get("commands_description_enabled"):
                    try:
                        logging.info("Trying to set bot commands")
                        bot_commands = []
                        for command_description in telegram_config.get("commands_description"):
                            bot_commands.append(
                                BotCommand(
                                    command_description["command"],
                                    command_description["description"],
                                )
                            )
                        self._event_loop.run_until_complete(self._application.bot.set_my_commands(bot_commands))
                    except Exception as e:
                        logging.error("Error setting bot commands description", exc_info=e)

                # User commands
                logging.info("Adding user command handlers")
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_START, self.bot_command_start))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_HELP, self.bot_command_help))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_CHAT, self.bot_module_request))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_MODULE, self.bot_command_module))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_STYLE, self.bot_command_style))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_CLEAR, self.bot_command_clear))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_LANG, self.bot_command_lang))
                self._application.add_handler(CaptionCommandHandler(BOT_COMMAND_CHAT_ID, self.bot_command_chatid))

                # Direct module commands
                for module_name, _ in self.modules.items():
                    logging.info(f"Adding /{module_name} command handlers")
                    self._application.add_handler(
                        CaptionCommandHandler(
                            module_name, functools.partial(self.bot_module_request, module_name=module_name)
                        )
                    )

                # Handle requests as messages
                if telegram_config.get("reply_to_messages"):
                    logging.info("Adding message handlers")
                    self._application.add_handler(
                        MessageHandler(filters.TEXT & (~filters.COMMAND), self.bot_module_request)
                    )
                    self._application.add_handler(
                        MessageHandler(filters.PHOTO & (~filters.COMMAND), self.bot_module_request)
                    )

                # Admin commands
                logging.info("Adding admin command handlers")
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_QUEUE, self.bot_command_queue))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_RESTART, self.bot_command_restart))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_USERS, self.bot_command_users))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_BAN, self.bot_command_ban))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_UNBAN, self.bot_command_unban))
                self._application.add_handler(CommandHandler(BOT_COMMAND_ADMIN_BROADCAST, self.bot_command_broadcast))

                # Unknown command -> send help
                logging.info("Adding unknown command handler")
                self._application.add_handler(MessageHandler(filters.COMMAND, self.bot_command_unknown))

                # Add buttons handler
                logging.info("Adding markup handler")
                self._application.add_handler(CallbackQueryHandler(self.query_callback))

                # Start telegram bot polling
                logging.info("Starting bot polling")
                self._application.run_polling(close_loop=False, stop_signals=[])

            # Exit requested
            except (KeyboardInterrupt, SystemExit):
                logging.warning("KeyboardInterrupt or SystemExit @ bot_start")
                break

            # Bot error?
            except Exception as e:
                if "Event loop is closed" in str(e):
                    with self.prevent_shutdown_flag.get_lock():
                        prevent_shutdown = self.prevent_shutdown_flag.value
                    if not prevent_shutdown:
                        logging.warning("Stopping telegram bot")
                        break
                else:
                    logging.error("Telegram bot error", exc_info=e)

                # Restart bot
                logging.info(f"Restarting bot polling after {RESTART_ON_ERROR_DELAY} seconds")
                try:
                    time.sleep(RESTART_ON_ERROR_DELAY)

                # Exit requested while waiting for restart
                except (KeyboardInterrupt, SystemExit):
                    logging.warning("KeyboardInterrupt or SystemExit while waiting @ bot_start")
                    break

            # Restart bot or exit from loop
            with self.prevent_shutdown_flag.get_lock():
                prevent_shutdown = self.prevent_shutdown_flag.value
            if prevent_shutdown:
                logging.info("Restarting bot polling")
            else:
                break

        # If we're here, exit requested
        logging.warning("Telegram bot stopped")

    async def query_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Buttons (reply_markup) callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback

        Raises:
            Exception: _description_
        """
        try:
            telegram_chat_id = update.effective_chat.id
            data_ = update.callback_query.data
            if telegram_chat_id is None or data_ is None:
                return

            # Parse data from markup
            action, data_, reply_message_id = data_.split("|")
            if not action:
                raise Exception("No action in callback data")
            if not data_:
                data_ = None
            if not reply_message_id:
                reply_message_id = None
            else:
                reply_message_id = int(reply_message_id.strip())

            # Get user
            banned, user = await self._user_get_check(update, context, prompt_language_selection=False)
            if user is None:
                return
            user_id = user.get("user_id")
            user_name = self.users_handler.get_key(0, "user_name", "", user=user)
            lang_id = self.users_handler.get_key(0, "lang_id", "eng", user=user)

            # Log action
            logging.info(f"{action} markup action from {user_name} ({user_id})")

            # Exit if banned
            if banned:
                return

            # Regenerate request
            if action == "regenerate":
                # Get last message ID
                reply_message_id_last = self.users_handler.get_key(0, "reply_message_id_last", user=user)
                if reply_message_id_last is None or reply_message_id_last != reply_message_id:
                    await _send_safe(
                        user_id,
                        self.messages.get_message("regenerate_error_not_last", lang_id=lang_id),
                        context,
                    )
                    return

                # Get user's latest request
                request_text = self.users_handler.get_key(0, "request_last", user=user)
                request_image = self.users_handler.get_key(0, "request_last_image", user=user)
                if request_image:
                    request_image = base64.urlsafe_b64decode(request_image.encode())

                # Check for empty request
                if not request_text:
                    await _send_safe(
                        user_id,
                        self.messages.get_message("regenerate_error_empty", lang_id=lang_id),
                        context,
                    )
                    return

                # Ask
                await self._bot_module_request_raw(
                    data_,
                    request_text,
                    user_id,
                    reply_message_id_last,
                    context,
                    request_image,
                )

            # Continue generating
            elif action == "continue":
                # Get last message ID
                reply_message_id_last = self.users_handler.get_key(0, "reply_message_id_last", user=user)
                if reply_message_id_last is None or reply_message_id_last != reply_message_id:
                    await _send_safe(
                        user_id,
                        self.messages.get_message("continue_error_not_last", lang_id=lang_id),
                        context,
                    )
                    return

                # Ask
                await self._bot_module_request_raw(
                    data_,
                    self.config.get(data_).get("continue_request_text", "continue"),
                    user_id,
                    reply_message_id_last,
                    context,
                )

            # Stop generating
            elif action == "stop":
                # Get last message ID
                reply_message_id_last = self.users_handler.get_key(0, "reply_message_id_last", user=user)
                if reply_message_id_last is None or reply_message_id_last != reply_message_id:
                    await _send_safe(
                        user_id,
                        self.messages.get_message("stop_error_not_last", lang_id=lang_id),
                        context,
                    )
                    return

                # Get queue as list
                with self.queue_handler.lock:
                    queue_list = queue_handler.queue_to_list(self.queue_handler.request_response_queue)

                # Try to find our container
                aborted = False
                for container in queue_list:
                    if container.user_id == user_id and container.reply_message_id == reply_message_id_last:
                        # Request cancel
                        logging.info(f"Requested container {container.id} abort")
                        container.processing_state = request_response_container.PROCESSING_STATE_CANCEL
                        queue_handler.put_container_to_queue(
                            self.queue_handler.request_response_queue,
                            self.queue_handler.lock,
                            container,
                        )
                        aborted = True
                        break

                # Cannot abort
                if not aborted:
                    await _send_safe(user_id, self.messages.get_message("stop_error", lang_id=lang_id), context)

            # Clear chat
            elif action == "clear":
                await self._bot_command_clear_raw(data_, user, context)

            # Change module
            elif action == "module":
                await self._bot_command_module_raw(data_, user, context)

            # Change style
            elif action == "style":
                await self._bot_command_style_raw(data_, user, context)

            # Change language
            elif action == "lang":
                await self._bot_command_lang_raw(data_, user, context)

        # Error parsing data?
        except Exception as e:
            logging.error("Query callback error", exc_info=e)

        await context.bot.answer_callback_query(update.callback_query.id)

    async def bot_module_request(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, module_name: str or None = None
    ) -> None:
        """Direct module command request (/lmao_chatgpt, /gemini, ...) or message request

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
            module_name (str or None, optional): name of module (command) or None in case of message. Defaults to None
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)

        # Log command or message
        if module_name:
            logging.info(f"/{module_name} command from {user_name} ({user_id})")
        else:
            logging.info(f"Text message from {user['user_name']} ({user['user_id']})")

        # Exit if banned
        if banned:
            return

        # Check for image and download it
        image = None
        if update.message.photo:
            try:
                logging.info("Trying to download request image")
                image_file_id = update.message.photo[-1].file_id
                image_url = (
                    await telegram.Bot(self.config.get("telegram").get("api_key")).getFile(image_file_id)
                ).file_path
                image = requests.get(image_url, timeout=60).content
            except Exception as e:
                logging.error(f"Error downloading request image: {e}")

        # Extract text request
        if update.message.caption:
            request_message = update.message.caption.strip()
        elif context.args is not None:
            request_message = str(" ".join(context.args)).strip()
        elif update.message.text:
            request_message = update.message.text.strip()
        else:
            request_message = ""

        # Process request
        await self._bot_module_request_raw(
            module_name,
            request_message,
            user_id,
            update.message.message_id,
            context,
            image=image,
        )

    async def _bot_module_request_raw(
        self,
        module_name: str or None,
        request_message: str or None,
        user_id: int,
        reply_message_id: int,
        context: ContextTypes.DEFAULT_TYPE,
        image: bytes or None = None,
    ) -> None:
        """Processes request to module

        Args:
            module_name (str or None): name of module or None to get from user's data
            request_message (str or None): request text or None to just change user's default module
            user_id (int): ID of user
            reply_message_id (int): ID of message to reply on
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
            image (bytes or None, optional): request image as bytes or None to use only text. Defaults to None
        """
        # Set default user' module
        if module_name:
            self.users_handler.set_key(user_id, "module", module_name)

        # Use user's module
        else:
            module_name = self.users_handler.get_key(user_id, "module", self.config.get("modules").get("default"))

        lang_id = self.users_handler.get_key(user_id, "lang_id", "eng")
        user_name = self.users_handler.get_key(user_id, "user_name", "")

        # Check module name
        if not module_name or self.modules.get(module_name) is None:
            await _send_safe(
                user_id,
                self.messages.get_message("response_error", lang_id=lang_id).format(
                    error_text=f"No module named {module_name}. Please load this module or select another one"
                ),
                context,
                reply_to_message_id=reply_message_id,
            )
            return

        # Name of module
        module_icon_name = self.messages.get_message("modules", lang_id=lang_id).get(module_name)
        module_name_user = f"{module_icon_name.get('icon')} {module_icon_name.get('name')}"

        # Just change module
        if not request_message:
            await _send_safe(
                user_id,
                self.messages.get_message("empty_request_module_changed", lang_id=lang_id).format(
                    module_name=module_name_user
                ),
                context,
            )
            return

        # Check queue size, send message and exit in case of overflow
        if self.queue_handler.request_response_queue.qsize() >= self.config.get("telegram").get("queue_max"):
            await _send_safe(user_id, self.messages.get_message("queue_overflow", lang_id=lang_id), context)
            return

        # Format request timestamp (for data collecting)
        request_timestamp = ""
        if self.config.get("data_collecting").get("enabled"):
            request_timestamp = datetime.datetime.now().strftime(
                self.config.get("data_collecting").get("timestamp_format")
            )

        # Create container
        logging.info("Creating new request-response container")
        request_response = request_response_container.RequestResponseContainer(
            user_id=user_id,
            reply_message_id=reply_message_id,
            module_name=module_name,
            request_text=request_message,
            request_image=image,
            request_timestamp=request_timestamp,
        )

        # Add request to the queue
        logging.info(f"Adding new request to {module_name} from {user_name} ({user_id}) to the queue")
        queue_handler.put_container_to_queue(
            self.queue_handler.request_response_queue,
            self.queue_handler.lock,
            request_response,
        )

        # Send queue position if queue size is more than 1
        with self.queue_handler.lock:
            queue_list = queue_handler.queue_to_list(self.queue_handler.request_response_queue)
            if len(queue_list) > 1:
                await _send_safe(
                    user_id,
                    self.messages.get_message("queue_accepted", lang_id=lang_id).format(
                        module_name=module_name_user,
                        queue_size=len(queue_list),
                        queue_max=self.config.get("telegram").get("queue_max"),
                    ),
                    context,
                    reply_to_message_id=request_response.reply_message_id,
                )

    async def bot_command_restart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/restart command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/restart command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Check for admin rules and send permissions and deny if user is not an admin
        if not self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("permissions_deny", lang_id=lang_id), context)
            return

        # Get requested module
        requested_module = None
        if context.args and len(context.args) >= 1:
            try:
                requested_module = context.args[0].strip().lower()
                if self.modules.get(requested_module) is None:
                    raise Exception(f"No module named {requested_module}")
            except Exception as e:
                logging.error("Error retrieving requested module", exc_info=e)
                await _send_safe(user_id, str(e), context)
                return

        # Send restarting message
        logging.info("Restarting")
        await _send_safe(user_id, self.messages.get_message("restarting", lang_id=lang_id), context)

        # Make sure queue is empty
        if self.queue_handler.request_response_queue.qsize() > 0:
            logging.info("Waiting for all requests to finish")
            while self.queue_handler.request_response_queue.qsize() > 0:
                # Cancel all active containers (clear the queue)
                self.queue_handler.lock.acquire(block=True)
                queue_list = queue_handler.queue_to_list(self.queue_handler.request_response_queue)
                for container in queue_list:
                    if container.processing_state != request_response_container.PROCESSING_STATE_ABORT:
                        container.processing_state = request_response_container.PROCESSING_STATE_ABORT
                        queue_handler.put_container_to_queue(
                            self.queue_handler.request_response_queue, None, container
                        )
                self.queue_handler.lock.release()

                # Check every 1s
                time.sleep(1)

        error_messages = ""

        # Unload selected module or all of them
        for module_name, module in self.modules.items():
            if requested_module is not None and module_name != requested_module:
                continue
            logging.info(f"Trying to close and unload {module_name} module")
            try:
                module.on_exit()
                gc.collect()
            except Exception as e:
                logging.error(f"Error closing {module_name} module", exc_info=e)
                error_messages += f"Error closing {module_name} module: {e}\n"

        # Reload configs in global restart
        if requested_module is None:
            logging.info(f"Reloading config from {self.config_file} file")
            try:
                config_new = load_and_parse_config(self.config_file)
                for key, value in config_new.items():
                    self.config[key] = value
            except Exception as e:
                logging.error("Error reloading config", exc_info=e)
                error_messages += f"Error reloading config: {e}\n"

        # Reload messages in global restart
        if requested_module is None:
            try:
                self.messages.langs_load(self.config.get("files").get("messages_dir"))
            except Exception as e:
                logging.error("Error reloading messages", exc_info=e)
                error_messages += f"Error reloading messages: {e}\n"

        # Try to load selected module or all of them
        for module_name in self.config.get("modules").get("enabled"):
            if requested_module is not None and module_name != requested_module:
                continue
            logging.info(f"Trying to load and initialize {module_name} module")
            try:
                module = module_wrapper_global.ModuleWrapperGlobal(
                    module_name, self.config, self.messages, self.users_handler, self.logging_queue
                )
                self.modules[module_name] = module
            except Exception as e:
                logging.error(f"Error initializing {module_name} module: {e} Module will be ignored")
                error_messages += f"Error initializing {module_name} module: {e} Module will be ignored\n"

        # Done?
        logging.info("Restarting done")
        await _send_safe(
            user_id,
            self.messages.get_message("restarting_done", lang_id=lang_id).format(errors=error_messages),
            context,
        )

    async def bot_command_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/queue command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/queue command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Check for admin rules and send permissions and deny if user is not an admin
        if not self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("permissions_deny", lang_id=lang_id), context)
            return

        # Get queue as list
        with self.queue_handler.lock:
            queue_list = queue_handler.queue_to_list(self.queue_handler.request_response_queue)

        # Queue is empty
        if len(queue_list) == 0:
            await _send_safe(user["user_id"], self.messages.get_message("queue_empty", lang_id=lang_id), context)
            return

        # Format and send queue content
        message = ""
        counter = 1
        for container in queue_list:
            request_status = request_response_container.PROCESSING_STATE_NAMES[container.processing_state]
            message_ = (
                f"{counter} ({container.id}). {self.users_handler.get_key(container.user_id, 'user_name', '')} "
                f"({container.user_id}) to {container.module_name} ({request_status}): {container.request_text}\n"
            )
            message += message_
            counter += 1

        # Send queue content with auto-splitting
        request_response = request_response_container.RequestResponseContainer(
            user_id=user_id,
            reply_message_id=update.effective_message.id,
            module_name="",
            response_text=message,
        )
        await bot_sender.send_message_async(
            self.config.get("telegram"), self.messages, request_response, end=True, plain_text=True
        )

    async def bot_command_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/clear commands callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/clear command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Get requested module
        requested_module = None
        if context.args and len(context.args) >= 1:
            try:
                requested_module = context.args[0].strip().lower()
                if self.modules.get(requested_module) is None:
                    raise Exception(f"No module named {requested_module}")
            except Exception as e:
                logging.error("Error retrieving requested module", exc_info=e)
                await _send_safe(
                    user_id,
                    self.messages.get_message("clear_error", lang_id=lang_id).format(error_text=e),
                    context,
                )
                return

        # Clear
        await self._bot_command_clear_raw(requested_module, user, context)

    async def _bot_command_clear_raw(
        self, module_name: str or None, user: Dict, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Clears conversation or asks user to select module to clear conversation of

        Args:
            module_name (str): name of module to clear conversation
            user (Dict): ID of user
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Ask user
        if not module_name:
            module_icon_names = self.messages.get_message("modules", lang_id=lang_id)

            # Build markup
            buttons = []
            for enabled_module_id, _ in self.modules.items():
                if enabled_module_id not in module_wrapper_global.MODULES_WITH_HISTORY:
                    continue
                buttons.append(
                    InlineKeyboardButton(
                        module_icon_names.get(enabled_module_id).get("icon")
                        + " "
                        + module_icon_names.get(enabled_module_id).get("name"),
                        callback_data=f"clear|{enabled_module_id}|",
                    )
                )

            # Send message if at least one module is available
            if len(buttons) != 0:
                await _send_safe(
                    user_id,
                    self.messages.get_message("clear_select_module", lang_id=lang_id),
                    context,
                    reply_markup=InlineKeyboardMarkup(bot_sender.build_menu(buttons)),
                )
            return

        # Clear conversation
        try:
            logging.info(f"Trying to clear {module_name} conversation for user {user_id}")
            self.modules.get(module_name).delete_conversation(user_id)

            # Seems OK if no error was raised
            module_icon_name = self.messages.get_message("modules", lang_id=lang_id).get(module_name)
            module_name_user = f"{module_icon_name.get('icon')} {module_icon_name.get('name')}"
            await _send_safe(
                user_id,
                self.messages.get_message("chat_cleared", lang_id=lang_id).format(module_name=module_name_user),
                context,
            )

        # Error deleting conversation
        except Exception as e:
            logging.error("Error clearing conversation", exc_info=e)
            await _send_safe(user_id, self.messages.get_message("clear_error").format(error_text=e), context)

    async def bot_command_style(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/style commands callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/style command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        style = None

        # User specified style
        if context.args and len(context.args) >= 1:
            try:
                style = context.args[0].strip().lower()
                available_styles = ["precise", "balanced", "creative"]
                if style not in available_styles:
                    raise Exception(f"No style {style} in {' '.join(available_styles)}")
            except Exception as e:
                logging.error("Error retrieving requested style", exc_info=e)
                await _send_safe(
                    user["user_id"],
                    self.messages.get_message("style_change_error", lang_id=lang_id).format(error_text=str(e)),
                    context,
                )
                return

        # Change style or ask the user
        await self._bot_command_style_raw(style, user, context)

    async def _bot_command_style_raw(self, style: str or None, user: Dict, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Changes conversation style of EdgeGPT

        Args:
            style (str or None): "precise", "balanced", "creative" or None to ask user
            user (Dict): user's data as dictionary
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Ask user
        if not style:
            buttons = [
                InlineKeyboardButton(
                    self.messages.get_message("style_precise", lang_id=lang_id), callback_data="style|precise|"
                ),
                InlineKeyboardButton(
                    self.messages.get_message("style_balanced", lang_id=lang_id), callback_data="style|balanced|"
                ),
                InlineKeyboardButton(
                    self.messages.get_message("style_creative", lang_id=lang_id), callback_data="style|creative|"
                ),
            ]

            # Extract current style
            if self.config.get("ms_copilot") is not None:
                style_default = self.config.get("ms_copilot").get("conversation_style_type_default")
            else:
                style_default = "balanced"
            current_style = self.users_handler.get_key(0, "ms_copilot_style", style_default, user=user)
            current_style_text = self.messages.get_message(f"style_{current_style}", lang_id=lang_id)

            await _send_safe(
                user_id,
                self.messages.get_message("style_select").format(current_style=current_style_text),
                context,
                reply_markup=InlineKeyboardMarkup(bot_sender.build_menu(buttons)),
            )
            return

        # Change style
        try:
            # Change style of user
            self.users_handler.set_key(user_id, "ms_copilot_style", style)

            # Send confirmation
            changed_style_text = self.messages.get_message(f"style_{style}", lang_id=lang_id)
            await _send_safe(
                user_id,
                self.messages.get_message("style_changed", lang_id=lang_id).format(changed_style=changed_style_text),
                context,
            )

        # Error changing style
        except Exception as e:
            logging.error("Error changing conversation style", exc_info=e)
            await _send_safe(
                user_id,
                self.messages.get_message("style_change_error", lang_id=lang_id).format(error_text=str(e)),
                context,
            )

    ########################################
    # General (non-modules) commands below #
    ########################################

    async def bot_command_unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """unknown command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Ignore group chats
        if update.effective_message.chat.type.lower() != "private":
            return

        # Send help in private chats
        await self.bot_command_help(update, context)

    async def bot_command_ban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/ban command callback (wrapper for _bot_command_ban_unban)"""
        await self._bot_command_ban_unban(True, update, context)

    async def bot_command_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/unban command callback (wrapper for _bot_command_ban_unban)"""
        await self._bot_command_ban_unban(False, update, context)

    async def _bot_command_ban_unban(self, ban: bool, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/ban and /unban commands callback

        Args:
            ban (bool): True to ban, False to unban
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/{'ban' if ban else 'unban'} command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Check for admin rules and send permissions and deny if user is not an admin
        if not self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("permissions_deny", lang_id=lang_id), context)
            return

        # Check user_id to ban
        if not context.args or len(context.args) < 1:
            await _send_safe(user_id, self.messages.get_message("ban_no_user_id", lang_id=lang_id), context)
            return

        # Get user to ban (and create a new one if not exists)
        # TODO: Add error message to each language
        try:
            ban_user_id = int(str(context.args[0]).strip())
            ban_user = self.users_handler.get_user(ban_user_id)
            ban_user_lang_id = self.users_handler.get_key(0, "lang_id", user=ban_user)
            if ban_user is None:
                ban_user = self.users_handler.create_user(ban_user_id)
                if ban_user is None:
                    raise Exception(f"Error creating a new user with ID {ban_user_id}")
        except Exception as e:
            await _send_safe(user_id, str(e), context)
            return

        ban_reason_default = self.messages.get_message("ban_reason_default", lang_id=ban_user_lang_id)

        # Ban user
        if ban:
            # Get ban reason
            if len(context.args) > 1:
                ban_reason = str(" ".join(context.args[1:])).strip()
            else:
                ban_reason = self.users_handler.get_key(0, "ban_reason", ban_reason_default, user=ban_user)

            self.users_handler.set_key(ban_user_id, "banned", True)
            self.users_handler.set_key(ban_user_id, "ban_reason", ban_reason)

        # Unban user and reset ban reason
        else:
            self.users_handler.set_key(ban_user_id, "banned", False)
            self.users_handler.set_key(ban_user_id, "ban_reason", ban_reason_default)

        # Send confirmation
        if ban:
            await _send_safe(
                user_id,
                self.messages.get_message("ban_message_admin", lang_id=lang_id).format(
                    banned_user=f"{self.users_handler.get_key(0, 'user_name', '', user=ban_user) (ban_user_id)}",
                    ban_reason=ban_reason,
                ),
                context,
            )
        else:
            await _send_safe(
                user_id,
                self.messages.get_message("unban_message_admin", lang_id=lang_id).format(
                    unbanned_user=f"{self.users_handler.get_key(0, 'user_name', '', user=ban_user) (ban_user_id)}",
                ),
                context,
            )

    async def bot_command_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/broadcast command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/broadcast command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Check for admin rules and send permissions and deny if user is not an admin
        if not self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("permissions_deny", lang_id=lang_id), context)
            return

        # Get message to broadcast
        effective_message = update.effective_message
        if effective_message is not None:
            broadcast_message = effective_message.text.strip()
            broadcast_message_splitted = broadcast_message.split("/" + BOT_COMMAND_ADMIN_BROADCAST)
            if len(broadcast_message_splitted) > 1:
                broadcast_message = ("/" + BOT_COMMAND_ADMIN_BROADCAST).join(broadcast_message_splitted[1:]).strip()
        else:
            broadcast_message = None

        # Check for message
        if not broadcast_message:
            await _send_safe(user_id, self.messages.get_message("broadcast_no_message", lang_id=lang_id), context)
            return

        # Read users database
        database = self.users_handler.read_database()

        # Check
        if database is None:
            await _send_safe(user_id, self.messages.get_message("users_read_error", lang_id=lang_id), context)
            return

        # Send initial message
        await _send_safe(user_id, self.messages.get_message("broadcast_initiated", lang_id=lang_id), context)

        # List of successful users (list of strings: "user_name (user_id)")
        broadcast_ok_users = []

        # Broadcast to users skipping banned ones
        for broadcast_user in database:
            if self.users_handler.get_key(0, "banned", False, user=broadcast_user):
                continue

            broadcast_user_id = broadcast_user.get("user_id")

            try:
                # Get other broadcast user's data
                broadcast_user_name = self.users_handler.get_key(0, "user_name", "", user=broadcast_user)
                broadcast_user_lang_id = self.users_handler.get_key(0, "lang_id", "eng", user=broadcast_user)

                # Try to send message and get message ID
                message = self.messages.get_message("broadcast", lang_id=broadcast_user_lang_id).format(
                    message=broadcast_message
                )
                message_id = (
                    await telegram.Bot(self.config.get("telegram").get("api_key")).sendMessage(
                        chat_id=broadcast_user_id, text=message
                    )
                ).message_id

                # Check
                if message_id is not None and message_id != 0:
                    logging.info(f"Message sent to: {broadcast_user_name} ({broadcast_user_id})")
                    broadcast_ok_users.append(f"{broadcast_user_name} ({broadcast_user_id})")

                # Wait some time
                time.sleep(self.config.get("telegram").get("broadcast_delay_per_user_seconds"))
            except Exception as e:
                logging.warning(f"Error sending message to {broadcast_user_id}", exc_info=e)

        # Send final message with list of users
        await _send_safe(
            user_id,
            self.messages.get_message("broadcast_done", lang_id=lang_id).format(
                broadcast_ok_users="\n".join(broadcast_ok_users)
            ),
            context,
        )

    async def bot_command_module(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/module command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)

        # Log command
        logging.info(f"/module command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Request module selection
        await self._bot_command_module_raw(None, user, context)

    async def _bot_command_module_raw(
        self, module_name: str or None, user: Dict, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Suggest module selection to the user or changes user's module

        Args:
            module_name (str or None): name of the module to change to or None to show selection message
            user (Dict): user's data as dictionary
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Change module (send an empty request)
        if module_name:
            await self._bot_module_request_raw(module_name, "", user_id, -1, context)
            return

        module_icon_names = self.messages.get_message("modules", lang_id=lang_id)

        # Build markup
        buttons = []
        for enabled_module_id, _ in self.modules.items():
            buttons.append(
                InlineKeyboardButton(
                    module_icon_names.get(enabled_module_id).get("icon")
                    + " "
                    + module_icon_names.get(enabled_module_id).get("name"),
                    callback_data=f"module|{enabled_module_id}|",
                )
            )

        # Extract current user's module
        current_module_id = self.users_handler.get_key(
            0, "module", self.config.get("modules").get("default"), user=user
        )
        current_module_name = module_icon_names.get(current_module_id).get("name")
        current_module_icon = module_icon_names.get(current_module_id).get("icon")
        current_module_name = f"{current_module_icon} {current_module_name}"

        # Send message
        message = self.messages.get_message("module_select_module", lang_id=lang_id).format(
            current_module=current_module_name
        )
        await _send_safe(
            user_id,
            message,
            context,
            reply_markup=InlineKeyboardMarkup(bot_sender.build_menu(buttons)),
        )
        return

    async def bot_command_lang(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/lang command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)

        # Log command
        logging.info(f"/lang command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Request language selection
        await self._bot_command_lang_raw(None, user, context)

    async def _bot_command_lang_raw(
        self, lang_id: str or None, user: Dict, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Selects user language

        Args:
            lang_id (str or None): selected language or None to show message containing all languages
            user (Dict): user's data as dictionary
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")

        # Send message with all languages
        if not lang_id:
            # Build message and markup
            buttons = []
            message = ""
            for lang_id_, lang_messages in self.messages.langs.items():
                buttons.append(
                    InlineKeyboardButton(lang_messages.get("language_name"), callback_data=f"lang|{lang_id_}|")
                )
                message += lang_messages.get("language_select") + "\n"

            # Send language selection message
            await _send_safe(
                user_id,
                message,
                context,
                reply_markup=InlineKeyboardMarkup(
                    bot_sender.build_menu(buttons, n_cols=min(int(sqrt(len(self.messages.langs.items()))), 3))
                ),
            )
            return

        # Change language
        try:
            # Change language of the user
            self.users_handler.set_key(user_id, "lang_id", lang_id)

            # Send confirmation
            await _send_safe(user_id, self.messages.get_message("language_changed", lang_id=lang_id), context)

            # Send start message if it is a new user
            if not self.users_handler.get_key(0, "started", False, user=user):
                await self._bot_command_start_raw(user, context)

        # Error changing lang
        except Exception as e:
            logging.error("Error selecting language", exc_info=e)
            await _send_safe(
                user_id,
                self.messages.get_message("language_select_error", lang_id=lang_id).format(error_text=str(e)),
                context,
            )

    async def bot_command_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/users command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/users command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Check for admin rules and send permissions and deny if user is not an admin
        if not self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("permissions_deny", lang_id=lang_id), context)
            return

        # Read users database
        database = self.users_handler.read_database()

        # Check
        if database is None:
            await _send_safe(user_id, self.messages.get_message("users_read_error", lang_id=lang_id), context)
            return

        # Sort by number of requests (larger values on top)
        database = sorted(
            database, key=lambda user: self.users_handler.get_key(0, "requests_total", 0, user=user), reverse=True
        )

        # Add them to message
        message = ""
        module_default = self.config.get("modules").get("default")
        for user_ in database:
            # Banned?
            if self.users_handler.get_key(0, "banned", False, user=user_):
                message += self.config.get("telegram").get("banned_symbol", "B") + " "
            else:
                message += self.config.get("telegram").get("non_banned_symbol", " ") + " "

            # Admin?
            if self.users_handler.get_key(0, "admin", False, user=user_):
                message += self.config.get("telegram").get("admin_symbol", "A") + " "
            else:
                message += self.config.get("telegram").get("non_admin_symbol", " ") + " "

            # Language icon
            lang_id_ = self.users_handler.get_key(0, "lang_id", None, user=user_)
            message += self.messages.get_message("language_icon", lang_id=lang_id_) + " "

            # Module icon
            module_id_ = self.users_handler.get_key(0, "module", module_default, user=user_)
            module_ = self.messages.get_message("modules", lang_id=lang_id).get(module_id_, None)
            if module_ is not None:
                message += module_.get("icon", "?") + " "
            else:
                message += self.messages.get_message("modules", lang_id=lang_id).get(module_default).get("icon", "?")
                message += " "

            # User ID
            user_id_ = user_.get("user_id")
            message += f"{user_id_} "

            # Name of user (with link to profile if available)
            is_private_ = (
                self.users_handler.get_key(0, "user_type", "private" if user_id_ > 0 else "", user=user_) == "private"
            )
            user_name_ = self.users_handler.get_key(0, "user_name", str(user_id_), user=user_)
            user_username_ = self.users_handler.get_key(0, "user_username", user=user_)
            if is_private_:
                message += f"[{user_name_}](tg://user?id={user_id_}) "
            elif user_username_:
                message += f"[{user_name_}](https://t.me/{user_username_}) "
            else:
                message += f"{user_name_} "

            # Total number of requests
            message += f"- {self.users_handler.get_key(0, 'requests_total', 0, user=user_)}"

            # New line
            message += "\n"

        # Format final message
        message = self.messages.get_message("users_admin", lang_id=lang_id).format(users_data=message)

        # Send as markdown
        await bot_sender.send_reply(self.config.get("telegram").get("api_key"), user_id, message, markdown=True)

    async def bot_command_chatid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/chatid command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        _, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)

        # Log command
        logging.info(f"/chatid command from {user_name} ({user_id})")

        # Send chat id and not exit if banned
        await _send_safe(user_id, str(user_id), context)

    async def bot_command_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/help command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)

        # Log command
        logging.info(f"/help command from {user_name} ({user_id})")

        # Exit if banned
        if banned:
            return

        # Send help message
        await self._bot_command_help_raw(user, context)

    async def _bot_command_help_raw(self, user: Dict, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends help message to the user

        Args:
            user (Dict): user's data as dictionary
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Send default help message
        await _send_safe(user_id, self.messages.get_message("help_message", lang_id=lang_id), context)

        # Send admin help message
        if self.users_handler.get_key(0, "admin", False, user=user):
            await _send_safe(user_id, self.messages.get_message("help_message_admin", lang_id=lang_id), context)

    async def bot_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """/start command callback

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        # Get user
        banned, user = await self._user_get_check(update, context)
        if user is None:
            return
        user_id = user.get("user_id")
        user_name = self.users_handler.get_key(0, "user_name", "", user=user)
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Log command
        logging.info(f"/start command from {user_name} ({user_id})")

        # Exit if banned or user not selected the language
        if banned or lang_id is None:
            return

        # Send start message
        await self._bot_command_start_raw(user, context)

    async def _bot_command_start_raw(self, user: Dict, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends start message to the user

        Args:
            user (Dict): user's data as dictionary
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
        """
        user_id = user.get("user_id")
        lang_id = self.users_handler.get_key(0, "lang_id", user=user)

        # Send start message
        await _send_safe(
            user_id,
            self.messages.get_message("start_message", lang_id=lang_id).format(version=__version__),
            context,
        )

        # Send help message
        await self._bot_command_help_raw(user, context)

        # Assume that user received this message
        self.users_handler.set_key(user_id, "started", True)

    async def _user_get_check(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        send_banned_message: bool = True,
        prompt_language_selection: bool = True,
    ) -> Tuple[bool, Dict or None]:
        """Gets user's ID based on update.effective_chat.id and checks if they're banned or not
        Will create a new one if user doesn't exist

        Args:
            update (Update): update object from bot's callback
            context (ContextTypes.DEFAULT_TYPE): context object from bot's callback
            send_banned_message (bool, optional): True to send message to user if they're banned. Defaults to True
            prompt_language_selection (bool, optional): True to send language selection prompt if language is not set

        Returns:
            Tuple[bool, Dict or None]: (banned?, user as dictionary)
        """
        try:
            # Get user
            user_id = update.effective_chat.id
            user = self.users_handler.get_user(user_id)

            # Create a new one
            if user is None:
                user = self.users_handler.create_user(user_id)

            # Check
            if user is None:
                raise Exception("Unable to get or create user")

            # Update user name
            if update.effective_chat.effective_name is not None:
                self.users_handler.set_key(user_id, "user_name", str(update.effective_chat.effective_name))

            # Update user username
            if (
                update.message is not None
                and update.message.chat is not None
                and update.message.chat.username is not None
            ):
                self.users_handler.set_key(user_id, "user_username", str(update.message.chat.username))

            # Update user type
            self.users_handler.set_key(user_id, "user_type", update.effective_chat.type)

            # Get banned flag
            banned_by_default = (
                False
                if user_id in self.config.get("telegram").get("admin_ids")
                else self.config.get("telegram").get("ban_by_default")
            )
            banned = self.users_handler.get_key(0, "banned", banned_by_default, user=user)

            # Get user's language or None if not yet set
            lang_id = self.users_handler.get_key(0, "lang_id", user=user)

            # Send banned message
            if banned and send_banned_message:
                ban_reason_default = self.messages.get_message("ban_reason_default", lang_id=lang_id)
                ban_reason = self.users_handler.get_key(0, "ban_reason", ban_reason_default, user=user)
                ban_message = self.messages.get_message("ban_message_user", lang_id=lang_id).format(
                    ban_reason=ban_reason
                )
                await _send_safe(user_id, ban_message, context)

            # Select language
            if not banned and lang_id is None and prompt_language_selection:
                await self._bot_command_lang_raw(None, user, context)

            return banned, user

        # I don't think it's possible but just in case
        except Exception as e:
            logging.error("Error retrieving user's data", exc_info=e)
            return False, None
