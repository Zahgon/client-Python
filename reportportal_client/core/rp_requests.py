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

"""This module includes classes representing ReportPortal API requests.

Detailed information about requests wrapped up in that module
can be found by the following link:
https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md
"""

# mypy: disable_error_code=override

import asyncio
import logging
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, TypeVar, Union, cast

import aiohttp

from reportportal_client import helpers

# noinspection PyProtectedMember
from reportportal_client._internal.static.abstract import AbstractBaseClass, abstractmethod

# noinspection PyProtectedMember
from reportportal_client._internal.static.defines import DEFAULT_LOG_LEVEL, DEFAULT_PRIORITY, LOW_PRIORITY, Priority
from reportportal_client.aio.util import await_if_necessary
from reportportal_client.core.rp_file import RPFile
from reportportal_client.core.rp_issues import Issue
from reportportal_client.core.rp_responses import AsyncRPResponse, RPResponse
from reportportal_client.helpers import dict_to_payload
from reportportal_client.helpers.common_helpers import clean_binary_characters, verify_value_length

try:
    # noinspection PyPackageRequirements
    import simplejson as _json_converter
except ImportError:
    import json as _json_converter  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
T = TypeVar("T")


class HttpRequest:
    """This object stores attributes related to ReportPortal HTTP requests and makes them."""

    session_method: Callable
    url: Any
    files: Optional[Any]
    data: Optional[Any]
    json: Optional[Any]
    verify_ssl: Optional[Union[bool, str]]
    http_timeout: Union[float, tuple[float, float]]
    name: Optional[str]
    _priority: Priority

    def __init__(
        self,
        session_method: Callable,
        url: Any,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        files: Optional[Any] = None,
        verify_ssl: Optional[Union[bool, str]] = None,
        http_timeout: Union[float, tuple[float, float]] = (10, 10),
        name: Optional[str] = None,
    ) -> None:
        """Initialize an instance of the request with attributes.

        :param session_method: Method of the requests.Session instance
        :param url:            Request URL
        :param data:           Dictionary, list of tuples, bytes, or file-like object to send in the body of
                               the request
        :param json:           JSON to be sent in the body of the request
        :param files           Dictionary for multipart encoding upload
        :param verify_ssl:     Is SSL certificate verification required
        :param http_timeout:   a float in seconds for connect and read timeout. Use a Tuple to specific
                               connect and read separately
        :param name:           request name
        """
        self.data = data
        self.files = files
        self.json = json
        self.session_method = session_method
        self.url = url
        self.verify_ssl = verify_ssl
        self.http_timeout = http_timeout
        self.name = name
        self._priority = cast(Priority, DEFAULT_PRIORITY)

    def __lt__(self, other: "HttpRequest") -> bool:
        """Priority protocol for the PriorityQueue.

        :param other: another object to compare
        :return:      if current object is less than other
        """
        return self.priority < other.priority

    @property
    def priority(self) -> Priority:
        """Get the priority of the request.

        :return: the object priority
        """
        pass

    @priority.setter
    def priority(self, value: Priority) -> None:
        """Set the priority of the request.

        :param value: the object priority
        """
        pass

    def make(self) -> Any:
        """Make HTTP request to the ReportPortal API.

        The method catches any request error to not fail reporting. Since we are reporting tool and should not fail
        tests.

        :return: wrapped HTTP response or None in case of failure
        """
        try:
            return RPResponse(
                self.session_method(
                    self.url,
                    data=self.data,
                    json=self.json,
                    files=self.files,
                    verify=self.verify_ssl,
                    timeout=self.http_timeout,
                )
            )
        except (KeyError, IOError, ValueError, TypeError) as exc:
            logger.warning("ReportPortal %s request failed", self.name, exc_info=exc)
            return None


class ErrorPrintingHttpRequest(HttpRequest):
    """This is specific request object which catches any request error and prints it to the "sys.stderr".

    The object is supposed to be used in logging methods only to prevent infinite recursion of logging, when logging
    framework configured to log everything to ReportPortal. In this case if a request to ReportPortal fails, the
    failure will be logged to ReportPortal once again and, for example, in case of endpoint configuration error, it
    will also fail and will be logged again. So, the recursion will never end.

    This class is used to prevent this situation. It catches any request error and prints it to the "sys.stderr".
    """

    def make(self) -> Optional[RPResponse]:
        """Make HTTP request to the ReportPortal API.

        The method catches any request error and prints it to the "sys.stderr".

        :return: wrapped HTTP response or None in case of failure
        """
        # noinspection PyBroadException
        try:
            return RPResponse(
                self.session_method(
                    self.url,
                    data=self.data,
                    json=self.json,
                    files=self.files,
                    verify=self.verify_ssl,
                    timeout=self.http_timeout,
                )
            )
        except Exception:
            print(
                f"{datetime.now().isoformat()} - [ERROR] - ReportPortal request error:\n{traceback.format_exc()}",
                file=sys.stderr,
            )
            return None


class AsyncHttpRequest(HttpRequest):
    """This object stores attributes related to asynchronous ReportPortal HTTP requests and make them."""

    def __init__(
        self,
        session_method: Callable,
        url: Any,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        name: Optional[str] = None,
    ) -> None:
        """Initialize an instance of the request with attributes.

        :param session_method: Method of the requests.Session instance
        :param url:            Request URL or async coroutine returning the URL
        :param data:           Dictionary, list of tuples, bytes, or file-like object, or async coroutine to
                               send in the body of the request
        :param json:           JSON to be sent in the body of the request as Dictionary or async coroutine
        :param name:           request name
        """
        super().__init__(session_method=session_method, url=url, data=data, json=json, name=name)

    async def make(self) -> Optional[AsyncRPResponse]:
        """Asynchronously make HTTP request to the ReportPortal API.

        The method catches any request error to not fail reporting. Since we are reporting tool and should not fail
        tests.

        :return: wrapped HTTP response or None in case of failure
        """
        url = await await_if_necessary(self.url)
        if not url:
            return None
        data = await await_if_necessary(self.data)
        json = await await_if_necessary(self.json)
        try:
            return AsyncRPResponse(await self.session_method(url, data=data, json=json))
        except (KeyError, IOError, ValueError, TypeError) as exc:
            logger.warning("ReportPortal %s request failed", self.name, exc_info=exc)
            return None


class ErrorPrintingAsyncHttpRequest(AsyncHttpRequest):
    """This is specific request object which catches any request error and prints it to the "sys.stderr".

    The object is supposed to be used in logging methods only to prevent infinite recursion of logging, when logging
    framework configured to log everything to ReportPortal. In this case if a request to ReportPortal fails, the
    failure will be logged to ReportPortal once again and, for example, in case of endpoint configuration error, it
    will also fail and will be logged again. So, the recursion will never end.

    This class is used to prevent this situation. It catches any request error and prints it to the "sys.stderr".
    """

    async def make(self) -> Optional[AsyncRPResponse]:
        """Asynchronously make HTTP request to the ReportPortal API.

        The method catches any request error and prints it to the "sys.stderr".

        :return: wrapped HTTP response or None in case of failure
        """
        url = await await_if_necessary(self.url)
        if not url:
            return None
        data = await await_if_necessary(self.data)
        json = await await_if_necessary(self.json)
        # noinspection PyBroadException
        try:
            return AsyncRPResponse(await self.session_method(url, data=data, json=json))
        except Exception:
            print(
                f"{datetime.now().isoformat()} - [ERROR] - ReportPortal request error:\n{traceback.format_exc()}",
                file=sys.stderr,
            )
            return None


@dataclass(frozen=True)
class RPRequestBase(metaclass=AbstractBaseClass):
    """Base class for specific ReportPortal request models.

    Its main function to provide interface of 'payload' method which is used to generate HTTP request payload.
    """

    __metaclass__ = AbstractBaseClass
    truncate_attributes_enabled: Optional[bool]
    truncate_fields_enabled: Optional[bool]
    replace_binary_characters: Optional[bool]

    @property
    def _truncate_attributes_enabled(self) -> bool:
        pass

    @property
    def _truncate_fields_enabled(self) -> bool:
        pass

    @property
    def _replace_binary_characters_enabled(self) -> bool:
        pass

    def _sanitize_field(self, value: Optional[str], limit: int) -> Optional[str]:
        pass

    def _truncate_attributes(self, attributes: Optional[Union[list, dict]]) -> Optional[list[dict[str, Any]]]:
        pass

    @property
    @abstractmethod
    def payload(self) -> Any:
        """Abstract interface for getting HTTP request payload.

        :return: JSON representation in the form of a Dictionary
        """
        raise NotImplementedError("Payload interface is not implemented!")


@dataclass(frozen=True)
class LaunchStartRequest(RPRequestBase):
    """ReportPortal start launch request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#start-launch
    """

    name: str
    start_time: str
    attributes: Optional[Union[list, dict]] = None
    description: Optional[str] = None
    mode: str = "default"
    rerun: bool = False
    rerun_of: Optional[str] = None
    uuid: Optional[str] = None

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


@dataclass(frozen=True)
class LaunchFinishRequest(RPRequestBase):
    """ReportPortal finish launch request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#finish-launch
    """

    end_time: str
    status: Optional[str] = None
    attributes: Optional[Union[list, dict]] = None
    description: Optional[str] = None

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


@dataclass(frozen=True)
class ItemStartRequest(RPRequestBase):
    """ReportPortal start test item request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#start-rootsuite-item
    """

    name: str
    start_time: str
    type_: str
    launch_uuid: Any
    attributes: Optional[Union[list, dict]]
    code_ref: Optional[str]
    description: Optional[str]
    has_stats: Optional[bool]
    parameters: Optional[Union[list, dict]]
    retry: Optional[bool]
    retry_of: Optional[str]
    test_case_id: Optional[str]
    uuid: Optional[str]

    def _create_request(self, **kwargs) -> dict:
        pass

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


class AsyncItemStartRequest(ItemStartRequest):
    """ReportPortal start test item request asynchronous model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#start-rootsuite-item
    """

    def __int__(self, *args, **kwargs) -> None:
        """Initialize an instance of the request with attributes."""
        super.__init__(*args, **kwargs)

    @property
    async def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


@dataclass(frozen=True)
class ItemFinishRequest(RPRequestBase):
    """ReportPortal finish test item request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#finish-child-item
    """

    end_time: str
    launch_uuid: Any
    status: Optional[str]
    attributes: Optional[Union[list, dict]]
    description: Optional[str]
    is_skipped_an_issue: Optional[bool]
    issue: Optional[Issue]
    retry: Optional[bool]
    retry_of: Optional[str]
    test_case_id: Optional[str]

    def _create_request(self, **kwargs) -> dict:
        pass

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


class AsyncItemFinishRequest(ItemFinishRequest):
    """ReportPortal finish test item request asynchronous model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#finish-child-item
    """

    def __int__(self, *args, **kwargs) -> None:
        """Initialize an instance of the request with attributes."""
        super.__init__(*args, **kwargs)

    @property
    async def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


@dataclass(frozen=True)
class ItemUpdateRequest(RPRequestBase):
    """ReportPortal update test item request model."""

    attributes: Optional[Union[list, dict]] = None
    description: Optional[str] = None

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass


@dataclass(frozen=True)
class RPRequestLog(RPRequestBase):
    """ReportPortal log save request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#save-single-log-without-attachment
    """

    launch_uuid: Any
    time: str
    file: Optional[RPFile] = None
    item_uuid: Optional[Any] = None
    level: str = DEFAULT_LOG_LEVEL
    message: Optional[str] = None

    @staticmethod
    def _create_request(**kwargs) -> dict:
        pass

    @property
    def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass

    @staticmethod
    def _multipart_size(payload: dict, file: Optional[RPFile]):
        pass

    @property
    def multipart_size(self) -> Any:
        """Calculate request size how it would be transfer in Multipart HTTP.

        :return: estimate request size
        """
        pass


class AsyncRPRequestLog(RPRequestLog):
    """ReportPortal log save request asynchronous model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#save-single-log-without-attachment
    """

    def __int__(self, *args, **kwargs) -> None:
        """Initialize an instance of the request with attributes."""
        super.__init__(*args, **kwargs)

    @property
    async def payload(self) -> dict:
        """Get HTTP payload for the request.

        :return: JSON representation in the form of a Dictionary
        """
        pass

    @property
    async def multipart_size(self) -> int:
        """Calculate request size how it would be transfer in Multipart HTTP.

        :return: estimate request size
        """
        pass


@dataclass(frozen=True)
class RPLogBatch(RPRequestBase):
    """ReportPortal log save batches with attachments request model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#batch-save-logs
    """

    log_reqs: list[Union[RPRequestLog, AsyncRPRequestLog]]
    default_content: str = "application/octet-stream"
    priority: Priority = cast(Priority, LOW_PRIORITY)

    def __get_file(self, rp_file) -> tuple[str, tuple]:
        """Form a tuple for the single file."""
        pass

    def _get_files(self) -> list[tuple[str, tuple]]:
        """Get list of files for the JSON body."""
        pass

    def __get_request_part(self) -> list[tuple[str, tuple]]:
        pass

    @property
    def payload(self) -> list[tuple[str, tuple]]:
        r"""Get HTTP payload for the request.

        Example:
        [('json_request_part',
          (None,
           '[{"launchUuid": "bf6edb74-b092-4b32-993a-29967904a5b4",
              "time": "1588936537081",
              "message": "Html report",
              "level": "INFO",
              "itemUuid": "d9dc2514-2c78-4c4f-9369-ee4bca4c78f8",
              "file": {"name": "Detailed report"}}]',
           'application/json')),
         ('file',
          ('Detailed report',
           '<html lang="utf-8">\n<body><p>Paragraph</p></body></html>',
           'text/html'))]
        """
        pass


class AsyncRPLogBatch(RPLogBatch):
    """ReportPortal log save batches with attachments request asynchronous model.

    https://github.com/reportportal/documentation/blob/master/src/md/src/DevGuides/reporting.md#batch-save-logs
    """

    def __int__(self, *args, **kwargs) -> None:
        """Initialize an instance of the request with attributes."""
        super.__init__(*args, **kwargs)

    async def __get_request_part(self) -> list[dict]:
        pass

    @property
    async def payload(self) -> aiohttp.MultipartWriter:
        """Get HTTP payload for the request.

        :return: Multipart request object capable to send with AIOHTTP
        """
        pass
