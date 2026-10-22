//! Helpers which reproduce the behaviour of Python's `str` methods. NMR-STAR is mostly ASCII,
//! but the library's checks (whitespace in names, stripping) were defined in terms of Python's
//! Unicode-aware methods, and so are reproduced exactly.

/// Whether a character is whitespace as Python's `str.isspace()` (and so `str.split()` and
/// `str.strip()`) define it. That is Unicode's White_Space property, plus the four ASCII
/// information separators (U+001C to U+001F), which Python counts and Rust does not.
pub fn is_space(c: char) -> bool {
    c.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&c)
}

/// Python's `s.split() == [s]`: the string is non-empty and contains no whitespace.
pub fn is_single_word(s: &str) -> bool {
    !s.is_empty() && !s.chars().any(is_space)
}

/// Python's `str.strip()` with no arguments.
pub fn strip(s: &str) -> &str {
    s.trim_matches(is_space)
}

/// Python's `str.lower()`.
pub fn lower(s: &str) -> String {
    if s.is_ascii() {
        s.to_ascii_lowercase()
    } else {
        s.to_lowercase()
    }
}

/// Python's `str.upper()`.
pub fn upper(s: &str) -> String {
    if s.is_ascii() {
        s.to_ascii_uppercase()
    } else {
        s.to_uppercase()
    }
}

/// Python's `str.splitlines()`: split on any line boundary, which a trailing boundary does not
/// follow with an empty line.
pub fn splitlines(s: &str) -> Vec<&str> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut chars = s.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        let boundary = matches!(c, '\n' | '\r' | '\u{0b}' | '\u{0c}' | '\u{1c}' | '\u{1d}' | '\u{1e}'
            | '\u{85}' | '\u{2028}' | '\u{2029}');
        if boundary {
            lines.push(&s[start..i]);
            let mut end = i + c.len_utf8();
            if c == '\r' {
                if let Some(&(_, '\n')) = chars.peek() {
                    chars.next();
                    end += 1;
                }
            }
            start = end;
        }
    }
    if start < s.len() {
        lines.push(&s[start..]);
    }
    lines
}

/// The number of characters (Unicode code points) in a string, which is what Python's `len()`
/// counts.
pub fn char_len(s: &str) -> usize {
    if s.is_ascii() {
        s.len()
    } else {
        s.chars().count()
    }
}

/// Python's `re.sub(r'\s+', replacement, s)`.
pub fn collapse_whitespace(s: &str, replacement: &str) -> String {
    let mut result = String::with_capacity(s.len());
    let mut in_space = false;
    for c in s.chars() {
        if is_space(c) {
            if !in_space {
                result.push_str(replacement);
                in_space = true;
            }
        } else {
            result.push(c);
            in_space = false;
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn splitlines_matches_python() {
        assert_eq!(splitlines("a\nb\r\nc\rd"), vec!["a", "b", "c", "d"]);
        assert_eq!(splitlines("a\n"), vec!["a"]);
        assert_eq!(splitlines("a\n\nb"), vec!["a", "", "b"]);
        assert_eq!(splitlines(""), Vec::<&str>::new());
    }

    #[test]
    fn whitespace_matches_python() {
        assert!(is_space('\u{1c}'));
        assert!(is_space('\u{3000}'));
        assert!(!is_space('a'));
        assert!(!is_single_word(""));
        assert!(!is_single_word("a b"));
        assert!(is_single_word("ab"));
        assert_eq!(strip("\u{1c} x \n"), "x");
    }
}
