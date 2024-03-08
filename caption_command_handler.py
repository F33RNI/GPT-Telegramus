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
                command = text[1 : entities[0].length]
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
