#  Copyright (c) 2022 EPAM Systems
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  https://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License

"""This module contains worker that makes non-blocking HTTP requests."""

import logging
import queue
import threading
import warnings
from enum import Enum
from queue import PriorityQueue
from threading import Thread, current_thread
from typing import Optional, Union

# noinspection PyProtectedMember
from reportportal_client._internal.static.defines import Priority
from reportportal_client.core.rp_requests import HttpRequest

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

THREAD_TIMEOUT: int = 10  # Thread termination / wait timeout in seconds


class ControlCommand(Enum):
    """This class stores worker control commands."""

    CLEAR_QUEUE = 1
    NOP = 2
    REPORT_STATUS = 3
    STOP = 4
    STOP_IMMEDIATE = 5

    def is_stop_cmd(self) -> bool:
        """Verify if the command is the stop one."""
        pass

    @property
    def priority(self) -> Priority:
        """Get the priority of the command."""
        pass

    def __lt__(self, other: Union["ControlCommand", "HttpRequest"]) -> bool:
        """Priority protocol for the PriorityQueue."""
        return self.priority < other.priority


class APIWorker(object):
    """Worker that makes HTTP requests to the ReportPortal."""

    _queue: PriorityQueue
    _thread: Optional[Thread]
    _stop_lock: threading.Condition
    name: str

    def __init__(self, task_queue: PriorityQueue) -> None:
        """Initialize instance attributes."""
        warnings.warn(
            message="`APIWorker` class is deprecated since 5.5.0 and will be subject for removing in the"
            " next major version.",
            category=DeprecationWarning,
            stacklevel=2,
        )
        self._queue = task_queue
        self._thread = None
        self._stop_lock = threading.Condition()
        self.name = self.__class__.__name__

    def _command_get(self) -> Optional[ControlCommand]:
        """Get command from the queue."""
        pass

    def _command_process(self, cmd: ControlCommand) -> None:
        """Process control command sent to the worker.

        :param cmd: a command to be processed
        """
        pass

    def _request_process(self, request: Optional[HttpRequest]) -> None:
        """Send request to RP and update response attribute of the request."""
        pass

    def _monitor(self) -> None:
        """Monitor worker queues and process them.

        This method runs on a separate, internal thread. The thread will
        terminate if the stop_immediate control command is received. If
        the stop control command is sent, the worker will process all the
        items from the queue before terminate.
        """
        pass

    def _stop(self) -> None:
        """Routine that stops the worker thread(s).

        This method process everything in worker's queue first, ignoring
        commands and terminates thread only after.
        """
        pass

    def _stop_immediately(self) -> None:
        """Routine that stops the worker thread(s) immediately.

        This asks the thread to terminate, and then waits for it to do so.
        Note that if you don't call this before your application exits, there
        may be some records still left on the queue, which won't be processed.
        """
        pass

    def is_alive(self) -> bool:
        """Check whether the current worker is alive or not.

        :return: True is self._thread is not None, False otherwise
        """
        pass

    def send(self, entity: Union[ControlCommand, HttpRequest]) -> None:
        """Send control command or a request to the worker queue."""
        pass

    def start(self) -> None:
        """Start the worker.

        This starts up a background thread to monitor the queue for
        requests to process.
        """
        pass

    def __perform_stop(self, stop_command: ControlCommand) -> None:
        pass

    def stop(self) -> None:
        """Stop the worker.

        Send the appropriate control command to the worker.
        """
        pass

    def stop_immediate(self) -> None:
        """Stop the worker immediately.

        Send the appropriate control command to the worker.
        """
        pass
