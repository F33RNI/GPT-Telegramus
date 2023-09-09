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

REQUEST_TYPE_CHATGPT = 0
REQUEST_TYPE_DALLE = 1
REQUEST_TYPE_EDGEGPT = 2
REQUEST_TYPE_BARD = 3
REQUEST_TYPE_BING_IMAGEGEN = 4

PROCESSING_STATE_IN_QUEUE = 0
PROCESSING_STATE_INITIALIZING = 1
PROCESSING_STATE_ACTIVE = 2
PROCESSING_STATE_DONE = 3
PROCESSING_STATE_TIMED_OUT = 4
PROCESSING_STATE_CANCEL = 5
PROCESSING_STATE_CANCELING = 5

REQUEST_NAMES = ["ChatGPT", "DALL-E", "EdgeGPT", "Bard", "Bing ImageGen"]
PROCESSING_STATE_NAMES = ["Waiting", "Starting", "Active", "Done", "Timed out", "Canceling", "Canceling"]


class RequestResponseContainer:
    def __init__(self,
                 user: dict,
                 reply_message_id: int,
                 processing_state=PROCESSING_STATE_IN_QUEUE,
                 message_id=-1,
                 request="",
                 response="",
                 response_len_last=0,
                 request_type=REQUEST_TYPE_CHATGPT,
                 request_timestamp="",
                 response_timestamp="",
                 response_send_timestamp_last=0,
                 reply_markup=None,
                 pid=0) -> None:
        """
        Contains all info about request
        :param user: user data as dictionary from UsersHandler class
        :param reply_message_id: id of message reply to
        :param processing_state: PROCESSING_STATE_IN_QUEUE or PROCESSING_STATE_ACTIVE or PROCESSING_STATE_DONE
        :param message_id: current message id (for editing aka live replying)
        :param request: text request
        :param response: text response
        :param response_len_last: length of last response (for editing aka live replying)
        :param request_type: REQUEST_TYPE_CHATGPT / REQUEST_TYPE_DALLE / ...
        :param request_timestamp: timestamp of request (for data collecting)
        :param response_timestamp: timestamp of response (for data collecting)
        :param response_send_timestamp_last: timestamp of last response (for editing aka live replying)
        :param reply_markup: message buttons
        :param pid: current multiprocessing process PID for handling this container
        """
        self.user = user
        self.reply_message_id = reply_message_id

        self.processing_state = processing_state
        self.message_id = message_id
        self.request = request
        self.response = response
        self.response_len_last = response_len_last
        self.request_type = request_type
        self.request_timestamp = request_timestamp
        self.response_timestamp = response_timestamp
        self.response_send_timestamp_last = response_send_timestamp_last
        self.reply_markup = reply_markup
        self.pid = pid

        self.processing_start_timestamp = 0.
        self.error = False

        # Used by BotHandler to split large message into smaller ones
        self.response_parts = []

        # Unique ID for container to get it from queue (address)
        self.id = -1
