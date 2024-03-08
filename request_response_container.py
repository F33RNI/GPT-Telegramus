"""
Copyright (C) 2023-2024 Fern Lane

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

from typing import List

from telegram import InlineKeyboardMarkup


PROCESSING_STATE_IN_QUEUE = 0
PROCESSING_STATE_INITIALIZING = 1
PROCESSING_STATE_ACTIVE = 2
PROCESSING_STATE_DONE = 3
PROCESSING_STATE_TIMED_OUT = 4
PROCESSING_STATE_CANCEL = 5
PROCESSING_STATE_CANCELING = 6
PROCESSING_STATE_ABORT = 7

# State to string
PROCESSING_STATE_NAMES = ["Waiting", "Starting", "Active", "Done", "Timed out", "Canceling", "Canceling"]


class RequestResponseContainer:
    def __init__(
        self,
        user_id: str,
        reply_message_id: int,
        module_name: str,
        request_text: str or None = None,
        request_image: bytes or None = None,
        request_timestamp: str or None = None,
        response_text: str or None = None,
        response_images: List[str] or None = None,
        response_timestamp: str or None = None,
        response_send_timestamp_last: float = 0.0,
        processing_state: int = PROCESSING_STATE_IN_QUEUE,
        message_id: int = -1,
        reply_markup: InlineKeyboardMarkup or None = None,
        pid: int = 0,
    ) -> None:
        """TODO: Universal request-response wrapper

        Args:
            user (str): ID of user
            reply_message_id (int): ID of message reply to
            processing_state (str, optional): PROCESSING_STATE_.... Defaults to PROCESSING_STATE_IN_QUEUE
            message_id (int, optional): current message ID (for editing aka live replying). Defaults to -1
            request (str, optional): text request. Defaults to ""
            response (str, optional): text response. Defaults to ""
            response_images (type, optional): Images in the responses.
                Defaults to None.
            request_type (type, optional): REQUEST_TYPE_CHATGPT / REQUEST_TYPE_DALLE / ...
                Defaults to REQUEST_TYPE_CHATGPT.
            request_timestamp (str, optional): Timestamp of request (for data collecting).
            FORMATTED
                Defaults to "".
            response_timestamp (str, optional): Timestamp of response (for data collecting).
                Defaults to "".
            response_send_timestamp_last (int, optional): Timestamp of last response (for editing aka live replying).
                Defaults to 0.
            reply_markup (type, optional): Message buttons.
                Defaults to None.
            pid (int, optional): Current multiprocessing process PID for handling this container.
                Defaults to 0.
            image_url (type, optional): URL of the photo inside the message.
                Defaults to None.

         logging.info("Downloading user image")
                image = requests.get(request_response.image_url, timeout=120)

                logging.info("Asking Gemini...")
                response = self._vision_model.generate_content(
                    [
                        Part(
                            inline_data={
                                "mime_type": "image/jpeg",
                                "data": image.content,
                            }
                        ),
                        Part(text=request_response.request),
                    ],
                    stream=True,
                )
        """
        # Required args
        self.user_id = user_id
        self.reply_message_id = reply_message_id
        self.module_name = module_name

        # Request
        self.request_text = request_text
        self.request_image = request_image
        self.request_timestamp = request_timestamp

        # Response
        self.response_text = response_text
        self.response_images = []
        if response_images is not None:
            for response_image in response_images:
                self.response_images.append(response_image)
        self.response_timestamp = response_timestamp

        # Other args
        self.response_send_timestamp_last = response_send_timestamp_last
        self.processing_state = processing_state
        self.message_id = message_id
        self.reply_markup = reply_markup
        self.pid = pid

        self.processing_start_timestamp = 0.0
        self.error = False

        # Used by BotHandler to split large message into smaller ones
        self.response_next_chunk_start_index = 0
        self.response_sent_len = 0

        # Unique ID for container to get it from queue (it's address)
        self.id = -1
