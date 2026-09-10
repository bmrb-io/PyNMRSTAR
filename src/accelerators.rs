use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::import_exception;
use pyo3::intern;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString, PyTuple};

use crate::utils::Quoting;

import_exception!(pynmrstar.exceptions, InvalidStateError);

/// Converts values to the strings which represent them, applying STR_CONVERSION_DICT.
struct Converter<'a, 'py> {
    dict: Option<&'a Bound<'py, PyAny>>,
    /// The dictionary, when it is exactly a dict - it can then be read without calling
    /// into Python, and with one lookup rather than two
    exact_dict: Option<&'a Bound<'py, PyDict>>,
    /// Whether a str value could be a key of the dictionary. It can not when every key is
    /// None, a bool, an int, or a float, as none of those ever compare equal to a str -
    /// which is the case for the default dictionary. Then str values (almost all values)
    /// need not be looked up at all.
    str_lookup: bool,
}

impl<'a, 'py> Converter<'a, 'py> {
    fn new(dict: Option<&'a Bound<'py, PyAny>>) -> Self {
        let exact_dict = dict.and_then(|d| d.cast_exact::<PyDict>().ok());
        let str_lookup = match (dict, exact_dict) {
            (None, _) => false,
            (Some(_), Some(d)) => d.keys().iter().any(|key| {
                !(key.is_none()
                    || key.is_exact_instance_of::<PyBool>()
                    || key.is_exact_instance_of::<PyInt>()
                    || key.is_exact_instance_of::<PyFloat>())
            }),
            (Some(_), None) => true,
        };
        Converter { dict, exact_dict, str_lookup }
    }

    /// Returns the string to print for a value.
    fn convert(&self, py: Python<'py>, value: &Bound<'py, PyAny>) -> PyResult<Bound<'py, PyString>> {
        if !self.str_lookup {
            if let Ok(s) = value.cast_exact::<PyString>() {
                return Ok(s.clone());
            }
        }

        // Apply STR_CONVERSION_DICT if provided
        let converted = if let Some(dict) = self.exact_dict {
            dict.get_item(value)?
        } else if let Some(dict) = self.dict {
            if dict.contains(value)? { Some(dict.get_item(value)?) } else { None }
        } else {
            None
        };
        let converted = converted.as_ref().unwrap_or(value);

        // Convert to string, handling None specially (default conversion)
        if converted.is_none() {
            Ok(intern!(py, ".").clone())
        } else {
            converted.str()
        }
    }
}

/// Append `count` spaces.
fn push_spaces(out: &mut String, mut count: usize) {
    const SPACES: &str = "                                                                ";
    while count > SPACES.len() {
        out.push_str(SPACES);
        count -= SPACES.len();
    }
    out.push_str(&SPACES[..count]);
}

/// Format a saveframe in NMR-STAR format.
/// Comments are handled by Python, this focuses on the heavy lifting of tag/loop formatting.
#[pyfunction]
#[pyo3(signature = (name, tag_prefix, tags, formatted_loops, skip_empty_tags=false, str_conversion_dict=None, null_values=None))]
pub fn format_saveframe<'py>(
    py: Python<'py>,
    name: &str,
    tag_prefix: &str,
    tags: Vec<Vec<Bound<'py, PyAny>>>,  // List of [tag_name, tag_value]
    formatted_loops: Vec<Bound<'py, PyString>>,
    skip_empty_tags: bool,
    str_conversion_dict: Option<&Bound<'py, PyAny>>,
    null_values: Option<&Bound<'py, PyAny>>,
) -> PyResult<String> {
    let converter = Converter::new(str_conversion_dict);
    let formatted_loops = formatted_loops.iter().map(|l| l.to_str()).collect::<PyResult<Vec<&str>>>()?;

    // The tag name, or "" if it is not a string
    fn tag_name<'a>(tag: &'a [Bound<'_, PyAny>]) -> &'a str {
        tag[0].cast::<PyString>().ok().and_then(|s| s.to_str().ok()).unwrap_or("")
    }

    // Estimate capacity for result string
    let estimated_size = 100 + tags.len() * (tag_prefix.len() + 50)
        + formatted_loops.iter().map(|s| s.len()).sum::<usize>();
    let mut result = String::with_capacity(estimated_size);

    // Print the saveframe header
    result.push_str("save_");
    result.push_str(name);
    result.push('\n');

    // Calculate maximum tag width for formatting
    let max_width = tags.iter()
        .filter(|tag| !tag.is_empty())
        .map(|tag| tag_prefix.len() + 1 + tag_name(tag).len())
        .max()
        .unwrap_or(0);

    // Process and print each tag
    for tag in &tags {
        if tag.len() < 2 {
            continue;
        }

        let tag_name = tag_name(tag);
        let tag_value = &tag[1];

        // Skip empty tags if requested
        if skip_empty_tags {
            if let Some(null_set) = null_values {
                if null_set.contains(tag_value).unwrap_or(false) {
                    continue;
                }
            }
        }

        let string_val = converter.convert(py, tag_value)?;
        let string_val = string_val.to_str()?;
        if string_val.is_empty() {
            return Err(PyValueError::new_err(format!(
                "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] = None. Saveframe: {} Tag: {}",
                name, tag_name
            )));
        }
        let quoting = Quoting::of(string_val);

        result.push_str("   ");
        result.push_str(tag_prefix);
        result.push('.');
        result.push_str(tag_name);
        if quoting.is_multiline() {
            // Multiline value format (no padding needed before newline)
            result.push_str("\n;\n");
            quoting.write(string_val, &mut result);
            result.push_str(";\n");
        } else {
            // Single line format: pad to max_width + 2 spaces
            let formatted_tag_len = tag_prefix.len() + 1 + tag_name.len();
            push_spaces(&mut result, max_width.saturating_sub(formatted_tag_len) + 2);
            quoting.write(string_val, &mut result);
            result.push('\n');
        }
    }

    // Append all formatted loops
    for loop_str in formatted_loops {
        result.push_str(loop_str);
    }

    // Close the saveframe
    result.push_str("\nsave_\n");

    Ok(result)
}

/// The values of one row of loop data, read in place when the row is a list or tuple.
enum Row<'py> {
    List(Bound<'py, PyList>),
    Tuple(Bound<'py, PyTuple>),
    Other(Vec<Bound<'py, PyAny>>),
}

impl<'py> Row<'py> {
    fn new(row: Bound<'py, PyAny>) -> PyResult<Self> {
        match row.cast_into::<PyList>() {
            Ok(list) => Ok(Row::List(list)),
            Err(err) => {
                let row = err.into_inner();
                match row.cast_into::<PyTuple>() {
                    Ok(tuple) => Ok(Row::Tuple(tuple)),
                    Err(err) => Ok(Row::Other(err.into_inner().extract()?)),
                }
            }
        }
    }

    fn len(&self) -> usize {
        match self {
            Row::List(list) => list.len(),
            Row::Tuple(tuple) => tuple.len(),
            Row::Other(values) => values.len(),
        }
    }

    fn get(&self, index: usize) -> PyResult<Bound<'py, PyAny>> {
        match self {
            Row::List(list) => list.get_item(index),
            Row::Tuple(tuple) => tuple.get_item(index),
            Row::Other(values) => Ok(values[index].clone()),
        }
    }
}

/// Format a loop in NMR-STAR format.
/// This is the performance-critical function that formats all the data in a loop.
#[pyfunction]
#[pyo3(signature = (tags, category, data, skip_empty_loops=false, str_conversion_dict=None))]
pub fn format_loop<'py>(
    py: Python<'py>,
    tags: Vec<String>,
    category: &str,
    data: &Bound<'py, PyAny>,
    skip_empty_loops: bool,
    str_conversion_dict: Option<&Bound<'py, PyAny>>,
) -> PyResult<String> {
    // Loop.data is a list; anything else is read as a sequence of sequences into one
    let data = match data.cast::<PyList>() {
        Ok(list) => list.clone(),
        Err(_) => {
            let rows: Vec<Vec<Bound<'py, PyAny>>> = data.extract()?;
            PyList::new(py, rows.into_iter().map(|row| PyList::new(py, row)).collect::<PyResult<Vec<_>>>()?)?
        }
    };

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

    let mut header = String::with_capacity(100 + tags.len() * (category.len() + 8));

    // Start the loop
    header.push_str("\n   loop_\n");

    // Print the tags
    for tag in &tags {
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

    // First pass: convert every value to a string, determine how it must be quoted, and
    //  track the column widths. The strings are kept (borrowed from Python) so they can be
    //  written out directly in the second pass.
    let converter = Converter::new(str_conversion_dict);
    let num_cols = tags.len();
    let num_rows = data.len();
    let mut values: Vec<(Bound<'py, PyString>, Quoting)> = Vec::with_capacity(num_rows * num_cols);
    let mut col_widths: Vec<usize> = vec![4; num_cols]; // minimum width of 4
    let mut multiline_size = 0;

    for (row_idx, row) in data.iter().enumerate() {
        let row = Row::new(row)?;
        if row.len() != num_cols {
            return Err(InvalidStateError::new_err(format!(
                "The number of tags must match the width of the data. Error in loop '{}'. \
                 In this case, there are {} tags, and row number {} has {} tags.",
                category, num_cols, row_idx, row.len()
            )));
        }

        for col_idx in 0..num_cols {
            let string_val = converter.convert(py, &row.get(col_idx)?)?;
            let s = string_val.to_str()?;

            // Empty strings are not allowed - return error
            if s.is_empty() {
                return Err(PyValueError::new_err(format!(
                    "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] = None.\nLoop: {} Row: {} Column: {}",
                    category, row_idx, col_idx
                )));
            }

            let quoting = Quoting::of(s);
            if quoting.is_multiline() {
                multiline_size += quoting.quoted_len(s) + 5;
            } else {
                // Track width (but not for multiline values), +3 for spacing
                let width = quoting.quoted_len(s) + 3;
                if width > col_widths[col_idx] {
                    col_widths[col_idx] = width;
                }
            }
            values.push((string_val, quoting));
        }
    }

    // Second pass: print the data rows into a buffer allocated once at (at least) the final size
    let row_size = 6 + col_widths.iter().sum::<usize>();
    let mut result = String::with_capacity(header.len() + num_rows * row_size + multiline_size + 16);
    result.push_str(&header);

    for row in values.chunks_exact(num_cols) {
        result.push_str("     ");
        for (col_idx, (string_val, quoting)) in row.iter().enumerate() {
            let s = string_val.to_str()?;
            if quoting.is_multiline() {
                // Multiline value - format specially
                result.push_str("\n;\n");
                quoting.write(s, &mut result);
                result.push_str(";\n");
            } else {
                // Pad to column width
                quoting.write(s, &mut result);
                push_spaces(&mut result, col_widths[col_idx] - quoting.quoted_len(s));
            }
        }
        result.push('\n');
    }

    // Close the loop
    result.push_str("\n   stop_\n");

    Ok(result)
}
