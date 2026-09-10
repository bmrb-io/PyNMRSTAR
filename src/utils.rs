use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use memchr::memchr_iter;

pub const RESERVED_KEYWORDS: [&str; 5] = ["data_", "save_", "loop_", "stop_", "global_"];

/// Fix multiline semicolon values where content appears on the same line as the semicolon.
/// Transforms patterns like `\n;content\n` to `\n;\ncontent\n`.
/// This is equivalent to the regex: `\n;([^\n]+?)\n` -> `\n;\n$1\n`
pub fn fix_multiline_semicolons(data: &str) -> String {
    let bytes = data.as_bytes();
    let len = bytes.len();

    // Quick check: if no semicolons exist, return as-is
    if memchr::memchr(b';', bytes).is_none() {
        return data.to_string();
    }

    let mut result = String::with_capacity(len + 64);
    let mut last_end = 0;

    // Find all newlines and check if pattern `\n;[^\n]+\n` follows
    for nl_pos in memchr_iter(b'\n', bytes) {
        // Check if we have `\n;` pattern (need at least 2 more chars: ; and something)
        if nl_pos + 2 < len && bytes[nl_pos + 1] == b';' {
            let after_semi = nl_pos + 2;
            // Check if next char is NOT a newline (meaning there's content on same line)
            if bytes[after_semi] != b'\n' {
                // Find the next newline after the semicolon
                if memchr::memchr(b'\n', &bytes[after_semi..]).is_some() {
                    // We found the pattern: \n;[content]\n
                    // Copy everything up to and including \n;
                    result.push_str(&data[last_end..after_semi]);
                    // Insert the extra newline
                    result.push('\n');
                    // Update position to continue from the content
                    last_end = after_semi;
                }
            }
        }
    }

    // Append remaining data
    result.push_str(&data[last_end..]);
    result
}

pub fn is_reserved_keyword(token: &str) -> bool {
    RESERVED_KEYWORDS.iter().any(|&kw| token.eq_ignore_ascii_case(kw))
}

pub fn starts_with_ignore_case(s: &str, prefix: &str) -> bool {
    // For ASCII-only prefixes, we can safely check byte-by-byte
    if s.len() < prefix.len() {
        return false;
    }

    let s_bytes = s.as_bytes();
    let prefix_bytes = prefix.as_bytes();

    for i in 0..prefix.len() {
        if !s_bytes[i].eq_ignore_ascii_case(&prefix_bytes[i]) {
            return false;
        }
    }
    true
}

#[pyfunction]
#[pyo3(signature = (orig, str_conversion_dict=None))]
pub fn quote_value(orig: &Bound<PyAny>, str_conversion_dict: Option<&Bound<'_, PyAny>>) -> PyResult<String> {
    // Apply STR_CONVERSION_DICT if provided
    let converted: std::borrow::Cow<'_, Bound<'_, PyAny>> = if let Some(conv_dict) = str_conversion_dict {
        if conv_dict.contains(orig)? {
            std::borrow::Cow::Owned(conv_dict.get_item(orig)?)
        } else {
            std::borrow::Cow::Borrowed(orig)
        }
    } else {
        std::borrow::Cow::Borrowed(orig)
    };

    // Convert to string
    let str_obj = converted.str()?;
    let s = str_obj.to_str()?;

    // Don't allow empty string
    if s.is_empty() {
        return Err(PyValueError::new_err("Empty strings are not allowed as values. Use the None singleton, or '.' to represent null values."));
    }

    // Delegate to the internal implementation
    Ok(quote_value_str(s))
}

/// Internal function to quote a value for NMR-STAR format.
/// This is a simpler version that takes a string directly.
pub fn quote_value_str(s: &str) -> String {
    // Don't allow empty string - return as-is, caller handles this error
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
/// writing the value lets the formatters measure and write values without allocating a
/// quoted copy of each one.
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
            // Handle embedded STAR format multiline comments
            if s.contains("\n;") {
                return Quoting::Embedded;
            }
            return if s.ends_with('\n') { Quoting::Multiline } else { Quoting::MultilineAppendNewline };
        }

        let has_single = flags & QF_SINGLE_QUOTE != 0;
        let has_double = flags & QF_DOUBLE_QUOTE != 0;

        // If it has both single and double quotes, it can only be wrapped in a quote which
        //  is never followed by whitespace within the value
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
                // Must use multiline format
                Quoting::MultilineAppendNewline
            };
        }

        // Check if we need wrapping: a leading character with special meaning, a
        //  reserved keyword prefix, or whitespace anywhere
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

    /// Whether the quoted value spans lines, and so must be written as a semicolon-delimited value.
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
    s.chars().next().map_or(false, |c| c.is_whitespace())
}
