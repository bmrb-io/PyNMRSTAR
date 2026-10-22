//! Writing loops and saveframes as NMR-STAR.

use std::borrow::Cow;

use crate::error::{Error, Result};
use crate::quoting::{Converter, Quoting};
use crate::saveframe::Tag;
use crate::value::Value;

/// Append `count` spaces.
fn push_spaces(out: &mut String, count: usize) {
    out.extend(std::iter::repeat_n(' ', count));
}

/// Format a saveframe. The loops are formatted already; the comment goes before the saveframe.
pub(crate) fn format_saveframe(name: &str, tag_prefix: &str, tags: &[Tag], formatted_loops: &[String],
                               skip_empty_tags: bool, comment: &str) -> Result<String> {
    let converter = Converter::new();
    let estimated_size = 100 + comment.len() + tags.len() * (tag_prefix.len() + 50)
        + formatted_loops.iter().map(|s| s.len()).sum::<usize>();
    let mut result = String::with_capacity(estimated_size);

    result.push_str(comment);
    result.push_str("save_");
    result.push_str(name);
    result.push('\n');

    let max_width = tags.iter().map(|tag| tag_prefix.len() + 1 + tag.name.len()).max().unwrap_or(0);

    for tag in tags {
        if skip_empty_tags && tag.value.is_null_value() {
            continue;
        }
        let string_val = converter.convert(&tag.value);
        if string_val.is_empty() {
            return Err(Error::invalid_state(format!(
                "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please \
                 either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] \
                 = None. Saveframe: {} Tag: {}", name, tag.name)));
        }
        let quoting = Quoting::of(&string_val);

        result.push_str("   ");
        result.push_str(tag_prefix);
        result.push('.');
        result.push_str(&tag.name);
        if quoting.is_multiline() {
            result.push_str("\n;\n");
            quoting.write(&string_val, &mut result);
            result.push_str(";\n");
        } else {
            let formatted_tag_len = tag_prefix.len() + 1 + tag.name.len();
            push_spaces(&mut result, max_width.saturating_sub(formatted_tag_len) + 2);
            quoting.write(&string_val, &mut result);
            result.push('\n');
        }
    }

    for loop_str in formatted_loops {
        result.push_str(loop_str);
    }
    result.push_str("\nsave_\n");
    Ok(result)
}

/// Format a loop.
pub(crate) fn format_loop(tags: &[String], category: &str, data: &[Vec<Value>], skip_empty_loops: bool) -> Result<String> {
    if data.is_empty() {
        if skip_empty_loops {
            return Ok(String::new());
        } else if tags.is_empty() {
            return Ok("\n   loop_\n\n   stop_\n".to_string());
        }
    }
    if tags.is_empty() {
        return Err(Error::invalid_state(format!(
            "Impossible to print data if there are no associated tags. Error in loop '{}' which contains data but \
             hasn't had any tags added.", category)));
    }

    let mut header = String::with_capacity(100 + tags.len() * (category.len() + 8));
    header.push_str("\n   loop_\n");
    for tag in tags {
        header.push_str("      ");
        header.push_str(category);
        header.push('.');
        header.push_str(tag);
        header.push('\n');
    }
    header.push('\n');

    if data.is_empty() {
        header.push_str("\n   stop_\n");
        return Ok(header);
    }

    // First pass: convert every value to text, determine how it must be quoted, and track the
    //  column widths
    let converter = Converter::new();
    let num_cols = tags.len();
    let mut widths = vec![4usize; num_cols];
    let mut multiline_size = 0;
    let mut converted: Vec<(Cow<str>, Quoting)> = Vec::with_capacity(data.len() * num_cols);
    for (row_idx, row) in data.iter().enumerate() {
        if row.len() != num_cols {
            return Err(Error::invalid_state(format!(
                "The number of tags must match the width of the data. Error in loop '{}'. In this case, there are {} \
                 tags, and row number {} has {} tags.", category, num_cols, row_idx, row.len())));
        }
        for (col_idx, value) in row.iter().enumerate() {
            // A value the same as the one above it is already measured
            if let Some(above) = converted.len().checked_sub(num_cols) {
                if let (Value::Str(a), Value::Str(b)) = (&data[row_idx - 1][col_idx], value) {
                    if std::ptr::eq(a.as_str(), b.as_str()) || a == b {
                        let copy = converted[above].clone();
                        converted.push(copy);
                        continue;
                    }
                }
            }
            let string_val = converter.convert(value);
            if string_val.is_empty() {
                return Err(Error::invalid_state(format!(
                    "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. \
                     Please either replace the empty strings with None objects, or set \
                     pynmrstar.definitions.STR_CONVERSION_DICT[''] = None.\nLoop: {} Row: {} Column: {}",
                    category, row_idx, col_idx)));
            }
            let quoting = Quoting::of(&string_val);
            if quoting.is_multiline() {
                multiline_size += quoting.quoted_len(&string_val) + 5;
            } else {
                let width = quoting.quoted_len(&string_val) + 3;
                if width > widths[col_idx] {
                    widths[col_idx] = width;
                }
            }
            converted.push((string_val, quoting));
        }
    }

    // Second pass: print the data rows
    let row_size = 6 + widths.iter().sum::<usize>();
    let mut result = String::with_capacity(header.len() + data.len() * row_size + multiline_size + 16);
    result.push_str(&header);

    if multiline_size == 0 {
        // Every row is then the same width, and each value is at its column's offset
        let offsets: Vec<usize> = widths.iter().scan(5, |pos, width| {
            let offset = *pos;
            *pos += width;
            Some(offset)
        }).collect();
        let mut out = result.into_bytes();
        for row in converted.chunks_exact(num_cols) {
            let start = out.len();
            out.resize(start + row_size, b' ');
            out[start + row_size - 1] = b'\n';
            let line = &mut out[start..];
            for ((value, quoting), offset) in row.iter().zip(&offsets) {
                quoting.write_into(value, &mut line[*offset..]);
            }
        }
        result = String::from_utf8(out).expect("only whole strings and ASCII were written");
    } else {
        for row in converted.chunks_exact(num_cols) {
            result.push_str("     ");
            for ((value, quoting), width) in row.iter().zip(&widths) {
                if quoting.is_multiline() {
                    result.push_str("\n;\n");
                    quoting.write(value, &mut result);
                    result.push_str(";\n");
                } else {
                    quoting.write(value, &mut result);
                    push_spaces(&mut result, width - quoting.quoted_len(value));
                }
            }
            result.push('\n');
        }
    }

    result.push_str("\n   stop_\n");
    Ok(result)
}
