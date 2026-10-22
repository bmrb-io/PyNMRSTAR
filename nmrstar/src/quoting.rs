//! Quoting values for NMR-STAR, and converting values to the text they are written as.

use std::borrow::Cow;

use memchr::memchr_iter;

use crate::definitions;
use crate::value::Value;

pub const RESERVED_KEYWORDS: [&str; 5] = ["data_", "save_", "loop_", "stop_", "global_"];

pub fn is_reserved_keyword(token: &str) -> bool {
    RESERVED_KEYWORDS.iter().any(|&kw| token.eq_ignore_ascii_case(kw))
}

pub fn starts_with_ignore_case(s: &str, prefix: &str) -> bool {
    s.len() >= prefix.len() && s.as_bytes()[..prefix.len()].eq_ignore_ascii_case(prefix.as_bytes())
}

/// Converts values to the text which represents them, applying the conversion table of
/// [`definitions::str_conversion`]. A snapshot of the table is taken when it is created.
pub(crate) struct Converter {
    /// None when the table is the default (`None -> "."`)
    table: Option<Vec<(Value, String)>>,
}

impl Converter {
    pub fn new() -> Converter {
        if definitions::str_conversion_is_default() {
            Converter { table: None }
        } else {
            let table = definitions::str_conversion().into_iter()
                .map(|(from, to)| (from, to.to_py_string().into_owned()))
                .collect();
            Converter { table: Some(table) }
        }
    }

    /// The text a value is written as. A null value which the table does not convert is
    /// written as `.`.
    pub fn convert<'a>(&'a self, value: &'a Value) -> Cow<'a, str> {
        match &self.table {
            None => match value {
                Value::Null => Cow::Borrowed("."),
                _ => value.to_py_string(),
            },
            Some(table) => {
                if let Some((_, to)) = table.iter().find(|(from, _)| from == value) {
                    return Cow::Borrowed(to);
                }
                match value {
                    Value::Null => Cow::Borrowed("."),
                    _ => value.to_py_string(),
                }
            }
        }
    }

    /// As [`Converter::convert`], but a null value which the table does not convert is `None`,
    /// as Python's `str(None)` gives.
    pub fn convert_plain<'a>(&'a self, value: &'a Value) -> Cow<'a, str> {
        let table = match &self.table {
            None => return match value {
                Value::Null => Cow::Borrowed("."),
                _ => value.to_py_string(),
            },
            Some(table) => table,
        };
        match table.iter().find(|(from, _)| from == value) {
            Some((_, to)) => Cow::Borrowed(to),
            None => value.to_py_string(),
        }
    }
}

/// Fix multiline semicolon values where content appears on the same line as the semicolon.
/// Transforms patterns like `\n;content\n` to `\n;\ncontent\n`.
///
/// Returns the rewritten data along with the line numbers, *in the rewritten data*, of each line
/// a break was inserted after. Every inserted break pushes the rest of the file down a line, so
/// anything reporting a position has to undo that before naming a line of the file the user has.
pub fn fix_multiline_semicolons(data: Cow<'_, str>) -> (Cow<'_, str>, Vec<usize>) {
    let bytes = data.as_bytes();
    let len = bytes.len();

    if memchr::memchr(b';', bytes).is_none() {
        return (data, Vec::new());
    }

    // Only allocated once a newline needs inserting, as most files need none
    let mut result: Option<String> = None;
    let mut last_end = 0;
    let mut inserted_lines: Vec<usize> = Vec::new();

    for (newline_count, nl_pos) in memchr_iter(b'\n', bytes).enumerate() {
        if nl_pos + 2 < len && bytes[nl_pos + 1] == b';' {
            let after_semi = nl_pos + 2;
            if bytes[after_semi] != b'\n' && memchr::memchr(b'\n', &bytes[after_semi..]).is_some() {
                let result = result.get_or_insert_with(|| String::with_capacity(len + 64));
                result.push_str(&data[last_end..after_semi]);
                result.push('\n');
                // The semicolon sits on the line after the newlines seen so far, plus one line
                // for each break already inserted above it
                inserted_lines.push(newline_count + 2 + inserted_lines.len());
                last_end = after_semi;
            }
        }
    }

    match result {
        None => (data, inserted_lines),
        Some(mut result) => {
            result.push_str(&data[last_end..]);
            (Cow::Owned(result), inserted_lines)
        }
    }
}

/// Quote a (non-empty) string for NMR-STAR. An empty string is returned unchanged.
pub fn quote_str(s: &str) -> String {
    if s.is_empty() {
        return String::new();
    }
    let quoting = Quoting::of(s);
    let mut result = String::with_capacity(quoting.quoted_len(s));
    quoting.write(s, &mut result);
    result
}

// Byte flags used to classify a value for quoting in a single pass
const QF_NEWLINE: u8 = 1;
const QF_SINGLE_QUOTE: u8 = 2;
const QF_DOUBLE_QUOTE: u8 = 4;
/// ASCII whitespace, as recognized by char::is_whitespace()
const QF_WHITESPACE: u8 = 8;
/// A non-ASCII byte - the value may contain Unicode whitespace
const QF_NON_ASCII: u8 = 16;

static QUOTE_FLAGS: [u8; 256] = {
    let mut table = [0u8; 256];
    table[b'\n' as usize] = QF_NEWLINE | QF_WHITESPACE;
    table[b'\'' as usize] = QF_SINGLE_QUOTE;
    table[b'"' as usize] = QF_DOUBLE_QUOTE;
    table[b' ' as usize] = QF_WHITESPACE;
    table[b'\t' as usize] = QF_WHITESPACE;
    table[b'\r' as usize] = QF_WHITESPACE;
    table[0x0B] = QF_WHITESPACE;
    table[0x0C] = QF_WHITESPACE;
    let mut i = 128;
    while i < 256 {
        table[i] = QF_NON_ASCII;
        i += 1;
    }
    table
};

/// How a (non-empty) value must be written in NMR-STAR. Determining this separately from
/// writing the value lets the formatters measure and write values without allocating a quoted
/// copy of each one.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Quoting {
    /// Written as-is
    Bare,
    /// Wrapped in single quotes
    Single,
    /// Wrapped in double quotes
    Double,
    /// A multi-line value which already ends with a newline, written as-is
    Multiline,
    /// A multi-line value, written with a newline appended
    MultilineAppendNewline,
    /// A value containing embedded STAR ("\n;"): every line is indented by three spaces
    Embedded,
}

impl Quoting {
    /// Determine how a non-empty value must be quoted.
    pub fn of(s: &str) -> Quoting {
        let bytes = s.as_bytes();
        let mut flags = 0u8;
        for &b in bytes {
            flags |= QUOTE_FLAGS[b as usize];
        }

        if flags & QF_NEWLINE != 0 {
            if s.contains("\n;") {
                return Quoting::Embedded;
            }
            return if s.ends_with('\n') { Quoting::Multiline } else { Quoting::MultilineAppendNewline };
        }

        let has_single = flags & QF_SINGLE_QUOTE != 0;
        let has_double = flags & QF_DOUBLE_QUOTE != 0;

        // If it has both single and double quotes, it can only be wrapped in a quote which is
        //  never followed by whitespace within the value
        if has_single && has_double {
            let mut can_wrap_single = true;
            let mut can_wrap_double = true;
            for (i, &b) in bytes.iter().enumerate() {
                if (b == b'\'' || b == b'"') && i + 1 < bytes.len() && starts_with_whitespace(&s[i + 1..]) {
                    if b == b'\'' {
                        can_wrap_single = false;
                    } else {
                        can_wrap_double = false;
                    }
                }
            }

            return if can_wrap_single {
                Quoting::Single
            } else if can_wrap_double {
                Quoting::Double
            } else {
                Quoting::MultilineAppendNewline
            };
        }

        // Check if we need wrapping: a leading character with special meaning, a reserved
        //  keyword prefix, or whitespace anywhere
        let needs_wrapping = matches!(bytes[0], b'_' | b'"' | b'\'' | b'#')
            || (matches!(bytes[0] | 0x20, b'd' | b's' | b'l' | b'g')
                && RESERVED_KEYWORDS.iter().any(|kw| starts_with_ignore_case(s, kw)))
            || flags & QF_WHITESPACE != 0
            || (flags & QF_NON_ASCII != 0 && s.chars().any(|c| c.is_whitespace()));

        if needs_wrapping {
            if has_single { Quoting::Double } else { Quoting::Single }
        } else {
            Quoting::Bare
        }
    }

    /// Whether the quoted value spans lines, and so must be written as a semicolon-delimited
    /// value.
    pub fn is_multiline(self) -> bool {
        matches!(self, Quoting::Multiline | Quoting::MultilineAppendNewline | Quoting::Embedded)
    }

    /// The length in bytes of the value once quoted.
    pub fn quoted_len(self, s: &str) -> usize {
        match self {
            Quoting::Bare | Quoting::Multiline => s.len(),
            Quoting::Single | Quoting::Double => s.len() + 2,
            Quoting::MultilineAppendNewline => s.len() + 1,
            Quoting::Embedded => {
                let prefix = if s.starts_with('\n') { 0 } else { 4 };
                prefix + s.len() + memchr_iter(b'\n', s.as_bytes()).count() * 3 + 1
            }
        }
    }

    /// Write the quoted value of a single-line value to the start of `out`.
    pub fn write_into(self, s: &str, out: &mut [u8]) {
        let s = s.as_bytes();
        match self {
            Quoting::Single | Quoting::Double => {
                let quote = if self == Quoting::Single { b'\'' } else { b'"' };
                out[0] = quote;
                out[1..=s.len()].copy_from_slice(s);
                out[s.len() + 1] = quote;
            }
            _ => out[..s.len()].copy_from_slice(s),
        }
    }

    /// Append the quoted value to the output.
    pub fn write(self, s: &str, out: &mut String) {
        match self {
            Quoting::Bare | Quoting::Multiline => out.push_str(s),
            Quoting::Single => {
                out.push('\'');
                out.push_str(s);
                out.push('\'');
            }
            Quoting::Double => {
                out.push('"');
                out.push_str(s);
                out.push('"');
            }
            Quoting::MultilineAppendNewline => {
                out.push_str(s);
                out.push('\n');
            }
            Quoting::Embedded => {
                if !s.starts_with('\n') {
                    out.push_str("\n   ");
                }
                let mut last_end = 0;
                for i in memchr_iter(b'\n', s.as_bytes()) {
                    out.push_str(&s[last_end..=i]);
                    out.push_str("   ");
                    last_end = i + 1;
                }
                out.push_str(&s[last_end..]);
                out.push('\n');
            }
        }
    }
}

/// Whether the string begins with a (Unicode) whitespace character.
fn starts_with_whitespace(s: &str) -> bool {
    s.chars().next().is_some_and(|c| c.is_whitespace())
}
