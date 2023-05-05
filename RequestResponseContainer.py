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

REQUEST_NAMES = ["ChatGPT", "DALL-E", "EdgeGPT", "Bard"]


class RequestResponseContainer:
    def __init__(self,
                 user: dict,
                 message_id: int,
                 request="",
                 response="",
                 request_type=REQUEST_TYPE_CHATGPT) -> None:
        self.user = user
        self.message_id = message_id
        self.request = request
        self.response = response
        self.request_type = request_type
        self.error = False
