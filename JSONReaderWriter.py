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

import json
import logging
import os.path


def load_json(file_name: str):
    """
    Loads json from file_name
    :return: json if loaded or None if not
    """
    try:
        if os.path.exists(file_name):
            logging.info("Loading {0}".format(file_name))

            messages_file = open(file_name, encoding="utf-8")
            json_content = json.load(messages_file)
            messages_file.close()

            if json_content is not None:
                logging.info("Loaded json from {0}".format(file_name))
            else:
                logging.error("Error loading json data from file {0}".format(file_name))
                return None
        else:
            logging.warning("No {0} file! Returning empty json".format(file_name))
            return None

    except Exception as e:
        logging.error("Error loading json data from file {0}".format(file_name), exc_info=e)
        return None

    return json_content


def save_json(file_name: str, content):
    """
    Saves
    :param file_name: filename to save
    :param content: JSON dictionary
    :return:
    """
    logging.info("Saving to {0}".format(file_name))
    file = open(file_name, "w")
    json.dump(content, file, indent=4)
    file.close()
