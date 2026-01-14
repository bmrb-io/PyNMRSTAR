use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

use crate::utils::quote_value_str;

/// Format a saveframe in NMR-STAR format.
/// Comments are handled by Python, this focuses on the heavy lifting of tag/loop formatting.
#[pyfunction]
#[pyo3(signature = (name, tag_prefix, tags, formatted_loops, skip_empty_tags=false, str_conversion_dict=None, null_values=None))]
pub fn format_saveframe(
    _py: Python,
    name: &str,
    tag_prefix: &str,
    tags: Vec<Vec<Bound<'_, PyAny>>>,  // List of [tag_name, tag_value]
    formatted_loops: Vec<String>,
    skip_empty_tags: bool,
    str_conversion_dict: Option<&Bound<'_, PyAny>>,
    null_values: Option<&Bound<'_, PyAny>>,
) -> PyResult<String> {
    // Estimate capacity for result string
    let estimated_size = 100 + tags.len() * (tag_prefix.len() + 50)
        + formatted_loops.iter().map(|s| s.len()).sum::<usize>();
    let mut result = String::with_capacity(estimated_size);

    // Print the saveframe header
    result.push_str("save_");
    result.push_str(name);
    result.push('\n');

    // Print the tags if there are any
    if !tags.is_empty() {
        // Calculate maximum tag width for formatting
        let mut max_width = 0;
        for tag in &tags {
            if tag.is_empty() {
                continue;
            }
            let tag_name: String = tag[0].extract().unwrap_or_default();
            let full_tag_len = tag_prefix.len() + 1 + tag_name.len();
            if full_tag_len > max_width {
                max_width = full_tag_len;
            }
        }

        // Process and print each tag
        for tag in &tags {
            if tag.len() < 2 {
                continue;
            }

            let tag_name: String = tag[0].extract().unwrap_or_default();
            let tag_value = &tag[1];

            // Skip empty tags if requested
            if skip_empty_tags {
                if let Some(null_set) = null_values {
                    if null_set.contains(tag_value).unwrap_or(false) {
                        continue;
                    }
                }
            }

            // Apply STR_CONVERSION_DICT if provided
            let converted_value: std::borrow::Cow<'_, Bound<'_, PyAny>> = if let Some(conv_dict) = str_conversion_dict {
                if conv_dict.contains(tag_value)? {
                    std::borrow::Cow::Owned(conv_dict.get_item(tag_value)?)
                } else {
                    std::borrow::Cow::Borrowed(tag_value)
                }
            } else {
                std::borrow::Cow::Borrowed(tag_value)
            };

            // Convert to string
            let string_val: String = if converted_value.is_none() {
                ".".to_string()
            } else {
                converted_value.str()?.to_str()?.to_string()
            };

            // Quote the value
            let quoted = if string_val.is_empty() {
                return Err(PyValueError::new_err(format!(
                    "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] = None. Saveframe: {} Tag: {}",
                    name, tag_name
                )));
            } else {
                quote_value_str(&string_val)
            };

            // Format the tag
            let formatted_tag = format!("{}.{}", tag_prefix, tag_name);

            if quoted.contains('\n') {
                // Multiline value format
                result.push_str("   ");
                result.push_str(&formatted_tag);
                // Pad to max_width
                for _ in formatted_tag.len()..max_width {
                    result.push(' ');
                }
                result.push_str("\n;\n");
                result.push_str(&quoted);
                result.push_str(";\n");
            } else {
                // Single line format
                result.push_str("   ");
                result.push_str(&formatted_tag);
                // Pad to max_width + 2 spaces
                for _ in formatted_tag.len()..max_width {
                    result.push(' ');
                }
                result.push_str("  ");
                result.push_str(&quoted);
                result.push('\n');
            }
        }
    }

    // Append all formatted loops
    for loop_str in formatted_loops {
        result.push_str(&loop_str);
    }

    // Close the saveframe
    result.push_str("\nsave_\n");

    Ok(result)
}

/// Format a loop in NMR-STAR format.
/// This is the performance-critical function that formats all the data in a loop.
#[pyfunction]
#[pyo3(signature = (tags, category, data, skip_empty_loops=false, str_conversion_dict=None))]
pub fn format_loop(
    _py: Python,
    tags: Vec<String>,
    category: &str,
    data: Vec<Vec<Bound<'_, PyAny>>>,
    skip_empty_loops: bool,
    str_conversion_dict: Option<&Bound<'_, PyAny>>,
) -> PyResult<String> {
    // Handle empty data case
    if data.is_empty() {
        if skip_empty_loops {
            return Ok(String::new());
        } else {
            if tags.is_empty() {
                return Ok("\n   loop_\n\n   stop_\n".to_string());
            }
            // Fall through to print tags with no data
        }
    }

    if tags.is_empty() && !data.is_empty() {
        return Err(PyValueError::new_err(format!(
            "Impossible to print data if there are no associated tags. Error in loop '{}' which contains data but hasn't had any tags added.",
            category
        )));
    }

    // Pre-allocate for the result
    // Estimate: header (~50) + tags (category.len + tag.len + 10 per tag) + data
    let estimated_size = 100 + tags.len() * (category.len() + 20) + data.len() * tags.len() * 15;
    let mut result = String::with_capacity(estimated_size);

    // Start the loop
    result.push_str("\n   loop_\n");

    // Print the tags
    for tag in &tags {
        result.push_str("      ");
        result.push_str(category);
        result.push('.');
        result.push_str(tag);
        result.push('\n');
    }
    result.push('\n');

    if data.is_empty() {
        result.push_str("\n   stop_\n");
        return Ok(result);
    }

    // Convert and quote all data, tracking column widths
    let num_cols = tags.len();
    let mut quoted_data: Vec<Vec<String>> = Vec::with_capacity(data.len());
    let mut col_widths: Vec<usize> = vec![4; num_cols]; // minimum width of 4

    for (row_idx, row) in data.iter().enumerate() {
        let mut quoted_row: Vec<String> = Vec::with_capacity(num_cols);

        for (col_idx, cell) in row.iter().enumerate() {
            // Apply STR_CONVERSION_DICT if provided
            let converted_cell: std::borrow::Cow<'_, Bound<'_, PyAny>> = if let Some(conv_dict) = str_conversion_dict {
                // Check if the cell value is a key in the conversion dict
                if conv_dict.contains(cell)? {
                    // Get the converted value
                    std::borrow::Cow::Owned(conv_dict.get_item(cell)?)
                } else {
                    std::borrow::Cow::Borrowed(cell)
                }
            } else {
                std::borrow::Cow::Borrowed(cell)
            };

            // Convert to string, handling None specially (default conversion)
            let string_val: String = if converted_cell.is_none() {
                ".".to_string()
            } else {
                converted_cell.str()?.to_str()?.to_string()
            };

            // Quote the value
            let quoted = if string_val.is_empty() {
                // Empty strings are not allowed - return error
                return Err(PyValueError::new_err(format!(
                    "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] = None.\nLoop: {} Row: {} Column: {}",
                    category, row_idx, col_idx
                )));
            } else {
                quote_value_str(&string_val)
            };

            // Track width (but not for multiline values)
            if !quoted.contains('\n') {
                let width = quoted.len() + 3; // +3 for spacing
                if width > col_widths[col_idx] {
                    col_widths[col_idx] = width;
                }
            }

            quoted_row.push(quoted);
        }
        quoted_data.push(quoted_row);
    }

    // Print the data rows
    for row in &quoted_data {
        result.push_str("     ");
        for (col_idx, val) in row.iter().enumerate() {
            if val.contains('\n') {
                // Multiline value - format specially
                result.push_str("\n;\n");
                result.push_str(val);
                result.push_str(";\n");
            } else {
                // Pad to column width
                result.push_str(val);
                let padding = col_widths[col_idx].saturating_sub(val.len());
                for _ in 0..padding {
                    result.push(' ');
                }
            }
        }
        result.push_str(" \n");
    }

    // Close the loop
    result.push_str("\n   stop_\n");

    Ok(result)
}
