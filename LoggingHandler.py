"""
 Copyright (C) 2023 Fern Lane, SeismoHome earthquake detector project
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
import datetime
import logging
import logging.handlers
import multiprocessing
import os

# Logging level
LOGGING_LEVEL = logging.INFO

# Where to save log files
LOGS_DIR = "logs"


def worker_configurer(queue: multiprocessing.Queue):
    """
    Call this method in your process
    :param queue:
    :return:
    """
    # Setup queue handler
    queue_handler = logging.handlers.QueueHandler(queue)
    root_logger = logging.getLogger()
    root_logger.addHandler(queue_handler)
    root_logger.setLevel(logging.INFO)

    # Log test message
    logging.info("Logging setup is complete for current process")


class LoggingHandler:
    def __init__(self):
        # Logging queue
        self.queue = multiprocessing.Queue(-1)

    def configure_and_start_listener(self):
        """
        Initializes logging and starts listening. Send None to queue to stop it
        :return:
        """
        # Create logs directory is not exists
        if not os.path.exists(LOGS_DIR):
            os.makedirs(LOGS_DIR)

        # Create logs formatter
        log_formatter = logging.Formatter("[%(asctime)s] [%(process)-8d] [%(levelname)-8s] %(message)s",
                                          datefmt="%Y-%m-%d %H:%M:%S")

        # Setup logging into file
        file_handler = logging.FileHandler(os.path.join(LOGS_DIR,
                                                        datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".log"),
                                           encoding="utf-8")
        file_handler.setFormatter(log_formatter)

        # Setup logging into console
        import sys
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)

        # Add all handlers and setup level
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        root_logger.setLevel(LOGGING_LEVEL)

        # Start queue listener
        while True:
            try:
                # Get logging record
                record = self.queue.get()

                # Send None to exit
                if record is None:
                    break

                # Handle current logging record
                logger = logging.getLogger(record.name)
                logger.handle(record)

            # Ignore Ctrl+C (call queue.put(None) to stop this listener)
            except KeyboardInterrupt:
                pass

            # Error! WHY???
            except Exception:
                import sys, traceback
                print("Logging error: ", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
