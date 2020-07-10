import decimal
import logging
import os
import sys
from datetime import date
from gzip import GzipFile
from io import StringIO, BytesIO
from typing import Dict, Union, IO
from urllib.request import urlopen

from pynmrstar import definitions

__version__: str = "3.0.6"


def _build_extension() -> bool:
    """ Try to compile the c extension. """
    import subprocess

    cur_dir = os.getcwd()
    try:
        src_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)))
        os.chdir(os.path.join(src_dir, '..', "c"))

        # Use the appropriate build command
        process = subprocess.Popen(['make', 'python3'], stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        stdout, stderr = process.communicate()
        ret_code = process.poll()
        # The make command exited with a non-zero status
        if ret_code:
            logging.warning('Compiling cnmrstar failed with error code %s and stderr: %s', ret_code, stderr)
            return False

        # We were able to build the extension?
        return True
    except OSError:
        # There was an error going into the c dir
        logging.warning('Could not find a directory with c source code.')
        return False
    finally:
        # Go back to the directory we were in before exiting
        os.chdir(cur_dir)


def _get_cnmrstar() -> Union[None, object]:
    """ Returns the cnmrstar module, or returns None if it isn't available. """

    # First see if it's installed via pip
    try:
        import cnmrstar
        logging.debug('Imported cnmrstar via installed package.')
        return cnmrstar
    except ImportError:

        # See if it is compiled locally
        try:
            import pynmrstar.cnmrstar as cnmrstar
            logging.debug('Imported cnmrstar from locally compiled file.')

            if "version" not in dir(cnmrstar) or cnmrstar.version() < "2.2.8":
                logging.warning("Recompiling cnmrstar module due to API changes. You may experience a segmentation "
                                "fault immediately following this message but should have no issues the next time you "
                                "run your script or this program.")
                _build_extension()
                sys.exit(0)

            return cnmrstar

        except ImportError:

            # Try to compile cnmrstar, but check for the 'no c module' file before continuing
            if not os.path.isfile(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".nocompile")):
                logging.info('Compiling local cnmrstar module...')

                if _build_extension():
                    try:
                        import pynmrstar.cnmrstar as cnmrstar
                        logging.debug('Imported cnmrstar from locally compiled file.')
                        return cnmrstar
                    except ImportError:
                        return
            else:
                logging.debug("Not compiling cnmrstar due to presence of '.nocompile' file")
                return


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
            comment_entry = Entry.from_file(_interpret_file(definitions.COMMENT_URL))
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
            with urlopen(the_file) as url_data:
                buffer = BytesIO(url_data.read())
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
    return StringIO(buffer.read().decode())
