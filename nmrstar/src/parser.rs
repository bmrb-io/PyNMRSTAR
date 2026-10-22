//! The NMR-STAR tokenizer and parser.

use std::borrow::Cow;
use std::collections::HashSet;

use log::warn;

use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::quoting::{fix_multiline_semicolons, is_reserved_keyword, starts_with_ignore_case};
use crate::saveframe::{AddMode, Saveframe};
use crate::schema::Schema;
use crate::star_loop::Loop;
use crate::value::Value;

/// Options controlling how NMR-STAR is parsed.
#[derive(Clone, Copy, Default)]
pub struct ParseOptions<'a> {
    /// Convert the values read into the types the dictionary declares for their tags: integers,
    /// decimals and dates. Text tags stay text, and null values become `None`.
    pub convert_data_types: bool,
    /// Raise a parsing error, rather than logging a warning, for problems which can be ignored.
    pub raise_parse_warnings: bool,
    /// The schema used to convert data types. The default schema if not given.
    pub schema: Option<&'a Schema>,
}

impl<'a> ParseOptions<'a> {
    pub fn new() -> ParseOptions<'a> {
        ParseOptions::default()
    }

    pub fn convert_data_types(mut self, convert: bool) -> Self {
        self.convert_data_types = convert;
        self
    }

    pub fn raise_parse_warnings(mut self, raise: bool) -> Self {
        self.raise_parse_warnings = raise;
        self
    }

    pub fn schema(mut self, schema: &'a Schema) -> Self {
        self.schema = Some(schema);
        self
    }
}

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

/// Splits NMR-STAR text into tokens.
struct Tokenizer<'a> {
    data: Cow<'a, str>,
    index: usize,
    line_no: usize,
    /// Line number (1-based) on which the token last returned by get_token began. line_no can
    /// not be used for this: it is advanced past the token, and past the whitespace which
    /// follows it.
    token_line: usize,
    last_delimiter: char,
    /// Line number (0-based) where non-standard whitespace was first encountered, if any.
    unusual_whitespace_line: Option<usize>,
    /// Lines the data gained over the file it was read from, from fix_multiline_semicolons()
    /// splitting `;content` in two. See source_line().
    inserted_lines: Vec<usize>,
}

impl<'a> Tokenizer<'a> {
    fn new(data: Cow<'a, str>, inserted_lines: Vec<usize>) -> Self {
        Tokenizer {
            data,
            index: 0,
            line_no: 0,
            token_line: 0,
            last_delimiter: ' ',
            unusual_whitespace_line: None,
            inserted_lines,
        }
    }

    /// Translate a line number in the data being tokenized back to the line of the file it
    /// came from.
    fn source_line(&self, line: usize) -> usize {
        if self.inserted_lines.is_empty() {
            return line;
        }
        line - self.inserted_lines.partition_point(|&inserted| inserted < line)
    }

    fn is_standard_whitespace(b: u8) -> bool {
        matches!(b, b' ' | b'\n' | b'\t' | b'\r' | b'\x0B')
    }

    /// The number of bytes of the whitespace character at a position, or 0 if there is none.
    fn whitespace_len_at(s: &str, pos: usize) -> usize {
        if pos >= s.len() {
            return 0;
        }
        match BYTE_CLASS[s.as_bytes()[pos] as usize] {
            CLASS_OTHER => 0,
            CLASS_WHITESPACE | CLASS_UNUSUAL_WHITESPACE => 1,
            _ => Self::unicode_whitespace_len_at(s, pos),
        }
    }

    #[cold]
    fn unicode_whitespace_len_at(s: &str, pos: usize) -> usize {
        if !s.is_char_boundary(pos) {
            return 0;
        }
        match s[pos..].chars().next() {
            Some(c) if c.is_whitespace() => c.len_utf8(),
            _ => 0,
        }
    }

    fn pass_whitespace(&mut self) {
        let bytes = self.data.as_bytes();
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
                    let len = Self::whitespace_len_at(&self.data, index);
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
        let end = (self.index + length).min(self.data.len());
        memchr::memchr(b'\n', &self.data.as_bytes()[self.index..end]).is_some()
    }

    fn update_line_number(&mut self, start_pos: usize, length: usize) {
        let end = (start_pos + length).min(self.data.len());
        self.line_no += memchr::memchr_iter(b'\n', &self.data.as_bytes()[start_pos..end]).count();
    }

    fn find_byte(&self, needle: u8, start_pos: usize) -> Option<usize> {
        if start_pos >= self.data.len() {
            return None;
        }
        memchr::memchr(needle, &self.data.as_bytes()[start_pos..])
    }

    /// Find "\n;" from a position.
    fn find_semicolon_end(&self, start_pos: usize) -> Option<usize> {
        if start_pos >= self.data.len() {
            return None;
        }
        memchr::memmem::find(&self.data.as_bytes()[start_pos..], b"\n;")
    }

    fn get_next_whitespace(&self, start_pos: usize) -> usize {
        let bytes = self.data.as_bytes();
        let mut pos = start_pos;
        while pos < bytes.len() {
            match BYTE_CLASS[bytes[pos] as usize] {
                CLASS_OTHER => pos += 1,
                CLASS_NON_ASCII => {
                    if Self::whitespace_len_at(&self.data, pos) > 0 {
                        return pos;
                    }
                    pos += 1;
                }
                _ => return pos,
            }
        }
        pos
    }

    /// Scan a quoted value starting at self.index, returning the position of the closing
    /// quote relative to the character after the opening one. A quote only closes the value
    /// when it is followed by whitespace (or ends the data).
    fn find_closing_quote(&self, quote: u8, name: &str) -> std::result::Result<usize, String> {
        let mut end_quote = match self.find_byte(quote, self.index + 1) {
            Some(end_quote) => end_quote,
            None => return Err(format!("Invalid file. {} quoted value was not terminated.", name)),
        };
        loop {
            let absolute_quote_pos = self.index + end_quote + 1;
            if absolute_quote_pos + 1 < self.data.len()
                && Self::whitespace_len_at(&self.data, absolute_quote_pos + 1) == 0 {
                match self.find_byte(quote, absolute_quote_pos + 1) {
                    Some(next) => end_quote = (absolute_quote_pos - self.index - 1) + next + 1,
                    None => return Err(format!(
                        "Invalid file. {} quoted value was never terminated at end of file.", name)),
                }
            } else {
                return Ok(end_quote);
            }
        }
    }

    /// The next token, as a range of the data, or None at the end of the data.
    fn get_token(&mut self) -> std::result::Result<Option<(usize, usize)>, String> {
        self.last_delimiter = '?';
        self.pass_whitespace();

        if self.index >= self.data.len() {
            return Ok(None);
        }

        // The whitespace before the token has been passed, so line_no now names the line the
        // token starts on
        self.token_line = self.source_line(self.line_no + 1);

        let bytes = self.data.as_bytes();

        // Comments
        if bytes[self.index] == b'#' {
            return match self.find_byte(b'\n', self.index) {
                Some(length) => {
                    let start = self.index;
                    self.last_delimiter = '#';
                    self.line_no += 1;
                    self.index += length + 1;
                    Ok(Some((start, start + length)))
                }
                // Comment at end of file with no newline
                None => Ok(None),
            };
        }

        // Multiline values (semicolon-delimited)
        if self.index + 1 < bytes.len() && bytes[self.index] == b';' && bytes[self.index + 1] == b'\n' {
            return match self.find_semicolon_end(self.index) {
                Some(length) => {
                    self.line_no += 1;
                    self.index += 2;
                    let start = self.index;
                    let end = self.index + length - 1;
                    self.last_delimiter = ';';
                    self.update_line_number(self.index, length);
                    self.index += length;
                    Ok(Some((start, end)))
                }
                None => Err("Invalid file. Semicolon-delineated value was not terminated.".to_string()),
            };
        }

        // Quoted values
        for (quote, name) in [(b'\'', "Single"), (b'"', "Double")] {
            if bytes[self.index] == quote {
                let end_quote = self.find_closing_quote(quote, name)?;
                if self.check_multiline(end_quote + 1) {
                    return Err(format!(
                        "Invalid file. {} quoted value was not terminated on the same line it began.", name));
                }
                self.index += 1;
                let start = self.index;
                let end = self.index + end_quote;
                self.last_delimiter = quote as char;
                self.index += end_quote + 1;
                return Ok(Some((start, end)));
            }
        }

        // Unquoted tokens
        let end = self.get_next_whitespace(self.index);
        let start = self.index;
        self.last_delimiter = ' ';
        let token = &self.data[start..end];
        if token.starts_with('$') && token.len() > 1 {
            self.last_delimiter = '$';
        }

        // The token ends at the first whitespace, so the only newline it can pass is the one
        // ending it
        if self.data.as_bytes().get(end) == Some(&b'\n') {
            self.line_no += 1;
        }
        let ws_len = Self::whitespace_len_at(&self.data, end);
        if ws_len > 0 && self.unusual_whitespace_line.is_none()
            && !Self::is_standard_whitespace(self.data.as_bytes()[end]) {
            self.unusual_whitespace_line = Some(self.line_no);
        }
        self.index = end + ws_len;
        Ok(Some((start, end)))
    }
}

/// The parsing state.
struct Parser<'a, 'o> {
    tokenizer: Tokenizer<'a>,
    /// The line the current token began on
    line_number: usize,
    delimiter: char,
    token: Option<(usize, usize)>,
    /// The text of the current token, when it had to be changed (embedded STAR)
    processed_token: Option<String>,
    options: ParseOptions<'o>,
    source: String,
    warned_unusual_whitespace: bool,
    saveframe_names: HashSet<String>,
}

const UNUSUAL_WHITESPACE: &str = "Non-standard whitespace character found. Only standard whitespace characters \
    (space, tab, newline, vertical tab, carriage return) are expected in NMR-STAR files.";

/// A ParsingError naming a line of the file. Line 0 means no token has been read yet, so there
/// is no line to name.
fn parsing_error(message: impl Into<String>, line_number: usize) -> Error {
    Error::parsing(message, if line_number == 0 { None } else { Some(line_number) })
}

impl<'a, 'o> Parser<'a, 'o> {
    /// Advance to the next token which is not a comment. Returns false at the end of the data.
    fn get_token(&mut self) -> Result<bool> {
        self.processed_token = None;
        loop {
            match self.tokenizer.get_token() {
                Ok(Some((start, end))) => {
                    if self.tokenizer.last_delimiter == '#' {
                        continue;
                    }
                    let token = &self.tokenizer.data[start..end];

                    // Unwrap embedded STAR in a semicolon-delimited value
                    if self.tokenizer.last_delimiter == ';' && token.starts_with("\n   ") {
                        let shift_over = token.split('\n').skip(1)
                            .all(|line| line.is_empty() || line.starts_with("   "));
                        if shift_over && token.contains("\n   ;") {
                            self.processed_token = Some(token.trim_end_matches('\n').replace("\n   ", "\n"));
                        }
                    }

                    self.token = Some((start, end));
                    self.line_number = self.tokenizer.token_line;
                    self.delimiter = self.tokenizer.last_delimiter;

                    // Warn (or raise) once per file about unusual whitespace
                    if !self.warned_unusual_whitespace {
                        if let Some(line) = self.tokenizer.unusual_whitespace_line {
                            self.warned_unusual_whitespace = true;
                            let line = self.tokenizer.source_line(line + 1);
                            if self.options.raise_parse_warnings {
                                return Err(parsing_error(UNUSUAL_WHITESPACE, line));
                            }
                            warn!("{} Found on line {}.", UNUSUAL_WHITESPACE, line);
                        }
                    }
                    return Ok(true);
                }
                Ok(None) => {
                    self.token = None;
                    return Ok(false);
                }
                Err(message) => return Err(parsing_error(message, self.tokenizer.token_line)),
            }
        }
    }

    fn token_str(&self) -> &str {
        if let Some(processed) = &self.processed_token {
            processed
        } else if let Some((start, end)) = self.token {
            &self.tokenizer.data[start..end]
        } else {
            ""
        }
    }

    fn error(&self, message: impl Into<String>) -> Error {
        parsing_error(message, self.line_number)
    }

    fn parse_entry(&mut self, entry: &mut Entry) -> Result<()> {
        if !self.get_token()? {
            return Err(self.error("Empty file"));
        }
        let token = self.token_str();
        if !starts_with_ignore_case(token, "data_") {
            return Err(self.error(format!(
                "Invalid file. NMR-STAR files must start with 'data_' followed by the data name. Did you \
                 accidentally select the wrong file? Your file started with '{}'.", token)));
        }
        if token.len() < 6 {
            return Err(self.error("'data_' must be followed by data name. Simply 'data_' is not allowed."));
        }
        if self.delimiter != ' ' {
            return Err(self.error("The data_ keyword may not be quoted or semicolon-delimited."));
        }
        entry.entry_id = Value::from(&token[5..]);

        self.saveframe_names = entry.frame_list.iter().map(|frame| frame.name().to_string()).collect();
        while self.get_token()? {
            let token = self.token_str();
            if !starts_with_ignore_case(token, "save_") {
                return Err(self.error(format!(
                    "Only 'save_NAME' is valid in the body of a NMR-STAR file. Found '{}'.", token)));
            }
            if token.len() < 6 {
                return Err(self.error(
                    "'save_' must be followed by saveframe name. You have a 'save_' tag which is illegal \
                     without a specified saveframe name."));
            }
            if self.delimiter != ' ' {
                return Err(self.error("The save_ keyword may not be quoted or semicolon-delimited."));
            }

            let name = token[5..].to_string();
            if !self.saveframe_names.insert(name.clone()) {
                return Err(Error::parsing(format!(
                    "Cannot add a saveframe with name '{}' since a saveframe with that name already exists in the \
                     entry.", name), None));
            }
            let mut saveframe = Saveframe::with_name(name, &self.source);
            self.parse_saveframe(&mut saveframe)?;
            entry.frame_list.push(saveframe);
        }
        Ok(())
    }

    /// Add the tags read since the last flush to the saveframe. Like PyNMR-STAR, the tags are
    /// added in batches, when a loop or the end of the saveframe is reached, and a failure is
    /// reported against the line the failing tag was read from.
    fn flush_tags(&self, saveframe: &mut Saveframe, pending: &mut Vec<(String, Value, usize)>) -> Result<()> {
        let mode = AddMode::Parse { raise_parse_warnings: self.options.raise_parse_warnings };
        for (name, value, line) in pending.drain(..) {
            saveframe.add_tag_impl(&name, value, false, self.options.convert_data_types, self.options.schema, mode)
                .map_err(|error| relocate(error, line))?;
        }
        Ok(())
    }

    fn parse_saveframe(&mut self, saveframe: &mut Saveframe) -> Result<()> {
        let mut pending: Vec<(String, Value, usize)> = Vec::new();
        // The lowercased categories of the saveframe's loops, for the duplicate check
        let mut loop_categories: HashSet<String> = HashSet::new();

        while self.get_token()? {
            let token = self.token_str();

            if token.eq_ignore_ascii_case("loop_") {
                self.flush_tags(saveframe, &mut pending)?;
                if self.delimiter != ' ' {
                    return Err(self.error("The loop_ keyword may not be quoted or semicolon-delimited."));
                }
                self.parse_loop(saveframe, &mut loop_categories)?;
            } else if token.eq_ignore_ascii_case("save_") {
                self.flush_tags(saveframe, &mut pending)?;
                if self.delimiter != ' ' {
                    return Err(self.error("The save_ keyword may not be quoted or semicolon-delimited."));
                }
                if saveframe.tag_prefix.is_none() {
                    return Err(self.error(format!(
                        "The tag prefix was never set! Either the saveframe had no tags, you tried to read a \
                         version 2.1 file, or there is something else wrong with your file. Saveframe error \
                         occurred within: '{}'", saveframe.name())));
                }
                return Ok(());
            } else if token.starts_with('_') {
                if self.delimiter != ' ' {
                    return Err(self.error(format!(
                        "Saveframe tags may not be quoted or semicolon-delimited. Quoted tag: '{}'.", token)));
                }
                let tag_line = self.line_number;
                let tag_name = token.to_string();

                if !self.get_token()? {
                    return Err(self.error("Tag without value"));
                }
                let value = self.token_str();
                if self.delimiter == ' ' {
                    if is_reserved_keyword(value) {
                        return Err(self.error(format!(
                            "Cannot use keywords as data values unless quoted or semi-colon delimited. Illegal \
                             value: '{}'", value)));
                    }
                    if value.starts_with('_') {
                        return Err(self.error(format!(
                            "Cannot have a tag value start with an underscore unless the entire value is quoted. \
                             You may be missing a data value on the previous line. Illegal value: '{}'", value)));
                    }
                }
                pending.push((tag_name, Value::from(value), tag_line));
            } else if saveframe.name() == "internaluseyoushouldntseethis_frame" {
                return Err(self.error(format!(
                    "Invalid token found in loop contents. Expecting 'loop_' but found: '{}'", token)));
            } else {
                return Err(self.error(format!(
                    "Invalid token found in saveframe '{}'. Expecting a tag, loop, or 'save_' token but found: '{}'",
                    saveframe.name(), token)));
            }
        }

        Err(self.error("Saveframe improperly terminated at end of file. Saveframes must be terminated with the \
                        'save_' token."))
    }

    fn parse_loop(&mut self, saveframe: &mut Saveframe, loop_categories: &mut HashSet<String>) -> Result<()> {
        let mut new_loop = Loop::with_source(&self.source);
        // As with saveframe tags, each tag carries the line it was read from: they are added in
        // one batch, once the first data value is seen
        let mut tags: Vec<(String, usize)> = Vec::new();

        while self.get_token()? {
            let token = self.token_str();
            if token.starts_with('_') && self.delimiter == ' ' {
                tags.push((token.to_string(), self.line_number));
                continue;
            }

            for (tag, line) in &tags {
                new_loop.add_tag(tag).map_err(|error| relocate(error, *line))?;
            }

            // The duplicate check Saveframe::add_loop() would make, in O(1). A loop without a
            //  category is never a duplicate.
            if let Some(category) = new_loop.category() {
                if !loop_categories.insert(crate::pystr::lower(category)) {
                    return Err(Error::parsing(format!(
                        "You cannot have two loops with the same category in one saveframe. Category: '{}'.",
                        category), None));
                }
            }

            let rows = self.parse_loop_data(&new_loop, tags.len())?;
            if !rows.is_empty() {
                if self.options.convert_data_types {
                    new_loop.add_data_with(crate::star_loop::Data::Rows(rows), true, true, self.options.schema)
                        .map_err(|error| Error::parsing(error.message().to_string(), None))?;
                } else {
                    new_loop.data = rows;
                }
            }
            saveframe.loops.push(new_loop);
            return Ok(());
        }
        // The data ended while reading the loop's tags; the saveframe reports it
        Ok(())
    }

    /// Read a loop's values, from the current token to its stop_.
    fn parse_loop_data(&mut self, new_loop: &Loop, tags_len: usize) -> Result<Vec<Vec<Value>>> {
        let mut rows: Vec<Vec<Value>> = Vec::new();
        let mut row: Vec<Value> = Vec::with_capacity(tags_len);
        let mut seen_data = false;
        loop {
            if self.token.is_none() {
                return Err(self.error("Loop improperly terminated at end of file. Loops must end with the 'stop_' \
                                       token, but the file ended without the stop token."));
            }
            let token = self.token_str();

            if token.eq_ignore_ascii_case("stop_") {
                if self.delimiter != ' ' {
                    return Err(self.error("The stop_ keyword may not be quoted or semicolon-delimited."));
                }
                if tags_len == 0 {
                    if self.options.raise_parse_warnings {
                        return Err(self.error("Loop with no tags."));
                    }
                    warn!("Loop with no tags in parsed file on line: {}", self.line_number);
                }
                if !seen_data {
                    if self.options.raise_parse_warnings {
                        return Err(self.error("Loop with no data."));
                    }
                    warn!("Loop with no data on line: {}", self.line_number);
                }
                if !row.is_empty() {
                    return Err(self.error(format!(
                        "The loop being parsed, '{}' does not have the expected number of data elements. This \
                         indicates that either one or more tag values are either missing from or duplicated in \
                         this loop.", new_loop.category().unwrap_or("None"))));
                }
                return Ok(rows);
            } else if token.starts_with('_') && self.delimiter == ' ' {
                return Err(self.error(format!(
                    "Cannot have more loop tags after loop data. Or perhaps this was a data value which was not \
                     quoted (but must be, if it starts with '_')? Value: '{}'.", token)));
            } else {
                if tags_len == 0 {
                    return Err(self.error(format!(
                        "Data value found in loop before any loop tags were defined. Value: '{}'", token)));
                }
                if is_reserved_keyword(token) && self.delimiter == ' ' {
                    let mut error = format!(
                        "Cannot use keywords as data values unless quoted or semi-colon delimited. Perhaps this is \
                         a loop that wasn't properly terminated with a 'stop_' keyword before the saveframe ended \
                         or another loop began? Value found where 'stop_' or another data value expected: '{}'.",
                        token);
                    if let Some(last) = row.last().or_else(|| rows.last().and_then(|r| r.last())) {
                        error.push_str(&format!(" Last loop data element parsed: '{}'.", last));
                    }
                    return Err(self.error(error));
                }
                row.push(Value::from(token));
                if row.len() == tags_len {
                    rows.push(std::mem::replace(&mut row, Vec::with_capacity(tags_len)));
                }
                seen_data = true;
            }

            if !self.get_token()? {
                return Err(self.error("Loop improperly terminated at end of file. Loops must end with the 'stop_' \
                                       token, but the file ended without the stop token."));
            }
        }
    }
}

/// Report a failure to add a tag against the line the tag was read from.
fn relocate(error: Error, line: usize) -> Error {
    if error.is_value_error() {
        parsing_error(error.message().to_string(), line)
    } else {
        error
    }
}

/// Parse NMR-STAR text into an entry, adding its saveframes to those already there.
pub(crate) fn parse(data: &str, entry: &mut Entry, source: &str, options: ParseOptions) -> Result<()> {
    // Fix DOS line endings
    let data = if data.contains('\r') {
        Cow::Owned(data.replace("\r\n", "\n").replace('\r', "\n"))
    } else {
        Cow::Borrowed(data)
    };
    // Change '\n; data ' started multi-lines to '\n;\ndata'
    let (data, inserted_lines) = fix_multiline_semicolons(data);

    let mut parser = Parser {
        tokenizer: Tokenizer::new(data, inserted_lines),
        line_number: 0,
        delimiter: ' ',
        token: None,
        processed_token: None,
        options,
        source: source.to_string(),
        warned_unusual_whitespace: false,
        saveframe_names: HashSet::new(),
    };
    parser.parse_entry(entry).map_err(|error| match error {
        Error::Parsing { .. } => error,
        error if error.is_value_error() => Error::parsing(error.message().to_string(), None),
        error => error,
    })
}
