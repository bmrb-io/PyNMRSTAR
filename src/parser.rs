use std::collections::HashSet;

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::{IntoPyDict, PyList, PyString};
use pyo3::{import_exception, intern};

use crate::utils::{fix_multiline_semicolons, is_reserved_keyword, starts_with_ignore_case};

// Import the ParsingError exception from pynmrstar.exceptions
import_exception!(pynmrstar.exceptions, ParsingError);

// Byte classes used by the tokenizer to scan whitespace and tokens with one table lookup per byte
const CLASS_OTHER: u8 = 0;
/// Standard whitespace: space, tab, newline, carriage return, vertical tab
const CLASS_WHITESPACE: u8 = 1;
/// Form feed - whitespace, but reported as unusual
const CLASS_UNUSUAL_WHITESPACE: u8 = 2;
/// A non-ASCII byte - may begin a multi-byte Unicode whitespace character
const CLASS_NON_ASCII: u8 = 3;

static BYTE_CLASS: [u8; 256] = {
    let mut table = [CLASS_OTHER; 256];
    table[b' ' as usize] = CLASS_WHITESPACE;
    table[b'\n' as usize] = CLASS_WHITESPACE;
    table[b'\t' as usize] = CLASS_WHITESPACE;
    table[b'\r' as usize] = CLASS_WHITESPACE;
    table[0x0B] = CLASS_WHITESPACE;
    table[0x0C] = CLASS_UNUSUAL_WHITESPACE;
    let mut i = 128;
    while i < 256 {
        table[i] = CLASS_NON_ASCII;
        i += 1;
    }
    table
};

// Tokenizer state
pub struct TokenizerState {
    pub full_data: String,
    index: usize,
    pub line_no: usize,
    /// Line number (1-based) on which the token last returned by get_token began.
    /// line_no cannot be used for this: it is advanced past the token, and past
    /// the whitespace which follows it, so it names the token's last line - and
    /// for a token followed by a newline, the line after that.
    pub token_line: usize,
    pub last_delimiter: char,
    /// Line number (0-based) where non-standard whitespace was first encountered, if any.
    pub unusual_whitespace_line: Option<usize>,
    /// Lines this tokenizer's data gained over the file it was read from, from
    /// fix_multiline_semicolons() splitting `;content` in two. See source_line().
    inserted_lines: Vec<usize>,
}

impl TokenizerState {
    pub fn new() -> Self {
        TokenizerState {
            full_data: String::new(),
            index: 0,
            line_no: 0,
            token_line: 0,
            last_delimiter: ' ',
            unusual_whitespace_line: None,
            inserted_lines: Vec::new(),
        }
    }

    fn reset(&mut self) {
        self.full_data.clear();
        self.index = 0;
        self.line_no = 0;
        self.token_line = 0;
        self.last_delimiter = ' ';
        self.unusual_whitespace_line = None;
        self.inserted_lines.clear();
    }

    /// Translate a line number in the data being tokenized back to the line of
    /// the file it came from. They differ only where a `;content` value was
    /// split across two lines before tokenizing; without this, every line
    /// reported after such a value would be off by one, and confidently so.
    pub fn source_line(&self, line: usize) -> usize {
        if self.inserted_lines.is_empty() {
            return line;
        }
        line - self.inserted_lines.partition_point(|&inserted| inserted < line)
    }

    fn is_standard_whitespace(b: u8) -> bool {
        matches!(b, b' ' | b'\n' | b'\t' | b'\r' | b'\x0B')
    }

    pub fn load_string(&mut self, data: String, inserted_lines: Vec<usize>) {
        self.reset();
        self.full_data = data;
        self.inserted_lines = inserted_lines;
    }

    /// Check if the byte position starts with a Unicode whitespace character.
    /// Returns the number of bytes to advance (0 if not whitespace).
    fn whitespace_len_at(s: &str, pos: usize) -> usize {
        if pos >= s.len() {
            return 0;
        }
        let b = s.as_bytes()[pos];
        // Fast path: ASCII bytes (covers >99% of NMR-STAR content)
        match BYTE_CLASS[b as usize] {
            CLASS_OTHER => 0,
            CLASS_WHITESPACE | CLASS_UNUSUAL_WHITESPACE => 1,
            _ => Self::unicode_whitespace_len_at(s, pos),
        }
    }

    /// Slow path of whitespace_len_at(), for a non-ASCII byte.
    #[cold]
    fn unicode_whitespace_len_at(s: &str, pos: usize) -> usize {
        if !s.is_char_boundary(pos) {
            return 0;
        }
        if let Some(c) = s[pos..].chars().next() {
            if c.is_whitespace() {
                return c.len_utf8();
            }
        }
        0
    }

    fn pass_whitespace(&mut self) {
        let bytes = self.full_data.as_bytes();
        let mut index = self.index;
        while index < bytes.len() {
            let b = bytes[index];
            match BYTE_CLASS[b as usize] {
                CLASS_WHITESPACE => {
                    if b == b'\n' {
                        self.line_no += 1;
                    }
                    index += 1;
                }
                CLASS_OTHER => break,
                _ => {
                    // Form feed, or a non-ASCII byte which may start Unicode whitespace
                    let len = Self::whitespace_len_at(&self.full_data, index);
                    if len == 0 {
                        break;
                    }
                    if self.unusual_whitespace_line.is_none() {
                        self.unusual_whitespace_line = Some(self.line_no);
                    }
                    index += len;
                }
            }
        }
        self.index = index;
    }

    fn check_multiline(&self, length: usize) -> bool {
        let end = (self.index + length).min(self.full_data.len());
        memchr::memchr(b'\n', &self.full_data.as_bytes()[self.index..end]).is_some()
    }

    fn update_line_number(&mut self, start_pos: usize, length: usize) {
        let end = (start_pos + length).min(self.full_data.len());
        self.line_no += memchr::memchr_iter(b'\n', &self.full_data.as_bytes()[start_pos..end]).count();
    }

    fn find_substring(&self, needle: &str, start_pos: usize) -> Option<usize> {
        if start_pos >= self.full_data.len() {
            return None;
        }
        let haystack = &self.full_data.as_bytes()[start_pos..];

        // Single-byte searches (quotes, newlines) use memchr, which is SIMD accelerated
        if needle.len() == 1 {
            return memchr::memchr(needle.as_bytes()[0], haystack);
        }

        // Two-byte searches (e.g., "\n;"): find each occurrence of the first byte with
        //  memchr, and check the byte which follows it
        if needle.len() == 2 {
            let needle_bytes = needle.as_bytes();
            let mut offset = 0;
            while let Some(found) = memchr::memchr(needle_bytes[0], &haystack[offset..]) {
                let pos = offset + found;
                if pos + 1 >= haystack.len() {
                    return None;
                }
                if haystack[pos + 1] == needle_bytes[1] {
                    return Some(pos);
                }
                offset = pos + 1;
            }
            return None;
        }

        // Fall back to str::find for longer patterns
        self.full_data[start_pos..].find(needle)
    }

    fn get_next_whitespace(&self, start_pos: usize) -> usize {
        let bytes = self.full_data.as_bytes();
        let mut pos = start_pos;
        while pos < bytes.len() {
            match BYTE_CLASS[bytes[pos] as usize] {
                CLASS_OTHER => pos += 1,
                CLASS_NON_ASCII => {
                    if Self::whitespace_len_at(&self.full_data, pos) > 0 {
                        return pos;
                    }
                    pos += 1;
                }
                _ => return pos,
            }
        }
        pos
    }

    pub fn get_token(&mut self) -> Result<Option<(usize, usize)>, String> {
        // Reset delimiter
        self.last_delimiter = '?';

        // Skip whitespace
        self.pass_whitespace();

        // Check if we're at the end
        if self.index >= self.full_data.len() {
            return Ok(None);
        }

        // The whitespace before the token has been passed, so line_no now names
        // the line the token starts on. Record it before the token is consumed.
        self.token_line = self.source_line(self.line_no + 1);

        let bytes = self.full_data.as_bytes();

        // Handle comments
        if bytes[self.index] == b'#' {
            if let Some(length) = self.find_substring("\n", self.index) {
                let start = self.index;
                let end = self.index + length;
                self.last_delimiter = '#';
                self.update_line_number(self.index, length + 1);
                self.index += length + 1;
                return Ok(Some((start, end)));
            } else {
                // Comment at end of file with no newline
                return Ok(None);
            }
        }

        // Handle multiline values (semicolon-delimited)
        if self.index + 1 < bytes.len() && bytes[self.index] == b';' && bytes[self.index + 1] == b'\n' {
            if let Some(length) = self.find_substring("\n;", self.index) {
                // We started with a newline so count it
                self.line_no += 1;
                self.index += 2;

                let start = self.index;
                let end = self.index + length - 1;
                self.last_delimiter = ';';
                self.update_line_number(self.index, length);
                self.index += length;
                return Ok(Some((start, end)));
            } else {
                return Err(format!("Invalid file. Semicolon-delineated value was not terminated. Error on line: {}", self.token_line));
            }
        }

        // Handle single-quoted values
        if bytes[self.index] == b'\'' {
            if let Some(mut end_quote) = self.find_substring("'", self.index + 1) {
                // Make sure we don't stop for quotes not followed by whitespace
                loop {
                    let absolute_quote_pos = self.index + end_quote + 1;
                    if absolute_quote_pos + 1 < self.full_data.len() && Self::whitespace_len_at(&self.full_data, absolute_quote_pos + 1) == 0 {
                        // Search for next quote starting after this one
                        if let Some(next_relative_idx) = self.find_substring("'", absolute_quote_pos + 1) {
                            // Update end_quote to be relative to self.index + 1 (after opening quote)
                            end_quote = (absolute_quote_pos - self.index - 1) + next_relative_idx + 1;
                        } else {
                            return Err("Invalid file. Single quoted value was never terminated at end of file.".to_string());
                        }
                    } else {
                        break;
                    }
                }

                // Check for newlines
                if self.check_multiline(end_quote + 1) {
                    return Err(format!("Invalid file. Single quoted value was not terminated on the same line it began. Error on line: {}", self.token_line));
                }

                self.index += 1;
                let start = self.index;
                let end = self.index + end_quote;
                self.last_delimiter = '\'';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some((start, end)));
            } else {
                return Err(format!("Invalid file. Single quoted value was not terminated. Error on line: {}", self.token_line));
            }
        }

        // Handle double-quoted values
        if bytes[self.index] == b'"' {
            if let Some(mut end_quote) = self.find_substring("\"", self.index + 1) {
                // Make sure we don't stop for quotes not followed by whitespace
                loop {
                    let absolute_quote_pos = self.index + end_quote + 1;
                    if absolute_quote_pos + 1 < self.full_data.len() && Self::whitespace_len_at(&self.full_data, absolute_quote_pos + 1) == 0 {
                        // Search for next quote starting after this one
                        if let Some(next_relative_idx) = self.find_substring("\"", absolute_quote_pos + 1) {
                            // Update end_quote to be relative to self.index + 1 (after opening quote)
                            end_quote = (absolute_quote_pos - self.index - 1) + next_relative_idx + 1;
                        } else {
                            return Err("Invalid file. Double quoted value was never terminated at end of file.".to_string());
                        }
                    } else {
                        break;
                    }
                }

                // Check for newlines
                if self.check_multiline(end_quote + 1) {
                    return Err(format!("Invalid file. Double quoted value was not terminated on the same line it began. Error on line: {}", self.token_line));
                }

                self.index += 1;
                let start = self.index;
                let end = self.index + end_quote;
                self.last_delimiter = '"';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some((start, end)));
            } else {
                return Err(format!("Invalid file. Double quoted value was not terminated. Error on line: {}", self.token_line));
            }
        }

        // Handle normal unquoted tokens
        let end_pos = self.get_next_whitespace(self.index);
        let start = self.index;
        let end = end_pos;

        // Set delimiter for unquoted tokens
        self.last_delimiter = ' ';

        // Check if it's a reference (starts with $ and delimiter was space)
        let token_slice = &self.full_data[start..end];
        if token_slice.starts_with('$') && self.last_delimiter == ' ' && token_slice.len() > 1 {
            self.last_delimiter = '$';
        }

        self.update_line_number(self.index, end_pos - self.index + 1);
        let ws_len = Self::whitespace_len_at(&self.full_data, end_pos);
        if ws_len > 0 && self.unusual_whitespace_line.is_none()
            && !Self::is_standard_whitespace(self.full_data.as_bytes()[end_pos])
        {
            self.unusual_whitespace_line = Some(self.line_no);
        }
        // Advance past the token and any trailing whitespace
        // If at end of file (ws_len=0), end_pos already equals full_data.len()
        self.index = end_pos + ws_len;
        Ok(Some((start, end)))
    }
}

// Represents a token either as indices into tokenizer.full_data or as a materialized string
// (for rare processed tokens from embedded STAR format)
enum TokenValue {
    Indexed(usize, usize),      // Indices into ctx.tokenizer.full_data
    Materialized(String),        // Pre-materialized string (< 0.1% of tokens)
}

impl TokenValue {
    fn as_str<'a>(&'a self, full_data: &'a str) -> std::borrow::Cow<'a, str> {
        match self {
            TokenValue::Indexed(start, end) => std::borrow::Cow::Borrowed(&full_data[*start..*end]),
            TokenValue::Materialized(s) => std::borrow::Cow::Borrowed(s),
        }
    }

    /// Create the Python string for this token directly from the source data, without an
    /// intermediate Rust String
    fn to_py<'py>(&self, py: Python<'py>, full_data: &str) -> Bound<'py, PyString> {
        match self {
            TokenValue::Indexed(start, end) => PyString::new(py, &full_data[*start..*end]),
            TokenValue::Materialized(s) => PyString::new(py, s),
        }
    }
}

struct LoopStatistics {
    total_data_items: usize,
    loop_count: usize,
}

struct ParserContext {
    tokenizer: TokenizerState,
    line_number: usize,
    delimiter: char,
    token: Option<(usize, usize)>,
    processed_token: Option<String>,  // For rare cases where we need to process the token
    entry: Py<PyAny>,
    current_saveframe: Option<Py<PyAny>>,
    current_loop: Option<Py<PyAny>>,
    loop_data: Vec<TokenValue>,  // Store indices instead of materialized strings
    seen_data: bool,
    in_loop: bool,
    _source: String,
    raise_parse_warnings: bool,
    _convert_data_types: bool,
    _schema: Option<Py<PyAny>>,
    saveframe_class: Py<PyAny>,
    loop_class: Py<PyAny>,
    source_dict: Py<PyAny>,
    add_tags_kwargs: Py<PyAny>,
    add_data_kwargs: Py<PyAny>,
    // Loop pre-allocation tracking by loop type
    loop_statistics: std::collections::HashMap<String, LoopStatistics>,
    current_loop_type: Option<String>,
    current_loop_tags_len: usize,
    warned_unusual_whitespace: bool,
    // The entry's saveframe list, and the names of the saveframes in it. Saveframes are
    // appended directly, as Entry.add_saveframe() checks for duplicate names by building a
    // dictionary of every saveframe - O(n^2) over a whole file.
    frame_list: Py<PyList>,
    saveframe_names: HashSet<String>,
    // The string members of definitions.NULL_VALUES, which can't be tag names. None if it has
    // members other than strings and None, which disables adding tags without Python.
    null_tag_names: Option<Vec<String>>,
    // State of the current saveframe, for add_saveframe_tags_fast(). Only reliable while every
    // tag of the saveframe has been added that way, which sf_fast_path tracks.
    sf_fast_path: bool,
    sf_name: String,
    sf_tag_prefix: Option<String>,
    sf_tags_lc: HashSet<String>,
}

impl ParserContext {
    fn new(py: Python, entry: Py<PyAny>, source: String, raise_parse_warnings: bool,
           convert_data_types: bool, schema: Option<Py<PyAny>>, tokenizer: TokenizerState) -> PyResult<Self> {
        // Cache module/class lookups at initialization
        let saveframe_mod = py.import("pynmrstar.saveframe")?;
        let saveframe_class = saveframe_mod.getattr("Saveframe")?.into();

        let loop_mod = py.import("pynmrstar.loop")?;
        let loop_class = loop_mod.getattr("Loop")?.into();

        // Pre-create reusable dictionaries for kwargs
        let source_dict = [("source", source.as_str())].into_py_dict(py)?.into();

        let add_tags_kwargs = if schema.is_some() {
            [
                ("convert_data_types", convert_data_types.into_pyobject(py)?.to_owned().into_any().unbind()),
                ("schema", schema.as_ref().unwrap().clone_ref(py))
            ].into_py_dict(py)?.into()
        } else {
            [("convert_data_types", convert_data_types.into_pyobject(py)?.to_owned().into_any().unbind())]
                .into_py_dict(py)?.into()
        };

        let add_data_kwargs = if schema.is_some() {
            [
                ("rearrange", true.into_pyobject(py)?.to_owned().into_any().unbind()),
                ("convert_data_types", convert_data_types.into_pyobject(py)?.to_owned().into_any().unbind()),
                ("schema", schema.as_ref().unwrap().clone_ref(py))
            ].into_py_dict(py)?.into()
        } else {
            [
                ("rearrange", true.into_pyobject(py)?.to_owned().into_any().unbind()),
                ("convert_data_types", convert_data_types.into_pyobject(py)?.to_owned().into_any().unbind())
            ].into_py_dict(py)?.into()
        };

        let frame_list = entry.bind(py).getattr("_frame_list")?.cast_into::<PyList>()?;
        let mut saveframe_names = HashSet::new();
        for frame in frame_list.iter() {
            if let Ok(name) = frame.getattr("name")?.extract::<String>() {
                saveframe_names.insert(name);
            }
        }

        let mut null_tag_names = Some(Vec::new());
        for value in py.import("pynmrstar.definitions")?.getattr("NULL_VALUES")?.try_iter()? {
            let value = value?;
            if value.is_none() {
                continue;
            }
            match value.cast_exact::<PyString>() {
                Ok(s) => null_tag_names.as_mut().unwrap().push(s.to_str()?.to_string()),
                Err(_) => {
                    null_tag_names = None;
                    break;
                }
            }
        }

        Ok(ParserContext {
            frame_list: frame_list.unbind(),
            saveframe_names,
            null_tag_names,
            sf_fast_path: false,
            sf_name: String::new(),
            sf_tag_prefix: None,
            sf_tags_lc: HashSet::new(),
            tokenizer,
            line_number: 0,
            delimiter: ' ',
            token: None,
            processed_token: None,
            entry,
            current_saveframe: None,
            current_loop: None,
            loop_data: Vec::new(),
            seen_data: false,
            in_loop: false,
            _source: source,
            raise_parse_warnings,
            _convert_data_types: convert_data_types,
            _schema: schema,
            saveframe_class,
            loop_class,
            source_dict,
            add_tags_kwargs,
            add_data_kwargs,
            loop_statistics: std::collections::HashMap::new(),
            current_loop_type: None,
            current_loop_tags_len: 0,
            warned_unusual_whitespace: false,
        })
    }

    fn get_token(&mut self, py: Python) -> PyResult<bool> {
        // Clear any previous processed token
        self.processed_token = None;

        // Get token and skip comments
        loop {
            match self.tokenizer.get_token() {
                Ok(Some((start, end))) => {
                    if self.tokenizer.last_delimiter != '#' {
                        let token_str = &self.tokenizer.full_data[start..end];

                        // Handle embedded STAR unwrapping for semicolon-delimited tokens
                        if self.tokenizer.last_delimiter == ';' && token_str.starts_with("\n   ") {
                            let mut shift_over = true;
                            let lines: Vec<&str> = token_str.split('\n').collect();

                            for line in &lines[1..] {  // Skip first empty line
                                if !line.is_empty() && !line.starts_with("   ") {
                                    shift_over = false;
                                    break;
                                }
                            }

                            if shift_over && token_str.contains("\n   ;") {
                                // Process the string and store it separately
                                let mut processed = token_str.trim_end_matches('\n').to_string();
                                processed = processed.replace("\n   ", "\n");
                                self.processed_token = Some(processed);
                            }
                        }

                        self.token = Some((start, end));
                        self.line_number = self.tokenizer.token_line;
                        self.delimiter = self.tokenizer.last_delimiter;

                        // Check for unusual whitespace (warn/raise once per file)
                        if !self.warned_unusual_whitespace {
                            if let Some(line) = self.tokenizer.unusual_whitespace_line {
                                self.warned_unusual_whitespace = true;
                                let msg = format!(
                                    "Non-standard whitespace character found on line {}. \
                                     Only standard whitespace characters (space, tab, newline, \
                                     vertical tab, carriage return) are expected in NMR-STAR files.",
                                    self.tokenizer.source_line(line + 1)
                                );
                                if self.raise_parse_warnings {
                                    return Err(self.raise_error(&msg));
                                } else {
                                    let logging = py.import("logging")?;
                                    let logger = logging.call_method1("getLogger", ("pynmrstar",))?;
                                    logger.call_method1("warning", (msg,))?;
                                }
                            }
                        }

                        return Ok(true);
                    }
                    // If it's a comment, continue to get the next token
                }
                Ok(None) => {
                    self.token = None;
                    return Ok(false);
                }
                Err(e) => return Err(ParsingError::new_err((e, self.tokenizer.token_line))),
            }
        }
    }

    fn token_str(&self) -> &str {
        // Return processed token if available
        if let Some(ref processed) = self.processed_token {
            processed
        } else if let Some((start, end)) = self.token {
            &self.tokenizer.full_data[start..end]
        } else {
            ""
        }
    }

    fn raise_error(&self, message: &str) -> PyErr {
        parsing_error(message, self.line_number)
    }
}

/// Build a ParsingError against a line of the file.
///
/// ParsingError takes (message, line_number=None) and renders the line itself,
/// so the caller gets it as an attribute rather than glued into the message
/// text. Line 0 means no token has been read yet, so there is no line to name.
fn parsing_error(message: &str, line_number: usize) -> PyErr {
    if line_number == 0 {
        ParsingError::new_err(message.to_string())
    } else {
        ParsingError::new_err((message.to_string(), line_number))
    }
}

/// The number of tags currently held by a Saveframe or a Loop.
fn tag_count(py: Python, object: &Py<PyAny>) -> PyResult<usize> {
    object.getattr(py, "tags")?.bind(py).len()
}

/// The message carried by a Python exception.
fn error_message(py: Python, error: &PyErr) -> String {
    match error.value(py).str() {
        Ok(message) => message.to_string(),
        Err(_) => error.to_string(),
    }
}

/// Attach the right line number to a failure raised while adding a batch of tags.
///
/// Tags are read one at a time but handed to Python in batches, so by the time
/// one is rejected the tokenizer has moved on to whatever ended the batch. The
/// batch is added one tag at a time and stops at the first failure, so the
/// number of tags that landed is the index of the offending one within the
/// batch - and the line each was read from was recorded as it was read.
fn locate_failed_tag(py: Python, error: PyErr, object: &Py<PyAny>,
                     tags_before: usize, lines: &[usize]) -> PyErr {
    if !error.is_instance_of::<pyo3::exceptions::PyValueError>(py) {
        return error;
    }
    let added = match tag_count(py, object) {
        Ok(after) if after >= tags_before => after - tags_before,
        _ => return error,
    };
    match lines.get(added) {
        Some(line) => parsing_error(&error_message(py, &error), *line),
        None => error,
    }
}

fn parse_initial(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    // Get first token
    if !ctx.get_token(py)? {
        return Err(ctx.raise_error("Empty file"));
    }

    let token = ctx.token_str();

    // Validate data_ token
    if !starts_with_ignore_case(token, "data_") {
        return Err(ctx.raise_error(&format!(
            "Invalid file. NMR-STAR files must start with 'data_' followed by the data name. \
             Did you accidentally select the wrong file? Your file started with '{}'.",
            token
        )));
    }

    if token.len() < 6 {
        return Err(ctx.raise_error(
            "'data_' must be followed by data name. Simply 'data_' is not allowed."
        ));
    }

    if ctx.delimiter != ' ' {
        return Err(ctx.raise_error("The data_ keyword may not be quoted or semicolon-delimited."));
    }

    // Set entry_id
    let entry_id = &token[5..];
    ctx.entry.setattr(py, "_entry_id", entry_id)?;

    Ok(())
}

fn parse_entry_body(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    while ctx.get_token(py)? {
        let token = ctx.token_str();

        if !starts_with_ignore_case(token, "save_") {
            return Err(ctx.raise_error(&format!(
                "Only 'save_NAME' is valid in the body of a NMR-STAR file. Found '{}'.",
                token
            )));
        }

        if token.len() < 6 {
            return Err(ctx.raise_error(
                "'save_' must be followed by saveframe name. You have a 'save_' tag which is \
                 illegal without a specified saveframe name."
            ));
        }

        if ctx.delimiter != ' ' {
            return Err(ctx.raise_error("The save_ keyword may not be quoted or semicolon-delimited."));
        }

        // Create new saveframe using cached class
        let saveframe_name = &token[5..];
        let saveframe = ctx.saveframe_class.bind(py).call_method(
            "from_scratch",
            (saveframe_name,),
            Some(ctx.source_dict.bind(py).cast()?)
        )?;

        // Equivalent to Entry.add_saveframe(), with the duplicate name check done in O(1)
        let name: String = saveframe.getattr("name")?.extract()?;
        if ctx.saveframe_names.contains(&name) {
            return Err(PyValueError::new_err(format!(
                "Cannot add a saveframe with name '{}' since a saveframe with that name already exists in the entry.",
                name
            )));
        }
        ctx.frame_list.bind(py).append(&saveframe)?;
        ctx.saveframe_names.insert(name.clone());
        ctx.current_saveframe = Some(saveframe.into());

        // Tags can be added without Python unless they need converting using the schema
        ctx.sf_fast_path = !ctx._convert_data_types && ctx.null_tag_names.is_some();
        ctx.sf_name = name;
        ctx.sf_tag_prefix = None;
        ctx.sf_tags_lc.clear();

        // Parse saveframe body
        parse_saveframe_body(py, ctx)?;
    }

    Ok(())
}

/// Split a tag into its category and tag name, if it is a tag which Loop.add_tag() and
/// Saveframe.add_tag() would store without changing it or raising an error: printable ASCII
/// (so without whitespace, and lowercased the same way by Python and Rust), a category starting
/// with '_', exactly one '.', and a tag name which is not null-equivalent. Returns the position
/// of the '.'.
fn split_simple_tag(tag: &str, null_tag_names: &[String]) -> Option<usize> {
    if !tag.starts_with('_') || !tag.bytes().all(|b| (0x21..=0x7E).contains(&b)) {
        return None;
    }
    let dot = tag.find('.')?;
    let name = &tag[dot + 1..];
    if name.is_empty() || name.contains('.') || null_tag_names.iter().any(|null| null == name) {
        return None;
    }
    Some(dot)
}

/// Add tags to a newly created loop directly, rather than through Loop.add_tag(), when they are
/// all tags which Loop.add_tag() would accept unchanged (see split_simple_tag()) with a single
/// category and no duplicates. The result is the same: the category is set from the first tag,
/// and the tag names are stored without it.
///
/// Returns false, having changed nothing, if any tag needs the full handling of Loop.add_tag() -
/// which includes every tag it would reject, so errors are always raised by Python.
fn add_loop_tags_fast(py: Python, ctx: &ParserContext, loop_obj: &Py<PyAny>, tags: &[(TokenValue, usize)]) -> PyResult<bool> {
    let Some(null_tag_names) = &ctx.null_tag_names else { return Ok(false) };
    let full_data = &ctx.tokenizer.full_data;

    let mut category: Option<&str> = None;
    let mut names: Vec<&str> = Vec::with_capacity(tags.len());
    let mut seen: HashSet<String> = HashSet::with_capacity(tags.len());
    for (tag, _) in tags {
        let TokenValue::Indexed(start, end) = tag else { return Ok(false) };
        let tag = &full_data[*start..*end];
        let Some(dot) = split_simple_tag(tag, null_tag_names) else { return Ok(false) };
        let (tag_category, name) = (&tag[..dot], &tag[dot + 1..]);
        match category {
            None => category = Some(tag_category),
            Some(c) if !c.eq_ignore_ascii_case(tag_category) => return Ok(false),
            _ => {}
        }
        if !seen.insert(name.to_ascii_lowercase()) {
            return Ok(false);
        }
        names.push(name);
    }

    let loop_obj = loop_obj.bind(py);
    loop_obj.setattr(intern!(py, "category"), category)?;
    loop_obj.setattr(intern!(py, "_tags"), PyList::new(py, names)?)?;
    loop_obj.setattr(intern!(py, "_lc_tags_cache"), py.None())?;
    Ok(true)
}

/// Add a batch of tags to the current saveframe directly, rather than through
/// Saveframe.add_tags(), when they are all tags which Saveframe.add_tag() would accept unchanged:
/// see split_simple_tag(), plus the saveframe's tag prefix, no duplicates, and an Sf_framecode
/// matching the saveframe name. The result is the same: the tag prefix is set from the first
/// tag, Sf_category sets the category, and each tag is stored as [name, value].
///
/// Returns false, having changed nothing, if any tag needs the full handling of
/// Saveframe.add_tag() - which includes every tag it would reject or warn about, so those are
/// always handled by Python. The rest of the saveframe's tags then go through Python as well.
fn add_saveframe_tags_fast(py: Python, ctx: &mut ParserContext, pending: &[(TokenValue, TokenValue, usize)]) -> PyResult<bool> {
    if !ctx.sf_fast_path {
        return Ok(false);
    }
    let full_data = &ctx.tokenizer.full_data;
    let null_tag_names = ctx.null_tag_names.as_deref().unwrap_or(&[]);

    // Check every tag before changing anything
    let mut prefix: Option<&str> = ctx.sf_tag_prefix.as_deref();
    let mut names: Vec<&str> = Vec::with_capacity(pending.len());
    let mut lc_names: Vec<String> = Vec::with_capacity(pending.len());
    let mut category_value: Option<&TokenValue> = None;
    let mut accepted = true;
    for (tag, value, _) in pending {
        let TokenValue::Indexed(start, end) = tag else { accepted = false; break };
        let tag = &full_data[*start..*end];
        let Some(dot) = split_simple_tag(tag, null_tag_names) else { accepted = false; break };
        let (tag_prefix, name) = (&tag[..dot], &tag[dot + 1..]);
        match prefix {
            None => prefix = Some(tag_prefix),
            Some(p) if p != tag_prefix => { accepted = false; break }
            _ => {}
        }
        let lc_name = name.to_ascii_lowercase();
        if ctx.sf_tags_lc.contains(&lc_name) || lc_names.contains(&lc_name) {
            accepted = false;
            break;
        }
        if lc_name == "sf_framecode" && value.as_str(full_data) != ctx.sf_name.as_str() {
            accepted = false;
            break;
        }
        if lc_name == "sf_category" {
            category_value = Some(value);
        }
        names.push(name);
        lc_names.push(lc_name);
    }
    if !accepted {
        ctx.sf_fast_path = false;
        return Ok(false);
    }

    let saveframe = ctx.current_saveframe.as_ref().unwrap().bind(py);
    let new_prefix = if ctx.sf_tag_prefix.is_none() { prefix.map(str::to_string) } else { None };
    if let Some(new_prefix) = &new_prefix {
        saveframe.setattr(intern!(py, "tag_prefix"), new_prefix)?;
    }
    let saveframe_tags = saveframe.getattr(intern!(py, "_tags"))?.cast_into::<PyList>()?;
    for (name, (_, value, _)) in names.iter().zip(pending) {
        saveframe_tags.append(PyList::new(py, [PyString::new(py, name), value.to_py(py, full_data)])?)?;
    }
    if let Some(value) = category_value {
        saveframe.setattr(intern!(py, "_category"), value.to_py(py, full_data))?;
    }
    saveframe.setattr(intern!(py, "_lc_tags_cache"), py.None())?;

    if new_prefix.is_some() {
        ctx.sf_tag_prefix = new_prefix;
    }
    ctx.sf_tags_lc.extend(lc_names);
    Ok(true)
}

/// Add the pending tags to the current saveframe.
fn flush_saveframe_tags(py: Python, ctx: &mut ParserContext, pending: &mut Vec<(TokenValue, TokenValue, usize)>) -> PyResult<()> {
    if pending.is_empty() {
        return Ok(());
    }
    let tags_to_add = std::mem::take(pending);
    if add_saveframe_tags_fast(py, ctx, &tags_to_add)? {
        return Ok(());
    }

    let saveframe = ctx.current_saveframe.as_ref().unwrap();
    // Materialize TokenValues into a list of (str, str) tuples for Python
    let full_data = &ctx.tokenizer.full_data;
    let materialized = PyList::new(py, tags_to_add
        .iter()
        .map(|(tag, value, _)| (tag.to_py(py, full_data), value.to_py(py, full_data))))?;
    let tags_before = tag_count(py, saveframe)?;
    if let Err(error) = saveframe.call_method(py, "add_tags", (materialized,),
                                              Some(ctx.add_tags_kwargs.bind(py).cast()?)) {
        let lines: Vec<usize> = tags_to_add.iter().map(|(_, _, line)| *line).collect();
        return Err(locate_failed_tag(py, error, saveframe, tags_before, &lines));
    }
    Ok(())
}

fn parse_saveframe_body(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    // Each pending tag carries the line it was read from, so that a tag rejected
    // at flush time can still be reported against its own line.
    let mut pending_tags: Vec<(TokenValue, TokenValue, usize)> = Vec::new();

    while ctx.get_token(py)? {
        let token = ctx.token_str();

        if token.eq_ignore_ascii_case("loop_") {
            // Flush any pending tags before processing loop
            flush_saveframe_tags(py, ctx, &mut pending_tags)?;
            if ctx.delimiter != ' ' {
                return Err(ctx.raise_error("The loop_ keyword may not be quoted or semicolon-delimited."));
            }

            // Create new loop using cached class
            let new_loop = ctx.loop_class.bind(py).call_method(
                "from_scratch",
                (),
                Some(ctx.source_dict.bind(py).cast()?)
            )?;

            ctx.current_loop = Some(new_loop.into());
            ctx.loop_data.clear();
            ctx.seen_data = false;
            ctx.in_loop = true;

            parse_loop_tags(py, ctx)?;

        } else if token.eq_ignore_ascii_case("save_") {
            // Flush any pending tags before exiting saveframe
            flush_saveframe_tags(py, ctx, &mut pending_tags)?;

            if ctx.delimiter != ' ' {
                return Err(ctx.raise_error("The save_ keyword may not be quoted or semicolon-delimited."));
            }

            // Check tag_prefix is set
            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            let tag_prefix = saveframe.getattr(py, "tag_prefix")?;
            if tag_prefix.is_none(py) {
                let frame_name = saveframe.getattr(py, "name")?;
                return Err(ctx.raise_error(&format!(
                    "The tag prefix was never set! Either the saveframe had no tags, you \
                     tried to read a version 2.1 file, or there is something else wrong with \
                     your file. Saveframe error occurred within: '{}'",
                    frame_name.extract::<String>(py)?
                )));
            }

            break; // Exit saveframe

        } else if token.starts_with('_') {
            if ctx.delimiter != ' ' {
                return Err(ctx.raise_error(&format!(
                    "Saveframe tags may not be quoted or semicolon-delimited. Quoted tag: '{}'.",
                    token
                )));
            }

            // Capture tag name as TokenValue
            let tag_line = ctx.line_number;
            let tag_name = if let Some(ref processed) = ctx.processed_token {
                TokenValue::Materialized(processed.clone())
            } else if let Some((start, end)) = ctx.token {
                TokenValue::Indexed(start, end)
            } else {
                TokenValue::Materialized(String::new())
            };

            // Get tag value
            if !ctx.get_token(py)? {
                return Err(ctx.raise_error("Tag without value"));
            }
            let value = ctx.token_str();

            if ctx.delimiter == ' ' {
                if is_reserved_keyword(value) {
                    return Err(ctx.raise_error(&format!(
                        "Cannot use keywords as data values unless quoted or semi-colon \
                         delimited. Illegal value: '{}'",
                        value
                    )));
                }
                if value.starts_with('_') {
                    return Err(ctx.raise_error(&format!(
                        "Cannot have a tag value start with an underscore unless the entire value \
                         is quoted. You may be missing a data value on the previous line. \
                         Illegal value: '{}'",
                        value
                    )));
                }
            }

            // Capture value as TokenValue
            let value_token = if let Some(ref processed) = ctx.processed_token {
                TokenValue::Materialized(processed.clone())
            } else if let Some((start, end)) = ctx.token {
                TokenValue::Indexed(start, end)
            } else {
                TokenValue::Materialized(String::new())
            };

            // Collect tag-value pair for batch addition
            pending_tags.push((tag_name, value_token, tag_line));
        } else {
            // Invalid token in saveframe
            let frame_name = ctx.current_saveframe.as_ref().unwrap()
                .getattr(py, "name")?
                .extract::<String>(py)?;

            if frame_name == "internaluseyoushouldntseethis_frame" {
                return Err(ctx.raise_error(&format!(
                    "Invalid token found in loop contents. Expecting 'loop_' but found: '{}'",
                    token
                )));
            } else {
                return Err(ctx.raise_error(&format!(
                    "Invalid token found in saveframe '{}'. Expecting a tag, \
                     loop, or 'save_' token but found: '{}'",
                    frame_name, token
                )));
            }
        }
    }

    // Validate saveframe was properly closed
    if ctx.token.is_none() || !ctx.token_str().eq_ignore_ascii_case("save_") {
        return Err(ctx.raise_error(
            "Saveframe improperly terminated at end of file. Saveframes must be terminated \
             with the 'save_' token."
        ));
    }

    Ok(())
}

fn parse_loop_tags(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    // As with saveframe tags, each tag carries the line it was read from: they
    // are added to the loop in one batch, once the first data value is seen.
    let mut tags: Vec<(TokenValue, usize)> = Vec::new();

    while ctx.in_loop && ctx.get_token(py)? {
        let token = ctx.token_str();

        // Check if this is a tag
        if token.starts_with('_') && ctx.delimiter == ' ' {
            // Extract loop type from first tag (e.g., "_Entry_author.Ordinal" -> "_Entry_author")
            if tags.is_empty() {
                let loop_type = if let Some(dot_pos) = token.find('.') {
                    token[..dot_pos].to_string()
                } else {
                    // Tag without a dot - use the whole tag as loop type
                    token.to_string()
                };

                // Store loop type first
                ctx.current_loop_type = Some(loop_type);
            }

            // Capture tag as TokenValue
            let tag_value = if let Some(ref processed) = ctx.processed_token {
                TokenValue::Materialized(processed.clone())
            } else if let Some((start, end)) = ctx.token {
                TokenValue::Indexed(start, end)
            } else {
                TokenValue::Materialized(String::new())
            };

            // Collect tag for batch addition
            tags.push((tag_value, ctx.line_number));
        } else {
            // First non-tag token, batch add all tags to loop
            let loop_obj = ctx.current_loop.as_ref().unwrap();

            // Batch add all collected tags (materialize to strings for Python)
            if !tags.is_empty() && !add_loop_tags_fast(py, ctx, loop_obj, &tags)? {
                let materialized = PyList::new(py, tags
                    .iter()
                    .map(|(tv, _)| tv.to_py(py, &ctx.tokenizer.full_data)))?;
                let tags_before = tag_count(py, loop_obj)?;
                if let Err(error) = loop_obj.call_method1(py, "add_tag", (materialized,)) {
                    let lines: Vec<usize> = tags.iter().map(|(_, line)| *line).collect();
                    return Err(locate_failed_tag(py, error, loop_obj, tags_before, &lines));
                }
            }

            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            saveframe.call_method1(py, "add_loop", (loop_obj,))?;

            // Preallocate loop_data Vec based on number of tags
            // Use adaptive sizing based on loop type statistics
            let tags_len = tags.len();
            ctx.current_loop_tags_len = tags_len;
            if tags_len > 0 {
                let estimated_rows = if let Some(loop_type) = &ctx.current_loop_type {
                    // Look up statistics for this specific loop type
                    if let Some(stats) = ctx.loop_statistics.get(loop_type) {
                        let avg_items_per_loop = stats.total_data_items / stats.loop_count;
                        let avg_rows = (avg_items_per_loop / tags_len).max(10); // At least 10 rows
                        avg_rows
                    } else {
                        // First time seeing this loop type: use reasonable default
                        100
                    }
                } else {
                    // No loop type detected (shouldn't happen): use default
                    100
                };
                ctx.loop_data.reserve(tags_len * estimated_rows);
            }

            // Parse loop data (without consuming current token)
            parse_loop_data(py, ctx)?;
            break;
        }
    }

    Ok(())
}

fn parse_loop_data(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    loop {
        if ctx.token.is_none() {
            return Err(ctx.raise_error("Loop improperly terminated at end of file. \
                                        Loops must end with the 'stop_' token, but the \
                                        file ended without the stop token."));
        }

        let token = ctx.token_str();

        if token.eq_ignore_ascii_case("stop_") {
            if ctx.delimiter != ' ' {
                return Err(ctx.raise_error("The stop_ keyword may not be quoted or semicolon-delimited."));
            }

            let loop_obj = ctx.current_loop.as_ref().unwrap();
            let tags_len = ctx.current_loop_tags_len;

            // Warnings/errors for empty loops
            if tags_len == 0 {
                if ctx.raise_parse_warnings {
                    return Err(ctx.raise_error("Loop with no tags."));
                } else {
                    // Log warning via Python logger
                    let logging = py.import("logging")?;
                    let logger = logging.call_method1("getLogger", ("pynmrstar",))?;
                    logger.call_method1("warning", (format!("Loop with no tags in parsed file on line: {}", ctx.line_number),))?;
                }
            }

            if !ctx.seen_data {
                if ctx.raise_parse_warnings {
                    return Err(ctx.raise_error("Loop with no data."));
                } else {
                    // Log warning via Python logger
                    let logging = py.import("logging")?;
                    let logger = logging.call_method1("getLogger", ("pynmrstar",))?;
                    logger.call_method1("warning", (format!("Loop with no data on line: {}", ctx.line_number),))?;
                }
            }

            // Add data to loop
            if !ctx.loop_data.is_empty() {
                if ctx.loop_data.len() % tags_len != 0 {
                    let category = loop_obj.getattr(py, "category")?;
                    return Err(ctx.raise_error(&format!(
                        "The loop being parsed, '{}' does not have the expected number of data elements. \
                         This indicates that either one or more tag values are either missing from or \
                         duplicated in this loop.",
                        category.extract::<String>(py)?
                    )));
                }

                // Materialize TokenValues into Python strings only when passing to Python
                let loop_data_to_add = std::mem::take(&mut ctx.loop_data);
                let data_items_count = loop_data_to_add.len();
                let materialized = PyList::new(py, loop_data_to_add
                    .iter()
                    .map(|tv| tv.to_py(py, &ctx.tokenizer.full_data)))?;
                loop_obj.call_method(py, "add_data", (materialized,), Some(ctx.add_data_kwargs.bind(py).cast()?))?;

                // Track statistics for adaptive pre-allocation by loop type
                if let Some(loop_type) = &ctx.current_loop_type {
                    let stats = ctx.loop_statistics.entry(loop_type.clone()).or_insert(LoopStatistics {
                        total_data_items: 0,
                        loop_count: 0,
                    });
                    stats.total_data_items += data_items_count;
                    stats.loop_count += 1;
                }
            } else {
                // Track empty loops too (for accurate statistics)
                if let Some(loop_type) = &ctx.current_loop_type {
                    let stats = ctx.loop_statistics.entry(loop_type.clone()).or_insert(LoopStatistics {
                        total_data_items: 0,
                        loop_count: 0,
                    });
                    stats.loop_count += 1;
                }
            }

            ctx.loop_data.clear();
            ctx.current_loop = None;
            ctx.current_loop_type = None;
            ctx.current_loop_tags_len = 0;
            ctx.in_loop = false;
            break;

        } else if token.starts_with('_') && ctx.delimiter == ' ' {
            return Err(ctx.raise_error(&format!(
                "Cannot have more loop tags after loop data. Or perhaps this \
                 was a data value which was not quoted (but must be, \
                 if it starts with '_')? Value: '{}'.",
                token
            )));

        } else {
            // Data value
            let tags_len = ctx.current_loop_tags_len;

            if tags_len == 0 {
                return Err(ctx.raise_error(&format!(
                    "Data value found in loop before any loop tags were defined. Value: '{}'",
                    token
                )));
            }

            if is_reserved_keyword(token) && ctx.delimiter == ' ' {
                let mut error = format!(
                    "Cannot use keywords as data values unless quoted or semi-colon \
                     delimited. Perhaps this is a loop that wasn't properly terminated \
                     with a 'stop_' keyword before the saveframe ended or another loop \
                     began? Value found where 'stop_' or another data value expected: '{}'.",
                    token
                );

                if !ctx.loop_data.is_empty() {
                    let last_value = ctx.loop_data.last().unwrap().as_str(&ctx.tokenizer.full_data);
                    error.push_str(&format!(" Last loop data element parsed: '{}'.", last_value));
                }

                return Err(ctx.raise_error(&error));
            }

            // Store token as indices or materialized string
            let token_value = if let Some(ref processed) = ctx.processed_token {
                TokenValue::Materialized(processed.clone())
            } else if let Some((start, end)) = ctx.token {
                TokenValue::Indexed(start, end)
            } else {
                // Should never happen
                TokenValue::Materialized(String::new())
            };
            ctx.loop_data.push(token_value);
            ctx.seen_data = true;
        }

        // Get next token
        if !ctx.get_token(py)? {
            return Err(ctx.raise_error("Loop improperly terminated at end of file. \
                                        Loops must end with the 'stop_' token, but the \
                                        file ended without the stop token."));
        }
    }

    Ok(())
}

#[pyfunction]
#[pyo3(signature = (data, entry, source, raise_parse_warnings, convert_data_types, schema=None))]
pub fn parse(
    py: Python,
    data: String,
    entry: Py<PyAny>,
    source: String,
    raise_parse_warnings: bool,
    convert_data_types: bool,
    schema: Option<&Bound<PyAny>>,
) -> PyResult<Py<PyAny>> {
    // Convert to PyObject if Some
    let schema = schema.map(|s| s.clone().into());

    // Preprocess data (same as Python's Parser.load_data)
    // Fix DOS line endings
    let data = if data.contains('\r') { data.replace("\r\n", "\n").replace("\r", "\n") } else { data };
    // Change '\n; data ' started multi-lines to '\n;\ndata'
    let (data, inserted_lines) = fix_multiline_semicolons(&data);

    // Create tokenizer and load data
    let mut tokenizer = TokenizerState::new();
    tokenizer.load_string(data, inserted_lines);

    // Create parser context
    let mut ctx = ParserContext::new(py, entry.clone_ref(py), source,
                                     raise_parse_warnings, convert_data_types, schema, tokenizer)?;
    // Parse
    parse_initial(py, &mut ctx)?;
    parse_entry_body(py, &mut ctx)?;

    Ok(entry)
}
