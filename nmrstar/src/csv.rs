//! Reading and writing CSV as Python's `csv` module does with its default ("excel") dialect.

use std::collections::HashMap;
use std::iter::Peekable;
use std::str::Chars;

use crate::value::Value;

/// The rows of CSV text, read one at a time. A blank line is an empty row, as Python's reader
/// yields it.
pub struct Rows<'a> {
    chars: Peekable<Chars<'a>>,
}

impl Iterator for Rows<'_> {
    type Item = Vec<String>;

    fn next(&mut self) -> Option<Vec<String>> {
        self.chars.peek()?;
        let mut row: Vec<String> = Vec::new();
        let mut field = String::new();
        let mut in_quotes = false;
        // Whether the current field has begun (so a quote is literal)
        let mut field_started = false;
        // Whether anything at all has been read for this row
        let mut in_row = false;

        while let Some(c) = self.chars.next() {
            if in_quotes {
                if c == '"' {
                    if self.chars.peek() == Some(&'"') {
                        self.chars.next();
                        field.push('"');
                    } else {
                        in_quotes = false;
                    }
                } else {
                    field.push(c);
                }
                continue;
            }
            match c {
                '"' if !field_started => {
                    in_quotes = true;
                    field_started = true;
                    in_row = true;
                }
                ',' => {
                    row.push(std::mem::take(&mut field));
                    field_started = false;
                    in_row = true;
                }
                '\r' | '\n' => {
                    if c == '\r' && self.chars.peek() == Some(&'\n') {
                        self.chars.next();
                    }
                    if in_row {
                        row.push(field);
                    }
                    return Some(row);
                }
                _ => {
                    field.push(c);
                    field_started = true;
                    in_row = true;
                }
            }
        }
        if in_row {
            row.push(field);
        }
        Some(row)
    }
}

/// Read CSV text as rows.
pub fn rows(text: &str) -> Rows<'_> {
    Rows { chars: text.chars().peekable() }
}

/// Parse CSV text into rows.
pub fn read(text: &str) -> Vec<Vec<String>> {
    rows(text).collect()
}

/// Python's `csv.DictReader`: each row after the first as a map from the first row's names. A
/// short row's missing fields are absent (Python gives `None`); blank rows are skipped. Where a
/// name repeats, the last column of that name wins.
pub fn dicts(text: &str) -> impl Iterator<Item = HashMap<String, String>> + '_ {
    let mut rows = rows(text);
    let header = rows.next().unwrap_or_default();
    rows.filter(|row| !row.is_empty())
        .map(move |row| header.iter().cloned().zip(row).collect())
}

/// Write rows of values as CSV, with newline line endings.
pub fn write(rows: &[Vec<Value>]) -> String {
    let mut out = String::new();
    for row in rows {
        let fields: Vec<String> = row.iter().map(|value| match value {
            Value::Null => String::new(),
            _ => value.to_py_string().into_owned(),
        }).collect();
        let single = fields.len() == 1;
        for (i, field) in fields.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            if field.contains([',', '"', '\r', '\n']) || (single && field.is_empty()) {
                out.push('"');
                out.push_str(&field.replace('"', "\"\""));
                out.push('"');
            } else {
                out.push_str(field);
            }
        }
        out.push('\n');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_like_python() {
        assert_eq!(read("a,b\n\"c,d\",\"e\"\"f\"\n\nx"),
                   vec![vec!["a", "b"], vec!["c,d", "e\"f"], vec![], vec!["x"]]);
        assert_eq!(read("a,\n"), vec![vec!["a", ""]]);
        assert_eq!(read("\"multi\nline\",b\r\n"), vec![vec!["multi\nline", "b"]]);
        assert_eq!(read("\"\"\n"), vec![vec![""]]);
    }
}
