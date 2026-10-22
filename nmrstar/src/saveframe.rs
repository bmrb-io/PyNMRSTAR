//! Saveframes: named groups of tags and loops.

use std::cmp::Ordering;
use std::collections::HashMap;
use std::path::Path;
use std::sync::OnceLock;

use log::warn;

use crate::csv;
use crate::definitions;
use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::format::format_saveframe;
use crate::internal::{self, Source};
use crate::json::Json;
use crate::parser::{self, ParseOptions};
use crate::pystr;
use crate::quoting::Converter;
use crate::schema::Schema;
use crate::star_loop::Loop;
use crate::utils::{format_category, format_tag, format_tag_lc, get_schema};
use crate::value::Value;

/// A saveframe tag: its name (without the saveframe's tag prefix) and value.
#[derive(Clone, Debug, PartialEq)]
pub struct Tag {
    pub name: String,
    pub value: Value,
}

impl Tag {
    pub fn new(name: impl Into<String>, value: impl Into<Value>) -> Tag {
        Tag { name: name.into(), value: value.into() }
    }
}

/// How a tag is being added: through the API, where any inconsistency is an error, or while
/// parsing, where recoverable problems are warnings (unless raising them is asked for).
#[derive(Clone, Copy, Debug)]
pub(crate) enum AddMode {
    Api,
    Parse { raise_parse_warnings: bool },
}

/// The format to write a file in.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FileFormat {
    NmrStar,
    Json,
}

impl FileFormat {
    /// The format named `nmrstar` or `json`.
    pub fn from_name(name: &str) -> Result<FileFormat> {
        match name {
            "nmrstar" => Ok(FileFormat::NmrStar),
            "json" => Ok(FileFormat::Json),
            _ => Err(Error::value("Invalid output format.")),
        }
    }
}

pub(crate) fn write_file(path: &Path, text: &str) -> Result<()> {
    std::fs::write(path, text).map_err(|error| Error::Io(format!("{}: {}", path.display(), error)))
}

/// A saveframe: a set of tags sharing a tag prefix, and loops.
#[derive(Clone, Debug, Default)]
pub struct Saveframe {
    tags: Vec<Tag>,
    /// Lowercase tag name -> position, built on demand
    lc_tags: OnceLock<HashMap<String, usize>>,
    /// The loops
    pub loops: Vec<Loop>,
    name: String,
    /// Where the saveframe came from
    pub source: String,
    category: Option<String>,
    /// The prefix (category) of the saveframe's tags, such as `_Entry`
    pub tag_prefix: Option<String>,
}

impl PartialEq for Saveframe {
    /// Saveframes are equal when their names, categories, tags and loops are.
    fn eq(&self, other: &Saveframe) -> bool {
        self.name == other.name && self.category == other.category && self.tags == other.tags && self.loops == other.loops
    }
}

impl PartialOrd for Saveframe {
    /// Saveframes sort by tag prefix. Unordered when either has none.
    fn partial_cmp(&self, other: &Saveframe) -> Option<Ordering> {
        match (&self.tag_prefix, &other.tag_prefix) {
            (Some(a), Some(b)) => Some(a.cmp(b)),
            _ => None,
        }
    }
}

const STRUCTURAL_TAGS: [&str; 6] = ["sf_category", "sf_framecode", "id", "entry_id", "nmr_star_version",
                                    "original_nmr_star_version"];

impl Saveframe {
    pub(crate) fn with_name(name: impl Into<String>, source: &str) -> Saveframe {
        Saveframe { name: name.into(), source: source.to_string(), ..Default::default() }
    }

    /// An empty saveframe. The tag prefix (a `_` is added if needed) is otherwise set by the
    /// first tag added with one.
    pub fn from_scratch(name: &str, tag_prefix: Option<&str>) -> Saveframe {
        let mut saveframe = Saveframe::with_name(name, "from_scratch()");
        saveframe.tag_prefix = tag_prefix.map(format_category);
        saveframe
    }

    /// Parse a saveframe from NMR-STAR text.
    pub fn from_str(text: &str) -> Result<Saveframe> {
        Saveframe::from_str_opts(text, ParseOptions::new())
    }

    /// Parse a saveframe from NMR-STAR text, with options.
    pub fn from_str_opts(text: &str, options: ParseOptions) -> Result<Saveframe> {
        Saveframe::parse(text, "from_string()", options)
    }

    fn parse(text: &str, source: &str, options: ParseOptions) -> Result<Saveframe> {
        let mut tmp_entry = Entry::from_scratch(0);
        parser::parse(&format!("data_1 {}", text), &mut tmp_entry, source, options)?;
        if tmp_entry.frame_list.len() > 1 {
            let detected: Vec<String> = tmp_entry.frame_list.iter().map(Saveframe::repr).collect();
            return Err(Error::value(format!(
                "You attempted to parse one saveframe but the source you provided had more than one saveframe. \
                 Please either parse all saveframes as an entry or only parse one saveframe. Saveframes detected: [{}]",
                detected.join(", "))));
        }
        let mut saveframe = tmp_entry.frame_list.pop().ok_or_else(|| Error::Index("list index out of range".to_string()))?;
        saveframe.source = source.to_string();
        Ok(saveframe)
    }

    /// Read a saveframe's tags from CSV text: a header row of tags, then a row of values.
    pub fn from_csv_str(text: &str) -> Result<Saveframe> {
        Saveframe::from_csv(text, "from_string()")
    }

    fn from_csv(text: &str, source: &str) -> Result<Saveframe> {
        let mut saveframe = Saveframe::with_name("", source);
        let mut rows = csv::rows(text);
        let tags = rows.next().unwrap_or_default();
        let values = rows.next().ok_or_else(|| Error::value("Your CSV data is invalid. It has no row of values."))?;
        if tags.len() != values.len() {
            return Err(Error::value("Your CSV data is invalid. The header length does not match the data length."));
        }
        for (tag, value) in tags.iter().zip(values) {
            saveframe.add_tag(tag, value)?;
        }
        Ok(saveframe)
    }

    /// Read a saveframe from a file (or URL) in NMR-STAR format.
    pub fn from_file(source: impl Into<Source>) -> Result<Saveframe> {
        Saveframe::from_file_opts(source, ParseOptions::new())
    }

    /// Read a saveframe from a file (or URL) in NMR-STAR format, with options.
    pub fn from_file_opts(source: impl Into<Source>, options: ParseOptions) -> Result<Saveframe> {
        let source = source.into();
        let text = internal::read_text(&source)?;
        Saveframe::parse(&text, &format!("from_file('{}')", source.label()), options)
    }

    /// Read a saveframe's tags from a CSV file (or URL).
    pub fn from_csv_file(source: impl Into<Source>) -> Result<Saveframe> {
        let source = source.into();
        let text = internal::read_text(&source)?;
        Saveframe::from_csv(&text, &format!("from_file('{}')", source.label()))
    }

    /// Create a saveframe from its JSON (as written by [`Saveframe::to_json`]).
    pub fn from_json(json: &str) -> Result<Saveframe> {
        let json = Json::parse(json).map_err(|_| {
            Error::value("The JSON you provided was neither a Python dictionary nor a JSON string.")
        })?;
        Saveframe::from_json_value(&json)
    }

    /// Create a saveframe from parsed JSON.
    pub fn from_json_value(json: &Json) -> Result<Saveframe> {
        for check in ["name", "tag_prefix", "tags", "loops"] {
            if !json.has(check) {
                return Err(Error::value(format!(
                    "The JSON you provide must be a hash and must contain the key '{}' - even if the key points to None.",
                    check)));
            }
        }
        let name = json.get("name").and_then(Json::to_optional_string).unwrap_or_default();
        let mut saveframe = Saveframe::from_scratch(&name, None);
        saveframe.tag_prefix = json.get("tag_prefix").and_then(Json::to_optional_string);
        saveframe.category = json.get("category").and_then(Json::to_optional_string);
        for tag in json.get("tags").and_then(Json::as_array).map(Vec::as_slice).unwrap_or(&[]) {
            let pair = tag.as_array().filter(|pair| pair.len() == 2)
                .ok_or_else(|| Error::value("Each saveframe tag must be a [name, value] pair."))?;
            saveframe.tags.push(Tag::new(pair[0].to_optional_string().unwrap_or_default(), pair[1].to_value()?));
        }
        for each_loop in json.get("loops").and_then(Json::as_array).map(Vec::as_slice).unwrap_or(&[]) {
            saveframe.loops.push(Loop::from_json_value(each_loop)?);
        }
        saveframe.source = "from_json()".to_string();
        Ok(saveframe)
    }

    /// A saveframe with the tags and loops the dictionary defines for a category: those not
    /// marked internal, or with `all_tags` every one. The name defaults to the category. With
    /// `default_values`, tags get their dictionary default values; otherwise only Sf_category,
    /// Sf_framecode and the entry ID tag have values.
    pub fn from_template(category: &str, name: Option<&str>, entry_id: Option<Value>, all_tags: bool,
                         default_values: bool, schema: Option<&Schema>) -> Result<Saveframe> {
        let schema = get_schema(schema);
        let name = name.filter(|n| !n.is_empty()).unwrap_or(category);
        let mut saveframe = Saveframe::with_name(name, &format!("from_template({})", schema.version));
        saveframe.category = Some(category.to_string());

        if !schema.tags().any(|(_, data)| data.get("SFCategory") == category) {
            return Err(Error::value(format!("The saveframe category '{}' was not found in the dictionary.", category)));
        }

        let mut ordered: Vec<_> = schema.tags().map(|(_, data)| data).collect();
        ordered.sort_by(|a, b| {
            let sequence = |data: &crate::schema::TagData| data.get("Dictionary sequence").trim().parse::<f64>()
                .unwrap_or(f64::INFINITY);
            sequence(a).partial_cmp(&sequence(b)).unwrap_or(Ordering::Equal)
        });

        let entry_id = entry_id.unwrap_or(Value::Null);
        let mut loops_added: Vec<String> = Vec::new();
        for item in ordered {
            if item.get("SFCategory") != category {
                continue;
            }
            let tag = item.tag();
            if item.get("Loopflag") == "N" {
                let short = format_tag(tag);
                if short == "Sf_category" {
                    saveframe.add_tag(tag, category)?;
                } else if short == "Sf_framecode" {
                    let name = saveframe.name.clone();
                    saveframe.add_tag(tag, name)?;
                } else if item.get("entryIdFlg") == "Y" {
                    saveframe.add_tag(tag, entry_id.clone())?;
                } else {
                    let default = item.get("default value");
                    let value = if default_values && !definitions::is_null_str(default) {
                        Value::from(default)
                    } else {
                        Value::Null
                    };
                    if all_tags || item.get("public") != "I" {
                        saveframe.add_tag(tag, value)?;
                    }
                }
            } else {
                let loop_category = format_category(tag);
                if !loops_added.contains(&loop_category) {
                    loops_added.push(loop_category.clone());
                    if let Ok(new_loop) = Loop::from_template(&loop_category, all_tags, Some(schema)) {
                        // A loop which can't be added is left out, as PyNMR-STAR did
                        let _ = saveframe.add_loop(new_loop);
                    }
                }
            }
        }
        Ok(saveframe)
    }

    /// A description of the saveframe.
    pub fn repr(&self) -> String {
        format!("<pynmrstar.Saveframe '{}'>", self.name)
    }

    /// The name of the saveframe.
    pub fn name(&self) -> &str {
        &self.name
    }

    /// Rename the saveframe, updating its Sf_framecode tag (if it has one). The name may not be
    /// null or contain whitespace. To rename a saveframe in an entry, updating the references to
    /// it, see [`Entry::rename_saveframe`].
    pub fn set_name(&mut self, name: &str) -> Result<()> {
        if !pystr::is_single_word(name) {
            return Err(Error::value("Saveframe names can not contain whitespace characters."));
        }
        if definitions::is_null_str(name) {
            return Err(Error::value("Cannot set the saveframe name to a null-equivalent value."));
        }
        if let Some(&position) = self.lc_tags().get("sf_framecode") {
            self.tags[position].value = Value::from(name);
        }
        self.name = name.to_string();
        Ok(())
    }

    /// The category of the saveframe (the value of its Sf_category tag when it was added).
    pub fn category(&self) -> Option<&str> {
        self.category.as_deref()
    }

    /// Set the category, updating the Sf_category tag (or adding one).
    pub fn set_category(&mut self, category: &str) -> Result<()> {
        if definitions::is_null_str(category) {
            return Err(Error::value("Cannot set the saveframe category to a null-equivalent value."));
        }
        match self.tag_mut("sf_category") {
            Some(tag) => tag.value = Value::from(category),
            None => self.add_tag("Sf_category", category)?,
        }
        self.category = Some(category.to_string());
        Ok(())
    }

    /// Set the tag prefix, adding a `_` if needed and removing any tag name.
    pub fn set_tag_prefix(&mut self, tag_prefix: &str) {
        self.tag_prefix = Some(format_category(tag_prefix));
    }

    /// The tags.
    pub fn tags(&self) -> &[Tag] {
        &self.tags
    }

    /// The tags, to change directly, without the checks [`Saveframe::add_tag`] makes.
    pub fn tags_mut(&mut self) -> &mut Vec<Tag> {
        self.lc_tags = OnceLock::new();
        &mut self.tags
    }

    fn lc_tags(&self) -> &HashMap<String, usize> {
        self.lc_tags.get_or_init(|| {
            self.tags.iter().enumerate().map(|(i, tag)| (pystr::lower(&tag.name), i)).collect()
        })
    }

    /// A tag, found by name (with or without the tag prefix, in any case), to change directly.
    pub fn tag_mut(&mut self, name: &str) -> Option<&mut Tag> {
        let position = *self.lc_tags().get(&format_tag_lc(name))?;
        self.lc_tags = OnceLock::new();
        Some(&mut self.tags[position])
    }

    /// The tags as a map from lowercase name to value.
    pub fn tag_dict(&self) -> HashMap<String, Value> {
        self.tags.iter().map(|tag| (pystr::lower(&tag.name), tag.value.clone())).collect()
    }

    /// The loops by lowercase category. Loops without a category are left out.
    pub fn loop_dict(&self) -> HashMap<String, &Loop> {
        self.loops.iter().filter_map(|l| l.category().map(|c| (pystr::lower(c), l))).collect()
    }

    /// The number of loops.
    pub fn len(&self) -> usize {
        self.loops.len()
    }

    /// Whether the saveframe has no loops.
    pub fn is_empty(&self) -> bool {
        self.loops.is_empty()
    }

    /// The loops.
    pub fn iter(&self) -> std::slice::Iter<'_, Loop> {
        self.loops.iter()
    }

    /// Whether the saveframe holds no data: every tag but the structural ones (Sf_category,
    /// Sf_framecode, ID, Entry_ID and the versions) is null, and so is every loop value.
    pub fn empty(&self) -> bool {
        let tags_empty = self.tags.iter().all(|tag| {
            STRUCTURAL_TAGS.contains(&pystr::lower(&tag.name).as_str()) || tag.value.is_null_value()
        });
        tags_empty && self.loops.iter().all(Loop::empty)
    }

    /// Whether the saveframe has a tag (`Name` or `_Prefix.Name`) or, for text starting with
    /// `_` and without a `.`, a loop of that category.
    pub fn contains(&self, item: &str) -> bool {
        if item.starts_with('_') && !item.contains('.') {
            self.loop_dict().contains_key(&pystr::lower(item))
        } else {
            self.lc_tags().contains_key(&format_tag_lc(item))
        }
    }

    /// Whether the saveframe has every one of the tags or loops (see [`Saveframe::contains`]).
    pub fn contains_all<S: AsRef<str>>(&self, items: &[S]) -> bool {
        items.iter().all(|item| self.contains(item.as_ref()))
    }

    /// Whether the saveframe has a loop equal to the one given.
    pub fn contains_loop(&self, other: &Loop) -> bool {
        self.loops.contains(other)
    }

    /// The loop at a position.
    pub fn loop_at(&self, index: usize) -> Result<&Loop> {
        self.loops.get(index).ok_or_else(|| Error::Index(format!("No loop with index '{}'.", index)))
    }

    /// The loop at a position, to change.
    pub fn loop_at_mut(&mut self, index: usize) -> Result<&mut Loop> {
        self.loops.get_mut(index).ok_or_else(|| Error::Index(format!("No loop with index '{}'.", index)))
    }

    /// The values of a tag, which must have at least one.
    pub fn get_tag_required(&self, query: &str) -> Result<Vec<Value>> {
        let results = self.get_tag(query)?;
        if results.is_empty() {
            return Err(Error::key(format!("No tag matching '{}'.", query)));
        }
        Ok(results)
    }

    /// Replace the loop at a position.
    pub fn set_loop_at(&mut self, index: usize, new_loop: Loop) -> Result<()> {
        let slot = self.loops.get_mut(index).ok_or_else(|| Error::Index("list assignment index out of range".to_string()))?;
        *slot = new_loop;
        Ok(())
    }

    /// Replace the loop of a category.
    pub fn set_loop(&mut self, category: &str, new_loop: Loop) -> Result<()> {
        let lower = pystr::lower(category);
        if !self.loop_dict().contains_key(&lower) {
            return Err(Error::key(format!(
                "Loop with category '{}' does not exist and therefore cannot be written to. Use add_loop instead.",
                category)));
        }
        for slot in &mut self.loops {
            if slot.category().is_some_and(|c| pystr::lower(c) == lower) {
                *slot = new_loop.clone();
            }
        }
        Ok(())
    }

    /// Set a tag's value, adding the tag if needed.
    pub fn set_tag(&mut self, name: &str, value: impl Into<Value>) -> Result<()> {
        self.add_tag_with(name, value, true, false, None)
    }

    /// Remove a tag (`Name` or `_Prefix.Name`) or, for text starting with `_` and without a
    /// `.`, a loop of that category.
    pub fn delete(&mut self, item: &str) -> Result<()> {
        if item.starts_with('_') && !item.contains('.') {
            self.remove_loop(item)
        } else {
            self.remove_tag(item)
        }
    }

    /// Remove the loop at a position.
    pub fn remove_loop_at(&mut self, index: usize) -> Result<()> {
        if index >= self.loops.len() {
            return Err(Error::Index(format!("Index out of range: no loop at index: {}", index)));
        }
        let removed = self.loops[index].clone();
        self.remove_loop_obj(&removed)
    }

    /// The saveframe in NMR-STAR format, with its comment, as `str()` gave in PyNMR-STAR: loops
    /// without tags are written.
    pub fn to_star(&self) -> Result<String> {
        self.format_impl(true, false, false, true)
    }

    /// The saveframe in NMR-STAR format. `skip_empty_loops` leaves out loops with no tags;
    /// `skip_empty_tags` leaves out tags (in the saveframe and its loops) with no non-null
    /// values; `show_comments` writes the standard comment for the category before it.
    pub fn format(&self, skip_empty_loops: bool, skip_empty_tags: bool, show_comments: bool) -> Result<String> {
        self.format_impl(true, skip_empty_loops, skip_empty_tags, show_comments)
    }

    pub(crate) fn format_impl(&self, first_in_category: bool, skip_empty_loops: bool, skip_empty_tags: bool,
                              show_comments: bool) -> Result<String> {
        let tag_prefix = self.tag_prefix.as_deref().ok_or_else(|| Error::invalid_state(format!(
            "The tag prefix was never set! Error in saveframe named '{}'.", self.name)))?;

        let mut comment = "";
        if show_comments {
            if let Some((text, every_flag)) = self.category.as_ref().and_then(|c| internal::comments().get(c)) {
                if first_in_category || *every_flag {
                    comment = text;
                }
            }
        }

        let formatted_loops = self.loops.iter().map(|each_loop| each_loop.format(skip_empty_loops, skip_empty_tags))
            .collect::<Result<Vec<String>>>()?;
        format_saveframe(&self.name, tag_prefix, &self.tags, &formatted_loops, skip_empty_tags, comment)
    }

    /// Add a loop. A saveframe may not have two loops of the same category.
    pub fn add_loop(&mut self, loop_to_add: Loop) -> Result<()> {
        let loop_dict = self.loop_dict();
        let lower = pystr::lower(loop_to_add.category().unwrap_or("None"));
        if loop_dict.contains_key(&lower) {
            return Err(Error::value(match loop_to_add.category() {
                None => "You cannot have two loops with the same category in one saveframe. You are getting this error \
                         because you haven't yet set your loop categories.".to_string(),
                Some(category) => format!(
                    "You cannot have two loops with the same category in one saveframe. Category: '{}'.", category),
            }));
        }
        self.loops.push(loop_to_add);
        Ok(())
    }

    /// Add a tag. A tag given with its prefix sets the saveframe's tag prefix if it has none,
    /// and must match it otherwise. Adding a tag the saveframe already has is an error.
    pub fn add_tag(&mut self, name: &str, value: impl Into<Value>) -> Result<()> {
        self.add_tag_with(name, value, false, false, None)
    }

    /// Add a tag. With `update`, a tag the saveframe already has has its value replaced. With
    /// `convert_data_types`, the value is converted to the type the dictionary (the schema
    /// given, or the default) declares for the tag.
    pub fn add_tag_with(&mut self, name: &str, value: impl Into<Value>, update: bool, convert_data_types: bool,
                        schema: Option<&Schema>) -> Result<()> {
        self.add_tag_impl(name, value.into(), update, convert_data_types, schema, AddMode::Api)
    }

    pub(crate) fn add_tag_impl(&mut self, name: &str, value: Value, update: bool, convert_data_types: bool,
                               schema: Option<&Schema>, mode: AddMode) -> Result<()> {
        let mut name = name;
        if let Some(dot) = name.find('.') {
            if !name.starts_with('.') {
                let prefix = format_category(name);
                match &self.tag_prefix {
                    None => self.tag_prefix = Some(prefix),
                    Some(existing) if *existing != prefix => {
                        return Err(Error::value(format!(
                            "One saveframe cannot have tags with different categories (or tags that don't match the \
                             set category)! Saveframe tag prefix is '{}' but the added tag, '{}' has prefix '{}'.",
                            existing, name, prefix)));
                    }
                    _ => {}
                }
                name = &name[dot + 1..];
            } else {
                name = &name[1..];
            }
        }

        if definitions::is_null_str(name) {
            return Err(Error::value(format!(
                "Cannot use a null-equivalent value as a tag name. Invalid tag name: '{}'", name)));
        }
        if name.contains('.') {
            return Err(Error::value(format!(
                "There cannot be more than one '.' in a tag name. Invalid tag name: '{}'", name)));
        }
        if !pystr::is_single_word(name) {
            return Err(Error::value(format!(
                "Tag names can not contain whitespace characters. Invalid tag name: '{}'", name)));
        }

        let lower = pystr::lower(name);
        if let Some(&position) = self.lc_tags().get(&lower) {
            if !update {
                return Err(Error::value(format!(
                    "There is already a tag with the name '{}' in the saveframe '{}. Set update=True if you want to \
                     override its value.", name, self.name)));
            }
            if lower == "sf_category" {
                self.category = optional_string(&value);
            }
            if lower == "sf_framecode" {
                if value.is_null_value() {
                    return Err(Error::value(format!(
                        "Cannot set the saveframe name tag (Sf_framecode) to a null-equivalent value. Invalid value: \
                         '{}'", name)));
                }
                self.name = value.to_py_string().into_owned();
            }
            self.tags[position].value = value;
            return Ok(());
        }

        let new_value = if convert_data_types {
            let prefix = self.tag_prefix.as_deref().unwrap_or("None");
            get_schema(schema).convert_tag(&format!("{}.{}", prefix, name), &value)?
        } else {
            value.clone()
        };

        if lower == "sf_category" {
            self.category = optional_string(&value);
        }
        if lower == "sf_framecode" {
            if self.name.is_empty() {
                self.name = optional_string(&value).unwrap_or_default();
            } else if value != Value::from(self.name.as_str()) {
                let message = format!(
                    "The Sf_framecode tag cannot be different from the saveframe name. Error occurred in tag \
                     {}.Sf_framecode with value {} which conflicts with the saveframe name {}.",
                    self.tag_prefix.as_deref().unwrap_or("None"), value, self.name);
                // While parsing, keep both strings rather than refusing the file: the saveframe
                //  keeps the name from its save_ label and the tag keeps its own value, so a
                //  validator can compare the two and report the mismatch
                match mode {
                    AddMode::Api => return Err(Error::value(message)),
                    AddMode::Parse { raise_parse_warnings: true } => return Err(Error::parsing(message, None)),
                    AddMode::Parse { raise_parse_warnings: false } => warn!("{}", message),
                }
            }
        }

        self.tags.push(Tag { name: name.to_string(), value: new_value });
        let position = self.tags.len() - 1;
        if let Some(cache) = self.lc_tags.get_mut() {
            cache.insert(lower, position);
        }
        Ok(())
    }

    /// Add several tags, as (name, value) pairs.
    pub fn add_tags<N: AsRef<str>, V: Into<Value> + Clone>(&mut self, tags: &[(N, V)]) -> Result<()> {
        for (name, value) in tags {
            self.add_tag(name.as_ref(), value.clone())?;
        }
        Ok(())
    }

    /// Add several tags, as (name, value) pairs, where a value of None is `.`. With `update`,
    /// tags the saveframe already has have their values replaced.
    pub fn add_tags_with<N: AsRef<str>>(&mut self, tags: &[(N, Option<Value>)], update: bool, convert_data_types: bool,
                                        schema: Option<&Schema>) -> Result<()> {
        for (name, value) in tags {
            let value = value.clone().unwrap_or_else(|| Value::from("."));
            self.add_tag_with(name.as_ref(), value, update, convert_data_types, schema)?;
        }
        Ok(())
    }

    /// Add the tags the dictionary defines for the saveframe's tag prefix which it does not
    /// have (those not marked internal, or with `all_tags` every one), and sort the tags.
    /// With `recursive`, the loops are given their missing tags too.
    pub fn add_missing_tags(&mut self, schema: Option<&Schema>, all_tags: bool, recursive: bool) -> Result<()> {
        let tag_prefix = match self.tag_prefix.as_deref() {
            Some(prefix) if !prefix.is_empty() => format!("{}.", pystr::lower(prefix)),
            _ => return Err(Error::invalid_state(
                "You must first specify the tag prefix of this Saveframe before calling this method. You can do this \
                 by adding a fully qualified tag (i.e. _Entry.Sf_framecode), by specifying the tag_prefix when \
                 calling from_scratch() or by modifying the .tag_prefix attribute.")),
        };
        let schema = get_schema(schema);
        for item in &schema.schema_order {
            if pystr::lower(item).starts_with(&tag_prefix)
                && (all_tags || schema.get_tag(item).is_some_and(|data| data.get("public") != "I")) {
                match self.add_tag(item, Value::Null) {
                    Err(error) if !error.is_value_error() => return Err(error),
                    _ => {}
                }
            }
        }
        if recursive {
            for each_loop in &mut self.loops {
                match each_loop.add_missing_tags(Some(schema), all_tags) {
                    Err(error) if !error.is_value_error() => return Err(error),
                    _ => {}
                }
            }
        }
        self.sort_tags(Some(schema));
        Ok(())
    }

    /// The differences between two saveframes. Non-equal saveframes are always detected, but
    /// the specific differences reported depend on their order.
    pub fn compare(&self, other: &Saveframe) -> Vec<String> {
        if std::ptr::eq(self, other) {
            return Vec::new();
        }
        if let (Ok(a), Ok(b)) = (self.to_star(), other.to_star()) {
            if a == b {
                return Vec::new();
            }
        }

        let mut diffs = Vec::new();
        if self.name != other.name {
            diffs.push(format!("\tSaveframe names do not match: '{}' vs '{}'.", self.name, other.name));
            return diffs;
        }
        let prefix = self.tag_prefix.as_deref().unwrap_or("None");
        let other_prefix = other.tag_prefix.as_deref().unwrap_or("None");
        if prefix != other_prefix {
            diffs.push(format!("\tTag prefix does not match: '{}' vs '{}'.", prefix, other_prefix));
            return diffs;
        }
        if self.tags.len() < other.tags.len() {
            diffs.push(format!("\tNumber of tags does not match: '{}' vs '{}'. The compared entry has at least one \
                                tag this entry does not.", self.tags.len(), other.tags.len()));
        }

        let converter = Converter::new();
        for tag in &self.tags {
            let other_tag = other.get_tag(&tag.name).unwrap_or_default();
            let Some(other_value) = other_tag.first() else {
                diffs.push(format!("\tNo tag with name '{}.{}' in compared entry.", prefix, tag.name));
                continue;
            };
            if converter.convert_plain(&tag.value) != converter.convert_plain(other_value) {
                diffs.push(format!("\tMismatched tag values for tag '{}.{}': '{}' vs '{}'.", prefix, tag.name,
                                   tag.value.to_py_string().replace('\n', "\\n"),
                                   other_value.to_py_string().replace('\n', "\\n")));
            }
        }

        if self.loops.len() != other.loops.len() {
            diffs.push(format!("\tNumber of children loops does not match: '{}' vs '{}'.",
                               self.loops.len(), other.loops.len()));
        }

        let compare_loop_dict = other.loop_dict();
        for each_loop in &self.loops {
            let Some(category) = each_loop.category() else {
                diffs.push("\tAn exception occurred while comparing: ''NoneType' object has no attribute 'lower''."
                    .to_string());
                break;
            };
            match compare_loop_dict.get(&pystr::lower(category)) {
                Some(other_loop) => {
                    let compared = each_loop.compare(other_loop);
                    if !compared.is_empty() {
                        diffs.push(format!("\tLoops do not match: '{}'.", category));
                        diffs.extend(compared);
                    }
                }
                None => diffs.push(format!("\tNo loop with category '{}' in other entry.", category)),
            }
        }
        diffs
    }

    /// Whether the saveframe is written exactly as the given NMR-STAR text.
    pub fn compare_str(&self, other: &str) -> Vec<String> {
        match self.to_star() {
            Ok(text) if text == other => Vec::new(),
            _ => vec!["String was not exactly equal to saveframe.".to_string()],
        }
    }

    /// The tags as CSV: a header row of tag names (with the prefix, unless not
    /// `show_category`) unless not `header`, and a row of values.
    pub fn get_data_as_csv(&self, header: bool, show_category: bool) -> String {
        let mut rows: Vec<Vec<Value>> = Vec::new();
        if header {
            let prefix = self.tag_prefix.as_deref().unwrap_or("None");
            rows.push(self.tags.iter().map(|tag| {
                if show_category { Value::from(format!("{}.{}", prefix, tag.name)) } else { Value::from(&tag.name) }
            }).collect());
        }
        rows.push(self.tags.iter().map(|tag| tag.value.clone()).collect());
        csv::write(&rows)
    }

    /// The saveframe as JSON.
    pub fn to_json_value(&self) -> Json {
        let optional = |s: &Option<String>| s.as_ref().map_or(Json::Null, |s| Json::Str(s.clone()));
        Json::Object(vec![
            ("name".to_string(), Json::Str(self.name.clone())),
            ("category".to_string(), optional(&self.category)),
            ("tag_prefix".to_string(), optional(&self.tag_prefix)),
            ("tags".to_string(), Json::Array(self.tags.iter().map(|tag| {
                Json::Array(vec![Json::Str(tag.name.clone()), Json::from_value(&tag.value)])
            }).collect())),
            ("loops".to_string(), Json::Array(self.loops.iter().map(Loop::to_json_value).collect())),
        ])
    }

    /// The saveframe as serialized JSON.
    pub fn to_json(&self) -> String {
        self.to_json_value().dumps()
    }

    /// The loop of a category (given with or without the `_`, in any case).
    pub fn get_loop(&self, name: &str) -> Result<&Loop> {
        let lower = pystr::lower(&format_category(name));
        self.loops.iter().find(|l| pystr::lower(l.category().unwrap_or("None")) == lower)
            .ok_or_else(|| Error::key(format!("No loop with category '{}'.", lower)))
    }

    /// The loop of a category, to change.
    pub fn get_loop_mut(&mut self, name: &str) -> Result<&mut Loop> {
        let lower = pystr::lower(&format_category(name));
        self.loops.iter_mut().find(|l| pystr::lower(l.category().unwrap_or("None")) == lower)
            .ok_or_else(|| Error::key(format!("No loop with category '{}'.", lower)))
    }

    #[deprecated(note = "Use get_loop() instead.")]
    pub fn get_loop_by_category(&self, name: &str) -> Result<&Loop> {
        self.get_loop(name)
    }

    /// The prefix a query is for, and the lowercase prefix it must match.
    fn query_prefix(&self, query: &str) -> Option<String> {
        if query.contains('.') { Some(format_category(query)) } else { self.tag_prefix.clone() }
    }

    fn own_tag_matches(&self, tag_prefix: &Option<String>) -> bool {
        match (tag_prefix, &self.tag_prefix) {
            (Some(query), Some(own)) => pystr::lower(query) == pystr::lower(own),
            _ => false,
        }
    }

    /// The values of a tag: from the saveframe's own tags, and from the loop whose category is
    /// the tag's (or the saveframe's) prefix, if any. A loop of that category without the tag is
    /// an error.
    pub fn get_tag(&self, query: &str) -> Result<Vec<Value>> {
        let tag_prefix = self.query_prefix(query);
        let mut results = Vec::new();
        if let Some(prefix) = &tag_prefix {
            let lower = pystr::lower(prefix);
            for each_loop in &self.loops {
                if each_loop.category().is_some_and(|c| pystr::lower(c) == lower) {
                    results.extend(each_loop.get_tag(query)?);
                }
            }
        }
        if self.own_tag_matches(&tag_prefix) {
            let query = format_tag_lc(query);
            results.extend(self.tags.iter().filter(|tag| pystr::lower(&tag.name) == query).map(|tag| tag.value.clone()));
        }
        Ok(results)
    }

    /// As [`Saveframe::get_tag`], with each value's tag name: as the saveframe spells it for its
    /// own tags, and with the category for loop tags.
    pub fn get_tag_whole(&self, query: &str) -> Result<Vec<(String, Value)>> {
        let tag_prefix = self.query_prefix(query);
        let mut results = Vec::new();
        if let Some(prefix) = &tag_prefix {
            let lower = pystr::lower(prefix);
            for each_loop in &self.loops {
                if each_loop.category().is_some_and(|c| pystr::lower(c) == lower) {
                    results.extend(each_loop.get_tag_whole(query)?);
                }
            }
        }
        if self.own_tag_matches(&tag_prefix) {
            let query = format_tag_lc(query);
            results.extend(self.tags.iter().filter(|tag| pystr::lower(&tag.name) == query)
                .map(|tag| (tag.name.clone(), tag.value.clone())));
        }
        Ok(results)
    }

    /// A summary of the saveframe and its loops, one per line.
    pub fn tree(&self) -> String {
        let mut text = format!("{}\n", self.repr());
        for (pos, each_loop) in self.loops.iter().enumerate() {
            text.push_str(&format!("\t[{}] {}\n", pos, each_loop.repr()));
        }
        text
    }

    /// Print a summary of the saveframe and its loops.
    pub fn print_tree(&self) {
        print!("{}", self.tree());
    }

    /// Remove the loop of a category. With a `_`, the category is compared without regard to
    /// case; without one, it is added (and the rest compared as written).
    pub fn remove_loop(&mut self, category: &str) -> Result<()> {
        self.remove_loops(&[category])
    }

    /// Remove the loops of several categories. Nothing is removed unless every one exists.
    pub fn remove_loops<S: AsRef<str>>(&mut self, categories: &[S]) -> Result<()> {
        let mut to_remove = Vec::new();
        {
            let loop_names = self.loop_dict();
            for category in categories {
                let category = category.as_ref();
                let mut formatted = pystr::lower(category);
                if !formatted.starts_with('_') {
                    formatted = format!("_{}", category);
                }
                match loop_names.get(&formatted) {
                    Some(found) => to_remove.push((*found).clone()),
                    None => return Err(Error::value(format!(
                        "At least one loop specified to remove was not found in this saveframe. First missing loop: {}",
                        category))),
                }
            }
        }
        self.loops.retain(|l| !to_remove.contains(l));
        Ok(())
    }

    /// Remove every loop equal to the one given.
    pub fn remove_loop_obj(&mut self, target: &Loop) -> Result<()> {
        self.remove_loop_objs(std::slice::from_ref(target))
    }

    /// Remove every loop equal to one of those given. Nothing is removed unless each is found.
    pub fn remove_loop_objs(&mut self, targets: &[Loop]) -> Result<()> {
        for target in targets {
            if !self.loops.contains(target) {
                return Err(Error::value(format!(
                    "At least one loop specified to remove was not found in this saveframe. First missing loop: {}",
                    target.repr())));
            }
        }
        self.loops.retain(|l| !targets.contains(l));
        Ok(())
    }

    /// Remove a tag (given with or without the prefix).
    pub fn remove_tag(&mut self, tag: &str) -> Result<()> {
        self.remove_tags(&[tag])
    }

    /// Remove several tags. Nothing is removed unless every one exists.
    pub fn remove_tags<S: AsRef<str>>(&mut self, tags: &[S]) -> Result<()> {
        let lc_tags = self.lc_tags();
        let mut positions = Vec::with_capacity(tags.len());
        for tag in tags {
            match lc_tags.get(&format_tag_lc(tag.as_ref())) {
                Some(&position) => positions.push(position),
                None => return Err(Error::key(format!("There is no tag with name '{}' to remove.", tag.as_ref()))),
            }
        }
        let mut index = 0;
        self.tags.retain(|_| {
            let keep = !positions.contains(&index);
            index += 1;
            keep
        });
        self.lc_tags = OnceLock::new();
        Ok(())
    }

    #[deprecated(note = "Use remove_tag() instead.")]
    pub fn delete_tag(&mut self, tag: &str) -> Result<()> {
        self.remove_tag(tag)
    }

    /// Sort the tags into dictionary order.
    pub fn sort_tags(&mut self, schema: Option<&Schema>) {
        let schema = get_schema(schema);
        let prefix = self.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
        self.tags.sort_by_cached_key(|tag| schema.tag_key(&format!("{}.{}", prefix, tag.name)));
        self.lc_tags = OnceLock::new();
    }

    /// Validate the saveframe: its values against the dictionary (`validate_schema`) and their
    /// NMR-STAR syntax (`validate_star`), and its loops the same way. Returns the problems found.
    /// Only the checks a saveframe can answer on its own are made; see [`Entry::validate_full`].
    pub fn validate(&self, validate_schema: bool, schema: Option<&Schema>, validate_star: bool) -> Vec<String> {
        let mut errors = Vec::new();
        let my_category = match self.category.as_deref() {
            Some(category) if !category.is_empty() => Some(category),
            _ => {
                errors.push(format!("Cannot properly validate saveframe: '{}'. No saveframe category defined.", self.name));
                None
            }
        };
        let prefix = self.tag_prefix.as_deref().unwrap_or("None");

        if validate_schema {
            let my_schema = get_schema(schema);
            for tag in &self.tags {
                errors.extend(my_schema.val_type(&format!("{}.{}", prefix, tag.name), &tag.value, my_category));
            }
        }
        if validate_star {
            for tag in &self.tags {
                let value = tag.value.to_py_string();
                if !value.is_ascii() {
                    errors.push(crate::validation::non_ascii_error(&format!("{}.{}", prefix, tag.name), &value));
                }
            }
        }
        for each_loop in &self.loops {
            errors.extend(each_loop.validate(validate_schema, schema, validate_star, my_category));
        }
        errors
    }

    /// Write the saveframe to a file, as NMR-STAR or JSON. `show_comments`, `skip_empty_loops`
    /// and `skip_empty_tags` are as for [`Saveframe::format`], and ignored for JSON.
    pub fn write_to_file(&self, path: impl AsRef<Path>, format: FileFormat, show_comments: bool,
                         skip_empty_loops: bool, skip_empty_tags: bool) -> Result<()> {
        let text = match format {
            FileFormat::NmrStar => self.format(skip_empty_loops, skip_empty_tags, show_comments)?,
            FileFormat::Json => self.to_json(),
        };
        write_file(path.as_ref(), &text)
    }
}

/// A value as optional text: None for a null value.
fn optional_string(value: &Value) -> Option<String> {
    match value {
        Value::Null => None,
        other => Some(other.to_py_string().into_owned()),
    }
}

impl<'a> IntoIterator for &'a Saveframe {
    type Item = &'a Loop;
    type IntoIter = std::slice::Iter<'a, Loop>;

    fn into_iter(self) -> Self::IntoIter {
        self.loops.iter()
    }
}
