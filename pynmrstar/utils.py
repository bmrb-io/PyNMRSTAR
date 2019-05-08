import json

from pynmrstar import STR_CONVERSION_DICT, cnmrstar, _WHITESPACE, _API_URL, _interpret_file, Entry


def format_tag(value):
    """Strips anything before the '.'"""

    if '.' in value:
        value = value[value.index('.')+1:]
    return value


def format_category(value):
    """Adds a '_' to the front of a tag (if not present) and strips out
    anything after a '.'"""

    if value:
        if not value.startswith("_"):
            value = "_" + value
        if "." in value:
            value = value[:value.index(".")]
    return value


def clean_value(value):
    """Automatically quotes the value in the appropriate way. Don't
    quote values you send to this method or they will show up in
    another set of quotes as part of the actual data. E.g.:

    clean_value('"e. coli"') returns '\'"e. coli"\''

    while

    clean_value("e. coli") returns "'e. coli'"

    This will automatically be called on all values when you use a str()
    method (so don't call it before inserting values into tags or loops).

    Be mindful of the value of STR_CONVERSION_DICT as it will effect the
    way the value is converted to a string.

    """

    # Allow manual specification of conversions for booleans, Nones, etc.
    if value in STR_CONVERSION_DICT:
        if any(isinstance(value, type(x)) for x in STR_CONVERSION_DICT):
            value = STR_CONVERSION_DICT[value]

    # Use the fast code if it is available
    if cnmrstar is not None:
        # It's faster to assume we are working with a string and catch
        #  errors than to check the instance for every object and convert
        try:
            return cnmrstar.clean_value(value)
        except (ValueError, TypeError):
            return cnmrstar.clean_value(str(value))

    # Convert non-string types to string
    if not isinstance(value, str):
        value = str(value)

    # If it is a STAR-format multiline comment already, we need to escape it
    if "\n;" in value:
        value = value.replace("\n", "\n   ")
        if value[-1] != "\n":
            value = value + "\n"
        if value[0] != "\n":
            value = "\n   " + value
        return value

    # If it's going on it's own line, don't touch it
    if "\n" in value:
        if value[-1] != "\n":
            return value + "\n"
        return value

    if value == "":
        raise ValueError("Empty strings are not allowed as values. "
                         "Use a '.' or a '?' if needed.")

    # If it has single and double quotes it will need to go on its
    #  own line under certain conditions...
    if '"' in value and "'" in value:
        can_wrap_single = True
        can_wrap_double = True

        for pos, char in enumerate(value):
            next_char = value[pos+1:pos+2]

            if next_char != "" and next_char in _WHITESPACE:
                if char == "'":
                    can_wrap_single = False
                if char == '"':
                    can_wrap_double = False

        if not can_wrap_single and not can_wrap_double:
            return '%s\n' % value
        elif can_wrap_single:
            return "'%s'" % value
        elif can_wrap_double:
            return '"%s"' % value

    # Check for special characters in a tag
    if (any(x in value for x in " \t\v#") or
            any(value.startswith(x) for x in
                ["data_", "save_", "loop_", "stop_", "_"])):
        # If there is a single quote wrap in double quotes
        if "'" in value:
            return '"%s"' % value
        # Either there is a double quote or no quotes
        else:
            return "'%s'" % value

    # Quote if necessary
    if value[0] == "'":
        return '"' + value + '"'
    if value[0] == '"':
        return "'" + value + "'"

    # It's good to go
    return value


def iter_entries(metabolomics=False):
    """ Returns a generator that will yield an Entry object for every
        macromolecule entry in the current BMRB database. Perfect for performing
        an operation across the entire BMRB database. Set `metabolomics=True`
        in order to get all the entries in the metabolomics database."""

    api_url = "%s/list_entries?database=macromolecules" % _API_URL
    if metabolomics:
        api_url = "%s/list_entries?database=metabolomics" % _API_URL

    for entry in json.loads(_interpret_file(api_url).read()):
        yield Entry.from_database(entry)
