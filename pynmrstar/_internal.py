import decimal
import json
import logging
import os
import re
import threading
import time
import zlib
from contextlib import contextmanager
from datetime import date
from gzip import GzipFile
from importlib.metadata import version
from io import StringIO, BytesIO
from pathlib import Path
from typing import Dict, Union, IO, List, Optional, Tuple
from urllib.error import URLError

import requests

import pynmrstar

__version__: str = version("pynmrstar")

# Create a session to reuse for the duration of the program run
_session = requests.session()

logger = logging.getLogger('pynmrstar')


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
        logger.warning('Could not load comments from disk. No comments will be shown.')
        # No comments will be printed
        return {}

    # Load the comments. They are added to the cache all at once, so another thread never sees only some.
    comment_records = comment_entry[0][0].get_tag(["category", "comment", "every_flag"])
    comment_map = {'N': False, 'Y': True}
    comments = {}
    for comment in comment_records:
        if comment[1] != ".":
            comments[comment[0]] = {'comment': comment[1].rstrip() + "\n\n",
                                    'every_flag': comment_map[comment[2]]}
    _comment_cache.update(comments)

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

    try:
        response = _session.get(url, timeout=timeout,
                                headers={'Application': f'PyNMRSTAR {__version__}'})
    except requests.exceptions.ConnectionError:
        _session = requests.session()
        try:
            response = _session.get(url, timeout=timeout,
                                    headers={'Application': f'PyNMRSTAR {__version__}'})
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.HTTPError("A ConnectionError was thrown during an attempt to load the entry.")

    # We are rate limited - sleep and try again
    if response.status_code == 403:
        if retries > 0:
            logger.warning(f'We were rate limited. Sleeping for {wait_time} seconds.')
            time.sleep(wait_time)
            return _get_url_reliably(url, wait_time=wait_time * 2, raw=raw, timeout=timeout,
                                     retries=retries - 1)
        else:
            raise requests.exceptions.HTTPError("Continued to receive 403 (forbidden, due to rate limit) after multiple wait times.") \
                from None
    if response.status_code == 404:
        raise KeyError(f"Server returned 404.") from None
    response.raise_for_status()
    if raw:
        return response.content
    else:
        return response.text


def _get_entry_from_database(entry_num: Union[str, int],
                             convert_data_types: bool = False,
                             schema: 'pynmrstar.Schema' = None) -> 'pynmrstar.Entry':
    """ Fetches an entry from the API (or falls back to the FTP site) in
    as reliable and robust a way as possible. Used by Entry.from_database(). """

    entry_num = str(entry_num).strip()
    # The API looks chemcomps up case-sensitively, by their uppercase PDB ligand code ('chemcomp_ATP'), so
    #  only the prefix can be normalized. Everything else is lowercase ('bmse000001').
    if entry_num.lower().startswith("chemcomp_"):
        entry_num = "chemcomp_" + entry_num[9:].upper()
    else:
        entry_num = entry_num.lower()
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
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, RuntimeError):
        # Can't fall back to FTP for chemcomps
        if entry_num.startswith("chemcomp"):
            raise IOError("Unable to load that chemcomp from the API.")

        # We're going to try again from the FTP
        logger.warning('Failed to download entry from the API, trying again from the FTP site.')
        if "bmse" in entry_num or "bmst" in entry_num:
            url = f"{pynmrstar.definitions.FTP_URL}/metabolomics/entry_directories/{entry_num}/{entry_num}.str"
        else:
            url = f"{pynmrstar.definitions.FTP_URL}/entry_directories/bmr{entry_num}/bmr{entry_num}_3.str"
        try:
            # Use a longer timeout for the timeout
            entry_content = _get_url_reliably(url, raw=False, timeout=20, retries=1)
            ent = pynmrstar.Entry.from_string(entry_content)
        except requests.exceptions.HTTPError:
            raise IOError(f"Entry {entry_num} does not exist in the public database.") from None
        except URLError:
            raise IOError("You don't appear to have an active internet connection. Cannot fetch entry.") from None

    except KeyError:
        raise IOError(f"Entry {entry_num} does not exist in the public database.") from None

    # Update the entry source
    ent.source = f"from_database({entry_num})"
    for each_saveframe in ent:
        each_saveframe.source = ent.source
        for each_loop in each_saveframe:
            each_loop.source = ent.source

    if convert_data_types:
        schema = pynmrstar.utils.get_schema(schema)
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


def _interpret_file(the_file: Union[str, Path, IO]) -> StringIO:
    """Helper method returns some sort of object with a read() method.
    the_file could be a URL, a file location, a file object, or a
    gzipped version of any of the above."""

    return StringIO(_interpret_file_text(the_file))


def _interpret_file_text(the_file: Union[str, Path, IO]) -> str:
    """Returns the text of the_file, which can be anything _interpret_file() accepts, with its line endings
    normalized to newlines."""

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
    elif isinstance(the_file, Path):
        with open(str(the_file), 'rb') as read_file:
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
    text = buffer.read().decode()
    # Searching for a single character is much faster than replace() scanning the text twice
    if '\r' in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


#: Pass as a ``version`` to fetch the newest dictionary release from the internet.
LATEST_DICTIONARY: str = 'latest'


def _dictionary_cache_root() -> str:
    """Directory that holds cached dictionary distributions, one subdirectory
    per release version."""

    root = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(root, 'pynmrstar')


def _dictionary_version(xlschem_text: str) -> str:
    """Read the dictionary release version out of an xlschem_ann.csv body."""

    from csv import DictReader
    for row in DictReader(StringIO(xlschem_text)):
        if row.get('Dictionary sequence') == 'TBL_BEGIN':
            return row.get('ADIT category view type') or 'unknown'
    return 'unknown'


def _packaged_dictionary_directory() -> str:
    """The directory holding the dictionary distribution shipped with pynmrstar."""

    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'reference_files')


def read_dictionary_directory(directory: str) -> Dict[str, str]:
    """Read every distribution file from a local directory (or URL base).

    Raises if any of them is missing: a partial distribution would quietly
    produce a schema without its enumerations or validation rules."""

    if directory.startswith(('http://', 'https://', 'ftp://')):
        def _join(base: str, name: str) -> str:
            return base.rstrip('/') + '/' + name
    else:
        _join = os.path.join
    return {name: _interpret_file(_join(directory, name)).read()
            for name in pynmrstar.definitions.DICTIONARY_FILES}


def packaged_dictionary_version() -> str:
    """The version of the dictionary distribution shipped with pynmrstar."""

    with open(os.path.join(_packaged_dictionary_directory(), 'xlschem_ann.csv'), encoding='utf-8') as handle:
        return _dictionary_version(handle.read())


def _cache_dictionary(files: Dict[str, str], dictionary_version: str) -> None:
    """Write a distribution to the cache, best effort.

    The files are written to a scratch directory which is then renamed into
    place, so the cache only ever holds complete distributions -- an
    interrupted write, or two processes caching at once, cannot leave behind a
    truncated file that would be read back on every later run."""

    import shutil
    import tempfile

    root = _dictionary_cache_root()
    final = os.path.join(root, dictionary_version)
    if os.path.isdir(final):
        return
    scratch = None
    try:
        os.makedirs(root, exist_ok=True)
        scratch = tempfile.mkdtemp(prefix='.partial-', dir=root)
        for name, text in files.items():
            with open(os.path.join(scratch, name), 'w', encoding='utf-8', newline='') as handle:
                handle.write(text)
        os.rename(scratch, final)
        scratch = None
    except OSError:
        pass  # caching is best effort; most likely another process won the race
    finally:
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)


def local_dictionary(version: str) -> Optional[Dict[str, str]]:
    """The distribution files for one release if they are on this machine --
    packaged with pynmrstar or cached -- and None otherwise. Never touches the
    network."""

    if version == packaged_dictionary_version():
        return read_dictionary_directory(_packaged_dictionary_directory())
    cached = os.path.join(_dictionary_cache_root(), version)
    if os.path.isdir(cached):
        try:
            return read_dictionary_directory(cached)
        except OSError:
            return None
    return None


def _fetch_dictionary(source: str) -> Tuple[Dict[str, str], str]:
    """Read a whole distribution from a URL base or local directory, and return
    it with the version it contains. Raises ``ValueError`` if it cannot be
    read."""

    try:
        fetched = read_dictionary_directory(source)
    # _get_url_reliably raises KeyError for a 404
    except (requests.exceptions.RequestException, URLError, OSError, KeyError) as err:
        raise ValueError(f"Could not fetch the dictionary from '{source}': {err}") from err
    return fetched, _dictionary_version(fetched['xlschem_ann.csv'])


def load_dictionary(version: str = None, source: str = None) -> Tuple[Dict[str, str], str]:
    """Return ``({filename: contents}, version)`` for the dictionary distribution
    files a :class:`Schema` is built from.

    * ``version=None`` -- the distribution packaged with pynmrstar. This never
      touches the network or the cache.
    * ``version='latest'`` -- the newest release, fetched from ``source``
      every time and cached under ``${XDG_CACHE_HOME:-~/.cache}/pynmrstar/<version>/``
      so it can be asked for by number later. Raises ``ValueError`` if it
      cannot be fetched.
    * any other ``version`` -- that release: the packaged one if it matches,
      else a cached copy, else the release tagged for it in the dictionary
      repository (:data:`definitions.DICTIONARY_RELEASE_URL`), else ``source``
      if that is what it currently serves. A release downloaded either way is
      cached. Raises ``ValueError`` if it cannot be found.

    ``source`` defaults to the ``PYNMRSTAR_DICTIONARY_SOURCE`` environment
    variable, then :data:`definitions.DICTIONARY_URL`; it may be a URL base or a
    local directory holding the distribution files. Passing ``source`` or
    setting the environment variable means only it is read: the tagged releases
    are not looked up."""

    if version is None:
        files = read_dictionary_directory(_packaged_dictionary_directory())
        return files, _dictionary_version(files['xlschem_ann.csv'])

    if version != LATEST_DICTIONARY:
        local = local_dictionary(version)
        if local is not None:
            return local, version

    if source is None:
        source = os.environ.get('PYNMRSTAR_DICTIONARY_SOURCE')
    release_error = None
    if version != LATEST_DICTIONARY and source is None:
        release = pynmrstar.definitions.DICTIONARY_RELEASE_URL.format(version=version)
        try:
            fetched, fetched_version = _fetch_dictionary(release)
        except ValueError as err:
            # Not tagged (yet) -- it may still be the newest release
            release_error = err
        else:
            if fetched_version != version:
                raise ValueError(f"The dictionary release tagged for version '{version}' at '{release}' "
                                 f"contains version '{fetched_version}'.")
            _cache_dictionary(fetched, fetched_version)
            return fetched, fetched_version

    if source is None:
        source = pynmrstar.definitions.DICTIONARY_URL
    fetched, fetched_version = _fetch_dictionary(source)

    if version != LATEST_DICTIONARY and version != fetched_version:
        tagged = f" no release is tagged for it ({release_error})," if release_error else ""
        raise ValueError(f"Dictionary version '{version}' is unavailable: it is not the packaged version "
                         f"({packaged_dictionary_version()}), it is not cached,{tagged} and the newest release "
                         f"is '{fetched_version}'.")

    _cache_dictionary(fetched, fetched_version)
    return fetched, fetched_version


# Anything outside the "Basic Latin" unicode block (0x00-0x7f). NMR-STAR is an
# ASCII format, so non-ASCII characters are reported during validation.
_non_ascii_pattern = re.compile(r'[^\x00-\x7f]')


def _non_ascii_error(tag: str, value: str) -> str:
    """ Formats the validation error for a value that contains characters
    outside of ASCII. The offending characters are listed with their code
    points, since they are often invisible or ambiguous in the file itself."""

    characters: List[str] = []
    for character in _non_ascii_pattern.findall(value):
        if character not in characters:
            characters.append(character)
    described = ', '.join(f"'{_}' (U+{ord(_):04X})" for _ in characters)
    return f"Non-ASCII character(s) {described} in tag '{tag}': '{value}'."


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
        return [{"formatted": pynmrstar.utils.format_tag_lc(_), "original": _} for _ in tag_list]
    except AttributeError:
        raise ValueError('Your list or tuple may only contain tag names expressed as strings.')


def write_to_file(nmrstar_object: Union['pynmrstar.Entry', 'pynmrstar.Saveframe'],
                  file_name: Union[str, Path],
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

    out_file = open(str(file_name), "w")
    out_file.write(data_to_write)
    out_file.close()


# ---------------------------------------------------------------------------
# Parse-time leniency
#
# A few structural problems are detected while building the object model rather
# than while tokenizing (Saveframe.add_tag). Raising on them makes the library
# unusable for validation: a validator's input is by definition the not-yet-
# correct file, and refusing to load it means the very problem you exist to
# report cannot be reported. These conditions are therefore treated like the
# tokenizer's existing parse warnings -- logged by default, raised when the
# caller passes raise_parse_warnings=True.
#
# Outside a parse the behaviour is unchanged: building an inconsistent object
# through the API is a programming error, so it still raises.
# ---------------------------------------------------------------------------

_parse_state = threading.local()


@contextmanager
def parsing(raise_parse_warnings: bool):
    """ Marks the enclosing block as a parse, during which recoverable
    structural problems become warnings rather than exceptions. """

    previous = getattr(_parse_state, 'raise_parse_warnings', None)
    _parse_state.raise_parse_warnings = raise_parse_warnings
    try:
        yield
    finally:
        _parse_state.raise_parse_warnings = previous


def parse_warning(message: str) -> bool:
    """ Report a recoverable structural problem.

    Returns True if the caller should recover and continue, False if it should
    raise its own exception (which keeps the existing error messages and types
    for direct API use). Raises ParsingError when parsing with
    raise_parse_warnings=True. """

    state = getattr(_parse_state, 'raise_parse_warnings', None)
    if state is None:
        return False
    if state:
        raise pynmrstar.exceptions.ParsingError(message)
    logger.warning(message)
    return True
