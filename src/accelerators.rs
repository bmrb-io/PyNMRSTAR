use pyo3::prelude::*;
use pyo3::exceptions::{PyIndexError, PyValueError};
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
    fn convert(&self, py: Python<'py>, value: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyString>> {
        let value = if self.str_lookup {
            value
        } else {
            match value.cast_into_exact::<PyString>() {
                Ok(s) => return Ok(s),
                Err(err) => err.into_inner(),
            }
        };
        let value = &value;

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
#[pyo3(signature = (name, tag_prefix, tags, formatted_loops, skip_empty_tags=false, str_conversion_dict=None, null_values=None, comment=""))]
#[allow(clippy::too_many_arguments)] // Mirrors the arguments Python passes
pub fn format_saveframe<'py>(
    py: Python<'py>,
    name: &str,
    tag_prefix: &str,
    tags: Vec<Vec<Bound<'py, PyAny>>>,  // List of [tag_name, tag_value]
    formatted_loops: Vec<Bound<'py, PyString>>,
    skip_empty_tags: bool,
    str_conversion_dict: Option<&Bound<'py, PyAny>>,
    null_values: Option<&Bound<'py, PyAny>>,
    comment: &str,
) -> PyResult<String> {
    let converter = Converter::new(str_conversion_dict);
    let formatted_loops = formatted_loops.iter().map(|l| l.to_str()).collect::<PyResult<Vec<&str>>>()?;

    // The tag name, or "" if it is not a string
    fn tag_name<'a>(tag: &'a [Bound<'_, PyAny>]) -> &'a str {
        tag[0].cast::<PyString>().ok().and_then(|s| s.to_str().ok()).unwrap_or("")
    }

    // Estimate capacity for result string
    let estimated_size = 100 + comment.len() + tags.len() * (tag_prefix.len() + 50)
        + formatted_loops.iter().map(|s| s.len()).sum::<usize>();
    let mut result = String::with_capacity(estimated_size);

    // Print the comment, which goes before the saveframe, and the saveframe header
    result.push_str(comment);
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

        let string_val = converter.convert(py, tag_value.clone())?;
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

    /// Call `f` with the index and value of each of the row's first `len` values.
    fn for_each(&self, len: usize, mut f: impl FnMut(usize, Bound<'py, PyAny>) -> PyResult<()>) -> PyResult<()> {
        let mut count = 0;
        let mut f = |value| {
            f(count, value)?;
            count += 1;
            Ok::<_, PyErr>(())
        };
        match self {
            Row::List(list) => list.iter().take(len).try_for_each(&mut f)?,
            Row::Tuple(tuple) => tuple.iter().take(len).try_for_each(&mut f)?,
            Row::Other(values) => values.iter().take(len).try_for_each(|value| f(value.clone()))?,
        }
        // Converting a value can run Python code, which could shorten a list
        if count < len {
            return Err(PyIndexError::new_err("list index out of range"));
        }
        Ok(())
    }
}

/// What the first pass of format_loop() learns of a loop's values: the widths of its columns,
/// and the values which differ from the one above them - which, as equal values are very often
/// the same string (parsed files share one string between equal values), are most often few.
struct Measured<'py> {
    num_cols: usize,
    /// The width of each column
    widths: Vec<usize>,
    /// The space the multiline values take
    multiline_size: usize,
    /// For each row, a bit for each column, set when its value differs from the one above
    changed: Vec<u64>,
    /// The values whose bits are set, in order, and how each must be quoted
    values: Vec<(Bound<'py, PyString>, Quoting)>,
}

impl<'py> Measured<'py> {
    fn new(num_rows: usize, num_cols: usize) -> Self {
        Measured {
            num_cols,
            widths: vec![4; num_cols], // minimum width of 4
            multiline_size: 0,
            changed: vec![0; num_rows * num_cols.div_ceil(64)],
            values: Vec::new(),
        }
    }

    /// Add the value of a column of a row, which differs from the one above it. Values must be
    /// added in order.
    fn add(&mut self, row_idx: usize, col_idx: usize, value: Bound<'py, PyString>, category: &str) -> PyResult<()> {
        let s = value.to_str()?;
        if s.is_empty() {
            return Err(PyValueError::new_err(format!(
                "Cannot generate NMR-STAR for entry, as empty strings are not valid tag values in NMR-STAR. Please either replace the empty strings with None objects, or set pynmrstar.definitions.STR_CONVERSION_DICT[''] = None.\nLoop: {} Row: {} Column: {}",
                category, row_idx, col_idx
            )));
        }
        let quoting = Quoting::of(s);
        if quoting.is_multiline() {
            self.multiline_size += quoting.quoted_len(s) + 5;
        } else {
            // Track width (but not for multiline values), +3 for spacing
            let width = quoting.quoted_len(s) + 3;
            if width > self.widths[col_idx] {
                self.widths[col_idx] = width;
            }
        }
        self.changed[row_idx * self.num_cols.div_ceil(64) + col_idx / 64] |= 1 << (col_idx % 64);
        self.values.push((value, quoting));
        Ok(())
    }

    /// The columns of a row whose values differ from the ones above them.
    fn changed_columns(&self, row_idx: usize) -> impl Iterator<Item = usize> + '_ {
        let words = self.num_cols.div_ceil(64);
        self.changed[row_idx * words..][..words].iter().enumerate().flat_map(|(word_idx, &word)| {
            let mut bits = word;
            std::iter::from_fn(move || {
                (bits != 0).then(|| {
                    let col_idx = word_idx * 64 + bits.trailing_zeros() as usize;
                    bits &= bits - 1;
                    col_idx
                })
            })
        })
    }

    /// Print the data rows after the header.
    fn write(&self, header: &str) -> PyResult<String> {
        // Print into a buffer allocated once at (at least) the final size
        let num_rows = self.changed.len() / self.num_cols.div_ceil(64);
        let row_size = 6 + self.widths.iter().sum::<usize>();
        let mut result = String::with_capacity(header.len() + num_rows * row_size + self.multiline_size + 16);
        result.push_str(header);
        let mut values = self.values.iter();

        if self.multiline_size == 0 {
            // Every row is then the same width, and each value is at its column's offset. Each
            //  row starts as a copy of the row above, so only the values which differ from the
            //  ones above them need writing.
            let offsets: Vec<usize> = self.widths.iter().scan(5, |pos, width| {
                let offset = *pos;
                *pos += width;
                Some(offset)
            }).collect();
            // The length of the value written above in each column
            let mut lengths_above = vec![0; self.num_cols];
            let mut out = result.into_bytes();
            for row_idx in 0..num_rows {
                let start = out.len();
                if row_idx == 0 {
                    out.resize(start + row_size, b' ');
                    out[start + row_size - 1] = b'\n';
                } else {
                    out.extend_from_within(start - row_size..start);
                }
                let line = &mut out[start..];
                for col_idx in self.changed_columns(row_idx) {
                    let (value, quoting) = values.next().expect("a value was added for each changed column");
                    let s = value.to_str()?;
                    let pos = offsets[col_idx];
                    let len = quoting.quoted_len(s);
                    quoting.write_into(s, &mut line[pos..]);
                    // Clear what remains of the value above
                    if lengths_above[col_idx] > len {
                        line[pos + len..pos + lengths_above[col_idx]].fill(b' ');
                    }
                    lengths_above[col_idx] = len;
                }
            }
            result = String::from_utf8(out).expect("only whole strings and ASCII were written");
        } else {
            let mut row = vec![None; self.num_cols];
            for row_idx in 0..num_rows {
                for col_idx in self.changed_columns(row_idx) {
                    row[col_idx] = values.next();
                }
                result.push_str("     ");
                for (value, col_width) in row.iter().zip(&self.widths) {
                    let (value, quoting) = value.expect("the first row has every column's value");
                    let s = value.to_str()?;
                    if quoting.is_multiline() {
                        // Multiline value - format specially
                        result.push_str("\n;\n");
                        quoting.write(s, &mut result);
                        result.push_str(";\n");
                    } else {
                        // Pad to column width
                        quoting.write(s, &mut result);
                        push_spaces(&mut result, col_width - quoting.quoted_len(s));
                    }
                }
                result.push('\n');
            }
        }

        // Close the loop
        result.push_str("\n   stop_\n");
        Ok(result)
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
        } else if tags.is_empty() {
            return Ok("\n   loop_\n\n   stop_\n".to_string());
        }
        // Otherwise fall through to print tags with no data
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
    //  track the column widths
    let converter = Converter::new(str_conversion_dict);
    let num_cols = tags.len();
    let mut measured = Measured::new(data.len(), num_cols);
    // The string last read in each column
    let mut previous: Vec<Option<Bound<'py, PyString>>> = vec![None; num_cols];

    for (row_idx, row) in data.iter().enumerate() {
        let row = Row::new(row)?;
        if row.len() != num_cols {
            return Err(InvalidStateError::new_err(format!(
                "The number of tags must match the width of the data. Error in loop '{}'. \
                 In this case, there are {} tags, and row number {} has {} tags.",
                category, num_cols, row_idx, row.len()
            )));
        }

        row.for_each(num_cols, |col_idx, value| {
            let string_val = converter.convert(py, value)?;
            // A value which is the same string as the one above it is already measured
            let previous = &mut previous[col_idx];
            if previous.as_ref().is_some_and(|previous| previous.is(&string_val)) {
                return Ok(());
            }
            *previous = Some(string_val.clone());
            measured.add(row_idx, col_idx, string_val, category)
        })?;
    }

    // Second pass: print the data rows
    measured.write(&header)
}
