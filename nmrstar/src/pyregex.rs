//! The dictionary's value types are Python regular expressions. Rust's `regex` crate reads
//! nearly the same syntax, with a few differences this translates away:
//!
//! * In a character class, `[`, `&&`, `--` and `~~` have special meanings in Rust, where
//!   Python reads them literally. Python also allows `]` as the first character of a class.
//! * Python allows escaping a space (`\ `); Rust does not.
//! * Python's `$` matches at the end of the text *or before a newline which ends it*. Rust's
//!   only matches at the very end, so `$` becomes `\n?\z` - which is only equivalent where the
//!   pattern is matched against the whole text, which is the only way these are used.

use regex::Regex;

/// Translate a Python regular expression into one with the same meaning for the `regex` crate.
pub fn translate(pattern: &str) -> String {
    let mut out = String::with_capacity(pattern.len() + 16);
    let chars: Vec<char> = pattern.chars().collect();
    let mut i = 0;
    let mut in_class = false;
    // The number of characters of the class seen so far, to recognize a leading ']'
    let mut class_position = 0;
    let mut previous_in_class: Option<char> = None;

    while i < chars.len() {
        let c = chars[i];
        if c == '\\' && i + 1 < chars.len() {
            let next = chars[i + 1];
            if next == ' ' {
                out.push(' ');
            } else {
                out.push('\\');
                out.push(next);
            }
            if in_class {
                class_position += 1;
                previous_in_class = Some('\\');
            }
            i += 2;
            continue;
        }
        if in_class {
            match c {
                '^' if class_position == 0 => {
                    out.push('^');
                    i += 1;
                    continue;
                }
                ']' if class_position == 0 => out.push_str("\\]"),
                ']' => {
                    out.push(']');
                    in_class = false;
                }
                '[' | '&' | '~' => {
                    out.push('\\');
                    out.push(c);
                }
                '-' if previous_in_class == Some('-') => out.push_str("\\-"),
                _ => out.push(c),
            }
            class_position += 1;
            previous_in_class = Some(c);
        } else {
            match c {
                '[' => {
                    out.push('[');
                    in_class = true;
                    class_position = 0;
                    previous_in_class = None;
                }
                '$' => out.push_str(r"(?:\n?\z)"),
                _ => out.push(c),
            }
        }
        i += 1;
    }
    out
}

/// Compile a Python regular expression, anchored at both ends as Python's `re.fullmatch()`
/// (or `re.match('^...$')`) would apply it.
pub fn compile_full(pattern: &str) -> Result<Regex, regex::Error> {
    Regex::new(&format!(r"^(?:{})(?:\n?\z)", translate(pattern)))
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn translates_python_classes() {
        let name = compile_full(r"_[_A-Za-z0-9]+\.[][_A-Za-z0-9%-]+").unwrap();
        assert!(name.is_match("_Tag.na[me]"));
        let code = compile_full(r#"[_,.;:"&<>()/\{}'`~!@#$%A-Za-z0-9*|+-]*"#).unwrap();
        assert!(code.is_match("a&b~c"));
        assert!(!code.is_match("a b"));
        assert!(code.is_match("abc\n"));
        assert!(compile_full(r"\n--X--\n\ [][ \n\t]*\ \n--Y----").is_ok());
    }
}
