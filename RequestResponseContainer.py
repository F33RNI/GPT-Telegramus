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

REQUEST_TYPE_CHATGPT = 0
REQUEST_TYPE_DALLE = 1
REQUEST_TYPE_EDGEGPT = 2
REQUEST_TYPE_BARD = 3
REQUEST_TYPE_BING_IMAGEGEN = 4
REQUEST_TYPE_GEMINI = 5

PROCESSING_STATE_IN_QUEUE = 0
PROCESSING_STATE_INITIALIZING = 1
PROCESSING_STATE_ACTIVE = 2
PROCESSING_STATE_DONE = 3
PROCESSING_STATE_TIMED_OUT = 4
PROCESSING_STATE_CANCEL = 5
PROCESSING_STATE_CANCELING = 6
PROCESSING_STATE_ABORT = 7

REQUEST_NAMES = ["ChatGPT", "DALL-E", "EdgeGPT", "Bard", "Bing ImageGen", "Gemini"]
PROCESSING_STATE_NAMES = ["Waiting", "Starting", "Active", "Done", "Timed out", "Canceling", "Canceling"]


class RequestResponseContainer:
    def __init__(self,
                 user: dict,
                 reply_message_id: int,
                 processing_state=PROCESSING_STATE_IN_QUEUE,
                 message_id=-1,
                 request="",
                 response="",
                 response_images=None,
                 request_type=REQUEST_TYPE_CHATGPT,
                 request_timestamp="",
                 response_timestamp="",
                 response_send_timestamp_last=0,
                 reply_markup=None,
                 pid=0,
                 image_url=None) -> None:
        """
        Contains all info about request
        :param user: user data as dictionary from UsersHandler class
        :param reply_message_id: id of message reply to
        :param processing_state: PROCESSING_STATE_IN_QUEUE or PROCESSING_STATE_ACTIVE or PROCESSING_STATE_DONE
        :param message_id: current message id (for editing aka live replying)
        :param request: text request
        :param response: text response
        :param response_images: images in the responses
        :param request_type: REQUEST_TYPE_CHATGPT / REQUEST_TYPE_DALLE / ...
        :param request_timestamp: timestamp of request (for data collecting)
        :param response_timestamp: timestamp of response (for data collecting)
        :param response_send_timestamp_last: timestamp of last response (for editing aka live replying)
        :param reply_markup: message buttons
        :param pid: current multiprocessing process PID for handling this container
        :param image_url: URL of the photo inside the message
        """
        self.user = user
        self.reply_message_id = reply_message_id

        self.processing_state = processing_state
        self.message_id = message_id
        self.request = request
        self.response = response
        self.request_type = request_type
        self.request_timestamp = request_timestamp
        self.response_timestamp = response_timestamp
        self.response_send_timestamp_last = response_send_timestamp_last
        self.reply_markup = reply_markup
        self.pid = pid
        self.image_url = image_url

        # Empty or response_images
        if response_images is None:
            self.response_images = []
        else:
            self.response_images = response_images

        self.processing_start_timestamp = 0.
        self.error = False

        # Used by BotHandler to split large message into smaller ones
        self.response_next_chunk_start_index = 0
        self.response_sent_len = 0

        # Unique ID for container to get it from queue (address)
        self.id = -1
