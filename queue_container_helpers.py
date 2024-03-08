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

import multiprocessing
import random
from typing import List

import request_response_container


def queue_to_list(
    request_response_queue: multiprocessing.Queue,
) -> List[request_response_container.RequestResponseContainer]:
    """Retrieves all elements from queue and returns them as list
    NOTE: THIS FUNCTION MUST BE CALLED INSIDE LOCK

    Args:
        request_response_queue (multiprocessing.Queue): multiprocessing Queue to convert to list

    Returns:
        List[Any]: list of queue elements (containers)
    """
    queue_list = []

    # Convert entire queue to list
    while request_response_queue.qsize() > 0:
        container = request_response_queue.get()
        if container not in queue_list:
            queue_list.append(container)

    # Convert list back to the queue
    for container_ in queue_list:
        request_response_queue.put(container_)

    # Return list
    return queue_list


def get_container_from_queue(
    request_response_queue: multiprocessing.Queue,
    lock: multiprocessing.Lock,
    container_id: int,
) -> request_response_container.RequestResponseContainer | None:
    """Retrieves request_response_container from queue by ID without removing it

    Args:
        request_response_queue (multiprocessing.Queue): multiprocessing Queue to get container from
        lock (multiprocessing.Lock): multiprocessing lock to prevent errors while updating the queue
        container_id: requested container ID

    Returns:
        RequestResponseContainer or None: container if exists, otherwise None
    """

    def _get_container_from_queue() -> request_response_container.RequestResponseContainer | None:
        # Convert entire queue to list
        queue_list = queue_to_list(request_response_queue)

        # Search container in list
        container = None
        for container__ in queue_list:
            if container__.id == container_id:
                container = container__
        return container

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            container_ = _get_container_from_queue()
        return container_

    # Get without lock
    else:
        return _get_container_from_queue()


def put_container_to_queue(
    request_response_queue: multiprocessing.Queue,
    lock: multiprocessing.Lock,
    request_response_container_: request_response_container.RequestResponseContainer,
) -> int:
    """Generates unique container ID (if needed) and puts container to the queue (deletes previous one if exists)

    Args:
        request_response_queue (multiprocessing.Queue): Multiprocessing Queue into which put the container
        lock (multiprocessing.Lock): Multiprocessing lock to prevent errors while updating the queue
        request_response_container_: Container to put into the queue

    Returns:
        container ID: container ID
    """

    def _put_container_to_queue() -> int:
        # Delete previous one
        if request_response_container_.id >= 0:
            remove_container_from_queue(request_response_queue, None, request_response_container_.id)

        # Convert queue to lost
        queue_list = queue_to_list(request_response_queue)

        # Check if we need to generate a new ID for the container
        if request_response_container_.id < 0:
            # Generate unique ID
            while True:
                container_id = random.randint(0, 2147483647)
                unique = True
                for container in queue_list:
                    if container.id == container_id:
                        unique = False
                        break
                if unique:
                    break

            # Set container id
            request_response_container_.id = container_id

        # Add our container to the queue
        request_response_queue.put(request_response_container_)

        return request_response_container_.id

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            id_ = _put_container_to_queue()
        return id_

    # Put without lock
    else:
        return _put_container_to_queue()


def remove_container_from_queue(
    request_response_queue: multiprocessing.Queue, lock: multiprocessing.Lock, container_id: int
) -> bool:
    """Tries to remove container by specific ID from the queue

    Args:
        request_response_queue (multiprocessing.Queue): multiprocessing Queue to remove container from
        lock (multiprocessing.Lock): multiprocessing lock to prevent errors while updating the queue
        container_id (int): ID of container to remove from the queue

    Returns:
        bool: True if removed successfully, False if not
    """

    def remove_container_from_queue_() -> bool:
        # Convert entire queue to list
        queue_list = []
        while not request_response_queue.empty():
            queue_list.append(request_response_queue.get())

        # Flag to return
        removed = False

        # Convert list back to the queue without our container
        for container_ in queue_list:
            if container_.id != container_id:
                request_response_queue.put(container_)
            else:
                removed = True

        return removed

    # Is lock available?
    if lock is not None:
        # Use it
        with lock:
            removed_ = remove_container_from_queue_()
        return removed_

    # Remove without lock
    else:
        return remove_container_from_queue_()
