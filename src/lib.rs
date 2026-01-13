use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use pyo3::types::IntoPyDict;

const RESERVED_KEYWORDS: [&str; 5] = ["data_", "save_", "loop_", "stop_", "global_"];

#[derive(Debug)]
enum ParserState {
    Initial,
    EntryBody,
    SaveframeBody,
    LoopTags,
    LoopData,
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
        let cnmrstar = py.import("pynmrstar.cnmrstar")?;
        let result = cnmrstar.call_method0("get_token_full")?;

        if result.is_none() {
            self.token = None;
            return Ok(None);
        }

        let tuple = result.extract::<(Option<String>, usize, Option<String>)>()?;

        // If token is None, we're at EOF
        if tuple.0.is_none() {
            self.token = None;
            return Ok(None);
        }

        let token_str = tuple.0.unwrap();
        let delimiter = tuple.2.unwrap_or_else(|| " ".to_string());
        self.token = Some(token_str.clone());
        self.line_number = tuple.1;
        self.delimiter = delimiter;

        Ok(Some(token_str))
    }

    fn raise_error(&self, message: &str) -> PyErr {
        PyValueError::new_err(format!("{} (line {})", message, self.line_number))
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
                    eprintln!("Warning: Loop with no tags in parsed file on line: {}", ctx.line_number);
                }
            }

            if !ctx.seen_data {
                if ctx.raise_parse_warnings {
                    return Err(ctx.raise_error("Loop with no data."));
                } else {
                    eprintln!("Warning: Loop with no data on line: {}", ctx.line_number);
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

    // Load data into tokenizer
    let parser_mod = py.import("pynmrstar.parser")?;
    let load_data = parser_mod.getattr("Parser")?.getattr("load_data")?;
    load_data.call1((data,))?;

    // Create parser context
    let mut ctx = ParserContext::new(py, entry.clone_ref(py), source,
                                     raise_parse_warnings, convert_data_types, schema);
    // Parse
    parse_initial(py, &mut ctx)?;
    parse_entry_body(py, &mut ctx)?;

    // Reset the tokenizer
    let cnmrstar = py.import("pynmrstar.cnmrstar")?;
    cnmrstar.call_method0("reset")?;

    Ok(entry)
}

#[pymodule]
fn pynmrstar_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    Ok(())
}
