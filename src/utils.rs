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
/// This is a simpler version that takes a string directly, used by format_loop.
pub fn quote_value_str(s: &str) -> String {
    let len = s.len();

    // Don't allow empty string - return as-is, caller handles this error
    if len == 0 {
        return String::new();
    }

    // Handle embedded STAR format multiline comments
    if s.contains("\n;") {
        let starts_with_newline = s.starts_with('\n');
        let newline_count = s.bytes().filter(|&b| b == b'\n').count();
        let mut result = String::with_capacity(len + newline_count * 3 + 8);

        if !starts_with_newline {
            result.push_str("\n   ");
        }

        let bytes = s.as_bytes();
        let mut last_end = 0;
        for i in memchr_iter(b'\n', bytes) {
            result.push_str(&s[last_end..=i]);
            result.push_str("   ");
            last_end = i + 1;
        }
        result.push_str(&s[last_end..]);
        result.push('\n');

        return result;
    }

    // If it has newlines but not "\n;", handle multiline
    if s.contains('\n') {
        if s.ends_with('\n') {
            return s.to_string();
        } else {
            let mut result = String::with_capacity(len + 1);
            result.push_str(s);
            result.push('\n');
            return result;
        }
    }

    // Check for quotes
    let has_single = s.contains('\'');
    let has_double = s.contains('"');

    // If it has both single and double quotes, need special handling
    if has_single && has_double {
        let mut can_wrap_single = true;
        let mut can_wrap_double = true;

        let bytes = s.as_bytes();
        for i in 0..bytes.len() - 1 {
            let next = bytes[i + 1];
            let next_is_ws = matches!(next, b' ' | b'\t' | b'\x0B');
            if next_is_ws {
                match bytes[i] {
                    b'\'' => can_wrap_single = false,
                    b'"' => can_wrap_double = false,
                    _ => {}
                }
            }
        }

        if !can_wrap_single && !can_wrap_double {
            let mut result = String::with_capacity(len + 1);
            result.push_str(s);
            result.push('\n');
            return result;
        }
        if can_wrap_single {
            let mut result = String::with_capacity(len + 2);
            result.push('\'');
            result.push_str(s);
            result.push('\'');
            return result;
        }
        if can_wrap_double {
            let mut result = String::with_capacity(len + 2);
            result.push('"');
            result.push_str(s);
            result.push('"');
            return result;
        }
    }

    // Check if we need wrapping
    let mut needs_wrapping = false;

    if s.starts_with('_') || s.starts_with('"') || s.starts_with('\'') {
        needs_wrapping = true;
    }

    if !needs_wrapping {
        if starts_with_ignore_case(s, "data_") || starts_with_ignore_case(s, "save_") ||
           starts_with_ignore_case(s, "loop_") || starts_with_ignore_case(s, "stop_") ||
           starts_with_ignore_case(s, "global_") {
            needs_wrapping = true;
        }

        if !needs_wrapping {
            let bytes = s.as_bytes();
            let mut prev_is_ws = true;
            for &b in bytes {
                if matches!(b, b' ' | b'\t' | b'\x0B') {
                    needs_wrapping = true;
                    break;
                }
                if b == b'#' && prev_is_ws {
                    needs_wrapping = true;
                    break;
                }
                prev_is_ws = matches!(b, b' ' | b'\t' | b'\x0B');
            }
        }
    }

    if needs_wrapping {
        let mut result = String::with_capacity(len + 2);
        if has_single {
            result.push('"');
            result.push_str(s);
            result.push('"');
        } else {
            result.push('\'');
            result.push_str(s);
            result.push('\'');
        }
        return result;
    }

    s.to_string()
}
