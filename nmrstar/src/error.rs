//! The errors the library reports.
//!
//! They mirror the exceptions PyNMR-STAR raised, so that each carries the same meaning: a
//! [`Error::Parsing`] for a file which is not valid NMR-STAR, a [`Error::InvalidState`] for objects
//! which can not be written as NMR-STAR, [`Error::Value`] for an invalid argument, and
//! [`Error::Key`] and [`Error::Index`] for something which was asked for and does not exist. As
//! in Python, parsing and invalid-state errors are kinds of value error: see
//! [`Error::is_value_error`].

use std::fmt;

#[derive(Clone, Debug, PartialEq)]
pub enum Error {
    /// The data is not valid NMR-STAR. Names the line the problem was found on, where that is
    /// known.
    Parsing { message: String, line_number: Option<usize> },
    /// The objects are not in a state which can be written as NMR-STAR, or are inconsistent with
    /// the dictionary.
    InvalidState(String),
    /// An invalid value or argument (Python's `ValueError`).
    Value(String),
    /// Something looked up by name does not exist (Python's `KeyError`).
    Key(String),
    /// Something looked up by position does not exist (Python's `IndexError`).
    Index(String),
    /// A value is of a type which does not support the operation (Python's `TypeError`).
    Type(String),
    /// Reading or writing a file, or fetching one over the network, failed (Python's `IOError`).
    Io(String),
}

impl Error {
    pub(crate) fn parsing(message: impl Into<String>, line_number: Option<usize>) -> Error {
        Error::Parsing { message: message.into(), line_number }
    }

    pub(crate) fn value(message: impl Into<String>) -> Error {
        Error::Value(message.into())
    }

    pub(crate) fn key(message: impl Into<String>) -> Error {
        Error::Key(message.into())
    }

    pub(crate) fn invalid_state(message: impl Into<String>) -> Error {
        Error::InvalidState(message.into())
    }

    /// Whether this would have been a `ValueError` (or a subclass of it) in PyNMR-STAR: a value,
    /// parsing, or invalid state error.
    pub fn is_value_error(&self) -> bool {
        matches!(self, Error::Value(_) | Error::Parsing { .. } | Error::InvalidState(_))
    }

    /// Whether this is a parsing error.
    pub fn is_parsing_error(&self) -> bool {
        matches!(self, Error::Parsing { .. })
    }

    /// The line on which a parsing error was detected, if known.
    pub fn line_number(&self) -> Option<usize> {
        match self {
            Error::Parsing { line_number, .. } => *line_number,
            _ => None,
        }
    }

    /// The message, without the line number a parsing error appends to it when displayed.
    pub fn message(&self) -> &str {
        match self {
            Error::Parsing { message, .. } => message,
            Error::InvalidState(message) | Error::Value(message) | Error::Key(message)
            | Error::Index(message) | Error::Type(message) | Error::Io(message) => message,
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Parsing { message, line_number: Some(line) } => {
                write!(f, "{} Error detected on line {}.", message, line)
            }
            _ => f.write_str(self.message()),
        }
    }
}

impl std::error::Error for Error {}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Error {
        Error::Io(error.to_string())
    }
}

pub type Result<T, E = Error> = std::result::Result<T, E>;
