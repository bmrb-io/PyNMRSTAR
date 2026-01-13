use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::IntoPyDict;
use pyo3::import_exception;
use std::sync::Mutex;

// Import the ParsingError exception from pynmrstar.exceptions
import_exception!(pynmrstar.exceptions, ParsingError);

const RESERVED_KEYWORDS: [&str; 5] = ["data_", "save_", "loop_", "stop_", "global_"];
const WHITESPACE_CHARS: [char; 4] = [' ', '\n', '\t', '\x0B']; // \v is \x0B

// Tokenizer state
struct TokenizerState {
    full_data: String,
    index: usize,
    line_no: usize,
    last_delimiter: char,
}

impl TokenizerState {
    fn new() -> Self {
        TokenizerState {
            full_data: String::new(),
            index: 0,
            line_no: 0,
            last_delimiter: ' ',
        }
    }

    fn reset(&mut self) {
        self.full_data.clear();
        self.index = 0;
        self.line_no = 0;
        self.last_delimiter = ' ';
    }

    fn load_string(&mut self, data: String) {
        self.reset();
        self.full_data = data;
    }

    fn is_whitespace(c: char) -> bool {
        WHITESPACE_CHARS.contains(&c)
    }

    fn pass_whitespace(&mut self) {
        let bytes = self.full_data.as_bytes();
        while self.index < bytes.len() {
            let c = bytes[self.index] as char;
            if Self::is_whitespace(c) {
                if c == '\n' {
                    self.line_no += 1;
                }
                self.index += 1;
            } else {
                break;
            }
        }
    }

    fn check_multiline(&self, length: usize) -> bool {
        let end = (self.index + length).min(self.full_data.len());
        let bytes = self.full_data.as_bytes();
        for i in self.index..end {
            if bytes[i] == b'\n' {
                return true;
            }
        }
        false
    }

    fn update_line_number(&mut self, start_pos: usize, length: usize) {
        let end = (start_pos + length).min(self.full_data.len());
        let bytes = self.full_data.as_bytes();
        for i in start_pos..end {
            if bytes[i] == b'\n' {
                self.line_no += 1;
            }
        }
    }

    fn find_substring(&self, needle: &str, start_pos: usize) -> Option<usize> {
        if start_pos >= self.full_data.len() {
            return None;
        }
        self.full_data[start_pos..].find(needle)
    }

    fn get_next_whitespace(&self, start_pos: usize) -> usize {
        let bytes = self.full_data.as_bytes();
        let mut pos = start_pos;
        while pos < bytes.len() {
            if Self::is_whitespace(bytes[pos] as char) {
                return pos;
            }
            pos += 1;
        }
        pos
    }

    fn get_token(&mut self) -> Result<Option<String>, String> {
        // Reset delimiter
        self.last_delimiter = '?';

        // Skip whitespace
        self.pass_whitespace();

        // Check if we're at the end
        if self.index >= self.full_data.len() {
            return Ok(None);
        }

        let bytes = self.full_data.as_bytes();

        // Handle comments
        if bytes[self.index] == b'#' {
            if let Some(length) = self.find_substring("\n", self.index) {
                let token = self.full_data[self.index..self.index + length].to_string();
                self.last_delimiter = '#';
                self.update_line_number(self.index, length + 1);
                self.index += length + 1;
                return Ok(Some(token));
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

                let token = self.full_data[self.index..self.index + length - 1].to_string();
                self.last_delimiter = ';';
                self.update_line_number(self.index, length);
                self.index += length;
                return Ok(Some(token));
            } else {
                return Err(format!("Invalid file. Semicolon-delineated value was not terminated. Error on line: {}", self.line_no + 1));
            }
        }

        // Handle single-quoted values
        if bytes[self.index] == b'\'' {
            if let Some(mut end_quote) = self.find_substring("'", self.index + 1) {
                // Make sure we don't stop for quotes not followed by whitespace
                loop {
                    let absolute_quote_pos = self.index + end_quote + 1;
                    if absolute_quote_pos + 1 < bytes.len() && !Self::is_whitespace(bytes[absolute_quote_pos + 1] as char) {
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
                    return Err(format!("Invalid file. Single quoted value was not terminated on the same line it began. Error on line: {}", self.line_no + 1));
                }

                self.index += 1;
                let token = self.full_data[self.index..self.index + end_quote].to_string();
                self.last_delimiter = '\'';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some(token));
            } else {
                return Err(format!("Invalid file. Single quoted value was not terminated. Error on line: {}", self.line_no + 1));
            }
        }

        // Handle double-quoted values
        if bytes[self.index] == b'"' {
            if let Some(mut end_quote) = self.find_substring("\"", self.index + 1) {
                // Make sure we don't stop for quotes not followed by whitespace
                loop {
                    let absolute_quote_pos = self.index + end_quote + 1;
                    if absolute_quote_pos + 1 < bytes.len() && !Self::is_whitespace(bytes[absolute_quote_pos + 1] as char) {
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
                    return Err(format!("Invalid file. Double quoted value was not terminated on the same line it began. Error on line: {}", self.line_no + 1));
                }

                self.index += 1;
                let token = self.full_data[self.index..self.index + end_quote].to_string();
                self.last_delimiter = '"';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some(token));
            } else {
                return Err(format!("Invalid file. Double quoted value was not terminated. Error on line: {}", self.line_no + 1));
            }
        }

        // Handle normal unquoted tokens
        let end_pos = self.get_next_whitespace(self.index);
        let token = self.full_data[self.index..end_pos].to_string();

        // Determine delimiter
        if self.index == 0 {
            self.last_delimiter = ' ';
        } else {
            self.last_delimiter = ' ';
        }

        // Check if it's a reference (starts with $ and delimiter was space)
        if token.starts_with('$') && self.last_delimiter == ' ' && token.len() > 1 {
            self.last_delimiter = '$';
        }

        self.update_line_number(self.index, end_pos - self.index + 1);
        self.index = end_pos + 1;
        Ok(Some(token))
    }

    fn get_token_full(&mut self) -> Result<Option<(String, usize, char)>, String> {
        // Get token and skip comments
        loop {
            match self.get_token()? {
                Some(token) => {
                    if self.last_delimiter != '#' {
                        // Unwrap embedded STAR if all lines start with three spaces
                        let processed_token = if self.last_delimiter == ';' && token.starts_with("\n   ") {
                            let mut shift_over = true;
                            let lines: Vec<&str> = token.split('\n').collect();

                            for line in &lines[1..] {  // Skip first empty line
                                if !line.is_empty() && !line.starts_with("   ") {
                                    shift_over = false;
                                    break;
                                }
                            }

                            if shift_over && token.contains("\n   ;") {
                                // Remove the trailing newline and shift text over
                                let mut processed = token.trim_end_matches('\n').to_string();
                                processed = processed.replace("\n   ", "\n");
                                processed
                            } else {
                                token
                            }
                        } else {
                            token
                        };

                        return Ok(Some((processed_token, self.line_no, self.last_delimiter)));
                    }
                    // If it's a comment, continue to get the next token
                }
                None => return Ok(None),
            }
        }
    }
}

// Global tokenizer state
static TOKENIZER: Mutex<TokenizerState> = Mutex::new(TokenizerState {
    full_data: String::new(),
    index: 0,
    line_no: 0,
    last_delimiter: ' ',
});

#[derive(Debug)]
enum ParserState {
    Initial,
    EntryBody,
    SaveframeBody,
    LoopTags,
    LoopData,
}

// Python-facing tokenizer functions
#[pyfunction]
fn reset() -> PyResult<()> {
    let mut tokenizer = TOKENIZER.lock().unwrap();
    tokenizer.reset();
    Ok(())
}

#[pyfunction]
fn get_token_full(py: Python) -> PyResult<Option<(String, usize, char)>> {
    let mut tokenizer = TOKENIZER.lock().unwrap();
    match tokenizer.get_token_full() {
        Ok(result) => Ok(result),
        Err(e) => Err(ParsingError::new_err(e)),
    }
}

#[pyfunction]
fn quote_value(py: Python, orig: &Bound<PyAny>) -> PyResult<String> {
    // Convert to string
    let str_obj = orig.str()?;
    let s = str_obj.to_str()?;

    // Get length
    let len = s.len();

    // Don't allow empty string
    if len == 0 {
        return Err(PyValueError::new_err("Empty strings are not allowed as values. Use the None singleton, or '.' to represent null values."));
    }

    // Handle embedded STAR format multiline comments
    if s.contains("\n;") {
        let replaced = s.replace("\n", "\n   ");

        // Check if we need newlines at start/end
        let needs_start_newline = !replaced.starts_with('\n');
        let needs_end_newline = !replaced.ends_with('\n');

        return Ok(match (needs_start_newline, needs_end_newline) {
            (true, true) => format!("\n   {}\n", replaced),
            (true, false) => format!("\n   {}", replaced),
            (false, true) => format!("{}\n", replaced),
            (false, false) => replaced,
        });
    }

    // If it has newlines but not "\n;", handle multiline
    if s.contains('\n') {
        if s.ends_with('\n') {
            return Ok(s.to_string());
        } else {
            return Ok(format!("{}\n", s));
        }
    }

    // Check for quotes
    let has_single = s.contains('\'');
    let has_double = s.contains('"');

    // If it has both single and double quotes, need special handling
    if has_single && has_double {
        let chars: Vec<char> = s.chars().collect();
        let mut can_wrap_single = true;
        let mut can_wrap_double = true;

        for i in 0..chars.len()-1 {
            if TokenizerState::is_whitespace(chars[i+1]) {
                if chars[i] == '\'' {
                    can_wrap_single = false;
                }
                if chars[i] == '"' {
                    can_wrap_double = false;
                }
            }
        }

        if !can_wrap_single && !can_wrap_double {
            return Ok(format!("{}\n", s));
        }
        if can_wrap_single {
            return Ok(format!("'{}'", s));
        }
        if can_wrap_double {
            return Ok(format!("\"{}\"", s));
        }
    }

    // Check if we need wrapping
    let mut needs_wrapping = false;

    // Check first character
    if s.starts_with('_') || s.starts_with('"') || s.starts_with('\'') {
        needs_wrapping = true;
    }

    if !needs_wrapping {
        let lower = s.to_lowercase();

        // Check for reserved keywords
        if lower.starts_with("data_") || lower.starts_with("save_") ||
           lower.starts_with("loop_") || lower.starts_with("stop_") ||
           lower.starts_with("global_") {
            needs_wrapping = true;
        }

        // Check for whitespace or problematic characters
        if !needs_wrapping {
            let chars: Vec<char> = s.chars().collect();
            for i in 0..chars.len() {
                if TokenizerState::is_whitespace(chars[i]) {
                    needs_wrapping = true;
                    break;
                }
                // The pound sign only needs quotes if preceded by whitespace
                if chars[i] == '#' {
                    if i == 0 || TokenizerState::is_whitespace(chars[i-1]) {
                        needs_wrapping = true;
                        break;
                    }
                }
            }
        }
    }

    if needs_wrapping {
        // If there is a single quote wrap in double quotes
        if has_single {
            return Ok(format!("\"{}\"", s));
        }
        // Either there is a double quote or no quotes
        else {
            return Ok(format!("'{}'", s));
        }
    }

    // If we got here it's good to go as is
    Ok(s.to_string())
}

struct ParserContext {
    line_number: usize,
    delimiter: String,
    token: Option<String>,
    entry: PyObject,
    current_saveframe: Option<PyObject>,
    current_loop: Option<PyObject>,
    loop_data: Vec<String>,
    seen_data: bool,
    in_loop: bool,
    source: String,
    raise_parse_warnings: bool,
    convert_data_types: bool,
    schema: Option<PyObject>,
}

impl ParserContext {
    fn new(_py: Python, entry: PyObject, source: String, raise_parse_warnings: bool,
           convert_data_types: bool, schema: Option<PyObject>) -> Self {
        ParserContext {
            line_number: 0,
            delimiter: " ".to_string(),
            token: None,
            entry,
            current_saveframe: None,
            current_loop: None,
            loop_data: Vec::new(),
            seen_data: false,
            in_loop: false,
            source,
            raise_parse_warnings,
            convert_data_types,
            schema,
        }
    }

    fn get_token(&mut self, py: Python) -> PyResult<Option<String>> {
        let mut tokenizer = TOKENIZER.lock().unwrap();
        match tokenizer.get_token_full() {
            Ok(Some((token, line_no, delimiter))) => {
                self.token = Some(token.clone());
                self.line_number = line_no;
                self.delimiter = delimiter.to_string();
                Ok(Some(token))
            }
            Ok(None) => {
                self.token = None;
                Ok(None)
            }
            Err(e) => Err(ParsingError::new_err(e)),
        }
    }

    fn raise_error(&self, message: &str) -> PyErr {
        ParsingError::new_err(format!("{} (line {})", message, self.line_number))
    }
}

fn is_reserved_keyword(token: &str) -> bool {
    let lower = token.to_lowercase();
    RESERVED_KEYWORDS.iter().any(|&kw| lower == kw)
}

fn parse_initial(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    // Get first token
    ctx.get_token(py)?;

    let token = ctx.token.as_ref()
        .ok_or_else(|| ctx.raise_error("Empty file"))?;

    // Validate data_ token
    if !token.to_lowercase().starts_with("data_") {
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

    if ctx.delimiter != " " {
        return Err(ctx.raise_error("The data_ keyword may not be quoted or semicolon-delimited."));
    }

    // Set entry_id
    let entry_id = &token[5..];
    ctx.entry.setattr(py, "_entry_id", entry_id)?;

    Ok(())
}

fn parse_entry_body(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    while ctx.get_token(py)?.is_some() {
        let token = ctx.token.as_ref().unwrap();

        if !token.to_lowercase().starts_with("save_") {
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

        if ctx.delimiter != " " {
            return Err(ctx.raise_error("The save_ keyword may not be quoted or semicolon-delimited."));
        }

        // Create new saveframe
        let saveframe_name = &token[5..];
        let saveframe_mod = py.import("pynmrstar.saveframe")?;
        let saveframe_class = saveframe_mod.getattr("Saveframe")?;

        let saveframe = saveframe_class.call_method(
            "from_scratch",
            (saveframe_name,),
            Some(&[("source", &ctx.source)].into_py_dict(py)?)
        )?;

        ctx.current_saveframe = Some(saveframe.into());
        ctx.entry.call_method1(py, "add_saveframe", (ctx.current_saveframe.as_ref().unwrap(),))?;

        // Parse saveframe body
        parse_saveframe_body(py, ctx)?;
    }

    Ok(())
}

fn parse_saveframe_body(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    while ctx.get_token(py)?.is_some() {
        let token = ctx.token.as_ref().unwrap().clone();
        let token_lower = token.to_lowercase();

        if token_lower == "loop_" {
            if ctx.delimiter != " " {
                return Err(ctx.raise_error("The loop_ keyword may not be quoted or semicolon-delimited."));
            }

            // Create new loop
            let loop_mod = py.import("pynmrstar.loop")?;
            let loop_class = loop_mod.getattr("Loop")?;
            let new_loop = loop_class.call_method(
                "from_scratch",
                (),
                Some(&[("source", &ctx.source)].into_py_dict(py)?)
            )?;

            ctx.current_loop = Some(new_loop.into());
            ctx.loop_data.clear();
            ctx.seen_data = false;
            ctx.in_loop = true;

            parse_loop_tags(py, ctx)?;

        } else if token_lower == "save_" {
            if ctx.delimiter != " " && ctx.delimiter != ";" {
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
            if ctx.delimiter != " " {
                return Err(ctx.raise_error(&format!(
                    "Saveframe tags may not be quoted or semicolon-delimited. Quoted tag: '{}'.",
                    token
                )));
            }

            let tag_name = token.clone();

            // Get tag value
            ctx.get_token(py)?;
            let value = ctx.token.as_ref()
                .ok_or_else(|| ctx.raise_error("Tag without value"))?;

            if ctx.delimiter == " " {
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

            // Add tag to saveframe
            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            let kwargs = if ctx.schema.is_some() {
                [
                    ("convert_data_types", ctx.convert_data_types.into_py(py)),
                    ("schema", ctx.schema.as_ref().unwrap().clone_ref(py))
                ].into_py_dict(py)?
            } else {
                [("convert_data_types", ctx.convert_data_types.into_py(py))]
                    .into_py_dict(py)?
            };

            saveframe.call_method(py, "add_tag", (tag_name, value), Some(&kwargs))?;
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
    if ctx.token.is_none() || ctx.token.as_ref().unwrap().to_lowercase() != "save_" {
        return Err(ctx.raise_error(
            "Saveframe improperly terminated at end of file. Saveframes must be terminated \
             with the 'save_' token."
        ));
    }

    Ok(())
}

fn parse_loop_tags(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    while ctx.in_loop && ctx.get_token(py)?.is_some() {
        let token = ctx.token.as_ref().unwrap();

        // Check if this is a tag
        if token.starts_with('_') && ctx.delimiter == " " {
            // Add tag to loop
            let loop_obj = ctx.current_loop.as_ref().unwrap();
            loop_obj.call_method1(py, "add_tag", (token,))?;
        } else {
            // First non-tag token, add loop to saveframe and switch to data parsing
            let loop_obj = ctx.current_loop.as_ref().unwrap();
            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            saveframe.call_method1(py, "add_loop", (loop_obj,))?;

            // Parse loop data (without consuming current token)
            parse_loop_data(py, ctx)?;
            break;
        }
    }

    Ok(())
}

fn parse_loop_data(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    loop {
        let token = ctx.token.as_ref()
            .ok_or_else(|| ctx.raise_error("Loop improperly terminated at end of file. \
                                             Loops must end with the 'stop_' token, but the \
                                             file ended without the stop token."))?;
        let token_lower = token.to_lowercase();

        if token_lower == "stop_" {
            if ctx.delimiter != " " {
                return Err(ctx.raise_error("The stop_ keyword may not be quoted or semicolon-delimited."));
            }

            let loop_obj = ctx.current_loop.as_ref().unwrap();
            let tags = loop_obj.bind(py).getattr("tags")?;
            let tags_len = tags.len()?;

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

                let kwargs = if ctx.schema.is_some() {
                    [
                        ("rearrange", true.into_py(py)),
                        ("convert_data_types", ctx.convert_data_types.into_py(py)),
                        ("schema", ctx.schema.as_ref().unwrap().clone_ref(py))
                    ].into_py_dict(py)?
                } else {
                    [
                        ("rearrange", true.into_py(py)),
                        ("convert_data_types", ctx.convert_data_types.into_py(py))
                    ].into_py_dict(py)?
                };

                loop_obj.call_method(py, "add_data", (ctx.loop_data.clone(),), Some(&kwargs))?;
            }

            ctx.loop_data.clear();
            ctx.current_loop = None;
            ctx.in_loop = false;
            break;

        } else if token.starts_with('_') && ctx.delimiter == " " {
            return Err(ctx.raise_error(&format!(
                "Cannot have more loop tags after loop data. Or perhaps this \
                 was a data value which was not quoted (but must be, \
                 if it starts with '_')? Value: '{}'.",
                token
            )));

        } else {
            // Data value
            let loop_obj = ctx.current_loop.as_ref().unwrap();
            let tags = loop_obj.bind(py).getattr("tags")?;
            let tags_len = tags.len()?;

            if tags_len == 0 {
                return Err(ctx.raise_error(&format!(
                    "Data value found in loop before any loop tags were defined. Value: '{}'",
                    token
                )));
            }

            if is_reserved_keyword(token) && ctx.delimiter == " " {
                let mut error = format!(
                    "Cannot use keywords as data values unless quoted or semi-colon \
                     delimited. Perhaps this is a loop that wasn't properly terminated \
                     with a 'stop_' keyword before the saveframe ended or another loop \
                     began? Value found where 'stop_' or another data value expected: '{}'.",
                    token
                );

                if !ctx.loop_data.is_empty() {
                    error.push_str(&format!(" Last loop data element parsed: '{}'.",
                                           ctx.loop_data.last().unwrap()));
                }

                return Err(ctx.raise_error(&error));
            }

            ctx.loop_data.push(token.clone());
            ctx.seen_data = true;
        }

        // Get next token
        ctx.get_token(py)?;
    }

    Ok(())
}

#[pyfunction]
#[pyo3(signature = (data, entry, source, raise_parse_warnings, convert_data_types, schema=None))]
fn parse(
    py: Python,
    data: String,
    entry: PyObject,
    source: String,
    raise_parse_warnings: bool,
    convert_data_types: bool,
    schema: Option<&Bound<PyAny>>,
) -> PyResult<PyObject> {
    // Convert to PyObject if Some
    let schema = schema.map(|s| s.clone().into());

    // Preprocess data (same as Python's Parser.load_data)
    // Fix DOS line endings
    let data = data.replace("\r\n", "\n").replace("\r", "\n");
    // Change '\n; data ' started multi-lines to '\n;\ndata'
    let re = regex::Regex::new(r"\n;([^\n]+?)\n").unwrap();
    let data = re.replace_all(&data, "\n;\n$1\n").to_string();

    // Load data into tokenizer (using Rust tokenizer directly)
    let mut tokenizer = TOKENIZER.lock().unwrap();
    tokenizer.load_string(data);
    drop(tokenizer); // Release the lock

    // Create parser context
    let mut ctx = ParserContext::new(py, entry.clone_ref(py), source,
                                     raise_parse_warnings, convert_data_types, schema);
    // Parse
    parse_initial(py, &mut ctx)?;
    parse_entry_body(py, &mut ctx)?;

    // Reset the tokenizer
    let mut tokenizer = TOKENIZER.lock().unwrap();
    tokenizer.reset();

    Ok(entry)
}

#[pymodule]
fn pynmrstar_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(reset, m)?)?;
    m.add_function(wrap_pyfunction!(get_token_full, m)?)?;
    m.add_function(wrap_pyfunction!(quote_value, m)?)?;
    Ok(())
}
