""" Exceptions defined by PyNMR-STAR. """


class ParsingError(ValueError):
    """ Indicates that something went wrong when parsing NMR-STAR data.
    A line number on which the exception occurred will be provided if
    possible. """

    def __init__(self, message, line_number: int = None):
        Exception.__init__(self)
        self.message = message
        self.line_number = line_number

    def __repr__(self) -> str:
        if self.line_number is not None:
            return f'ParsingError("{self.message}") on line {self.line_number}'
        else:
            return f'ParsingError("{self.message}")'

    def __str__(self) -> str:
        if self.line_number is not None:
            return f"{self.message} Error detected on line {self.line_number}."
        else:
            return self.message


class InvalidStateError(ValueError):
    """ Indicates that the data as exists in the PyNMRSTAR objects is not
    consistent with the NMR-STAR format or dictionary. This often means that
    internal PyNMRSTAR attributes were modified directly rather than using the
    appropriate getters/setters, since the library attempts to prevent actions
    which would lead to such states. """

    def __init__(self, message):
        Exception.__init__(self)
        self.message = message

    def __repr__(self) -> str:
        return f'InvalidStateError("{self.message}")'

    def __str__(self) -> str:
        return self.message

