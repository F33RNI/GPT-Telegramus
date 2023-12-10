"""
 Copyright (C) 2022-2023 Fern Lane, GPT-Telegramus
 Copyright (C) 2023 Hanssen
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

from typing import List, Optional, Tuple, Union

from telegram import MessageEntity, Update
from telegram.ext import CommandHandler
from telegram.ext._utils.types import FilterDataDict


class CaptionCommandHandler(CommandHandler):
    def check_update(
            self, update: object
    ) -> Optional[Union[bool, Tuple[List[str], Optional[Union[bool, FilterDataDict]]]]]:
        """Determines whether an update should be passed to this handler's :attr:`callback`.

        Args:
            update (:class:`telegram.Update` | :obj:`object`): Incoming update.

        Returns:
            :obj:`list`: The list of args for the handler.

        """
        if isinstance(update, Update) and update.effective_message:
            message = update.effective_message
            text = message.text or message.caption
            entities = message.entities or message.caption_entities

            if (
                    entities
                    and entities[0].type == MessageEntity.BOT_COMMAND
                    and entities[0].offset == 0
                    and text
                    and message.get_bot()
            ):
                command = text[1: entities[0].length]
                args = text.split()[1:]
                command_parts = command.split("@")
                command_parts.append(message.get_bot().username)

                if not (
                        command_parts[0].lower() in self.commands
                        and command_parts[1].lower() == message.get_bot().username.lower()
                ):
                    return None

                filter_result = self.filters.check_update(update)
                if filter_result:
                    return args, filter_result
                return False
        return None
