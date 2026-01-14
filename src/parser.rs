use pyo3::prelude::*;
use pyo3::types::IntoPyDict;
use pyo3::import_exception;

use crate::utils::{fix_multiline_semicolons, is_reserved_keyword, starts_with_ignore_case};

// Import the ParsingError exception from pynmrstar.exceptions
import_exception!(pynmrstar.exceptions, ParsingError);

// Tokenizer state
pub struct TokenizerState {
    pub full_data: String,
    index: usize,
    pub line_no: usize,
    pub last_delimiter: char,
}

impl TokenizerState {
    pub fn new() -> Self {
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

    pub fn load_string(&mut self, data: String) {
        self.reset();
        self.full_data = data;
    }

    fn is_whitespace(c: char) -> bool {
        matches!(c, ' ' | '\n' | '\t' | '\x0B')
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

        // Optimize single-byte searches to work directly with bytes
        if needle.len() == 1 {
            let needle_byte = needle.as_bytes()[0];
            let bytes = self.full_data.as_bytes();
            for i in start_pos..bytes.len() {
                if bytes[i] == needle_byte {
                    return Some(i - start_pos);
                }
            }
            return None;
        }

        // Optimize two-byte searches (e.g., "\n;")
        if needle.len() == 2 {
            let needle_bytes = needle.as_bytes();
            let bytes = self.full_data.as_bytes();
            for i in start_pos..bytes.len().saturating_sub(1) {
                if bytes[i] == needle_bytes[0] && bytes[i + 1] == needle_bytes[1] {
                    return Some(i - start_pos);
                }
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
            if Self::is_whitespace(bytes[pos] as char) {
                return pos;
            }
            pos += 1;
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
                let start = self.index;
                let end = self.index + end_quote;
                self.last_delimiter = '\'';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some((start, end)));
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
                let start = self.index;
                let end = self.index + end_quote;
                self.last_delimiter = '"';
                self.update_line_number(self.index, end_quote + 1);
                self.index += end_quote + 1;
                return Ok(Some((start, end)));
            } else {
                return Err(format!("Invalid file. Double quoted value was not terminated. Error on line: {}", self.line_no + 1));
            }
        }

        // Handle normal unquoted tokens
        let end_pos = self.get_next_whitespace(self.index);
        let start = self.index;
        let end = end_pos;

        // Determine delimiter
        if self.index == 0 {
            self.last_delimiter = ' ';
        } else {
            self.last_delimiter = ' ';
        }

        // Check if it's a reference (starts with $ and delimiter was space)
        let token_slice = &self.full_data[start..end];
        if token_slice.starts_with('$') && self.last_delimiter == ' ' && token_slice.len() > 1 {
            self.last_delimiter = '$';
        }

        self.update_line_number(self.index, end_pos - self.index + 1);
        self.index = end_pos + 1;
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
    fn to_string(&self, full_data: &str) -> String {
        match self {
            TokenValue::Indexed(start, end) => full_data[*start..*end].to_string(),
            TokenValue::Materialized(s) => s.clone(),
        }
    }

    fn as_str<'a>(&'a self, full_data: &'a str) -> std::borrow::Cow<'a, str> {
        match self {
            TokenValue::Indexed(start, end) => std::borrow::Cow::Borrowed(&full_data[*start..*end]),
            TokenValue::Materialized(s) => std::borrow::Cow::Borrowed(s),
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

        Ok(ParserContext {
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
        })
    }

    fn get_token(&mut self) -> PyResult<bool> {
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
                        self.line_number = self.tokenizer.line_no;
                        self.delimiter = self.tokenizer.last_delimiter;
                        return Ok(true);
                    }
                    // If it's a comment, continue to get the next token
                }
                Ok(None) => {
                    self.token = None;
                    return Ok(false);
                }
                Err(e) => return Err(ParsingError::new_err(e)),
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
        ParsingError::new_err(format!("{} (line {})", message, self.line_number))
    }
}

fn parse_initial(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    // Get first token
    if !ctx.get_token()? {
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
    while ctx.get_token()? {
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

        ctx.current_saveframe = Some(saveframe.into());
        ctx.entry.call_method1(py, "add_saveframe", (ctx.current_saveframe.as_ref().unwrap(),))?;

        // Parse saveframe body
        parse_saveframe_body(py, ctx)?;
    }

    Ok(())
}

fn parse_saveframe_body(py: Python, ctx: &mut ParserContext) -> PyResult<()> {
    let mut pending_tags: Vec<(TokenValue, TokenValue)> = Vec::new();

    // Helper to flush pending tags
    let flush_tags = |ctx: &ParserContext, pending: &mut Vec<(TokenValue, TokenValue)>| -> PyResult<()> {
        if !pending.is_empty() {
            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            // Materialize TokenValues into (String, String) tuples for Python
            let tags_to_add = std::mem::take(pending);
            let materialized: Vec<(String, String)> = tags_to_add
                .iter()
                .map(|(tag, value)| (tag.to_string(&ctx.tokenizer.full_data), value.to_string(&ctx.tokenizer.full_data)))
                .collect();
            saveframe.call_method(py, "add_tags", (materialized,), Some(ctx.add_tags_kwargs.bind(py).cast()?))?;
        }
        Ok(())
    };

    while ctx.get_token()? {
        let token = ctx.token_str();

        if token.eq_ignore_ascii_case("loop_") {
            // Flush any pending tags before processing loop
            flush_tags(ctx, &mut pending_tags)?;
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
            flush_tags(ctx, &mut pending_tags)?;

            if ctx.delimiter != ' ' && ctx.delimiter != ';' {
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
            let tag_name = if let Some(ref processed) = ctx.processed_token {
                TokenValue::Materialized(processed.clone())
            } else if let Some((start, end)) = ctx.token {
                TokenValue::Indexed(start, end)
            } else {
                TokenValue::Materialized(String::new())
            };

            // Get tag value
            if !ctx.get_token()? {
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
            pending_tags.push((tag_name, value_token));
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
    let mut tags: Vec<TokenValue> = Vec::new();

    while ctx.in_loop && ctx.get_token()? {
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
            tags.push(tag_value);
        } else {
            // First non-tag token, batch add all tags to loop
            let loop_obj = ctx.current_loop.as_ref().unwrap();

            // Batch add all collected tags (materialize to strings for Python)
            if !tags.is_empty() {
                let materialized: Vec<String> = tags
                    .iter()
                    .map(|tv| tv.to_string(&ctx.tokenizer.full_data))
                    .collect();
                loop_obj.call_method1(py, "add_tag", (materialized.as_slice(),))?;
            }

            let saveframe = ctx.current_saveframe.as_ref().unwrap();
            saveframe.call_method1(py, "add_loop", (loop_obj,))?;

            // Preallocate loop_data Vec based on number of tags
            // Use adaptive sizing based on loop type statistics
            let tags_len = tags.len();
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

                // Materialize TokenValues into Strings only when passing to Python
                let loop_data_to_add = std::mem::take(&mut ctx.loop_data);
                let data_items_count = loop_data_to_add.len();
                let materialized: Vec<String> = loop_data_to_add
                    .iter()
                    .map(|tv| tv.to_string(&ctx.tokenizer.full_data))
                    .collect();
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
            let loop_obj = ctx.current_loop.as_ref().unwrap();
            let tags = loop_obj.bind(py).getattr("tags")?;
            let tags_len = tags.len()?;

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
        if !ctx.get_token()? {
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
    let data = data.replace("\r\n", "\n").replace("\r", "\n");
    // Change '\n; data ' started multi-lines to '\n;\ndata'
    let data = fix_multiline_semicolons(&data);

    // Create tokenizer and load data
    let mut tokenizer = TokenizerState::new();
    tokenizer.load_string(data);

    // Create parser context
    let mut ctx = ParserContext::new(py, entry.clone_ref(py), source,
                                     raise_parse_warnings, convert_data_types, schema, tokenizer)?;
    // Parse
    parse_initial(py, &mut ctx)?;
    parse_entry_body(py, &mut ctx)?;

    Ok(entry)
}
