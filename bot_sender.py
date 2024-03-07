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

import logging
import asyncio
import re
import time
from typing import Dict, List, Optional, Sequence, Tuple

import requests
import telegram
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
)
import md2tgmd

import messages
import request_response_container
import module_wrapper_global


def build_menu(buttons: List[InlineKeyboardButton], n_cols: int = 1, header_buttons=None, footer_buttons=None) -> List:
    """Returns a list of inline buttons used to generate inlinekeyboard responses

    Args:
        buttons (List[InlineKeyboardButton]): list of InlineKeyboardButton
        n_cols (int, optional): number of columns (number of list of buttons). Defaults to 1
        header_buttons (optional): first button value. Defaults to None
        footer_buttons (optional): last button value. Defaults to None

    Returns:
        List: list of inline buttons
    """
    buttons = [button for button in buttons if button is not None]
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


async def send_message_async(
    telegram_config: Dict,
    messages_: messages.Messages,
    request_response: request_response_container.RequestResponseContainer,
    end: bool = False,
    plain_text: bool = False,
) -> None:
    """Prepares and sends message

    Args:
        config (Dict): bot config ("telegram" section of config file)
        messages_ (messages.Messages): initialized messages handler
        request_response (request_response_container.RequestResponseContainer): container from the queue
        end (bool, optional): True if it's the final message. Defaults to False
        plain_text (bool, optional): True to ignore markup. Defaults to False
    """
    try:
        response_len = len(request_response.response_text) if request_response.response_text else 0

        # Fix empty message
        if end:
            if response_len == 0 and len(request_response.response_images) == 0:
                request_response.response_text = messages_.get_message(
                    "empty_message", user_id=request_response.user_id
                )

        await _send_prepared_message_async(telegram_config, messages_, request_response, end, plain_text)

    # Error?
    except Exception as e:
        logging.warning("Error sending message", exc_info=e)

    # Save current timestamp to container
    request_response.response_timestamp = time.time()


async def _send_prepared_message_async(
    telegram_config: Dict,
    messages_: messages.Messages,
    request_response: request_response_container.RequestResponseContainer,
    end: bool = False,
    plain_text: bool = False,
):
    """Sends new message or edits current one

    Args:
        telegram_config (Dict): bot config ("telegram" section of config file)
        messages_ (messages.Messages): initialized messages handler
        request_response (request_response_container.RequestResponseContainer): container from the queue
        end (bool, optional): True if it's the final message. Defaults to False
        plain_text (bool, optional): True to ignore markup. Defaults to False
    """
    if not should_send_message(telegram_config, request_response, end):
        return

    markup = build_markup(messages_, request_response, end, plain_text)
    if markup is not None:
        request_response.reply_markup = markup

    await _split_and_send_message_async(telegram_config, messages_, request_response, end)


def should_send_message(
    telegram_config: Dict,
    request_response: request_response_container.RequestResponseContainer,
    end: bool,
) -> bool:
    """Check if we should send this message

    Args:
        telegram_config (Dict): bot config ("telegram" section of config file)
        request_response (request_response_container.RequestResponseContainer): container from the queue
        end (bool): True if it's the final message

    Returns:
        bool: True if we should send this message
    """
    if end:
        return True

    response_len = len(request_response.response_text) if request_response.response_text else 0
    # Get current time
    time_current = time.time()

    # It's time to edit message, and we have any text to send, and we have new text
    if (
        time_current - request_response.response_send_timestamp_last
        >= telegram_config.get("edit_message_every_seconds_num")
        and response_len > 0
        and response_len != request_response.response_sent_len
    ):
        # Save new data
        request_response.response_send_timestamp_last = time_current

        return True

    return False


def build_markup(
    messages_: messages.Messages,
    request_response: request_response_container.RequestResponseContainer,
    end: bool = False,
    plain_text: bool = False,
) -> InlineKeyboardMarkup:
    """Builds markup for the response

    Args:
        messages_ (messages.Messages): initialized messages handler
        request_response (request_response_container.RequestResponseContainer): container from the queue
        end (bool, optional): True if it's the final message. Defaults to False
        plain_text (bool, optional): True to ignore markup. Defaults to False

    Returns:
        InlineKeyboardMarkup: markup for the response
    """
    if plain_text:
        return None

    user_id = request_response.user_id

    if not end:
        # Generate stop button if it's the first message
        if request_response.message_id is None or request_response.message_id < 0:
            button_stop = InlineKeyboardButton(
                messages_.get_message("button_stop_generating", user_id=user_id),
                callback_data=f"stop|{request_response.module_name}|{request_response.reply_message_id}",
            )
            return InlineKeyboardMarkup(build_menu([button_stop]))
        return None

    # Generate regenerate button
    button_regenerate = InlineKeyboardButton(
        messages_.get_message("button_regenerate", user_id=user_id),
        callback_data=f"regenerate|{request_response.module_name}|{request_response.reply_message_id}",
    )
    buttons = [button_regenerate]

    # Continue button (for ChatGPT only)
    if request_response.module_name == "chatgpt" or request_response.module_name == "lmao_chatgpt":
        # Check if there is no error
        if not request_response.error:
            button_continue = InlineKeyboardButton(
                messages_.get_message("button_continue", user_id=user_id),
                callback_data=f"continue|{request_response.module_name}|{request_response.reply_message_id}",
            )
            buttons.append(button_continue)

    # Add clear button for modules with conversation history
    if request_response.module_name in module_wrapper_global.MODULES_WITH_HISTORY:
        button_clear = InlineKeyboardButton(
            messages_.get_message("button_clear", user_id=user_id),
            callback_data=f"clear|{request_response.module_name}|{request_response.reply_message_id}",
        )
        buttons.append(button_clear)

    # Add change style button for MS Copilot
    if request_response.module_name == "ms_copilot":
        button_style = InlineKeyboardButton(
            messages_.get_message("button_style_change", user_id=user_id),
            callback_data=f"style||{request_response.reply_message_id}",
        )
        buttons.append(button_style)

    # Add change module button for all modules
    button_module = InlineKeyboardButton(
        messages_.get_message("button_module", user_id=user_id),
        callback_data=f"module||{request_response.reply_message_id}",
    )
    buttons.append(button_module)

    return InlineKeyboardMarkup(build_menu(buttons, n_cols=2))


async def test_img(img_source: str) -> str or None:
    """Test if an image source is valid

    Args:
        img_source (str): image URL to test

    Returns:
        str or None: img_source is valid or None if not
    """
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(
            None,
            lambda: requests.head(
                img_source,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.4472.114 Safari/537.36"
                },
                allow_redirects=True,
            ),
        )
        content_type = res.headers.get("content-type")
        if not content_type.startswith("image"):
            raise Exception("Not Image")
        if content_type == "image/svg+xml":
            raise Exception("SVG Image")
    except Exception as e:
        logging.warning(f"Invalid image from {img_source}: {e}. You can ignore this message")
        return None
    return img_source


async def _split_and_send_message_async(
    telegram_config: Dict,
    messages_: messages.Messages,
    request_response: request_response_container.RequestResponseContainer,
    end: bool = False,
):
    """Splits message into chunks if needed, then sends them

    Args:
        telegram_config (Dict): bot config ("telegram" section of config file)
        messages_ (messages.Messages): initialized messages handler
        request_response (request_response_container.RequestResponseContainer): container from the queue
        end (bool, optional): True if it's the final message. Defaults to False

    Raises:
        Exception: unknown message type or other error
    """
    msg_limit = telegram_config.get("one_message_limit")
    caption_limit = telegram_config.get("one_caption_limit")
    response = request_response.response_text or ""
    # Add cursor symbol?
    if (
        request_response.processing_state != request_response_container.PROCESSING_STATE_INITIALIZING
        and not end
        and telegram_config.get("add_cursor_symbol")
    ):
        response += telegram_config.get("cursor_symbol")

    # Verify images
    images = [
        img
        for img in (await asyncio.gather(*[test_img(img) for img in request_response.response_images]))
        if img is not None
    ]
    sent_len = request_response.response_sent_len
    sent_images_count = 0
    # Send all parts of message
    while (
        request_response.response_next_chunk_start_index < sent_len
        or sent_len < len(response)
        or (end and len(images) != 0)
    ):
        message_start_index = sent_len
        message_to_send = None
        edit_id = None
        # Get message ID to reply to
        # to the user's message if this is the first message
        reply_to_id = (
            request_response.message_id
            if (request_response.message_id or 0) >= 0
            else request_response.reply_message_id
        )

        if sent_len > len(response):
            # Reset message parts if new response is smaller than previous one (For loading message)
            # EdgeGPT also have this kind of loading message
            message_start_index = 0
            edit_id = request_response.message_id
        elif request_response.response_next_chunk_start_index < sent_len:
            # If the previous chunk is editable
            message_start_index = request_response.response_next_chunk_start_index
            edit_id = request_response.message_id

        should_contains_images = end and len(images) != 0 and edit_id is None

        # 0: plain text
        # 1: text with markup but no image
        # 2: text with markup and one image
        # 3: text with markup and multiple images
        message_type = None
        if should_contains_images:
            # Try to fit the message in caption
            message_to_send, consumed_len = _split_message(response, message_start_index, caption_limit)
            if message_start_index + consumed_len == len(response):
                if len(images) == 1:
                    message_type = 2
                else:
                    message_type = 3
                sent_len = message_start_index + consumed_len
        if message_type is None:
            # No images
            message_to_send, consumed_len = _split_message(response, message_start_index, msg_limit)
            if message_start_index + consumed_len < len(response) or should_contains_images:
                # Not the last chunk
                message_type = 0
            else:
                # Reached the last chunk
                message_type = 1
            sent_len = message_start_index + consumed_len

        request_response.response_next_chunk_start_index = sent_len
        # Don't count the cursor in
        request_response.response_sent_len = min(sent_len, len(request_response.response_text or ""))

        if message_type == 0:
            request_response.message_id = await send_reply(
                telegram_config.get("api_key"),
                request_response.user_id,
                message_to_send,
                reply_to_id,
                reply_markup=None,
                edit_message_id=edit_id,
            )
        elif message_type == 1:
            request_response.message_id = await send_reply(
                telegram_config.get("api_key"),
                request_response.user_id,
                message_to_send,
                reply_to_id,
                reply_markup=request_response.reply_markup,
                edit_message_id=edit_id,
            )
            if not end:
                # This message is editable, don't count the cursor in
                request_response.response_next_chunk_start_index = min(
                    message_start_index, len(request_response.response_text)
                )
                # This message has ended, break the loop
                break
        elif message_type == 2:
            message_id, err_msg = await send_photo(
                telegram_config.get("api_key"),
                request_response.user_id,
                images[0],
                caption=message_to_send,
                reply_to_message_id=reply_to_id,
                reply_markup=request_response.reply_markup,
            )
            images = []
            if message_id:
                request_response.message_id = message_id
            else:
                # send new message
                response += err_msg
        elif message_type == 3:
            media_group = [InputMediaPhoto(media=image_url) for image_url in images[0:9]]
            images = images[len(media_group) :]
            message_id, err_msg = await send_media_group(
                telegram_config.get("api_key"),
                chat_id=request_response.user_id,
                media=media_group,
                caption=message_to_send,
                reply_to_message_id=reply_to_id,
            )
            if message_id:
                request_response.message_id = message_id
                sent_images_count += len(media_group)
            else:
                response += err_msg

            if len(images) == 0:
                response += messages_.get_message("media_group_response", user_id=request_response.user_id).format(
                    request_text=request_response.request_text
                )
        else:
            raise Exception(f"Unknown message type {message_type}")


def _split_message(msg: str, after: int, max_length: int):
    """Split message, try to avoid break in a line / word
    Keep the code block in markdown

    Args:
        msg (str): _description_
        after (int): _description_
        max_length (int): _description_

    Returns:
        _type_: (message, consumed length)

    >>> _split_message("This is content", 0, 100)
    ('This is content', 15)
    >>> _split_message("This is content", 0, 10)
    ('This is', 8)
    >>> _split_message("This A\\nThis B", 0, 12)
    ('This A', 7)
    >>> _split_message("``` This is some code```", 0, 12)
    ('```\\n This```', 9)
    >>> _split_message("``` This is some code```", 9, 13)
    ('```\\nis```', 3)
    >>> _split_message("``` This is some code```", 9, 14)
    ('```\\nis some```', 8)
    >>> _split_message("```json\\nThis is some code```", 13, 18)
    ('```json\\nis some```', 8)
    >>> _split_message("```json\\nThis is some code```", 0, 18)
    ('```json\\nThis is```', 16)
    >>> _split_message("``` This A``` ``` This B```", 0, 14)
    ('```\\n This A```', 13)
    >>> _split_message("``` This A``` ``` This B```", 0, 25)
    ('```\\n This A``` ``````', 18)
    >>> _split_message("``` This A``` ``` This B```", 0, 26)
    ('```\\n This A``` ``` This```', 23)
    >>> _split_message("``` This A``` ``` This B```", 8, 24)
    ('```\\n A``` ``` This B```', 19)
    >>> _split_message("``` This A```", 0, 5)
    ('``` T', 5)
    >>> _split_message("``` This A", 0, 100)
    ('```\\n This A```', 10)
    >>> _split_message("This", 5, 100)
    ('', 0)
    """
    if after >= len(msg):
        return ("", 0)
    (_, _, begin_code_start_id, start_index) = _get_tg_code_block(msg, after)
    if begin_code_start_id == "":
        start_index = _regfind(msg, r"[^\s]", start_index)
    if start_index is None:
        start_index = 0
    end_index = min(start_index + max_length - len(begin_code_start_id), len(msg))

    end_code_end_id = ""
    result = ""
    while True:
        if end_index <= start_index:
            # Can't even fit the code block ids
            begin_code_start_id = ""
            end_code_end_id = ""
            start_index = _regfind(msg, r"[^\s]", after)
            end_index = min(start_index + max_length, len(msg))
            result = msg[start_index:end_index].strip()
            break

        for whitespace in ["\n", " "]:
            if end_index == len(msg) or msg[end_index] == whitespace:
                break
            if (i := msg.rfind(whitespace, start_index, end_index)) != -1:
                end_index = i + 1
                break
        (end_code_end_id, end_index, _, _) = _get_tg_code_block(msg, end_index)
        if begin_code_start_id == "":
            result = msg[start_index:end_index].strip()
        else:
            result = msg[start_index:end_index].rstrip()
        if len(begin_code_start_id) + len(result) + len(end_code_end_id) <= max_length:
            break
        # Too long after adding code ids
        end_index -= 1
    result = begin_code_start_id + result + end_code_end_id

    return (result, end_index - after)


def _get_tg_code_block(msg: str, at: int):
    """Get the code block id at a position of a message in Telegram
    Three backticks after a non-backtick are considered as the beginning of a code block
    And three backticks before a non-backtick are considered as the end of a code block
    There's no nested code blocks in Telegram

    Args:
        msg (str): _description_
        at (int): before index

    Returns:
        _type_: (prev readable code end id,
        prev readable end index,
        next readable code start id,
        next readable start index)

    >>> msg = "Hi ```Hi``` Hi\\n```json Hi```\\n```json\\nHi``` ```T````T``` ```A```\\n``` A```\\n```A"
    >>> #      0         1           2           3           4         5         6           7
    >>> #      012345678901234  56789012345678  90123456  789012345678901234567890123  456789012  3456
    >>> _get_tg_code_block(msg, 0)
    ('', 0, '', 0)
    >>> _get_tg_code_block(msg, 3)
    ('', 3, '```', 6)
    >>> _get_tg_code_block(msg, 6)
    ('```', 6, '```', 6)
    >>> _get_tg_code_block(msg, 7)
    ('```', 7, '```', 7)
    >>> _get_tg_code_block(msg, 8)
    ('```', 8, '', 11)
    >>> _get_tg_code_block(msg, 10)
    ('```', 8, '', 11)
    >>> _get_tg_code_block(msg, 12)
    ('', 12, '', 12)
    >>> _get_tg_code_block(msg, 15)
    ('', 15, '```json\\n', 22)
    >>> _get_tg_code_block(msg, 19)
    ('', 15, '```json\\n', 22)
    >>> _get_tg_code_block(msg, 29)
    ('', 29, '```json\\n', 37)
    >>> _get_tg_code_block(msg, 39)
    ('```', 39, '', 42)
    >>> _get_tg_code_block(msg, 43)
    ('', 43, '```', 46)
    >>> _get_tg_code_block(msg, 49)
    ('```', 49, '```', 49)
    >>> _get_tg_code_block(msg, 52)
    ('```', 52, '', 55)
    >>> _get_tg_code_block(msg, 56)
    ('', 56, '```', 59)
    >>> _get_tg_code_block(msg, 60)
    ('```', 60, '', 63)
    >>> _get_tg_code_block(msg, 65)
    ('', 64, '```\\n', 67)
    >>> _get_tg_code_block(msg, 999)
    ('```', 77, '```A\\n', 77)
    """
    if at >= len(msg):
        at = len(msg)
    # For easier matching the beginning of file and the end of file
    at += 1
    msg = " " + msg + " "

    skipped = 0
    code_id = ""
    while True:
        # +4 because a `|``a is possible
        start = _regfind(msg, r"[^`]```[^`]", skipped, at + 4)
        if start == -1:
            # No more code blocks
            break

        language = re.compile(r"[^`]*?[ \n]").match(msg, start + 4)
        code_begin = 0
        if language is None:
            # Single word block
            code_begin = start + 4
            code_id = "```"
        # Multiple words code block
        elif language.group(0).endswith("\n"):
            code_begin = language.end()
            code_id = msg[start + 1 : code_begin]
        else:
            # If the language section is ended by a space,
            # the space is content
            code_begin = language.end() - 1
            code_id = msg[start + 1 : code_begin] + "\n"

        # +4 because a|``` a is possible
        end = _regfind(msg, r"[^`]```[^`]", start + 4, at + 4)
        if end == -1:
            # Inside a code block
            if code_begin <= at:
                # In the code content
                return ("" if code_id == "" else "```", at - 1, code_id, at - 1)
            # In the code id
            return ("", start, code_id, code_begin - 1)

        skipped = end + 4

    # Outside a code block
    if skipped <= at:
        # In the plain content
        return ("", at - 1, "", at - 1)
    return ("" if code_id == "" else "```", skipped - 4, "", skipped - 1)


def _regfind(msg: str, reg: str, start: Optional[int] = None, end: Optional[int] = None):
    """Behave like str.find but support regex

    Args:
        msg (str): the message
        reg (str): regex
        start (Optional[int], optional): _description_. Defaults to None.
        end (Optional[int], optional): _description_. Defaults to None.

    Returns:
        _type_: first matched index, -1 if none

    >>> _regfind("a b", r"\\s")
    1
    >>> _regfind("ab", r"\\s")
    -1
    >>> _regfind("a bc ", r"\\s", 2)
    4
    >>> _regfind("abc d", r"\\s", 0, 2)
    -1
    """
    res = None
    if start is None:
        res = re.compile(reg).search(msg)
    elif end is None:
        res = re.compile(reg).search(msg, start)
    else:
        res = re.compile(reg).search(msg, start, end)

    if res:
        return res.start()
    return -1


async def send_reply(
    api_key: str,
    chat_id: int,
    message: str,
    reply_to_message_id: int or None = None,
    markdown: bool = True,
    reply_markup: InlineKeyboardMarkup or None = None,
    edit_message_id: int or None = None,
) -> int or None:
    """Sends reply to chat

    Args:
        api_key (str): telegram bot API key
        chat_id (int): chat id to send to
        message (str): message to send
        reply_to_message_id (int or None, optional): message ID to reply on. Defaults to None
        markdown (bool, optional): True to parse as markdown. Defaults to True
        reply_markup (InlineKeyboardMarkup or None, optional): buttons. Defaults to None
        edit_message_id (int or None, optional): message id to edit instead of sending a new one. Defaults to None

    Returns:
        int or None: message_id if sent correctly, or None if not
    """
    if (edit_message_id or -1) < 0:
        edit_message_id = None
    try:
        parse_mode, parsed_message = ("MarkdownV2", md2tgmd.escape(message)) if markdown else (None, message)

        if edit_message_id is None:
            if parsed_message == "":
                # Nothing to do
                return None

            # Send as new message
            return (
                await telegram.Bot(api_key).sendMessage(
                    chat_id=chat_id,
                    text=parsed_message,
                    reply_to_message_id=reply_to_message_id,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            ).message_id

        if parsed_message != "":
            # Edit current message
            return (
                await telegram.Bot(api_key).editMessageText(
                    chat_id=chat_id,
                    text=parsed_message,
                    message_id=edit_message_id,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
            ).message_id

        # Nothing inside this message, delete it
        await telegram.Bot(api_key).delete_message(
            chat_id=chat_id,
            message_id=edit_message_id,
        )
        return None
    except Exception as e:
        if markdown:
            logging.warning(f"Error sending reply with markdown {markdown}: {e}\t You can ignore this message")
            return await send_reply(
                api_key,
                chat_id,
                message,
                reply_to_message_id,
                False,
                reply_markup,
                edit_message_id,
            )
        logging.error(f"Error sending reply with markdown {markdown}", exc_info=e)
        return edit_message_id


async def send_photo(
    api_key: str,
    chat_id: int,
    photo: str,
    caption: str or None,
    reply_to_message_id: int or None,
    markdown: bool = True,
    reply_markup: InlineKeyboardMarkup or None = None,
) -> Tuple[int or None, str or None]:
    """Sends photo to chat

    Args:
        api_key (str): telegram bot API key
        chat_id (int): chat id to send to
        photo (str): URL of photo to send
        caption (str): message to send
        reply_to_message_id (int or None): message ID to reply on
        markdown (bool): True to parse as markdown
        reply_markup (InlineKeyboardMarkup or None, optional): buttons

    Returns:
        Tuple[int or None, str or None]: message_id if sent correctly, or None, error message or None
    """
    try:
        if caption:
            parse_mode, parsed_caption = ("MarkdownV2", md2tgmd.escape(caption)) if markdown else (None, caption)
        else:
            parse_mode = None
        return (
            (
                await telegram.Bot(api_key).send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=parsed_caption,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    reply_markup=reply_markup,
                    write_timeout=60,
                )
            ).message_id,
            None,
        )

    except Exception as e:
        logging.warning(f"Error sending photo with markdown {markdown}: {e}\t You can ignore this message")
        if not markdown:
            return (None, f"\n\n{photo}\n\n")
        return await send_photo(
            api_key,
            chat_id,
            photo,
            caption,
            reply_to_message_id,
            False,
            reply_markup,
        )


async def send_media_group(
    api_key: str,
    chat_id: int,
    media: Sequence[InputMediaAudio or InputMediaDocument or InputMediaPhoto or InputMediaVideo],
    caption: str,
    reply_to_message_id: int or None,
    markdown: bool = False,
) -> Tuple[int or None, str or None]:
    """Sends photo to chat

    Args:
        api_key (str): telegram bot API key
        chat_id (int): chat id to send to
        media (Sequence[InputMediaAudio or InputMediaDocument or InputMediaPhoto or InputMediaVideo]): media to send
        caption (str): message to send
        reply_to_message_id (int or None): message ID to reply on
        markdown (bool): True to parse as markdown

    Returns:
        Tuple[int or None, str or None]: message_id if sent correctly, or None, error message or None
    """

    try:
        parse_mode, parsed_caption = ("MarkdownV2", md2tgmd.escape(caption)) if markdown else (None, caption)

        return (
            (
                await telegram.Bot(api_key).sendMediaGroup(
                    chat_id=chat_id,
                    media=media,
                    caption=parsed_caption,
                    parse_mode=parse_mode,
                    reply_to_message_id=reply_to_message_id,
                    write_timeout=120,
                )
            )[0].message_id,
            "",
        )
    except Exception as e:
        logging.warning(f"Error sending media group with markdown {markdown}: {e}\t You can ignore this message")
        if not markdown:
            return (
                None,
                "\n\n" + "\n".join([f"{url.media}" for url in media]) + "\n\n",
            )
        return await send_media_group(api_key, chat_id, media, caption, reply_to_message_id, False)
