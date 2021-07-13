import decimal
import json
import logging
import os
import time
import zlib
from datetime import date
from gzip import GzipFile
from io import StringIO, BytesIO
from typing import Dict, Union, IO, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, Request

import pynmrstar

__version__: str = "3.2.1"
min_cnmrstar_version: str = "3.2.0"

# If we have requests, open a session to reuse for the duration of the program run
try:
    from requests import session as _requests_session
    # This replaces the urllib HTTPError if we have requests
    from requests.exceptions import HTTPError, ConnectionError
    _session = _requests_session()
except ModuleNotFoundError:
    _session = None


# noinspection PyDefaultArgument
def _get_comments(_comment_cache: Dict[str, Dict[str, str]] = {}) -> Dict[str, Dict[str, str]]:
    """ Loads the comments that should be placed in written files.

    The default argument is mutable on purpose, as it is used as a cache for memoization."""

    # Comment dictionary already exists
    if _comment_cache:
        return _comment_cache

    file_to_load = os.path.join(os.path.dirname(os.path.realpath(__file__)))
    file_to_load = os.path.join(file_to_load, "reference_files/comments.str")

    # The import needs to be here to avoid import errors due to circular imports
    from pynmrstar.entry import Entry
    try:
        comment_entry = Entry.from_file(file_to_load)
    except IOError:
        # Load the comments from Github if we can't find them locally
        try:
            logging.warning('Could not load comments from disk. Loading from web...')
            comment_entry = Entry.from_file(_interpret_file(pynmrstar.definitions.COMMENT_URL))
        except Exception:
            logging.exception('Could not load comments from web. No comments will be shown.')
            # No comments will be printed
            return {}

    # Load the comments
    comment_records = comment_entry[0][0].get_tag(["category", "comment", "every_flag"])
    comment_map = {'N': False, 'Y': True}
    for comment in comment_records:
        if comment[1] != ".":
            _comment_cache[comment[0]] = {'comment': comment[1].rstrip() + "\n\n",
                                          'every_flag': comment_map[comment[2]]}

    return _comment_cache


def _json_serialize(obj: object) -> str:
    """JSON serializer for objects not serializable by default json code"""

    # Serialize datetime.date objects by calling str() on them
    if isinstance(obj, (date, decimal.Decimal)):
        return str(obj)
    raise TypeError("Type not serializable: %s" % type(obj))


def _get_url_reliably(url: str, wait_time: float = 10, raw: bool = False, timeout: int = 10, retries: int = 2):
    """ Attempts to load data from a URL, retrying the specified number of times with an exponential
    backoff if rate limited. Fails immediately on 4xx errors that are not 403."""

    global _session

    # If using Requests
    if _session:
        try:
            response = _session.get(url, timeout=timeout,
                                    headers={'Application': f'PyNMRSTAR {__version__}'})
        except ConnectionError:
            _session = _requests_session()
            try:
                response = _session.get(url, timeout=timeout,
                                        headers={'Application': f'PyNMRSTAR {__version__}'})
            except ConnectionError:
                raise HTTPError("A ConnectionError was thrown during an attempt to load the entry.")

        # We are rate limited - sleep and try again
        if response.status_code == 403:
            if retries > 0:
                logging.warning(f'We were rate limited. Sleeping for {wait_time} seconds.')
                time.sleep(wait_time)
                return _get_url_reliably(url, wait_time=wait_time*2, raw=raw, timeout=timeout,
                                         retries=retries - 1)
            else:
                raise HTTPError("Continued to receive 403 (forbidden, due to rate limit) after multiple wait times.") \
                    from None
        if response.status_code == 404:
            raise KeyError(f"Server returned 404.") from None
        response.raise_for_status()
        if raw:
            return response.content
        else:
            return response.text
    else:
        # Use the built in library
        try:
            req = Request(url)
            req.add_header('Application', f'PyNMRSTAR {__version__}')
            url_request = urlopen(req, timeout=timeout)
            serialized_ent = url_request.read()
            url_request.close()

        except HTTPError as err:
            if err.code == 404:
                raise KeyError(f"Server returned 404.") from None
            # We are rate limited - sleep and try again
            elif err.code == 403:
                if retries > 0:
                    logging.warning(f'We were rate limited. Sleeping for {wait_time} seconds.')
                    time.sleep(wait_time)
                    return _get_url_reliably(url, wait_time=wait_time * 2, raw=raw, timeout=timeout,
                                             retries=retries - 1)
                else:
                    raise HTTPError("Continued to receive 403 (forbidden, due to rate limit) after multiple wait "
                                    "times.") from None
            else:
                raise err
        if raw:
            return serialized_ent
        else:
            return serialized_ent.decode()


def _get_entry_from_database(entry_num: Union[str, int], convert_data_types: bool = False) -> 'pynmrstar.Entry':
    """ Fetches an entry from the API (or falls back to the FTP site) in
    as reliable and robust a way as possible. Used by Entry.from_database(). """

    entry_num = str(entry_num).lower()
    if entry_num.startswith("bmr"):
        entry_num = entry_num[3:]

    # Try to load the entry using JSON

    entry_url: str = (pynmrstar.definitions.API_URL + "/entry/%s?format=zlib") % entry_num

    try:
        serialized_ent = _get_url_reliably(entry_url, raw=True, retries=2)
        json_data = json.loads(zlib.decompress(serialized_ent).decode())
        if "error" in json_data:
            raise RuntimeError('Something wrong with API response.')
        ent = pynmrstar.Entry.from_json(json_data)
    except (HTTPError, ConnectionError, RuntimeError):
        # Can't fall back to FTP for chemcomps
        if entry_num.startswith("chemcomp"):
            raise IOError("Unable to load that chemcomp from the API.")

        # We're going to try again from the FTP
        logging.warning('Failed to download entry from the API, trying again from the FTP site.')
        if "bmse" in entry_num or "bmst" in entry_num:
            url = f"{pynmrstar.definitions.FTP_URL}/metabolomics/entry_directories/{entry_num}/{entry_num}.str"
        else:
            url = f"{pynmrstar.definitions.FTP_URL}/entry_directories/bmr{entry_num}/bmr{entry_num}_3.str"
        try:
            # Use a longer timeout for the timeout
            entry_content = _get_url_reliably(url, raw=False, timeout=20, retries=1)
            ent = pynmrstar.Entry.from_string(entry_content)
        except HTTPError:
            raise IOError(f"Entry {entry_num} does not exist in the public database.")
        except URLError:
            raise IOError("You don't appear to have an active internet connection. Cannot fetch entry.")

    except KeyError:
        raise IOError(f"Entry {entry_num} does not exist in the public database.")

    # Update the entry source
    ent.source = f"from_database({entry_num})"
    for each_saveframe in ent:
        each_saveframe.source = ent.source
        for each_loop in each_saveframe:
            each_loop.source = ent.source

    if convert_data_types:
        schema = pynmrstar.utils.get_schema()
        for each_saveframe in ent:
            for tag in each_saveframe.tags:
                cur_tag = each_saveframe.tag_prefix + "." + tag[0]
                tag[1] = schema.convert_tag(cur_tag, tag[1])
            for loop in each_saveframe:
                for row in loop.data:
                    for pos in range(0, len(row)):
                        category = loop.category + "." + loop.tags[pos]
                        row[pos] = schema.convert_tag(category, row[pos])

    return ent


def _interpret_file(the_file: Union[str, IO]) -> StringIO:
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    if hasattr(the_file, 'read'):
        read_data: Union[bytes, str] = the_file.read()
        if type(read_data) == bytes:
            buffer: BytesIO = BytesIO(read_data)
        elif type(read_data) == str:
            buffer = BytesIO(read_data.encode())
        else:
            raise IOError("What did your file object return when .read() was called on it?")
    elif isinstance(the_file, str):
        if the_file.startswith("http://") or the_file.startswith("https://") or the_file.startswith("ftp://"):
            buffer = BytesIO(_get_url_reliably(the_file, raw=True, retries=0))
        else:
            with open(the_file, 'rb') as read_file:
                buffer = BytesIO(read_file.read())
    else:
        raise ValueError("Cannot figure out how to interpret the file you passed.")

    # Decompress the buffer if we are looking at a gzipped file
    try:
        gzip_buffer = GzipFile(fileobj=buffer)
        gzip_buffer.readline()
        gzip_buffer.seek(0)
        buffer = BytesIO(gzip_buffer.read())
    # Apparently we are not looking at a gzipped file
    except (IOError, AttributeError, UnicodeDecodeError):
        pass

    buffer.seek(0)
    return StringIO(buffer.read().decode().replace("\r\n", "\n").replace("\r", "\n"))


def get_clean_tag_list(item: Union[str, List[str], Tuple[str]]) -> List[Dict[str, str]]:
    """ Converts the provided item to a list of dictionaries of
    {
     formatted -> just the lower case tag name (category stripped)
     original -> whatever was provided, completely unmodified
    }"""

    if not isinstance(item, (str, list, tuple)):
        raise ValueError('Invalid object provided. Only a tag name (str), or list of tags (list or tuple)'
                         ' are valid inputs to this function.')

    if isinstance(item, list):
        tag_list: List[str] = item
    elif isinstance(item, tuple):
        tag_list = list(item)
    elif isinstance(item, str):
        tag_list = [item]
    else:
        raise ValueError(f'The value you provided was not a string, list, or tuple. Item: {repr(item)}')

    try:
        return [{"formatted": pynmrstar.utils.format_tag(_.lower()), "original": _} for _ in tag_list]
    except AttributeError:
        raise ValueError('Your list or tuple may only contain tag names expressed as strings.')


def write_to_file(nmrstar_object: Union['pynmrstar.Entry', 'pynmrstar.Saveframe'],
                  file_name: str,
                  format_: str = "nmrstar",
                  show_comments: bool = True,
                  skip_empty_loops: bool = False,
                  skip_empty_tags: bool = False):
    """ Writes the object to the specified file in NMR-STAR format. """

    if format_ not in ["nmrstar", "json"]:
        raise ValueError("Invalid output format.")

    data_to_write = ''
    if format_ == "nmrstar":
        data_to_write = nmrstar_object.format(show_comments=show_comments,
                                              skip_empty_loops=skip_empty_loops,
                                              skip_empty_tags=skip_empty_tags)
    elif format_ == "json":
        data_to_write = nmrstar_object.get_json()

    out_file = open(file_name, "w")
    out_file.write(data_to_write)
    out_file.close()
