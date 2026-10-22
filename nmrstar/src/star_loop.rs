//! Loops: tabular data within a saveframe.

use std::cmp::Ordering;
use std::collections::HashMap;
use std::sync::OnceLock;

use crate::csv;
use crate::definitions;
use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::format::format_loop;
use crate::internal::{self, Source};
use crate::json::Json;
use crate::parser::{self, ParseOptions};
use crate::pystr;
use crate::schema::Schema;
use crate::utils::{format_category, format_tag, format_tag_lc, get_schema};
use crate::value::{py_repr_list, Value};

/// Data to add to a loop with [`Loop::add_data`], in one of the four forms PyNMR-STAR accepted.
#[derive(Clone, Debug)]
pub enum Data {
    /// Rows of values, each with a value for every tag, in tag order.
    Rows(Vec<Vec<Value>>),
    /// A single row of values or, when rearranging, the values of several rows in a flat list.
    Flat(Vec<Value>),
    /// Rows given as (tag, value) pairs. Tags not given are `None`.
    Dicts(Vec<Vec<(String, Value)>>),
    /// The values of each tag, as (tag, values) pairs. A tag with fewer values than others is
    /// `None` in the rows it has no value for.
    Columns(Vec<(String, Vec<Value>)>),
}

impl Data {
    fn is_empty(&self) -> bool {
        match self {
            Data::Rows(rows) => rows.is_empty(),
            Data::Flat(values) => values.is_empty(),
            Data::Dicts(rows) => rows.is_empty(),
            Data::Columns(columns) => columns.is_empty(),
        }
    }
}

/// A loop: a table of values with one column per tag. All of a loop's tags share its category.
#[derive(Clone, Debug, Default)]
pub struct Loop {
    tags: Vec<String>,
    /// Lowercase tag -> position, built on demand
    lc_tags: OnceLock<HashMap<String, usize>>,
    /// The rows of the loop. Each should have a value for every tag.
    pub data: Vec<Vec<Value>>,
    category: Option<String>,
    /// Where the loop came from
    pub source: String,
}

impl PartialEq for Loop {
    /// Loops are equal when their categories, tags and data are.
    fn eq(&self, other: &Loop) -> bool {
        self.category == other.category && self.tags == other.tags && self.data == other.data
    }
}

impl PartialOrd for Loop {
    /// Loops sort by category. Unordered when either has no category.
    fn partial_cmp(&self, other: &Loop) -> Option<Ordering> {
        match (&self.category, &other.category) {
            (Some(a), Some(b)) => Some(a.cmp(b)),
            _ => None,
        }
    }
}

/// Raise an error if the category in a tag (if any) is not the loop's.
fn check_category(tag: &str, category: Option<&str>, message: &str) -> Result<()> {
    if tag.contains('.') {
        let supplied = format_category(tag);
        let matches = category.is_some_and(|category| pystr::lower(&supplied) == pystr::lower(category));
        if !matches {
            return Err(Error::value(message.replace("{supplied}", &supplied)
                .replace("{category}", category.unwrap_or("None"))));
        }
    }
    Ok(())
}

impl Loop {
    /// An empty loop with no category, which is set when the first tag with a category is
    /// added.
    pub fn new() -> Loop {
        Loop { source: "from_scratch()".to_string(), ..Default::default() }
    }

    pub(crate) fn with_source(source: &str) -> Loop {
        Loop { source: source.to_string(), ..Default::default() }
    }

    /// An empty loop, with a category if one is given (a `_` is added to it if needed).
    pub fn from_scratch(category: Option<&str>) -> Result<Loop> {
        let mut new_loop = Loop::new();
        if let Some(category) = category {
            new_loop.set_category(category)?;
        }
        Ok(new_loop)
    }

    /// Parse a loop from NMR-STAR text.
    pub fn from_str(text: &str) -> Result<Loop> {
        Loop::from_str_opts(text, ParseOptions::new())
    }

    /// Parse a loop from NMR-STAR text, with options.
    pub fn from_str_opts(text: &str, options: ParseOptions) -> Result<Loop> {
        Loop::parse(text, "from_string()", options)
    }

    fn parse(text: &str, source: &str, options: ParseOptions) -> Result<Loop> {
        let mut tmp_entry = Entry::from_scratch(0);
        let wrapped = format!("data_0 save_internaluseyoushouldntseethis_frame _internal.use internal {} save_", text);
        parser::parse(&wrapped, &mut tmp_entry, source, options)?;
        let mut loops = std::mem::take(&mut tmp_entry.frame_list[0].loops);
        if loops.len() > 1 {
            let detected: Vec<String> = loops.iter().map(Loop::repr).collect();
            return Err(Error::parsing(format!(
                "You attempted to parse one loop but the source you provided had more than one loop. Please either \
                 parse all loops as a saveframe or only parse one loop. Loops detected: [{}]", detected.join(", ")), None));
        }
        let mut parsed = loops.pop().ok_or_else(|| Error::parsing("You attempted to parse an empty string as a loop.", None))?;
        parsed.source = source.to_string();
        Ok(parsed)
    }

    /// Read a loop from CSV text: a header row of tags, then rows of values.
    pub fn from_csv_str(text: &str) -> Result<Loop> {
        Loop::from_csv_str_opts(text, false, None)
    }

    /// Read a loop from CSV text, converting its values to the types the dictionary declares if
    /// asked.
    pub fn from_csv_str_opts(text: &str, convert_data_types: bool, schema: Option<&Schema>) -> Result<Loop> {
        let mut new_loop = Loop::new();
        let mut rows = csv::rows(text);
        let header = rows.next().ok_or_else(|| Error::value("The CSV data has no header row."))?;
        new_loop.add_tags(&header)?;
        for row in rows {
            let values: Vec<Value> = row.into_iter().map(Value::from).collect();
            new_loop.add_data_with(Data::Flat(values), false, convert_data_types, schema)?;
        }
        new_loop.source = "from_csv('True')".to_string();
        Ok(new_loop)
    }

    /// Read a loop from a file (or a URL), in NMR-STAR format.
    pub fn from_file(source: impl Into<Source>) -> Result<Loop> {
        Loop::from_file_opts(source, ParseOptions::new())
    }

    /// Read a loop from a file (or a URL), in NMR-STAR format, with options.
    pub fn from_file_opts(source: impl Into<Source>, options: ParseOptions) -> Result<Loop> {
        let source = source.into();
        let text = internal::read_text(&source)?;
        Loop::parse(&text, &format!("from_file('{}')", source.label()), options)
    }

    /// Read a loop from a CSV file (or URL).
    pub fn from_csv_file(source: impl Into<Source>, convert_data_types: bool, schema: Option<&Schema>) -> Result<Loop> {
        let text = internal::read_text(&source.into())?;
        Loop::from_csv_str_opts(&text, convert_data_types, schema)
    }

    /// Create a loop from its JSON (as written by [`Loop::to_json`]).
    pub fn from_json(json: &str) -> Result<Loop> {
        let json = Json::parse(json).map_err(|_| {
            Error::value("The JSON you provided was neither a Python dictionary nor a JSON string.")
        })?;
        Loop::from_json_value(&json)
    }

    /// Create a loop from parsed JSON.
    pub fn from_json_value(json: &Json) -> Result<Loop> {
        for check in ["tags", "category", "data"] {
            if !json.has(check) {
                return Err(Error::value(format!(
                    "The JSON you provide must be a dictionary and must contain the key '{}' - even if the key points \
                     to None.", check)));
            }
        }
        let mut new_loop = Loop::new();
        new_loop.tags = json.get("tags").and_then(Json::as_array).map(|tags| {
            tags.iter().map(|tag| tag.to_optional_string().unwrap_or_default()).collect()
        }).unwrap_or_default();
        new_loop.set_category_raw(json.get("category").and_then(Json::to_optional_string).as_deref())?;
        if let Some(rows) = json.get("data").and_then(Json::as_array) {
            for row in rows {
                let row = row.as_array().ok_or_else(|| Error::value("Each row of loop data must be a list."))?;
                new_loop.data.push(row.iter().map(Json::to_value).collect::<Result<Vec<Value>>>()?);
            }
        }
        new_loop.source = "from_json()".to_string();
        Ok(new_loop)
    }

    /// A loop with the tags the dictionary defines for a category: those not marked internal,
    /// or with `all_tags` every one. It has no data.
    pub fn from_template(tag_prefix: &str, all_tags: bool, schema: Option<&Schema>) -> Result<Loop> {
        let schema = get_schema(schema);
        let mut new_loop = Loop::with_source(&format!("from_template({})", schema.version));
        for tag in Loop::tags_from_schema(tag_prefix, Some(schema), all_tags)? {
            new_loop.add_tag(&tag)?;
        }
        Ok(new_loop)
    }

    /// The tags the dictionary defines for a loop category.
    pub fn tags_from_schema(category: &str, schema: Option<&Schema>, all_tags: bool) -> Result<Vec<String>> {
        let schema = get_schema(schema);
        let mut category = category.to_string();
        if !category.starts_with('_') {
            category.insert(0, '_');
        }
        if !category.ends_with('.') {
            category.push('.');
        }
        let lower = pystr::lower(&category);
        let tags: Vec<String> = schema.schema_order.iter().filter(|item| {
            pystr::lower(item).starts_with(&lower)
                && (all_tags || schema.get_tag(item).is_some_and(|data| data.get("public") != "I"))
        }).cloned().collect();
        if tags.is_empty() {
            return Err(Error::invalid_state(format!(
                "The tag prefix '{}' has no corresponding tags in the dictionary.", category)));
        }
        Ok(tags)
    }

    /// The loop's category (its tag prefix, such as `_Entry_author`).
    pub fn category(&self) -> Option<&str> {
        self.category.as_deref()
    }

    /// Set the category exactly as given (without adding a `_`). It may not contain whitespace.
    pub fn set_category_raw(&mut self, category: Option<&str>) -> Result<()> {
        if let Some(category) = category {
            if !pystr::is_single_word(category) {
                return Err(Error::value(format!(
                    "Loop category cannot contain whitespace characters. Invalid category: '{}'", category)));
            }
        }
        self.category = category.map(str::to_string);
        Ok(())
    }

    /// Set the category, adding a `_` if needed and removing any tag name.
    pub fn set_category(&mut self, category: &str) -> Result<()> {
        self.set_category_raw(Some(&format_category(category)))
    }

    /// The tags (without the category).
    pub fn tags(&self) -> &[String] {
        &self.tags
    }

    /// The tags, to change. The data is not changed to match.
    pub fn tags_mut(&mut self) -> &mut Vec<String> {
        self.lc_tags = OnceLock::new();
        &mut self.tags
    }

    fn lc_tags(&self) -> &HashMap<String, usize> {
        self.lc_tags.get_or_init(|| {
            self.tags.iter().enumerate().map(|(i, tag)| (pystr::lower(tag), i)).collect()
        })
    }

    /// The position of a tag (given with or without the category), compared without regard to
    /// case.
    pub fn tag_index(&self, tag_name: &str) -> Option<usize> {
        self.lc_tags().get(&format_tag_lc(tag_name)).copied()
    }

    /// Whether the loop has a tag.
    pub fn contains_tag(&self, tag: &str) -> bool {
        self.tag_index(tag).is_some()
    }

    /// Whether the loop has every one of the tags.
    pub fn contains_tags<S: AsRef<str>>(&self, tags: &[S]) -> bool {
        tags.iter().all(|tag| self.contains_tag(tag.as_ref()))
    }

    /// The number of rows.
    pub fn len(&self) -> usize {
        self.data.len()
    }

    /// Whether the loop has no rows.
    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    /// The rows.
    pub fn iter(&self) -> std::slice::Iter<'_, Vec<Value>> {
        self.data.iter()
    }

    /// Whether the loop holds no data: every value (if any) is null.
    pub fn empty(&self) -> bool {
        self.data.iter().flatten().all(Value::is_null_value)
    }

    /// A description of the loop.
    pub fn repr(&self) -> String {
        format!("<pynmrstar.Loop '{}'>", self.category.as_deref().unwrap_or("None"))
    }

    /// Print a summary of the loop.
    pub fn print_tree(&self) {
        println!("{}", self.repr());
    }

    /// Set every value of a tag. As many values as there are rows must be given.
    pub fn set_tag_values(&mut self, key: &str, values: Vec<Value>) -> Result<()> {
        let tag_id = self.tag_index(key)
            .ok_or_else(|| Error::value(format!("Cannot assign to tag '{}' as it does not exist in this loop.", key)))?;
        let current = self.get_tag(key)?.len();
        if current != values.len() {
            return Err(Error::value(format!(
                "To assign to a tag you must provide a list (or iterable) of a length equal to the number of values \
                 that currently exist for that tag. The tag '{}' currently has {} values and you supplied {} values.",
                key, current, values.len())));
        }
        for (row, value) in self.data.iter_mut().zip(values) {
            row[tag_id] = value;
        }
        Ok(())
    }

    /// The loop in NMR-STAR format, as `str()` gave in PyNMR-STAR: loops without tags are
    /// written.
    pub fn to_star(&self) -> Result<String> {
        self.format(false, false)
    }

    /// The loop in NMR-STAR format. `skip_empty_loops` writes nothing for a loop with no tags;
    /// `skip_empty_tags` leaves out tags which have no non-null values.
    pub fn format(&self, skip_empty_loops: bool, skip_empty_tags: bool) -> Result<String> {
        if skip_empty_tags && !self.data.is_empty() {
            let width = self.data.iter().map(Vec::len).min().unwrap_or(0);
            let mut keep = Vec::new();
            for (x, tag) in self.tags.iter().enumerate() {
                if x >= width {
                    return Err(Error::Index("list index out of range".to_string()));
                }
                if !self.data.iter().all(|row| row[x].is_null_value()) {
                    keep.push(tag.clone());
                }
            }
            return self.filter(&keep, false)?.format(true, false);
        }

        if self.category.is_none() && !self.tags.is_empty() {
            return Err(Error::invalid_state(
                "The category was never set for this loop. Either add a tag with the category intact, specify it \
                 when generating the loop, or set it using Loop.set_category()."));
        }
        format_loop(&self.tags, self.category.as_deref().unwrap_or(""), &self.data, skip_empty_loops)
    }

    fn check_tags_match_data(&self) -> Result<()> {
        for (x, row) in self.data.iter().enumerate() {
            if self.tags.len() != row.len() {
                return Err(Error::invalid_state(format!(
                    "The number of tags must match the width of the data. Error in loop '{}'. In this case, there are \
                     {} tags, and row number {} has {} tags.",
                    self.category.as_deref().unwrap_or("None"), self.tags.len(), x, row.len())));
            }
        }
        Ok(())
    }

    /// Add data to the loop. See [`Data`] for the forms it may take.
    pub fn add_data(&mut self, data: Data) -> Result<()> {
        self.add_data_with(data, false, false, None)
    }

    /// Add a single row of values.
    pub fn add_row(&mut self, row: Vec<Value>) -> Result<()> {
        self.add_data(Data::Flat(row))
    }

    /// Add data to the loop. With `rearrange`, a flat list of values is split into rows. With
    /// `convert_data_types`, each value is converted to the type the dictionary (the schema
    /// given, or the default) declares for its tag.
    pub fn add_data_with(&mut self, data: Data, rearrange: bool, convert_data_types: bool, schema: Option<&Schema>) -> Result<()> {
        if data.is_empty() {
            return Err(Error::value("No valid data provided."));
        }
        let num_tags = self.tags.len();

        let mut pending: Vec<Vec<Value>> = match data {
            Data::Dicts(_) | Data::Columns(_) => {
                let rows: Vec<Vec<(String, Value)>> = match data {
                    Data::Dicts(rows) => rows,
                    Data::Columns(columns) => {
                        let max_length = columns.iter().map(|(_, values)| values.len()).max().unwrap_or(0);
                        (0..max_length).map(|row_id| {
                            columns.iter().filter_map(|(tag, values)| {
                                values.get(row_id).map(|value| (tag.clone(), value.clone()))
                            }).collect()
                        }).collect()
                    }
                    _ => unreachable!(),
                };
                let mut pending = Vec::with_capacity(rows.len());
                for (pos, row) in rows.into_iter().enumerate() {
                    let mut current_row = vec![Value::Null; num_tags];
                    for (tag, value) in row {
                        let index = self.lc_tags().get(&format_tag_lc(&tag)).copied().ok_or_else(|| Error::value(format!(
                            "In row {} of your provided data, a tag was supplied which was not already present in \
                             the loop. Invalid tag: '{}'", pos, tag)))?;
                        current_row[index] = value;
                    }
                    pending.push(current_row);
                }
                pending
            }
            Data::Rows(rows) => {
                for (pos, row) in rows.iter().enumerate() {
                    if row.len() != num_tags {
                        return Err(Error::value(format!(
                            "One of the lists you provided is not the correct length to match the number of tags \
                             present in the loop. Error on row {} with values: {}", pos, py_repr_list(row))));
                    }
                }
                rows
            }
            Data::Flat(values) => {
                if rearrange {
                    if num_tags == 0 {
                        return Err(Error::value("range() arg 3 must not be zero"));
                    }
                    let rows: Vec<Vec<Value>> = values.chunks(num_tags).map(<[Value]>::to_vec).collect();
                    if rows.last().is_some_and(|row| row.len() != num_tags) {
                        return Err(Error::value(format!(
                            "The number of data elements in the list you provided is not an even multiple of the \
                             number of tags which are set in the loop. Please either add missing tags using \
                             Loop.add_tag() or modify the list of tag values you are adding to be an even multiple \
                             of the number of tags. Error in loop '{}'.", self.category.as_deref().unwrap_or("None"))));
                    }
                    rows
                } else {
                    if values.len() != num_tags {
                        return Err(Error::value(
                            "The list must have the same number of elements as the number of tags when adding a \
                             single row of values! Insert tag names first by calling Loop.add_tag()."));
                    }
                    vec![values]
                }
            }
        };

        if convert_data_types {
            let schema = get_schema(schema);
            let category = self.category.as_deref().unwrap_or("None");
            for row in &mut pending {
                for (tag_id, datum) in row.iter_mut().enumerate() {
                    *datum = schema.convert_tag(&format!("{}.{}", category, self.tags[tag_id]), datum)?;
                }
            }
        }

        // Add the data at the very end so errors are caught before the data is changed
        self.data.extend(pending);
        Ok(())
    }

    /// Add data one value at a time, by tag. Values must be added in tag order.
    #[deprecated(note = "It is recommended to use Loop::add_data() instead for most use cases.")]
    pub fn add_data_by_tag(&mut self, tag_name: &str, value: Value) -> Result<()> {
        if tag_name.contains('.') {
            let supplied = format_category(tag_name);
            if self.category.as_deref().is_none_or(|category| pystr::lower(&supplied) != pystr::lower(category)) {
                return Err(Error::value(format!(
                    "Category provided in your tag '{}' does not match this loop's category '{}'.",
                    supplied, self.category.as_deref().unwrap_or("None"))));
            }
        }
        let pos = self.tag_index(tag_name).ok_or_else(|| Error::value(format!(
            "The tag '{}' to which you are attempting to add data does not yet exist. Create the tags using \
             Loop.add_tag() before adding data.", tag_name)))?;
        if self.data.is_empty() || self.data.last().unwrap().len() == self.tags.len() {
            self.data.push(Vec::new());
        }
        let last = self.data.last_mut().unwrap();
        if last.len() != pos {
            return Err(Error::value("You cannot add data out of tag order."));
        }
        last.push(value);
        Ok(())
    }

    /// Add the tags the dictionary defines for the loop's category which it does not have, sort
    /// the tags into dictionary order, and sort the rows by `Ordinal` (or number them).
    pub fn add_missing_tags(&mut self, schema: Option<&Schema>, all_tags: bool) -> Result<()> {
        let category = self.category.clone().ok_or_else(|| Error::invalid_state("The loop has no category."))?;
        let tags = Loop::tags_from_schema(&category, schema, all_tags)?;
        for tag in &tags {
            self.add_tag_with(tag, true, true)?;
        }
        self.sort_tags(schema)?;
        match self.sort_rows(&["Ordinal"]) {
            Err(Error::Type(_)) => {
                if let Some(ordinal_idx) = self.tag_index("Ordinal") {
                    for (pos, row) in self.data.iter_mut().enumerate() {
                        row[ordinal_idx] = Value::Int(pos as i64 + 1);
                    }
                }
            }
            Err(error) if error.is_value_error() => {}
            Err(error) => return Err(error),
            Ok(()) => {}
        }
        Ok(())
    }

    /// Add a tag. A tag given with its category sets the loop's category if it has none, and
    /// must match it otherwise.
    pub fn add_tag(&mut self, name: &str) -> Result<()> {
        self.add_tag_with(name, false, false)
    }

    /// Add several tags.
    pub fn add_tags<S: AsRef<str>>(&mut self, names: &[S]) -> Result<()> {
        for name in names {
            self.add_tag(name.as_ref())?;
        }
        Ok(())
    }

    /// Add a tag. With `ignore_duplicates`, adding a tag the loop already has does nothing
    /// rather than failing. With `update_data`, each row gains a `None` value for the tag.
    pub fn add_tag_with(&mut self, name: &str, ignore_duplicates: bool, update_data: bool) -> Result<()> {
        let mut name = pystr::strip(name);
        if let Some(dot) = name.find('.') {
            if !name.starts_with('.') {
                let mut category = name[..dot].to_string();
                if !category.starts_with('_') {
                    category.insert(0, '_');
                }
                match &self.category {
                    None => self.set_category_raw(Some(&category))?,
                    Some(existing) if pystr::lower(existing) != pystr::lower(&category) => {
                        return Err(Error::value(format!(
                            "One loop cannot have tags with different categories (or tags that don't match the loop \
                             category)! The loop category is '{}' while the category in the tag was '{}'.",
                            existing, category)));
                    }
                    _ => {}
                }
                name = &name[dot + 1..];
            } else {
                name = &name[1..];
            }
        }

        if self.tag_index(name).is_some() {
            if ignore_duplicates {
                return Ok(());
            }
            return Err(Error::value(format!("There is already a tag with the name '{}' in the loop '{}'.",
                                            name, self.category.as_deref().unwrap_or("None"))));
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

        self.tags.push(name.to_string());
        let position = self.tags.len() - 1;
        if let Some(cache) = self.lc_tags.get_mut() {
            cache.insert(pystr::lower(name), position);
        }
        if update_data {
            for row in &mut self.data {
                row.push(Value::Null);
            }
        }
        Ok(())
    }

    /// Remove all the rows. The tags and category stay.
    pub fn clear_data(&mut self) {
        self.data.clear();
    }

    /// The differences between two loops.
    pub fn compare(&self, other: &Loop) -> Vec<String> {
        if std::ptr::eq(self, other) {
            return Vec::new();
        }
        if let (Ok(a), Ok(b)) = (self.to_star(), other.to_star()) {
            if a == b {
                return Vec::new();
            }
        }

        let mut diffs = Vec::new();
        let category = self.category.as_deref().unwrap_or("None");
        let other_category = other.category.as_deref().unwrap_or("None");
        if pystr::lower(category) != pystr::lower(other_category) {
            diffs.push(format!("\t\tCategory of loops does not match: '{}' vs '{}'.", category, other_category));
        }
        let lower = |tags: &[String]| tags.iter().map(|t| pystr::lower(t)).collect::<Vec<_>>();
        if lower(&self.tags) != lower(&other.tags) {
            diffs.push(format!("\t\tLoop tag names do not match for loop with category '{}'.", category));
        } else if self.data != other.data {
            let sorted = |data: &[Vec<Value>]| {
                let mut copy = data.to_vec();
                copy.sort_by(|a, b| compare_rows(a, b));
                copy
            };
            if sorted(&self.data) != sorted(&other.data) {
                diffs.push(format!("\t\tLoop data does not match for loop with category '{}'.", category));
            }
        }
        diffs
    }

    /// Whether the loop is written exactly as the given NMR-STAR text.
    pub fn compare_str(&self, other: &str) -> Vec<String> {
        match self.to_star() {
            Ok(text) if text == other => Vec::new(),
            _ => vec!["String was not exactly equal to loop.".to_string()],
        }
    }

    /// A new loop with only some of the tags (and their data). Missing tags are an error,
    /// unless `ignore_missing_tags`.
    pub fn filter<S: AsRef<str>>(&self, tag_list: &[S], ignore_missing_tags: bool) -> Result<Loop> {
        let mut result = Loop::new();
        let mut columns = Vec::new();
        for tag in tag_list {
            let tag = tag.as_ref();
            match self.tag_index(tag) {
                Some(index) => {
                    check_category(tag, self.category.as_deref(),
                                   "Cannot fetch data with tag '{supplied}' because the category does not match the \
                                    category of this loop '{category}'.")?;
                    columns.push(index);
                    result.add_tag(&self.tags[index])?;
                }
                None if ignore_missing_tags => {}
                None => return Err(Error::key(format!("Cannot filter tag '{}' as it isn't present in this loop.", tag))),
            }
        }
        if columns.is_empty() && !self.data.is_empty() {
            return Err(Error::value("No valid data provided."));
        }
        for row in &self.data {
            let selected = columns.iter().map(|&c| row.get(c).cloned()
                .ok_or_else(|| Error::Index("list index out of range".to_string())))
                .collect::<Result<Vec<Value>>>()?;
            result.add_data(Data::Flat(selected))?;
        }
        if result.category.is_none() {
            result.category = self.category.clone();
        }
        Ok(result)
    }

    /// The data as CSV, with a header row of tags (with the category, unless not
    /// `show_category`) unless not `header`.
    pub fn get_data_as_csv(&self, header: bool, show_category: bool) -> String {
        let mut rows: Vec<Vec<Value>> = Vec::with_capacity(self.data.len() + 1);
        if header {
            let category = self.category.as_deref().unwrap_or("None");
            rows.push(self.tags.iter().map(|tag| {
                if show_category { Value::from(format!("{}.{}", category, tag)) } else { Value::from(tag) }
            }).collect());
        }
        rows.extend(self.data.iter().cloned());
        csv::write(&rows)
    }

    /// The loop as JSON.
    pub fn to_json_value(&self) -> Json {
        Json::Object(vec![
            ("category".to_string(), self.category.as_ref().map_or(Json::Null, |c| Json::Str(c.clone()))),
            ("tags".to_string(), Json::Array(self.tags.iter().map(|t| Json::Str(t.clone())).collect())),
            ("data".to_string(), Json::Array(self.data.iter().map(|row| {
                Json::Array(row.iter().map(Json::from_value).collect())
            }).collect())),
        ])
    }

    /// The loop as serialized JSON.
    pub fn to_json(&self) -> String {
        self.to_json_value().dumps()
    }

    /// The tags with the category.
    pub fn get_tag_names(&self) -> Result<Vec<String>> {
        match self.category.as_deref() {
            Some(category) if !category.is_empty() => {
                Ok(self.tags.iter().map(|tag| format!("{}.{}", category, tag)).collect())
            }
            _ => Err(Error::invalid_state(
                "You never set the category of this loop. You must set the category before calling this method, \
                 either by setting the loop category directly when creating the loop using the Loop.from_scratch() \
                 class method, by calling loop.set_category(), or by adding a fully qualified tag which includes the \
                 loop category (for example, adding '_Citation_author.Family_name' rather than just 'Family_name').")),
        }
    }

    /// The columns of the given tags, checking any categories given.
    fn tag_columns<S: AsRef<str>>(&self, tags: &[S]) -> Result<Vec<usize>> {
        let mut first_positions: HashMap<String, usize> = HashMap::new();
        for (i, tag) in self.tags.iter().enumerate() {
            first_positions.entry(pystr::lower(tag)).or_insert(i);
        }
        let mut columns = Vec::with_capacity(tags.len());
        for tag in tags {
            let tag = tag.as_ref();
            check_category(tag, self.category.as_deref(),
                           "Cannot fetch data with tag '{supplied}' because the category does not match the category \
                            of this loop '{category}'.").map_err(|_| Error::value(format!(
                "Cannot fetch data with tag '{}' because the category does not match the category of this loop '{}'.",
                tag, self.category.as_deref().unwrap_or("None"))))?;
            match first_positions.get(&format_tag_lc(tag)) {
                Some(&column) => columns.push(column),
                None => return Err(Error::key(format!(
                    "Could not locate the tag with name or ID: '{}' in loop '{}'.",
                    tag, self.category.as_deref().unwrap_or("None")))),
            }
        }
        Ok(columns)
    }

    fn cell(row: &[Value], column: usize) -> Result<Value> {
        row.get(column).cloned().ok_or_else(|| Error::Index("list index out of range".to_string()))
    }

    /// The values of one tag, one per row.
    pub fn get_tag(&self, tag: &str) -> Result<Vec<Value>> {
        let column = self.tag_columns(&[tag])?[0];
        self.data.iter().map(|row| Loop::cell(row, column)).collect()
    }

    /// The values of several tags, as rows.
    pub fn get_tags<S: AsRef<str>>(&self, tags: &[S]) -> Result<Vec<Vec<Value>>> {
        let columns = self.tag_columns(tags)?;
        self.data.iter().map(|row| columns.iter().map(|&c| Loop::cell(row, c)).collect()).collect()
    }

    /// The values of one tag with the full tag name: (`_Category.Tag`, value) per row.
    pub fn get_tag_whole(&self, tag: &str) -> Result<Vec<(String, Value)>> {
        Ok(self.get_tags_whole(&[tag])?.into_iter().map(|mut row| row.remove(0)).collect())
    }

    /// The values of several tags, as rows of (`_Category.Tag`, value) pairs.
    pub fn get_tags_whole<S: AsRef<str>>(&self, tags: &[S]) -> Result<Vec<Vec<(String, Value)>>> {
        let columns = self.tag_columns(tags)?;
        let category = self.category.as_deref().unwrap_or("None");
        self.data.iter().map(|row| columns.iter().map(|&c| {
            Ok((format!("{}.{}", category, self.tags[c]), Loop::cell(row, c)?))
        }).collect()).collect()
    }

    /// The values of the tags (every tag if None) as rows of (tag, value) pairs: the tag as
    /// given, or with `whole_tag` as the loop spells it, with its category.
    pub fn get_tags_dict<S: AsRef<str>>(&self, tags: Option<&[S]>, whole_tag: bool) -> Result<Vec<Vec<(String, Value)>>> {
        let names: Vec<String> = match tags {
            Some(tags) => tags.iter().map(|t| t.as_ref().to_string()).collect(),
            None => self.tags.clone(),
        };
        let columns = self.tag_columns(&names)?;
        let category = self.category.as_deref().unwrap_or("None");
        self.data.iter().map(|row| columns.iter().zip(&names).map(|(&c, name)| {
            let key = if whole_tag { format!("{}.{}", category, self.tags[c]) } else { name.clone() };
            Ok((key, Loop::cell(row, c)?))
        }).collect()).collect()
    }

    /// Remove every row whose value of a tag equals the given one, returning the removed rows.
    /// If `index_tag` is given, that tag is renumbered from 1.
    pub fn remove_data_by_tag_value(&mut self, tag: &str, value: &Value, index_tag: Option<&str>) -> Result<Vec<Vec<Value>>> {
        check_category(tag, self.category.as_deref(),
                       "The category provided in your tag '{supplied}' does not match this loop's category '{category}'.")?;
        let search_tag = self.tag_index(tag)
            .ok_or_else(|| Error::value(format!("The tag you provided '{}' isn't in this loop!", tag)))?;
        let mut deleted = Vec::new();
        let mut kept = Vec::with_capacity(self.data.len());
        for row in std::mem::take(&mut self.data) {
            if row.get(search_tag) == Some(value) {
                deleted.push(row);
            } else {
                kept.push(row);
            }
        }
        self.data = kept;
        if let Some(index_tag) = index_tag {
            self.renumber_rows(index_tag, 1, false)?;
        }
        Ok(deleted)
    }

    /// Remove tags, and their data.
    pub fn remove_tag(&mut self, tag: &str) -> Result<()> {
        self.remove_tags(&[tag])
    }

    /// Remove several tags, and their data. Nothing is removed unless every tag exists.
    pub fn remove_tags<S: AsRef<str>>(&mut self, tags: &[S]) -> Result<()> {
        for tag in tags {
            if self.tag_index(tag.as_ref()).is_none() {
                return Err(Error::key(format!("There is no tag with name '{}' to remove in loop '{}'.",
                                              tag.as_ref(), self.category.as_deref().unwrap_or("None"))));
            }
        }
        for tag in tags {
            let position = self.tag_index(tag.as_ref()).unwrap();
            self.tags.remove(position);
            self.lc_tags = OnceLock::new();
            for row in &mut self.data {
                if position < row.len() {
                    row.remove(position);
                }
            }
        }
        Ok(())
    }

    #[deprecated(note = "Use remove_tag() instead.")]
    pub fn delete_tag(&mut self, tag: &str) -> Result<()> {
        self.remove_tag(tag)
    }

    #[deprecated(note = "Use remove_data_by_tag_value() instead.")]
    pub fn delete_data_by_tag_value(&mut self, tag: &str, value: &Value, index_tag: Option<&str>) -> Result<Vec<Vec<Value>>> {
        self.remove_data_by_tag_value(tag, value, index_tag)
    }

    /// The column of a tag given by name, or by position as text ("0").
    fn tag_or_position(&self, tag: &str, error: impl FnOnce() -> Error) -> Result<usize> {
        match self.tag_index(tag) {
            Some(index) => Ok(index),
            None => match crate::value::parse_int(tag) {
                Some(position) if position >= 0 => Ok(position as usize),
                Some(_) => Err(Error::Index("list index out of range".to_string())),
                None => Err(error()),
            },
        }
    }

    /// Renumber a tag incrementally from `start_value`. With `maintain_ordering` the values are
    /// offset rather than replaced, so 2, 3, 3, 5 become 1, 2, 2, 4.
    pub fn renumber_rows(&mut self, index_tag: &str, start_value: i64, maintain_ordering: bool) -> Result<()> {
        check_category(index_tag, self.category.as_deref(),
                       "Category provided in your tag '{supplied}' does not match this loop's category '{category}'.")?;
        let column = self.tag_or_position(index_tag, || {
            Error::value(format!("The renumbering tag you provided '{}' isn't in this loop!", index_tag))
        })?;
        if self.data.is_empty() {
            return Ok(());
        }
        self.check_tags_match_data()?;
        if column >= self.tags.len() {
            return Err(Error::Index("list index out of range".to_string()));
        }

        if maintain_ordering {
            let data_copy = self.data.clone();
            let mut offset = 0;
            for pos in 0..self.data.len() {
                let current = self.data[pos][column].clone();
                let as_int = |value: &Value| match value.py_int() {
                    Ok(i) => Ok(i),
                    Err(crate::value::ConversionError::Type) => Err(Error::Type(format!(
                        "int() argument must be a string or a number, not '{}'", value))),
                    Err(crate::value::ConversionError::Value) => Err(Error::value(format!(
                        "You can't renumber a row containing anything that can't be coerced into an integer using \
                         maintain_ordering. I.e. what am I suppose to renumber '{}' to?", value))),
                };
                let result = (|| {
                    if pos == 0 {
                        offset = start_value - as_int(&self.data[0][column])?;
                    }
                    as_int(&current).map(|i| i + offset)
                })();
                match result {
                    Ok(new_value) => {
                        self.data[pos][column] = if current.is_str() {
                            Value::from(new_value.to_string())
                        } else {
                            Value::Int(new_value)
                        };
                    }
                    Err(error) => {
                        if matches!(error, Error::Value(_)) {
                            self.data = data_copy;
                        }
                        return Err(error);
                    }
                }
            }
        } else {
            for (pos, row) in self.data.iter_mut().enumerate() {
                let number = pos as i64 + start_value;
                row[column] = if row[column].is_str() { Value::from(number.to_string()) } else { Value::Int(number) };
            }
        }
        Ok(())
    }

    /// Sort the tags (and the data with them) into dictionary order.
    pub fn sort_tags(&mut self, schema: Option<&Schema>) -> Result<()> {
        let schema = get_schema(schema);
        let current_order = self.get_tag_names()?;
        let mut sorted_order = current_order.clone();
        sorted_order.sort_by_key(|tag| schema.tag_key(tag));
        if sorted_order == current_order {
            return Ok(());
        }
        self.data = self.get_tags(&sorted_order)?;
        self.tags = sorted_order.iter().map(|tag| format_tag(tag).to_string()).collect();
        self.lc_tags = OnceLock::new();
        Ok(())
    }

    /// The columns to sort by, from tag names or positions.
    fn sort_columns<S: AsRef<str>>(&self, tags: &[S]) -> Result<Vec<usize>> {
        tags.iter().map(|tag| {
            let tag = tag.as_ref();
            check_category(tag, self.category.as_deref(),
                           "The category provided in your tag '{supplied}' does not match this loop's category \
                            '{category}'.")?;
            self.tag_or_position(tag, || Error::value(format!("The sorting tag you provided '{}' isn't in this loop!", tag)))
        }).collect()
    }

    /// Sort the rows by the values of tags (given by name or position). The values are sorted as
    /// numbers if they all are numbers, and otherwise as text. With several tags, the last is
    /// the most significant.
    pub fn sort_rows<S: AsRef<str>>(&mut self, tags: &[S]) -> Result<()> {
        if self.data.is_empty() {
            return Ok(());
        }
        for column in self.sort_columns(tags)? {
            if self.data.iter().any(|row| row.len() <= column) {
                return Err(Error::Index("list index out of range".to_string()));
            }
            // Sort as numbers if every value is one; a null value can not be sorted at all
            let mut keys = Vec::with_capacity(self.data.len());
            let mut numeric = true;
            for row in &self.data {
                match row[column].py_float() {
                    Ok(key) => keys.push(key),
                    Err(crate::value::ConversionError::Type) => {
                        return Err(Error::Type(format!("float() argument must be a string or a real number, not '{}'",
                                                       row[column])));
                    }
                    Err(crate::value::ConversionError::Value) => {
                        numeric = false;
                        break;
                    }
                }
            }
            if numeric {
                let mut indexed: Vec<(f64, Vec<Value>)> = keys.into_iter().zip(std::mem::take(&mut self.data)).collect();
                indexed.sort_by(|a, b| a.0.partial_cmp(&b.0).unwrap_or(Ordering::Equal));
                self.data = indexed.into_iter().map(|(_, row)| row).collect();
            } else {
                let mut incomparable = false;
                let mut data = self.data.clone();
                data.sort_by(|a, b| a[column].py_cmp(&b[column]).unwrap_or_else(|| {
                    incomparable = true;
                    Ordering::Equal
                }));
                if incomparable {
                    // Python's sort raises, leaving the rows as they were
                    return Err(Error::Type("'<' not supported between the values".to_string()));
                }
                self.data = data;
            }
        }
        Ok(())
    }

    /// Sort the rows by a key computed from each row. The tags are checked to exist, but the key
    /// alone decides the order.
    pub fn sort_rows_by_key<S: AsRef<str>, K: Ord>(&mut self, tags: &[S], key: impl Fn(&[Value]) -> K) -> Result<()> {
        if self.data.is_empty() {
            return Ok(());
        }
        self.sort_columns(tags)?;
        self.data.sort_by_key(|row| key(row));
        Ok(())
    }

    /// Validate the loop: its values against the dictionary (`validate_schema`), and their
    /// NMR-STAR syntax (`validate_star`). Returns the problems found. Only the checks a loop can
    /// answer on its own are made; see [`Entry::validate_full`] for the rest.
    pub fn validate(&self, validate_schema: bool, schema: Option<&Schema>, validate_star: bool, category: Option<&str>) -> Vec<String> {
        let mut errors = Vec::new();
        let loop_category = self.category.as_deref().unwrap_or("None");

        if validate_schema {
            let schema = get_schema(schema);
            for row in &self.data {
                for (pos, datum) in row.iter().enumerate() {
                    if let Some(tag) = self.tags.get(pos) {
                        errors.extend(schema.val_type(&format!("{}.{}", loop_category, tag), datum, category));
                    }
                }
            }
        }

        if validate_star {
            let num_cols = self.tags.len();
            for (row_num, row) in self.data.iter().enumerate() {
                if row.len() != num_cols {
                    errors.push(format!("Loop '{}' data width does not match it's tag width on row '{}'.",
                                        loop_category, row_num));
                }
                if !row.is_empty() && row.iter().all(Value::is_null_value) {
                    errors.push(format!("Loop '{}' row '{}' contains only null values.", loop_category, row_num));
                    continue;
                }
                for (pos, datum) in row.iter().enumerate() {
                    let text = datum.to_py_string();
                    if !text.is_ascii() {
                        let tag = match self.tags.get(pos) {
                            Some(tag) => format!("{}.{}", loop_category, tag),
                            None => loop_category.to_string(),
                        };
                        errors.push(crate::validation::non_ascii_error(&tag, &text));
                    }
                }
            }
        }
        errors
    }
}

/// Compare rows as Python compares lists.
fn compare_rows(a: &[Value], b: &[Value]) -> Ordering {
    for (x, y) in a.iter().zip(b) {
        if x != y {
            return x.total_cmp(y);
        }
    }
    a.len().cmp(&b.len())
}
