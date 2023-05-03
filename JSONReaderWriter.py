"""
 Copyright (C) 2022 Fern Lane, GPT-telegramus
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
    :return: json if loaded or empty json if not
    """
    try:
        if os.path.exists(file_name):
            logging.info("Loading " + file_name + "...")
            messages_file = open(file_name, encoding="utf-8")
            json_content = json.load(messages_file)
            messages_file.close()
            if json_content is not None and len(str(json_content)) > 0:
                logging.info("Loaded json: " + str(json_content))
            else:
                json_content = None
                logging.error("Error loading json data from file " + file_name)
        else:
            logging.warning("No " + file_name + " file! Returning empty json")
            return {}
    except Exception as e:
        json_content = None
        logging.error(e, exc_info=True)

    if json_content is None:
        json_content = {}

    return json_content


def save_json(file_name: str, content):
    """
    Saves
    :param file_name: filename to save
    :param content: JSON dictionary
    :return:
    """
    logging.info("Saving to " + file_name + "...")
    file = open(file_name, "w")
    json.dump(content, file, indent=4)
    file.close()
