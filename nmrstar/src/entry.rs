//! Entries: a whole NMR-STAR file.

use std::collections::{HashMap, HashSet};
use std::path::Path;

use log::warn;

use crate::definitions;
use crate::error::{Error, Result};
use crate::internal::{self, Source};
use crate::json::Json;
use crate::parser::{self, ParseOptions};
use crate::pystr;
use crate::saveframe::{write_file, FileFormat, Saveframe};
use crate::schema::Schema;
use crate::sha1::sha1;
use crate::star_loop::Loop;
use crate::utils::{format_category, get_schema};
use crate::validation::{self, Severity, ValidationIssue};
use crate::value::Value;

/// An NMR-STAR entry, such as BMRB entry 15000: an ID, and a list of saveframes.
#[derive(Clone, Debug)]
pub struct Entry {
    /// The entry ID: the `xxx` of `data_xxx`. Set it with [`Entry::set_entry_id`] to update the
    /// tags which hold it too.
    pub entry_id: Value,
    /// The saveframes
    pub frame_list: Vec<Saveframe>,
    /// Where the entry came from
    pub source: Option<String>,
}

impl PartialEq for Entry {
    /// Entries are equal when their IDs and saveframes are.
    fn eq(&self, other: &Entry) -> bool {
        self.entry_id == other.entry_id && self.frame_list == other.frame_list
    }
}

/// The key a saveframe category sorts by when normalizing.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Debug)]
enum CategoryKey {
    /// The position of the category in the dictionary
    Known(usize),
    /// After every dictionary category, in an arbitrary but stable order
    Hashed([u8; 20]),
    Infinite,
}

#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Debug)]
enum IdKey {
    Id(i64),
    Infinite,
}

/// How many leading and trailing words two tags' names have in common. `Dipole_1_Comp_index_ID_2`
/// and `Dipole_1_Entity_ID_2` share four (`Dipole`, `1` and `ID`, `2`).
fn shared_decoration(first: &str, second: &str) -> usize {
    let words = |tag: &str| -> Vec<String> {
        pystr::lower(tag.rsplit('.').next().unwrap_or(tag)).split('_').map(str::to_string).collect()
    };
    let (first, second) = (words(first), words(second));
    let length = first.len().min(second.len());
    let mut leading = 0;
    while leading < length && first[leading] == second[leading] {
        leading += 1;
    }
    let mut trailing = 0;
    while trailing < length - leading && first[first.len() - 1 - trailing] == second[second.len() - 1 - trailing] {
        trailing += 1;
    }
    leading + trailing
}

/// The category part of a lowercase full tag name.
fn category_of(tag: &str) -> &str {
    tag.rsplit_once('.').map(|(category, _)| category).unwrap_or(tag)
}

impl Entry {
    /// An empty entry with an ID (the `xxx` of `data_xxx`).
    pub fn from_scratch(entry_id: impl Into<Value>) -> Entry {
        Entry { entry_id: entry_id.into(), frame_list: Vec::new(), source: Some("from_scratch()".to_string()) }
    }

    /// Parse an entry from NMR-STAR text.
    #[allow(clippy::should_implement_trait)]
    pub fn from_str(text: &str) -> Result<Entry> {
        Entry::from_str_opts(text, ParseOptions::new())
    }

    /// Parse an entry from NMR-STAR text, with options.
    pub fn from_str_opts(text: &str, options: ParseOptions) -> Result<Entry> {
        Entry::parse(text, "from_string()", options)
    }

    fn parse(text: &str, source: &str, options: ParseOptions) -> Result<Entry> {
        let mut entry = Entry { entry_id: Value::Int(0), frame_list: Vec::new(), source: Some(source.to_string()) };
        parser::parse(text, &mut entry, source, options)?;
        Ok(entry)
    }

    /// Read an entry from a file (or URL), which may be gzipped.
    pub fn from_file(source: impl Into<Source>) -> Result<Entry> {
        Entry::from_file_opts(source, ParseOptions::new())
    }

    /// Read an entry from a file (or URL), which may be gzipped, with options.
    pub fn from_file_opts(source: impl Into<Source>, options: ParseOptions) -> Result<Entry> {
        let source = source.into();
        let text = internal::read_text(&source)?;
        Entry::parse(&text, &format!("from_file('{}')", source.label()), options)
    }

    /// Fetch the current version of an entry from the BMRB (over HTTPS).
    pub fn from_database(entry_num: &str) -> Result<Entry> {
        internal::get_entry_from_database(entry_num, false, None)
    }

    /// Fetch the current version of an entry from the BMRB, converting its values to the types
    /// the dictionary declares.
    pub fn from_database_opts(entry_num: &str, convert_data_types: bool, schema: Option<&Schema>) -> Result<Entry> {
        internal::get_entry_from_database(entry_num, convert_data_types, schema)
    }

    /// Create an entry from its JSON (as written by [`Entry::to_json`]).
    pub fn from_json(json: &str) -> Result<Entry> {
        let json = Json::parse(json).map_err(|_| {
            Error::value("The JSON you provided was neither a Python dictionary nor a JSON string.")
        })?;
        Entry::from_json_value(&json)
    }

    /// Create an entry from parsed JSON.
    pub fn from_json_value(json: &Json) -> Result<Entry> {
        if !json.has("saveframes") {
            return Err(Error::value("The JSON you provide must be a hash and must contain the key 'saveframes' - even \
                                     if the key points to 'None'."));
        }
        let entry_id = json.get("entry_id").or_else(|| json.get("bmrb_id")).ok_or_else(|| Error::value(
            "The JSON you provide must be a hash and must contain the key 'entry_id' - even if the key points to 'None'."))?;
        let mut entry = Entry::from_scratch(entry_id.to_value()?);
        for frame in json.get("saveframes").and_then(Json::as_array).map(Vec::as_slice).unwrap_or(&[]) {
            entry.frame_list.push(Saveframe::from_json_value(frame)?);
        }
        entry.source = Some("from_json()".to_string());
        Ok(entry)
    }

    /// An entry with the saveframes and loops the dictionary defines, and their tags (those not
    /// marked internal, or with `all_tags` every one). With `default_values`, tags get their
    /// dictionary default values.
    pub fn from_template(entry_id: impl Into<Value>, all_tags: bool, default_values: bool, schema: Option<&Schema>) -> Result<Entry> {
        let schema = get_schema(schema);
        let mut entry = Entry::from_scratch(entry_id);
        let mut categories: HashSet<String> = HashSet::new();
        for tag in &schema.schema_order {
            let Some(data) = schema.get_tag(tag) else { continue };
            let category = data.get("SFCategory").to_string();
            if categories.insert(category.clone()) {
                entry.frame_list.push(Saveframe::from_template(&category, Some(&format!("{}_1", category)),
                                                               Some(entry.entry_id.clone()), all_tags, default_values,
                                                               Some(schema))?);
            }
        }
        let version = schema.version.clone();
        let frame = entry.get_saveframes_by_category_mut("entry_information").into_iter().next()
            .ok_or_else(|| Error::Index("list index out of range".to_string()))?;
        frame.set_tag("NMR_STAR_version", version.as_str())?;
        frame.set_tag("Original_NMR_STAR_version", version.as_str())?;
        entry.source = Some(format!("from_template({})", schema.version));
        Ok(entry)
    }

    /// A description of the entry.
    pub fn repr(&self) -> String {
        format!("<pynmrstar.Entry '{}' {}>", self.entry_id, self.source.as_deref().unwrap_or("None"))
    }

    /// The number of saveframes.
    pub fn len(&self) -> usize {
        self.frame_list.len()
    }

    /// Whether the entry has no saveframes.
    pub fn is_empty(&self) -> bool {
        self.frame_list.is_empty()
    }

    /// The saveframes.
    pub fn iter(&self) -> std::slice::Iter<'_, Saveframe> {
        self.frame_list.iter()
    }

    /// The saveframes, to change.
    pub fn iter_mut(&mut self) -> std::slice::IterMut<'_, Saveframe> {
        self.frame_list.iter_mut()
    }

    /// Whether any saveframe has the tag or loop (see [`Saveframe::contains`]).
    pub fn contains(&self, item: &str) -> bool {
        self.frame_list.iter().any(|frame| frame.contains(item))
    }

    /// Whether the entry has every one of the tags or loops.
    pub fn contains_all<S: AsRef<str>>(&self, items: &[S]) -> bool {
        items.iter().all(|item| self.contains(item.as_ref()))
    }

    /// Whether the entry has a saveframe equal to the one given.
    pub fn contains_saveframe(&self, saveframe: &Saveframe) -> bool {
        self.frame_list.contains(saveframe)
    }

    /// Whether any saveframe has a loop equal to the one given.
    pub fn contains_loop(&self, other: &Loop) -> bool {
        self.frame_list.iter().any(|frame| frame.contains_loop(other))
    }

    /// The saveframe at a position.
    pub fn frame_at(&self, index: usize) -> Result<&Saveframe> {
        self.frame_list.get(index).ok_or_else(|| Error::Index("list index out of range".to_string()))
    }

    /// The saveframe at a position, to change.
    pub fn frame_at_mut(&mut self, index: usize) -> Result<&mut Saveframe> {
        self.frame_list.get_mut(index).ok_or_else(|| Error::Index("list index out of range".to_string()))
    }

    /// Remove the saveframe at a position.
    pub fn remove_saveframe_at(&mut self, index: usize) -> Result<Saveframe> {
        if index >= self.frame_list.len() {
            return Err(Error::Index(format!("Index out of range: no saveframe at index: {}", index)));
        }
        Ok(self.frame_list.remove(index))
    }

    /// Replace the saveframe at a position.
    pub fn set_saveframe_at(&mut self, index: usize, saveframe: Saveframe) -> Result<()> {
        let slot = self.frame_list.get_mut(index).ok_or_else(|| Error::Index("list assignment index out of range".to_string()))?;
        *slot = saveframe;
        Ok(())
    }

    /// Replace the saveframe with a name.
    pub fn set_saveframe(&mut self, name: &str, saveframe: Saveframe) -> Result<()> {
        let mut found = false;
        for frame in &mut self.frame_list {
            if frame.name() == name {
                if found {
                    return Err(Error::value(format!(
                        "Cannot replace the saveframe with the name '{} because multiple saveframes in the entry have \
                         the same name. This library does not allow that normally, as it is invalid NMR-STAR. Did you \
                         manually edit the Entry.frame_list object? Please use the Entry.add_saveframe() method instead \
                         to add new saveframes.", frame.name())));
                }
                *frame = saveframe.clone();
                found = true;
            }
        }
        if !found {
            return Err(Error::value(format!(
                "Saveframe with name '{}' does not exist and therefore cannot be written to. Use the add_saveframe() \
                 method to add new saveframes.", name)));
        }
        Ok(())
    }

    /// The entry in NMR-STAR format, with comments, as `str()` gave in PyNMR-STAR: loops without
    /// tags are written.
    pub fn to_star(&self) -> Result<String> {
        self.format(false, false, true)
    }

    /// The entry in NMR-STAR format. `skip_empty_loops` leaves out loops with no tags;
    /// `skip_empty_tags` leaves out tags with no non-null values; `show_comments` writes the
    /// standard comments before the first saveframe of each category.
    pub fn format(&self, skip_empty_loops: bool, skip_empty_tags: bool, show_comments: bool) -> Result<String> {
        let mut seen: HashSet<Option<&str>> = HashSet::new();
        let mut parts: Vec<String> = Vec::with_capacity(self.frame_list.len() + 1);
        parts.push(format!("data_{}\n", self.entry_id));
        for frame in &self.frame_list {
            let first = seen.insert(frame.category());
            parts.push(frame.format_impl(true, skip_empty_loops, skip_empty_tags, show_comments && first)?);
        }
        if parts.len() == 1 {
            return Ok(format!("data_{}\n\n", self.entry_id));
        }
        Ok(parts.join("\n"))
    }

    /// The categories of the saveframes, each once, in order.
    pub fn category_list(&self) -> Vec<String> {
        let mut categories: Vec<String> = Vec::new();
        for frame in &self.frame_list {
            if let Some(category) = frame.category() {
                if !category.is_empty() && !categories.iter().any(|c| c == category) {
                    categories.push(category.to_string());
                }
            }
        }
        categories
    }

    /// Whether the entry holds no data (see [`Saveframe::empty`]).
    pub fn empty(&self) -> bool {
        self.frame_list.iter().all(Saveframe::empty)
    }

    /// Set the entry ID, and every tag the dictionary marks as holding it (such as `_Entry.ID`
    /// and `_Citation.Entry_ID`).
    pub fn set_entry_id(&mut self, value: impl Into<Value>) -> Result<()> {
        self.entry_id = value.into();
        let schema = get_schema(None);
        let entry_id = self.entry_id.clone();
        let is_entry_id = |tag: &str| schema.get(&pystr::lower(tag)).is_some_and(|data| data.get("entryIdFlg") == "Y");
        for frame in &mut self.frame_list {
            let prefix = frame.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
            for tag in frame.tags_mut() {
                if is_entry_id(&format!("{}.{}", prefix, tag.name)) {
                    tag.value = entry_id.clone();
                }
            }
            for each_loop in &mut frame.loops {
                let category = each_loop.category().unwrap_or("None").to_string();
                for tag in each_loop.tags().to_vec() {
                    if is_entry_id(&format!("{}.{}", category, tag)) {
                        let values = vec![entry_id.clone(); each_loop.len()];
                        each_loop.set_tag_values(&tag, values)?;
                    }
                }
            }
        }
        Ok(())
    }

    /// The saveframes by name. An entry with two saveframes of the same name is invalid.
    pub fn frame_dict(&self) -> Result<HashMap<&str, &Saveframe>> {
        let mut frames: HashMap<&str, &Saveframe> = HashMap::with_capacity(self.frame_list.len());
        for frame in &self.frame_list {
            if frames.insert(frame.name(), frame).is_some() {
                return Err(Error::invalid_state(format!(
                    "The entry has multiple saveframes with the same name. That is not allowed in the NMR-STAR format. \
                     Please remove or rename one. Duplicate name: '{}'. Furthermore, please use Entry.add_saveframe() \
                     and Entry.remove_saveframe() rather than manually editing the Entry.frame_list list, which will \
                     prevent this state from existing in the future.", frame.name())));
            }
        }
        Ok(frames)
    }

    /// Add a saveframe. Its name must not be that of a saveframe the entry already has.
    pub fn add_saveframe(&mut self, frame: Saveframe) -> Result<()> {
        if self.frame_dict()?.contains_key(frame.name()) {
            return Err(Error::value(format!(
                "Cannot add a saveframe with name '{}' since a saveframe with that name already exists in the entry.",
                frame.name())));
        }
        self.frame_list.push(frame);
        Ok(())
    }

    /// The differences between two entries. Non-equal entries are always detected, but the
    /// specific differences reported depend on the order of the entries.
    pub fn compare(&self, other: &Entry) -> Vec<String> {
        if std::ptr::eq(self, other) {
            return Vec::new();
        }
        let mut diffs = Vec::new();
        if self.entry_id.to_py_string() != other.entry_id.to_py_string() {
            diffs.push(format!("Entry ID does not match between entries: '{}' vs '{}'.", self.entry_id, other.entry_id));
        }
        if self.frame_list.len() != other.frame_list.len() {
            diffs.push(format!("The number of saveframes in the entries are not equal: '{}' vs '{}'.",
                               self.frame_list.len(), other.frame_list.len()));
        }
        let other_frames: HashMap<&str, &Saveframe> = other.frame_list.iter().map(|f| (f.name(), f)).collect();
        for frame in &self.frame_list {
            match other_frames.get(frame.name()) {
                None => diffs.push(format!("No saveframe with name '{}' in other entry.", frame.name())),
                Some(other_frame) => {
                    let compared = frame.compare(other_frame);
                    if !compared.is_empty() {
                        diffs.push(format!("Saveframes do not match: '{}'.", frame.name()));
                        diffs.extend(compared);
                    }
                }
            }
        }
        diffs
    }

    /// Whether the entry is written exactly as the given NMR-STAR text.
    pub fn compare_str(&self, other: &str) -> Vec<String> {
        match self.to_star() {
            Ok(text) if text == other => Vec::new(),
            _ => vec!["String was not exactly equal to entry.".to_string()],
        }
    }

    /// Add the tags the dictionary defines which are missing, to every saveframe and loop, and
    /// sort the tags.
    pub fn add_missing_tags(&mut self, schema: Option<&Schema>, all_tags: bool) -> Result<()> {
        for frame in &mut self.frame_list {
            frame.add_missing_tags(schema, all_tags, true)?;
        }
        Ok(())
    }

    /// The entry as JSON.
    pub fn to_json_value(&self) -> Json {
        Json::Object(vec![
            ("entry_id".to_string(), Json::from_value(&self.entry_id)),
            ("saveframes".to_string(), Json::Array(self.frame_list.iter().map(Saveframe::to_json_value).collect())),
        ])
    }

    /// The entry as serialized JSON.
    pub fn to_json(&self) -> String {
        self.to_json_value().dumps()
    }

    /// The loops of a category, from every saveframe.
    pub fn get_loops_by_category(&self, value: &str) -> Vec<&Loop> {
        let value = pystr::lower(&format_category(value));
        self.frame_list.iter().flat_map(|frame| frame.loops.iter())
            .filter(|l| l.category().is_some_and(|c| pystr::lower(c) == value)).collect()
    }

    /// The loops of a category, from every saveframe, to change.
    pub fn get_loops_by_category_mut(&mut self, value: &str) -> Vec<&mut Loop> {
        let value = pystr::lower(&format_category(value));
        self.frame_list.iter_mut().flat_map(|frame| frame.loops.iter_mut())
            .filter(|l| l.category().is_some_and(|c| pystr::lower(c) == value)).collect()
    }

    /// The saveframe with a name.
    pub fn get_saveframe_by_name(&self, name: &str) -> Result<&Saveframe> {
        self.frame_dict()?.get(name).copied().ok_or_else(|| Error::key(format!("No saveframe with name '{}'", name)))
    }

    /// The saveframe with a name, to change.
    pub fn get_saveframe_by_name_mut(&mut self, name: &str) -> Result<&mut Saveframe> {
        self.frame_dict()?;
        self.frame_list.iter_mut().find(|frame| frame.name() == name)
            .ok_or_else(|| Error::key(format!("No saveframe with name '{}'", name)))
    }

    /// The saveframes of a category (by the value of their Sf_category tags).
    pub fn get_saveframes_by_category(&self, value: &str) -> Vec<&Saveframe> {
        self.get_saveframes_by_tag_and_value("sf_category", &Value::from(value))
    }

    /// The saveframes of a category, to change.
    pub fn get_saveframes_by_category_mut(&mut self, value: &str) -> Vec<&mut Saveframe> {
        let value = Value::from(value);
        self.frame_list.iter_mut()
            .filter(|frame| frame.get_tag("sf_category").ok().and_then(|r| r.into_iter().next()).as_ref() == Some(&value))
            .collect()
    }

    /// The saveframes whose first value of a tag is the one given.
    pub fn get_saveframes_by_tag_and_value(&self, tag_name: &str, value: &Value) -> Vec<&Saveframe> {
        self.frame_list.iter()
            .filter(|frame| frame.get_tag(tag_name).ok().and_then(|r| r.into_iter().next()).as_ref() == Some(value))
            .collect()
    }

    /// Every value of a tag, which must be given with its category (`Entry.Title`).
    pub fn get_tag(&self, tag: &str) -> Result<Vec<Value>> {
        self.check_tag_has_category(tag)?;
        let mut results = Vec::new();
        for frame in &self.frame_list {
            results.extend(frame.get_tag(tag)?);
        }
        Ok(results)
    }

    /// Every value of a tag, with its tag name. See [`Saveframe::get_tag_whole`].
    pub fn get_tag_whole(&self, tag: &str) -> Result<Vec<(String, Value)>> {
        self.check_tag_has_category(tag)?;
        let mut results = Vec::new();
        for frame in &self.frame_list {
            results.extend(frame.get_tag_whole(tag)?);
        }
        Ok(results)
    }

    fn check_tag_has_category(&self, tag: &str) -> Result<()> {
        if !tag.contains('.') {
            return Err(Error::value(
                "You must provide the tag category to call this method at the entry level. For example, you must \
                 provide 'Entry.Title' rather than 'Title' as the tag if calling this at the Entry level. You can call \
                 Saveframe.get_tag('Title') without issue."));
        }
        Ok(())
    }

    /// The values of several tags, by tag.
    pub fn get_tags<S: AsRef<str>>(&self, tags: &[S]) -> Result<Vec<(String, Vec<Value>)>> {
        tags.iter().map(|tag| Ok((tag.as_ref().to_string(), self.get_tag(tag.as_ref())?))).collect()
    }

    /// Remove the saveframes with no data (see [`Saveframe::empty`]).
    pub fn remove_empty_saveframes(&mut self) {
        self.frame_list.retain(|frame| !frame.empty());
    }

    #[deprecated(note = "Use remove_empty_saveframes() instead.")]
    pub fn delete_empty_saveframes(&mut self) {
        self.remove_empty_saveframes()
    }

    /// Remove the saveframe with a name.
    pub fn remove_saveframe(&mut self, name: &str) -> Result<()> {
        self.remove_saveframes(&[name])
    }

    /// Remove the saveframes with the names. Nothing is removed unless every one exists.
    pub fn remove_saveframes<S: AsRef<str>>(&mut self, names: &[S]) -> Result<()> {
        let to_remove: Vec<Saveframe> = {
            let frames = self.frame_dict()?;
            names.iter().map(|name| frames.get(name.as_ref()).map(|f| (*f).clone()).ok_or_else(|| Error::value(format!(
                "At least one saveframe specified to remove was not found in this saveframe. First missing saveframe: {}",
                name.as_ref())))).collect::<Result<_>>()?
        };
        self.frame_list.retain(|frame| !to_remove.contains(frame));
        Ok(())
    }

    /// Remove every saveframe equal to the one given.
    pub fn remove_saveframe_obj(&mut self, saveframe: &Saveframe) -> Result<()> {
        if !self.frame_list.contains(saveframe) {
            return Err(Error::value(format!(
                "At least one loop specified to remove was not found in this saveframe. First missing loop: {}",
                saveframe.repr())));
        }
        self.frame_list.retain(|frame| frame != saveframe);
        Ok(())
    }

    /// Rename a saveframe, and update every reference to it (`$name`) in the entry.
    pub fn rename_saveframe(&mut self, original_name: &str, new_name: &str) -> Result<()> {
        let original_name = original_name.strip_prefix('$').unwrap_or(original_name);
        let new_name = new_name.strip_prefix('$').unwrap_or(new_name);
        if self.frame_list.iter().any(|frame| frame.name() == new_name) {
            return Err(Error::value(format!(
                "Cannot rename the saveframe '{}' as '{}' because a saveframe with that name already exists in the entry.",
                original_name, new_name)));
        }
        self.get_saveframe_by_name_mut(original_name)?.set_name(new_name)?;

        let old_reference = Value::from(format!("${}", original_name));
        let new_reference = Value::from(format!("${}", new_name));
        for frame in &mut self.frame_list {
            for tag in frame.tags_mut() {
                if tag.value == old_reference {
                    tag.value = new_reference.clone();
                }
            }
            for each_loop in &mut frame.loops {
                for value in each_loop.data.iter_mut().flatten() {
                    if *value == old_reference {
                        *value = new_reference.clone();
                    }
                }
            }
        }
        Ok(())
    }

    /// A summary of the saveframes and loops, one per line.
    pub fn tree(&self) -> String {
        let mut text = format!("{}\n", self.repr());
        for (pos, frame) in self.frame_list.iter().enumerate() {
            text.push_str(&format!("\t[{}] {}\n", pos, frame.repr()));
            for (pos2, each_loop) in frame.loops.iter().enumerate() {
                text.push_str(&format!("\t\t[{}] {}\n", pos2, each_loop.repr()));
            }
        }
        text
    }

    /// Print a summary of the saveframes and loops.
    pub fn print_tree(&self) {
        print!("{}", self.tree());
    }

    /// Write the entry to a file, as NMR-STAR or JSON. `show_comments`, `skip_empty_loops` and
    /// `skip_empty_tags` are as for [`Entry::format`], and ignored for JSON.
    pub fn write_to_file(&self, path: impl AsRef<Path>, format: FileFormat, show_comments: bool,
                         skip_empty_loops: bool, skip_empty_tags: bool) -> Result<()> {
        let text = match format {
            FileFormat::NmrStar => self.format(skip_empty_loops, skip_empty_tags, show_comments)?,
            FileFormat::Json => self.to_json(),
        };
        write_file(path.as_ref(), &text)
    }

    /// Validate the entry in the ways [`Saveframe::validate`] does, and check that saveframe
    /// names are unique and references to saveframes resolve. Returns the problems found. See
    /// [`Entry::validate_full`] for a more thorough validation.
    pub fn validate(&self, validate_schema: bool, schema: Option<&Schema>, validate_star: bool) -> Vec<String> {
        let mut errors = Vec::new();
        if !validate_star && !validate_schema {
            errors.push("Validate() should be called with at least one validation method enabled.".to_string());
        }
        if validate_star {
            let mut names: Vec<&str> = self.frame_list.iter().map(Saveframe::name).collect();
            names.sort();
            // As in PyNMR-STAR, the last pair of names is not compared
            for ordinal in 0..names.len().saturating_sub(2) {
                if names[ordinal] == names[ordinal + 1] {
                    errors.push(format!("Multiple saveframes with same name: '{}'", names[ordinal]));
                }
            }
            let names: HashSet<&str> = self.frame_list.iter().map(Saveframe::name).collect();
            for frame in &self.frame_list {
                let prefix = frame.tag_prefix.as_deref().unwrap_or("None");
                for tag in frame.tags() {
                    let text = tag.value.to_py_string();
                    if let Some(name) = text.strip_prefix('$') {
                        if !names.contains(name) {
                            errors.push(format!("Dangling saveframe reference '{}' in tag '{}.{}'", tag.value, prefix, tag.name));
                        }
                    }
                }
                for each_loop in &frame.loops {
                    for row in &each_loop.data {
                        for (pos, value) in row.iter().enumerate() {
                            let text = value.to_py_string();
                            if let Some(name) = text.strip_prefix('$') {
                                if !names.contains(name) {
                                    errors.push(format!("Dangling saveframe reference '{}' in tag '{}.{}'", text,
                                                        each_loop.category().unwrap_or("None"),
                                                        each_loop.tags().get(pos).map(String::as_str).unwrap_or("")));
                                }
                            }
                        }
                    }
                }
            }
        }
        for frame in &self.frame_list {
            errors.extend(frame.validate(validate_schema, schema, validate_star));
        }
        errors
    }

    /// Validate the entry against the NMR-STAR dictionary, returning structured findings. It
    /// reports everything [`Entry::validate`] does, and is entry-wide: the dictionary's
    /// mandatory rules are conditional on values in other saveframes.
    ///
    /// * `profile`: which set of the dictionary's validation flags to apply (see
    ///   [`definitions::VALIDATION_PROFILES`]). Defaults to `public`.
    /// * `severities`: restrict the result to these. By default every severity is returned.
    /// * `metadata_only`: check values only in the tags and loops the dictionary marks as
    ///   metadata, as BMRB's own validator does.
    pub fn validate_full(&self, schema: Option<&Schema>, profile: Option<&str>, severities: Option<&[Severity]>,
                         metadata_only: bool) -> Result<Vec<ValidationIssue>> {
        validation::validate_full(self, get_schema(schema), profile.unwrap_or(definitions::DEFAULT_VALIDATION_PROFILE),
                                  severities, metadata_only)
    }

    /// Number the rows of every loop with a row-index column (as the dictionary names it), 1, 2,
    /// 3, ... References to the renumbered values are *not* updated; see
    /// [`Entry::normalize`] for that.
    pub fn add_row_indexes(&mut self, schema: Option<&Schema>) -> Result<()> {
        let schema = get_schema(schema);
        for frame in &mut self.frame_list {
            for each_loop in &mut frame.loops {
                if let Some(index_tag) = validation::row_index_tag(each_loop, schema) {
                    each_loop.renumber_rows(&index_tag, 1, false)?;
                }
            }
        }
        Ok(())
    }

    /// Visit every saveframe-pointer value (one whose tag the dictionary flags as a pointer),
    /// possibly replacing it.
    fn update_framecode_values(&mut self, schema: &Schema, mut update: impl FnMut(&Value) -> Option<Value>) {
        let is_pointer = |tag: &str| schema.get(&pystr::lower(tag))
            .is_some_and(|data| validation::value_type(data).0 == validation::ValueKind::Framecode);
        for frame in &mut self.frame_list {
            let prefix = frame.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
            for tag in frame.tags_mut() {
                if is_pointer(&format!("{}.{}", prefix, tag.name)) {
                    if let Some(new_value) = update(&tag.value) {
                        tag.value = new_value;
                    }
                }
            }
            for each_loop in &mut frame.loops {
                let category = each_loop.category().unwrap_or("None").to_string();
                let columns: Vec<usize> = each_loop.tags().iter().enumerate()
                    .filter(|(_, tag)| is_pointer(&format!("{}.{}", category, tag))).map(|(i, _)| i).collect();
                for column in columns {
                    for row in &mut each_loop.data {
                        if let Some(value) = row.get(column) {
                            if let Some(new_value) = update(value) {
                                row[column] = new_value;
                            }
                        }
                    }
                }
            }
        }
    }

    /// A pointer value which is real text, rather than null.
    fn pointer_text(value: &Value) -> Option<&str> {
        let text = value.as_str()?;
        if definitions::is_null(value) || matches!(text.trim(), "." | "?") {
            return None;
        }
        Some(text)
    }

    /// Repair saveframe labels and the references to them: every Sf_framecode tag is set to its
    /// saveframe's name, and in every saveframe-pointer value runs of whitespace become a single
    /// underscore. Null values are left alone.
    pub fn fix_framecodes(&mut self, schema: Option<&Schema>) {
        let schema = get_schema(schema);
        for frame in &mut self.frame_list {
            let name = Value::from(frame.name());
            for tag in frame.tags_mut() {
                if pystr::lower(&tag.name) == "sf_framecode" {
                    tag.value = name.clone();
                }
            }
        }
        self.update_framecode_values(schema, |value| {
            let text = Entry::pointer_text(value)?;
            let collapsed = pystr::collapse_whitespace(text, "_");
            (collapsed != text).then(|| Value::from(collapsed))
        });
    }

    /// Make sure every saveframe-pointer value starts with its `$`.
    pub fn mark_framecode_values(&mut self, schema: Option<&Schema>) {
        let schema = get_schema(schema);
        self.update_framecode_values(schema, |value| {
            let text = Entry::pointer_text(value)?;
            (!text.starts_with('$')).then(|| Value::from(format!("${}", text)))
        });
    }

    /// The first `ID` value of the saveframe with a name, or None (with a warning) if there is
    /// no such saveframe or it has no ID.
    fn target_id(&self, names: &HashMap<String, usize>, name: &str, pointer: &str, pointed_from: &str) -> Option<Value> {
        let found = names.get(name).and_then(|&i| self.frame_list[i].get_tag("ID").ok()?.into_iter().next());
        if found.is_none() {
            warn!("Missing frame {} pointed to by {}", pointer, pointed_from);
        }
        found
    }

    /// Sort the saveframes, loops and tags into dictionary order, repair saveframe labels and the
    /// references to them, renumber local IDs and row indexes, and update the references to
    /// those.
    ///
    /// Normalizing can *remove* a validation finding: a Sf_framecode which disagrees with its
    /// saveframe's name is fixed. Run validation first if you want to see it.
    pub fn normalize(&mut self, schema: Option<&Schema>) -> Result<()> {
        let schema = get_schema(schema);
        self.fix_framecodes(Some(schema));
        self.mark_framecode_values(Some(schema));

        let mut ordering: HashMap<&str, usize> = HashMap::new();
        for (i, category) in schema.category_order.iter().enumerate() {
            ordering.entry(category.as_str()).or_insert(i);
        }
        let hashed = |category: &str| CategoryKey::Hashed(sha1(category.as_bytes()));

        for frame in &mut self.frame_list {
            frame.sort_tags(Some(schema));
            for each_loop in &mut frame.loops {
                each_loop.sort_tags(Some(schema))?;
                match each_loop.sort_rows(&["Ordinal"]) {
                    Err(error) if !error.is_value_error() => return Err(error),
                    _ => {}
                }
            }
            frame.loops.sort_by_cached_key(|l| match l.category().and_then(|c| ordering.get(c)) {
                Some(&i) => CategoryKey::Known(i),
                None => hashed(l.category().unwrap_or("None")),
            });
        }
        self.frame_list.sort_by_cached_key(|frame| {
            let category_key = match frame.tag_prefix.as_deref().and_then(|p| ordering.get(p)) {
                Some(&i) => CategoryKey::Known(i),
                None => match frame.category() {
                    None => CategoryKey::Infinite,
                    Some(category) => hashed(category),
                },
            };
            let id_key = frame.get_tag("ID").ok().and_then(|values| values.first().and_then(|v| v.py_int().ok()))
                .map_or(IdKey::Infinite, IdKey::Id);
            (category_key, id_key)
        });

        // The categories present, in order
        let mut categories: Vec<Option<String>> = Vec::new();
        for frame in &self.frame_list {
            let category = frame.category().map(str::to_string);
            if !categories.contains(&category) {
                categories.push(category);
            }
        }

        // tag_prefix.tag.original value -> mapped value
        let mut mapping: HashMap<String, Value> = HashMap::new();
        let entry_id = self.entry_id.clone();

        // Reassign the ID tags first
        for category in &categories {
            let category_value = Value::from(category.clone());
            let mut id_counter: i64 = 1;
            for f in 0..self.frame_list.len() {
                let first = self.frame_list[f].get_tag("sf_category").ok().and_then(|r| r.into_iter().next());
                if first.as_ref() != Some(&category_value) {
                    continue;
                }
                let frame = &mut self.frame_list[f];
                let prefix = frame.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
                let short_prefix: String = prefix.chars().skip(1).collect();
                for t in 0..frame.tags().len() {
                    let tag = &frame.tags()[t];
                    let Some(tag_schema) = schema.get(&pystr::lower(&format!("{}.{}", prefix, tag.name))) else { continue };
                    let field = tag_schema.get("Tag field").to_string();
                    let tag = &mut frame.tags_mut()[t];
                    tag.name = field;
                    let key = format!("{}.{}.{}", short_prefix, tag.name, tag.value);
                    if tag_schema.get("lclSfIdFlg") == "Y" {
                        if tag_schema.get("entryIdFlg") == "Y" {
                            mapping.insert(key, entry_id.clone());
                            tag.value = entry_id.clone();
                        } else if tag_schema.get("BMRB data type") == "int" {
                            let new_value = if tag.value.is_str() {
                                Value::from(id_counter.to_string())
                            } else {
                                Value::Int(id_counter)
                            };
                            tag.value = new_value.clone();
                            mapping.insert(key, new_value);
                        } else {
                            mapping.insert(key, tag.value.clone());
                        }
                    } else {
                        mapping.insert(key, tag.value.clone());
                    }
                }

                for l in 0..frame.loops.len() {
                    let category = frame.loops[l].category().unwrap_or("None").to_string();
                    let short_category: String = category.chars().skip(1).collect();
                    for x in 0..frame.loops[l].tags().len() {
                        let tag = frame.loops[l].tags()[x].clone();
                        let Some(tag_schema) = schema.get(&pystr::lower(&format!("{}.{}", category, tag))) else { continue };
                        frame.loops[l].tags_mut()[x] = tag_schema.get("Tag field").to_string();
                        let parent_id = if tag_schema.get("lclSfIdFlg") == "Y" && tag_schema.get("entryIdFlg") != "Y"
                            && tag_schema.get("BMRB data type") != "int" {
                            let parent_tag = format!("{}.{}", tag_schema.get("Foreign Table"), tag_schema.get("Foreign Column"));
                            Some(frame.get_tag(&parent_tag)?.into_iter().next()
                                .ok_or_else(|| Error::Index("list index out of range".to_string()))?)
                        } else {
                            None
                        };
                        for row in &mut frame.loops[l].data {
                            let Some(value) = row.get_mut(x) else { continue };
                            mapping.insert(format!("{}.{}.{}", short_category, tag, value), value.clone());
                            if tag_schema.get("lclSfIdFlg") == "Y" {
                                if tag_schema.get("entryIdFlg") == "Y" {
                                    *value = entry_id.clone();
                                } else if tag_schema.get("BMRB data type") == "int" {
                                    if value.is_null_value() {
                                        *value = if value.is_str() { Value::from(id_counter.to_string()) } else { Value::Int(id_counter) };
                                    }
                                } else if let Some(parent_id) = &parent_id {
                                    *value = if value.is_str() {
                                        Value::from(parent_id.to_py_string().into_owned())
                                    } else {
                                        parent_id.clone()
                                    };
                                }
                            }
                        }
                    }
                }
                id_counter += 1;
            }
        }

        // Now fix any other references
        let names: HashMap<String, usize> = self.frame_list.iter().enumerate().map(|(i, f)| (f.name().to_string(), i)).collect();
        for f in 0..self.frame_list.len() {
            let prefix = self.frame_list[f].tag_prefix.clone().unwrap_or_else(|| "None".to_string());
            for t in 0..self.frame_list[f].tags().len() {
                let tag = self.frame_list[f].tags()[t].clone();
                let Some(tag_schema) = schema.get(&pystr::lower(&format!("{}.{}", prefix, tag.name))) else { continue };
                let foreign_table = tag_schema.get("Foreign Table");
                let foreign_column = tag_schema.get("Foreign Column");
                if !foreign_table.is_empty() && tag_schema.get("Sf pointer") != "Y" {
                    if tag.value.is_null_value() {
                        if tag_schema.nullable {
                            continue;
                        }
                        warn!("A foreign key tag that is not nullable was set to a null value. Tag: {}.{} Primary key: \
                               {}.{} Value: {}", prefix, tag.value, foreign_table, foreign_column, tag.value);
                    }
                    match mapping.get(&format!("{}.{}.{}", foreign_table, foreign_column, tag.value)) {
                        Some(mapped) => self.frame_list[f].tags_mut()[t].value = mapped.clone(),
                        None => warn!("The tag {}.{} has value {} but there is no valid primary key.", prefix, tag.name, tag.value),
                    }
                } else if !foreign_table.is_empty() && foreign_column == "Sf_framecode" {
                    if tag.value.is_null_value() {
                        continue;
                    }
                    // A free saveframe pointer with an ID tag beside it: the ID is whatever the
                    //  saveframe pointed to says, if it says anything
                    for c in 0..self.frame_list[f].tags().len() {
                        let candidate = &self.frame_list[f].tags()[c];
                        let Some(candidate_schema) = schema.get(&pystr::lower(&format!("{}.{}", prefix, candidate.name))) else { continue };
                        if candidate_schema.get("Foreign Table") == foreign_table && candidate_schema.get("Foreign Column") == "ID"
                            && candidate_schema.get("entryIdFlg") != "Y" {
                            let text = tag.value.to_py_string();
                            let target_name: String = text.chars().skip(1).collect();
                            if let Some(target_id) = self.target_id(&names, &target_name, &text, &format!("{}.{}", prefix, tag.name)) {
                                if !target_id.is_null_value() {
                                    self.frame_list[f].tags_mut()[c].value = target_id;
                                }
                            }
                            break;
                        }
                    }
                }
            }

            for l in 0..self.frame_list[f].loops.len() {
                let category = self.frame_list[f].loops[l].category().unwrap_or("None").to_string();
                for x in 0..self.frame_list[f].loops[l].tags().len() {
                    let tag = self.frame_list[f].loops[l].tags()[x].clone();
                    let Some(tag_schema) = schema.get(&pystr::lower(&format!("{}.{}", category, tag))) else { continue };
                    let foreign_table = tag_schema.get("Foreign Table");
                    let foreign_column = tag_schema.get("Foreign Column");
                    if !foreign_table.is_empty() && tag_schema.get("Sf pointer") != "Y" {
                        for row in &mut self.frame_list[f].loops[l].data {
                            let Some(value) = row.get_mut(x) else { continue };
                            if value.is_null_value() {
                                if tag_schema.nullable {
                                    continue;
                                }
                                warn!("A foreign key reference tag that is not nullable was set to a null value. Tag: \
                                       {}.{} Foreign key: {}.{} Value: {}", category, tag, foreign_table, foreign_column, value);
                            }
                            match mapping.get(&format!("{}.{}.{}", foreign_table, foreign_column, value)) {
                                Some(mapped) => *value = mapped.clone(),
                                None => {
                                    if (category == "_Atom_chem_shift" || category == "_Entity_comp_index")
                                        && (tag == "Atom_ID" || tag == "Comp_ID") {
                                        continue;
                                    }
                                    warn!("The tag {}.{} has value {} but there is no valid primary key {}.{} with the \
                                           tag value.", category, tag, value, foreign_table, foreign_column);
                                }
                            }
                        }
                    }

                    // A framecode reference: if there is a tag pointing to the 'ID' tag of the same
                    //  saveframe, set it from the saveframe pointed to
                    if !foreign_table.is_empty() && foreign_column == "Sf_framecode" {
                        let loop_tags = self.frame_list[f].loops[l].tags().to_vec();
                        for conditional_tag in &loop_tags {
                            let Some(conditional_schema) = schema.get(&pystr::lower(&format!("{}.{}", category, conditional_tag))) else { continue };
                            if conditional_schema.get("Foreign Table") == foreign_table
                                && conditional_schema.get("Foreign Column") == "ID"
                                && conditional_schema.get("entryIdFlg") != "Y" {
                                let Some(tag_pos) = self.frame_list[f].loops[l].tag_index(conditional_tag) else { continue };
                                for r in 0..self.frame_list[f].loops[l].data.len() {
                                    let Some(value) = self.frame_list[f].loops[l].data[r].get(x).cloned() else { continue };
                                    if value.is_null_value() {
                                        if !tag_schema.nullable {
                                            warn!("A foreign saveframe reference tag that is not nullable was set to a \
                                                   null value. Tag: {}.{} Foreign saveframe: {}.{}",
                                                  category, tag, foreign_table, foreign_column);
                                        }
                                        continue;
                                    }
                                    let text = value.to_py_string();
                                    let target_name: String = text.chars().skip(1).collect();
                                    if let Some(target_id) = self.target_id(&names, &target_name, &text, &format!("{}.{}", category, tag)) {
                                        if !target_id.is_null_value() {
                                            if let Some(slot) = self.frame_list[f].loops[l].data[r].get_mut(tag_pos) {
                                                *slot = target_id;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Renumber every loop's row-index column, and rewrite the references to the numbers that
        //  change
        self.renumber_row_indexes(schema)
    }

    /// Renumber every loop's row-index column 1, 2, 3, ... and rewrite the references to the
    /// numbers that change.
    ///
    /// A loop row number is not unique in the entry: `_Entity_comp_index.ID` 5 means a different
    /// residue in each entity saveframe. The dictionary states the full key of a loop's rows
    /// (`Table Primary Key`): the row index, `Entry_ID`, and the local ID of the saveframe the
    /// loop is in, which the referring loop may or may not carry. So:
    ///
    /// * with one loop of the category in the entry, its row numbers are unique and references
    ///   are rewritten from the row number alone;
    /// * with several, where the referring side carries the discriminator, the map is keyed on
    ///   the composite value;
    /// * with several where it does not, the reference is ambiguous, and the column is left as
    ///   it is.
    ///
    /// A column which already contains duplicates is also left alone when anything refers to it.
    /// A null reference stays null, and a row that had no number gets one, but nothing follows it.
    fn renumber_row_indexes(&mut self, schema: &Schema) -> Result<()> {
        let mut children_of: HashMap<String, Vec<String>> = HashMap::new();
        for (child, parent) in &schema.parent_tags {
            children_of.entry(pystr::lower(parent)).or_default().push(child.clone());
        }
        for children in children_of.values_mut() {
            children.sort();
        }

        let mut key_columns: HashMap<String, Vec<String>> = HashMap::new();
        for (tag, data) in schema.tags() {
            if pystr::upper(data.get("Table Primary Key").trim()).starts_with('Y') && !tag.ends_with(".entry_id") {
                key_columns.entry(category_of(tag).to_string()).or_default().push(tag.to_string());
            }
        }

        let points_at = |tag: &str| -> Option<String> {
            let data = schema.get(tag)?;
            let table = data.get("Foreign Table").trim();
            let column = data.get("Foreign Column").trim();
            (!table.is_empty() && !column.is_empty()).then(|| pystr::lower(&format!("_{}.{}", table, column)))
        };

        let mut loop_count: HashMap<String, usize> = HashMap::new();
        for frame in &self.frame_list {
            for each_loop in &frame.loops {
                *loop_count.entry(pystr::lower(each_loop.category().unwrap_or(""))).or_insert(0) += 1;
            }
        }

        type Table = HashMap<(Vec<String>, String), Value>;
        let mut remap_order: Vec<String> = Vec::new();
        let mut remaps: HashMap<String, (Vec<String>, Table)> = HashMap::new();

        for frame in &mut self.frame_list {
            for each_loop in &mut frame.loops {
                let Some(index_tag) = validation::row_index_tag(each_loop, schema) else { continue };
                if each_loop.data.is_empty() {
                    continue;
                }
                let category = pystr::lower(each_loop.category().unwrap_or(""));
                let full_index = pystr::lower(&format!("{}.{}", category, index_tag));
                let position = each_loop.tags().iter().position(|t| *t == index_tag).unwrap_or(0);

                if !children_of.contains_key(&full_index) {
                    each_loop.renumber_rows(&index_tag, 1, false)?;
                    continue;
                }

                let mut discriminators: Vec<String> = key_columns.get(&category).map(|tags| {
                    tags.iter().filter(|t| **t != full_index).cloned().collect()
                }).unwrap_or_default();
                let mut columns: Vec<Option<usize>> = discriminators.iter().map(|t| each_loop.tag_index(t)).collect();
                if columns.iter().any(Option::is_none) {
                    if loop_count.get(&category) != Some(&1) {
                        continue;
                    }
                    discriminators.clear();
                    columns.clear();
                }
                let columns: Vec<usize> = columns.into_iter().flatten().collect();

                let cell = |row: &[Value], c: usize| row.get(c).map(|v| v.to_py_string().into_owned()).unwrap_or_default();
                let before: Vec<Value> = each_loop.data.iter().map(|row| row.get(position).cloned().unwrap_or_default()).collect();
                let keys: Vec<Vec<String>> = each_loop.data.iter()
                    .map(|row| columns.iter().map(|&c| cell(row, c)).collect()).collect();
                // Several blank indexes are not duplicates: nothing can refer to a blank
                let numbered: Vec<(&Vec<String>, String)> = keys.iter().zip(&before)
                    .filter(|(_, old)| !old.is_null_value())
                    .map(|(key, old)| (key, old.to_py_string().into_owned())).collect();
                let unique: HashSet<&(&Vec<String>, String)> = numbered.iter().collect();
                if unique.len() != numbered.len() {
                    continue;
                }

                each_loop.renumber_rows(&index_tag, 1, false)?;

                if !remaps.contains_key(&full_index) {
                    remap_order.push(full_index.clone());
                    remaps.insert(full_index.clone(), (discriminators, HashMap::new()));
                }
                let table = &mut remaps.get_mut(&full_index).unwrap().1;
                for ((key, old), row) in keys.into_iter().zip(before).zip(&each_loop.data) {
                    if old.is_null_value() {
                        continue;
                    }
                    table.insert((key, old.to_py_string().into_owned()), row[position].clone());
                }
            }
        }

        for parent_index in &remap_order {
            let (discriminators, table) = &remaps[parent_index];
            let wanted: Vec<Option<String>> = discriminators.iter().map(|d| points_at(d)).collect();
            if wanted.iter().any(Option::is_none) {
                continue;
            }
            for child in &children_of[parent_index] {
                let child_category = category_of(child);
                // The columns on the referring side that mean the same as the parent's
                //  discriminators: the ones drawing from the same tag, paired by the decoration
                //  of their names where there are several
                let mut counterparts: Vec<String> = Vec::new();
                for target in &wanted {
                    let mut matches: Vec<String> = schema.tags()
                        .filter(|(tag, _)| category_of(tag) == child_category && points_at(tag) == *target)
                        .map(|(tag, _)| tag.to_string()).collect();
                    if matches.len() > 1 {
                        let mut scores: Vec<(usize, String)> = matches.iter()
                            .map(|t| (shared_decoration(child, t), t.clone())).collect();
                        scores.sort_by(|a, b| b.cmp(a));
                        matches = if scores[0].0 > scores[1].0 { vec![scores[0].1.clone()] } else { Vec::new() };
                    }
                    match matches.into_iter().next() {
                        Some(found) => counterparts.push(found),
                        None => break,
                    }
                }
                if counterparts.len() != wanted.len() {
                    continue;
                }

                let child_name = schema.get(child).map(|d| d.tag().to_string()).unwrap_or_default();
                let names: Vec<String> = counterparts.iter()
                    .map(|t| schema.get(t).map(|d| d.tag().to_string()).unwrap_or_default()).collect();
                for frame in &mut self.frame_list {
                    for each_loop in &mut frame.loops {
                        if pystr::lower(each_loop.category().unwrap_or("")) != child_category {
                            continue;
                        }
                        let Some(position) = each_loop.tag_index(&child_name) else { continue };
                        let columns: Vec<Option<usize>> = names.iter().map(|n| each_loop.tag_index(n)).collect();
                        if columns.iter().any(Option::is_none) {
                            continue;
                        }
                        let columns: Vec<usize> = columns.into_iter().flatten().collect();
                        for row in &mut each_loop.data {
                            let key: Vec<String> = columns.iter()
                                .map(|&c| row.get(c).map(|v| v.to_py_string().into_owned()).unwrap_or_default()).collect();
                            let Some(current) = row.get(position) else { continue };
                            if let Some(replacement) = table.get(&(key, current.to_py_string().into_owned())) {
                                row[position] = replacement.clone();
                            }
                        }
                    }
                    if counterparts.is_empty() {
                        // A free tag can only be matched when there is nothing to match on but the
                        //  number itself
                        let prefix = frame.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
                        for tag in frame.tags_mut() {
                            if pystr::lower(&format!("{}.{}", prefix, tag.name)) != *child {
                                continue;
                            }
                            if let Some(replacement) = table.get(&(Vec::new(), tag.value.to_py_string().into_owned())) {
                                tag.value = replacement.clone();
                            }
                        }
                    }
                }
            }
        }
        Ok(())
    }
}

impl<'a> IntoIterator for &'a Entry {
    type Item = &'a Saveframe;
    type IntoIter = std::slice::Iter<'a, Saveframe>;

    fn into_iter(self) -> Self::IntoIter {
        self.frame_list.iter()
    }
}
