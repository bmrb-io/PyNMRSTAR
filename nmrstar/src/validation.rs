//! The structured validation of [`Entry::validate_full`].
//!
//! Each finding has an identity - a machine-readable check name, a severity, and the
//! saveframe/loop/tag it came from - so that a caller can route it, suppress it, or render it in
//! its own words. The checks are ports of the BMRB validator's, as PyNMR-STAR made them.

use std::collections::{BTreeMap, HashMap, HashSet};
use std::fmt;
use std::str::FromStr;

use regex::Regex;

use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::json::Json;
use crate::pystr;
use crate::saveframe::Saveframe;
use crate::schema::{is_valid_date, Profile, Schema, TagData};
use crate::star_loop::Loop;
use crate::value::{parse_int, Value};

/// How much a validation finding matters. The first four are the severities BMRB's validator
/// has always used. `Strict` marks a genuine dictionary violation that BMRB's own validator does
/// not report, so that a caller can present the historical result exactly.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Severity {
    Critical,
    Error,
    Warning,
    Info,
    Strict,
}

impl Severity {
    pub const ALL: [Severity; 5] = [Severity::Critical, Severity::Error, Severity::Warning, Severity::Info, Severity::Strict];

    pub fn as_str(&self) -> &'static str {
        match self {
            Severity::Critical => "critical",
            Severity::Error => "error",
            Severity::Warning => "warning",
            Severity::Info => "info",
            Severity::Strict => "strict",
        }
    }
}

impl fmt::Display for Severity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Severity {
    type Err = Error;

    fn from_str(s: &str) -> Result<Severity> {
        Severity::ALL.into_iter().find(|severity| severity.as_str() == s)
            .ok_or_else(|| Error::value(format!("'{}' is not a valid Severity", s)))
    }
}

/// One validation finding.
///
/// `check` names what was found and is stable; `message` describes it in words and may be
/// reworded between releases. A caller that needs its own wording should build it from `check`,
/// the location, `value` and `details`.
#[derive(Clone, Debug)]
pub struct ValidationIssue {
    pub severity: Severity,
    /// Machine-readable check name, e.g. `saveframe.duplicate_name`.
    pub check: String,
    pub message: String,
    pub saveframe: Option<String>,
    pub category: Option<String>,
    pub tag: Option<String>,
    /// The category of the loop the finding is in
    pub loop_category: Option<String>,
    /// The row's position in its loop, counting from 0.
    pub row: Option<usize>,
    pub value: Value,
    /// Anything else the message is built from, by name.
    pub details: BTreeMap<String, Value>,
}

impl ValidationIssue {
    fn new(severity: Severity, check: &str, message: String) -> ValidationIssue {
        ValidationIssue {
            severity,
            check: check.to_string(),
            message,
            saveframe: None,
            category: None,
            tag: None,
            loop_category: None,
            row: None,
            value: Value::Null,
            details: BTreeMap::new(),
        }
    }

    fn saveframe(mut self, name: &str) -> Self {
        self.saveframe = Some(name.to_string());
        self
    }

    fn category(mut self, category: Option<&str>) -> Self {
        self.category = category.map(str::to_string);
        self
    }

    fn tag(mut self, tag: &str) -> Self {
        self.tag = Some(tag.to_string());
        self
    }

    fn in_loop(mut self, loop_category: Option<&str>) -> Self {
        self.loop_category = loop_category.map(str::to_string);
        self
    }

    fn row(mut self, row: usize) -> Self {
        self.row = Some(row);
        self
    }

    fn value(mut self, value: &Value) -> Self {
        self.value = value.clone();
        self
    }

    fn detail(mut self, name: &str, value: impl Into<Value>) -> Self {
        self.details.insert(name.to_string(), value.into());
        self
    }

    /// A description of the issue.
    pub fn repr(&self) -> String {
        format!("<ValidationIssue {} {}: {}>", self.severity, self.check, self.message)
    }

    /// The issue as JSON, for serialization.
    pub fn to_json_value(&self) -> Json {
        let optional = |s: &Option<String>| s.as_ref().map_or(Json::Null, |s| Json::Str(s.clone()));
        Json::Object(vec![
            ("severity".to_string(), Json::Str(self.severity.to_string())),
            ("check".to_string(), Json::Str(self.check.clone())),
            ("message".to_string(), Json::Str(self.message.clone())),
            ("saveframe".to_string(), optional(&self.saveframe)),
            ("category".to_string(), optional(&self.category)),
            ("tag".to_string(), optional(&self.tag)),
            ("loop".to_string(), optional(&self.loop_category)),
            ("row".to_string(), self.row.map_or(Json::Null, |r| Json::Int(r as i64))),
            ("value".to_string(), Json::from_value(&self.value)),
            ("details".to_string(), Json::Object(self.details.iter().map(|(k, v)| (k.clone(), Json::from_value(v))).collect())),
        ])
    }

    fn key(&self) -> (Severity, &str, &str, &Option<String>, &Option<String>, &Option<String>, &Option<String>, Option<usize>) {
        (self.severity, &self.check, &self.message, &self.saveframe, &self.category, &self.tag, &self.loop_category, self.row)
    }
}

impl PartialEq for ValidationIssue {
    fn eq(&self, other: &ValidationIssue) -> bool {
        self.key() == other.key()
    }
}

impl Eq for ValidationIssue {}

impl std::hash::Hash for ValidationIssue {
    fn hash<H: std::hash::Hasher>(&self, state: &mut H) {
        self.key().hash(state)
    }
}

impl fmt::Display for ValidationIssue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "[{}] {}", self.severity, self.message)
    }
}

/// The validation message for a value containing characters outside of ASCII, naming them and
/// their code points.
pub fn non_ascii_error(tag: &str, value: &str) -> String {
    let mut characters: Vec<char> = Vec::new();
    for c in value.chars().filter(|c| !c.is_ascii()) {
        if !characters.contains(&c) {
            characters.push(c);
        }
    }
    let described: Vec<String> = characters.iter().map(|c| format!("'{}' (U+{:04X})", c, *c as u32)).collect();
    format!("Non-ASCII character(s) {} in tag '{}': '{}'.", described.join(", "), tag, value)
}

/// The values of one of a saveframe's own tags, ignoring its loops.
fn free_tag(saveframe: &Saveframe, name: &str) -> Vec<Value> {
    let folded = pystr::lower(name);
    saveframe.tags().iter().filter(|tag| pystr::lower(&tag.name) == folded).map(|tag| tag.value.clone()).collect()
}

/// A saveframe pointer's value without the `$` that marks it as one.
fn dereference(value: &Value) -> Value {
    match value {
        Value::Str(s) if s.starts_with('$') => Value::from(s[1..].to_string()),
        other => other.clone(),
    }
}

fn prefix_of(saveframe: &Saveframe) -> &str {
    saveframe.tag_prefix.as_deref().unwrap_or("None")
}

fn loop_category_of(each_loop: &Loop) -> &str {
    each_loop.category().unwrap_or("None")
}

/// A saveframe's category according to the dictionary (from its Sf_category tag), unstripped.
fn raw_saveframe_category<'a>(schema: &'a Schema, saveframe: &Saveframe) -> Option<&'a str> {
    let category = schema.get(&format!("{}.sf_category", pystr::lower(prefix_of(saveframe))))?.get("SFCategory");
    (!category.is_empty()).then_some(category)
}

/// A saveframe's category according to the dictionary.
fn saveframe_category<'a>(schema: &'a Schema, saveframe: &Saveframe) -> Option<&'a str> {
    raw_saveframe_category(schema, saveframe).map(str::trim).filter(|c| !c.is_empty())
}

/// Which of an entry's tags describe it, as opposed to being its data. A loop is in or out as a
/// whole, judged by every tag the dictionary places in its category. Unknown tags and categories
/// are in scope.
struct MetadataScope<'a> {
    schema: &'a Schema,
    categories: Option<HashMap<String, bool>>,
    metadata_only: bool,
}

impl<'a> MetadataScope<'a> {
    fn new(schema: &'a Schema, metadata_only: bool) -> Self {
        MetadataScope { schema, categories: None, metadata_only }
    }

    fn free(&self, full_tag: &str) -> bool {
        if !self.metadata_only {
            return true;
        }
        self.schema.get(&pystr::lower(full_tag)).is_none_or(|data| data.get("Meta data") == "Y")
    }

    fn in_loop(&mut self, category: Option<&str>) -> bool {
        if !self.metadata_only {
            return true;
        }
        let schema = self.schema;
        let categories = self.categories.get_or_insert_with(|| {
            let mut categories: HashMap<String, bool> = HashMap::new();
            for (tag, data) in schema.tags() {
                let folded = tag.rsplit_once('.').map(|(c, _)| c).unwrap_or(tag).to_string();
                let metadata = data.get("Meta data") == "Y";
                let entry = categories.entry(folded).or_insert(true);
                *entry = *entry && metadata;
            }
            categories
        });
        match category {
            None => true,
            Some(category) => categories.get(&pystr::lower(category)).copied().unwrap_or(true),
        }
    }
}

/// Structural checks over an entry's saveframes (the BMRB validator's CheckSaveFrames).
fn check_saveframes(entry: &Entry, schema: &Schema, profile: &str) -> Result<Vec<ValidationIssue>> {
    let mut issues = Vec::new();
    let categories = schema.validation_profile(Some(profile))?;

    let mut seen_names: HashMap<String, String> = HashMap::new();
    let mut seen_categories: HashMap<String, String> = HashMap::new();
    let mut present: HashSet<String> = HashSet::new();
    let mut previous: Option<(i64, String, String)> = None;

    for saveframe in entry {
        let name = saveframe.name();
        let category = raw_saveframe_category(schema, saveframe);
        let declared = free_tag(saveframe, "Sf_category");

        match category {
            None => issues.push(ValidationIssue::new(Severity::Error, "saveframe.missing_category", format!(
                "The category of saveframe '{}' cannot be determined: the dictionary has no tag '{}.Sf_category'.",
                name, prefix_of(saveframe))).saveframe(name)),
            Some(category) => {
                present.insert(category.to_string());

                if let Some(first) = declared.first() {
                    if *first != Value::from(category) {
                        issues.push(ValidationIssue::new(Severity::Error, "saveframe.invalid_category", format!(
                            "Saveframe '{}' has Sf_category '{}', but its tags are those of category '{}'.",
                            name, shown(&first.to_py_string()), category))
                            .saveframe(name).category(Some(category))
                            .tag(&format!("{}.Sf_category", prefix_of(saveframe))).value(first));
                    }
                }

                if schema.saveframe_categories.get(category).is_some_and(|c| c.unique) {
                    match seen_categories.get(category) {
                        Some(first) => issues.push(ValidationIssue::new(Severity::Error, "saveframe.duplicate_category", format!(
                            "Saveframe '{}' is a second saveframe of category '{}', which may appear only once. The \
                             first is '{}'.", name, category, first))
                            .saveframe(name).category(Some(category)).detail("previous_saveframe", first.as_str())),
                        None => {
                            seen_categories.insert(category.to_string(), name.to_string());
                        }
                    }
                }

                if let Some(ordinal) = schema.saveframe_categories.get(category).and_then(|c| c.id) {
                    if let Some((previous_ordinal, previous_category, previous_saveframe)) = &previous {
                        if *previous_ordinal > ordinal {
                            issues.push(ValidationIssue::new(Severity::Error, "saveframe.order", format!(
                                "Saveframe '{}' of category '{}' should come before saveframe '{}' of category '{}'.",
                                name, category, previous_saveframe, previous_category))
                                .saveframe(name).category(Some(category))
                                .detail("ordinal", ordinal)
                                .detail("previous_saveframe", previous_saveframe.as_str())
                                .detail("previous_category", previous_category.as_str())
                                .detail("previous_ordinal", *previous_ordinal));
                        }
                    }
                    previous = Some((ordinal, category.to_string(), name.to_string()));
                }
            }
        }

        let folded = pystr::lower(name);
        match seen_names.get(&folded) {
            Some(first) => issues.push(ValidationIssue::new(Severity::Error, "saveframe.duplicate_name", format!(
                "More than one saveframe is named '{}' (saveframe names are compared without regard to case).", name))
                .saveframe(name).category(category).detail("previous_saveframe", first.as_str())),
            None => {
                seen_names.insert(folded, name.to_string());
            }
        }

        let framecode = free_tag(saveframe, "Sf_framecode");
        if let Some(first) = framecode.first() {
            if !first.is_null_value() && *first != Value::from(name) {
                issues.push(ValidationIssue::new(Severity::Error, "saveframe.framecode_mismatch", format!(
                    "Saveframe '{}' has Sf_framecode '{}'; the two must match.", name, shown(&first.to_py_string())))
                    .saveframe(name).category(category)
                    .tag(&format!("{}.Sf_framecode", prefix_of(saveframe))).value(first));
            }
        }
    }

    let mut mandatory: Vec<&String> = categories.categories.iter().filter(|(_, code)| **code == 'M').map(|(c, _)| c).collect();
    mandatory.sort();
    for category in mandatory {
        if !present.contains(category) {
            issues.push(ValidationIssue::new(Severity::Error, "saveframe.missing_mandatory_category", format!(
                "The entry has no saveframe of category '{}', which is mandatory.", category)).category(Some(category)));
        }
    }
    Ok(issues)
}

/// Compile a conditional rule's control value into a pattern matched against a whole value. A
/// bracketed character class is implicitly repeated, a bare `*` is a wildcard (None), and a
/// value which is not a regular expression is matched literally.
fn control_pattern(value: &str) -> Option<Regex> {
    if value == "*" {
        return None;
    }
    let pattern = if value.len() > 2 && value.starts_with('[') && value.ends_with(']') {
        format!("{}+", value)
    } else {
        value.to_string()
    };
    let full = |pattern: &str| Regex::new(&format!(r"^(?:{})\z", pattern));
    Some(full(&crate::pyregex::translate(&pattern)).unwrap_or_else(|_| full(&regex::escape(value)).unwrap()))
}

/// Whether any non-null value matches the pattern in full (any non-null value, for None).
fn matches_pattern(pattern: &Option<Regex>, values: &[Value]) -> bool {
    values.iter().any(|value| {
        if value.is_null_value() {
            return false;
        }
        let text = value.to_py_string();
        let text = pystr::strip(&text);
        if text.is_empty() || text == "?" || text == "." {
            return false;
        }
        pattern.as_ref().is_none_or(|p| p.is_match(text))
    })
}

/// The values of a fully qualified tag within a saveframe, or none if it is absent.
fn tag_values(saveframe: &Saveframe, full_tag: &str) -> Vec<Value> {
    saveframe.get_tag(full_tag).unwrap_or_default()
}

/// Null as CheckMandatoryTags counts it: a null value, or a bare `?` or `.` once trimmed.
fn is_null(value: &Value) -> bool {
    value.is_null_value() || matches!(pystr::strip(&value.to_py_string()), "?" | ".")
}

/// Resolves a tag's mandatory code for one entry, conditional rules included.
pub(crate) struct MandatoryResolver<'a> {
    entry: &'a Entry,
    schema: &'a Schema,
    codes: std::sync::Arc<Profile>,
    index: usize,
    entry_values: HashMap<String, Vec<Value>>,
    patterns: HashMap<String, Option<Regex>>,
}

impl<'a> MandatoryResolver<'a> {
    pub(crate) fn new(entry: &'a Entry, schema: &'a Schema, profile: Option<&str>) -> Result<Self> {
        Ok(MandatoryResolver {
            entry,
            schema,
            codes: schema.validation_profile(profile)?,
            index: Schema::profile_index(profile)?,
            entry_values: HashMap::new(),
            patterns: HashMap::new(),
        })
    }

    /// The mandatory code that applies to a tag (lowercase) in a saveframe. The first rule
    /// whose control value matches wins.
    pub(crate) fn code(&mut self, tag: &str, saveframe: &Saveframe, category: Option<&str>) -> char {
        let code = self.codes.tags.get(tag).copied().unwrap_or('O');
        let Some(rules) = self.schema.conditional_rules.get(tag) else { return code };
        for rule in rules {
            let values = if Some(rule.control_category.as_str()) == category {
                tag_values(saveframe, &rule.control_tag)
            } else {
                let entry = self.entry;
                self.entry_values.entry(rule.control_tag.clone())
                    .or_insert_with(|| entry.get_tag(&rule.control_tag).unwrap_or_default()).clone()
            };
            let pattern = self.patterns.entry(rule.value.clone()).or_insert_with(|| control_pattern(&rule.value));
            if matches_pattern(pattern, &values) {
                return rule.flags.chars().nth(self.index).map(|c| c.to_ascii_uppercase())
                    .filter(|c| !pystr::is_space(*c)).unwrap_or(code);
            }
        }
        code
    }
}

fn sequence_of(data: &TagData) -> i64 {
    data.get("Dictionary sequence").trim().parse().unwrap_or(0)
}

/// Report tags the dictionary requires but the entry does not supply (CheckMandatoryTags).
fn check_mandatory_tags(entry: &Entry, schema: &Schema, profile: &str) -> Result<Vec<ValidationIssue>> {
    let mut issues = Vec::new();
    let mut resolver = MandatoryResolver::new(entry, schema, Some(profile))?;

    let mut by_category: HashMap<&str, Vec<&str>> = HashMap::new();
    for (tag, data) in schema.tags() {
        if data.get("Meta data") != "Y" || data.get("Saveframe ID tag") == "Y" {
            continue;
        }
        let category = data.sf_category();
        if !category.is_empty() {
            by_category.entry(category).or_default().push(tag);
        }
    }
    for tags in by_category.values_mut() {
        tags.sort_by_key(|tag| sequence_of(schema.get(tag).unwrap()));
    }

    for saveframe in entry {
        let Some(category) = raw_saveframe_category(schema, saveframe) else { continue };
        for tag in by_category.get(category).map(Vec::as_slice).unwrap_or(&[]) {
            let code = resolver.code(tag, saveframe, Some(category));
            if code == 'O' || code == 'I' {
                continue;
            }
            let full_tag = schema.get(tag).unwrap().tag();
            let values = tag_values(saveframe, full_tag);
            let located = |issue: ValidationIssue| issue.saveframe(saveframe.name()).category(Some(category)).tag(full_tag);
            if code == 'M' || code == 'C' {
                if values.is_empty() {
                    issues.push(located(ValidationIssue::new(Severity::Error, "tag.missing", format!(
                        "Mandatory tag '{}' is missing from saveframe '{}'.", full_tag, saveframe.name())))
                        .detail("requires_value", false));
                }
            } else if code == 'V' || code == 'R' {
                if values.is_empty() {
                    issues.push(located(ValidationIssue::new(Severity::Error, "tag.missing", format!(
                        "Mandatory tag '{}' is missing from saveframe '{}'. It must be present and have a value.",
                        full_tag, saveframe.name()))).detail("requires_value", true));
                } else if is_null(&values[0]) {
                    // The first value, and only the first, as the BMRB validator does
                    issues.push(located(ValidationIssue::new(Severity::Error, "tag.missing_value", format!(
                        "Mandatory tag '{}' in saveframe '{}' has no value.", full_tag, saveframe.name()))));
                }
            }
        }
    }
    Ok(issues)
}

/// Report tags that do not belong where they are used (CheckInvalidTags).
fn check_invalid_tags(entry: &Entry, schema: &Schema, profile: &str) -> Result<Vec<ValidationIssue>> {
    let mut issues = Vec::new();
    let mut resolver = MandatoryResolver::new(entry, schema, Some(profile))?;

    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        let mut examine = |issues: &mut Vec<ValidationIssue>, full_tag: &str, loop_category: Option<&str>| {
            let located = |issue: ValidationIssue| issue.saveframe(saveframe.name()).category(category).tag(full_tag);
            let tag_data = schema.get(&pystr::lower(full_tag));
            let belongs = tag_data.is_some_and(|data| Some(data.sf_category()) == category);
            if !belongs {
                let message = match tag_data {
                    None => format!("Tag '{}' is not in the dictionary.", full_tag),
                    Some(_) if category.is_none() => format!(
                        "Tag '{}' cannot be checked: the category of saveframe '{}' is not recognized.", full_tag, saveframe.name()),
                    Some(data) => format!("Tag '{}' belongs in a saveframe of category '{}', not '{}'.",
                                          full_tag, data.sf_category(), category.unwrap_or("None")),
                };
                issues.push(located(ValidationIssue::new(Severity::Error, "tag.unknown", message)).in_loop(loop_category));
                return;
            }
            let tag_data = tag_data.unwrap();
            if full_tag != tag_data.tag() {
                issues.push(located(ValidationIssue::new(Severity::Error, "tag.miscapitalized", format!(
                    "The tag '{}' is improperly capitalized but otherwise valid. Should be '{}'.", full_tag, tag_data.tag())))
                    .in_loop(loop_category).detail("correct", tag_data.tag()));
                return;
            }
            if loop_category.is_none() && tag_data.get("Loopflag") == "Y" {
                issues.push(located(ValidationIssue::new(Severity::Error, "tag.not_in_loop",
                                                         format!("Tag '{}' belongs in a loop.", full_tag))));
            } else if loop_category.is_some() && tag_data.get("Loopflag") == "N" {
                issues.push(located(ValidationIssue::new(Severity::Error, "tag.free_in_loop",
                                                         format!("Tag '{}' may not be in a loop.", full_tag))).in_loop(loop_category));
            }
            // Only metadata tags are asked: a profile marks data tags invalid simply because they
            //  are outside its view
            if tag_data.get("Meta data") != "Y" {
                return;
            }
            if resolver.code(&pystr::lower(full_tag), saveframe, category) == 'I' {
                issues.push(located(ValidationIssue::new(Severity::Error, "tag.invalid", format!(
                    "Tag '{}' is not allowed in saveframe '{}' by the '{}' validation profile.",
                    full_tag, saveframe.name(), profile))).in_loop(loop_category));
            }
        };

        // Where each tag is used, to find tags used twice in one saveframe
        let mut place_order: Vec<String> = Vec::new();
        let mut places: HashMap<String, Vec<Option<String>>> = HashMap::new();
        let mut place = |full_tag: &str, loop_category: Option<&str>| {
            let folded = pystr::lower(full_tag);
            if !places.contains_key(&folded) {
                place_order.push(folded.clone());
            }
            places.entry(folded).or_default().push(loop_category.map(str::to_string));
        };

        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            place(&full_tag, None);
            examine(&mut issues, &full_tag, None);
        }
        for each_loop in saveframe {
            for tag in each_loop.tags() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                place(&full_tag, each_loop.category());
                examine(&mut issues, &full_tag, each_loop.category());
            }
        }

        for full_tag in &place_order {
            let found = &places[full_tag];
            if found.len() < 2 {
                continue;
            }
            let display = schema.get(full_tag).map(|d| d.tag().to_string()).unwrap_or_else(|| full_tag.clone());
            for loop_category in found {
                issues.push(ValidationIssue::new(Severity::Error, "tag.duplicate", format!(
                    "Tag '{}' appears more than once in saveframe '{}'.", display, saveframe.name()))
                    .saveframe(saveframe.name()).category(category).tag(&display).in_loop(loop_category.as_deref()));
            }
        }
    }
    Ok(issues)
}

/// The tag that numbers a loop's rows (the dictionary's `Row Index Key`), or None. Where a
/// category marks two, the one the dictionary lists first wins.
pub fn row_index_tag(each_loop: &Loop, schema: &Schema) -> Option<String> {
    let category = loop_category_of(each_loop);
    let candidates: Vec<&String> = each_loop.tags().iter().filter(|tag| {
        schema.get(&pystr::lower(&format!("{}.{}", category, tag))).is_some_and(|d| d.get("Row Index Key").trim() == "Y")
    }).collect();
    match candidates.len() {
        0 => None,
        1 => Some(candidates[0].clone()),
        _ => {
            let order: HashMap<String, usize> = schema.schema_order.iter().enumerate()
                .map(|(at, tag)| (pystr::lower(tag), at)).collect();
            candidates.into_iter().min_by_key(|tag| {
                order.get(&pystr::lower(&format!("{}.{}", category, tag))).copied().unwrap_or(order.len())
            }).cloned()
        }
    }
}

/// Report loops whose row-index column does not count 1, 2, 3, ... (CheckRowIndexes). After a
/// wrong index the expectation resyncs to that value plus one; a negative index only advances
/// the count.
fn check_row_indexes(entry: &Entry, schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for each_loop in saveframe {
            let Some(index_tag) = row_index_tag(each_loop, schema) else { continue };
            let full_tag = format!("{}.{}", loop_category_of(each_loop), index_tag);
            let position = each_loop.tags().iter().position(|t| *t == index_tag).unwrap_or(0);
            let mut expected: i64 = 1;
            for (number, row) in each_loop.data.iter().enumerate() {
                let value = row.get(position).cloned().unwrap_or_default();
                let located = |issue: ValidationIssue| issue.saveframe(saveframe.name()).category(category).tag(&full_tag)
                    .in_loop(each_loop.category()).row(number).value(&value);
                let Some(index) = parse_int(&value.to_py_string()) else {
                    issues.push(located(ValidationIssue::new(Severity::Error, "row.index_not_a_number", format!(
                        "Row index '{}' of '{}' is not a number.", shown(&value.to_py_string()), full_tag))));
                    expected += 1;
                    continue;
                };
                if index < 0 {
                    expected += 1;
                    continue;
                }
                if index != expected {
                    issues.push(located(ValidationIssue::new(Severity::Error, "row.index_wrong", format!(
                        "Row index of '{}' is {}; expected {}.", full_tag, shown(&value.to_py_string()), expected)))
                        .detail("expected", expected));
                }
                expected = index + 1;
            }
        }
    }
    issues
}

/// Report tags written out of the dictionary's order, compared with the tag before
/// (CheckTagOrder).
fn check_tag_order(entry: &Entry, schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        let sequence = |full_tag: &str| -> Option<i64> {
            let data = schema.get(&pystr::lower(full_tag))?;
            if Some(data.sf_category()) != category {
                return None;
            }
            data.sequence()
        };
        let mut ordered: Vec<(String, i64, Option<&str>)> = Vec::new();
        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            if let Some(found) = sequence(&full_tag) {
                ordered.push((full_tag, found, None));
            }
        }
        for each_loop in saveframe {
            for tag in each_loop.tags() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                if let Some(found) = sequence(&full_tag) {
                    ordered.push((full_tag, found, each_loop.category()));
                }
            }
        }

        let mut previous: Option<(&str, i64)> = None;
        for (full_tag, sequence, loop_category) in &ordered {
            if let Some((previous_tag, previous_sequence)) = previous {
                if *sequence < previous_sequence {
                    issues.push(ValidationIssue::new(Severity::Error, "tag.order", format!(
                        "Tag '{}' should come before '{}'.", full_tag, previous_tag))
                        .saveframe(saveframe.name()).category(category).tag(full_tag).in_loop(*loop_category)
                        .detail("sequence", *sequence).detail("previous_tag", previous_tag)
                        .detail("previous_sequence", previous_sequence));
                }
            }
            previous = Some((full_tag, *sequence));
        }
    }
    issues
}

/// Every value each parent tag holds in the entry, by lowercase tag, dereferenced.
fn parent_values(entry: &Entry, schema: &Schema, scope: &mut MetadataScope) -> HashMap<String, HashSet<Value>> {
    let wanted: HashSet<String> = schema.parent_tags.values().map(|p| pystr::lower(p)).collect();
    let mut values: HashMap<String, HashSet<Value>> = HashMap::new();
    let mut record = |full_tag: &str, value: &Value| {
        let folded = pystr::lower(full_tag);
        if !wanted.contains(&folded) || value.is_null_value() {
            return;
        }
        values.entry(folded).or_default().insert(dereference(value));
    };
    for saveframe in entry {
        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            if scope.free(&full_tag) {
                record(&full_tag, &tag.value);
            }
        }
        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (position, tag) in each_loop.tags().iter().enumerate() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                if !wanted.contains(&pystr::lower(&full_tag)) {
                    continue;
                }
                for row in &each_loop.data {
                    if let Some(value) = row.get(position) {
                        record(&full_tag, value);
                    }
                }
            }
        }
    }
    values
}

/// Report values that refer to something the entry does not define (CheckRelatedTags). Ties
/// to a saveframe's local ID are left to check_local_ids. A missing parent tag is reported for a
/// free tag and not for a loop column, as the BMRB validator does.
fn check_related_tags(entry: &Entry, schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    // Always the metadata alone: a data loop's references are mostly to chemistry defined
    //  outside the entry
    let mut scope = MetadataScope::new(schema, true);
    let values = parent_values(entry, schema, &mut scope);
    let empty = HashSet::new();

    let parent_of = |full_tag: &str| -> Option<&String> {
        let parent = schema.parent_tags.get(&pystr::lower(full_tag))?;
        (!schema.local_id_tags.contains(&pystr::lower(parent))).then_some(parent)
    };
    let message = |value: &Value, full_tag: &str, parent: &str| format!(
        "Value '{}' of '{}' does not match any value of '{}' in the entry.",
        shown(&dereference(value).to_py_string()), full_tag, parent);

    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            let Some(parent) = parent_of(&full_tag) else { continue };
            if tag.value.is_null_value() || !scope.free(&full_tag) {
                continue;
            }
            if !values.get(&pystr::lower(parent)).unwrap_or(&empty).contains(&dereference(&tag.value)) {
                issues.push(ValidationIssue::new(Severity::Error, "tag.parent_value_missing", message(&tag.value, &full_tag, parent))
                    .saveframe(saveframe.name()).category(category).tag(&full_tag).value(&tag.value)
                    .detail("parent", parent.as_str()));
            }
        }
        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (position, tag) in each_loop.tags().iter().enumerate() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                let Some(parent) = parent_of(&full_tag) else { continue };
                let Some(known) = values.get(&pystr::lower(parent)).filter(|k| !k.is_empty()) else { continue };
                for (number, row) in each_loop.data.iter().enumerate() {
                    let value = row.get(position).cloned().unwrap_or_default();
                    if value.is_null_value() || known.contains(&dereference(&value)) {
                        continue;
                    }
                    issues.push(ValidationIssue::new(Severity::Error, "tag.parent_value_missing", message(&value, &full_tag, parent))
                        .saveframe(saveframe.name()).category(category).tag(&full_tag).in_loop(each_loop.category())
                        .row(number).value(&value).detail("parent", parent.as_str()));
                }
            }
        }
    }
    issues
}

/// Report loop rows that claim to belong to a different saveframe (CheckLocalIds), and
/// saveframes with no local ID.
fn check_local_ids(entry: &Entry, schema: &Schema, metadata_only: bool) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    let mut scope = MetadataScope::new(schema, metadata_only);
    let is_local_id = |full_tag: &str, in_loop: bool| -> bool {
        let folded = pystr::lower(full_tag);
        match schema.get(&folded) {
            Some(data) if schema.local_id_tags.contains(&folded) => data.get("Loopflag") == if in_loop { "Y" } else { "N" },
            _ => false,
        }
    };

    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        let local_id = saveframe.tags().iter().find(|tag| {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            is_local_id(&full_tag, false) && scope.free(&full_tag)
        }).map(|tag| tag.value.clone()).unwrap_or(Value::Null);

        if local_id.is_none() {
            if category == Some("entry_information") {
                continue;
            }
            issues.push(ValidationIssue::new(Severity::Error, "saveframe.no_local_id_tag", format!(
                "Saveframe '{}' has no local ID tag.", saveframe.name())).saveframe(saveframe.name()).category(category));
        }
        if local_id.is_null_value() {
            issues.push(ValidationIssue::new(Severity::Error, "saveframe.invalid_local_id", format!(
                "Saveframe '{}' has no local ID value.", saveframe.name())).saveframe(saveframe.name()).category(category));
            continue;
        }

        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (position, tag) in each_loop.tags().iter().enumerate() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                if !is_local_id(&full_tag, true) {
                    continue;
                }
                for (number, row) in each_loop.data.iter().enumerate() {
                    let value = row.get(position).cloned().unwrap_or_default();
                    if value != local_id {
                        issues.push(ValidationIssue::new(Severity::Error, "row.invalid_local_id", format!(
                            "'{}' is '{}', but the local ID of saveframe '{}' is '{}'.", full_tag,
                            shown(&value.to_py_string()), saveframe.name(), shown(&local_id.to_py_string())))
                            .saveframe(saveframe.name()).category(category).tag(&full_tag).in_loop(each_loop.category())
                            .row(number).value(&value).detail("local_id", local_id.clone()));
                    }
                }
            }
        }
    }
    issues
}

/// Report references to saveframes the entry does not contain (CheckFrameCodes).
fn check_frame_codes(entry: &Entry, schema: &Schema, metadata_only: bool) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    let mut scope = MetadataScope::new(schema, metadata_only);
    let names: HashSet<&str> = entry.iter().map(Saveframe::name).collect();
    let dangling = |value: &Value| -> Option<String> {
        let target = value.as_str()?.strip_prefix('$')?;
        (!names.contains(target)).then(|| target.to_string())
    };

    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            if !scope.free(&full_tag) {
                continue;
            }
            if let Some(target) = dangling(&tag.value) {
                issues.push(ValidationIssue::new(Severity::Error, "value.dangling_framecode", format!(
                    "'{}' refers to saveframe '{}', which does not exist.", full_tag, shown(&target)))
                    .value(&tag.value).saveframe(saveframe.name()).category(category).tag(&full_tag));
            }
        }
        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (position, tag) in each_loop.tags().iter().enumerate() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                for (number, row) in each_loop.data.iter().enumerate() {
                    let Some(value) = row.get(position) else { continue };
                    if let Some(target) = dangling(value) {
                        issues.push(ValidationIssue::new(Severity::Error, "value.dangling_framecode", format!(
                            "'{}' refers to saveframe '{}', which does not exist.", full_tag, shown(&target)))
                            .value(value).saveframe(saveframe.name()).category(category).tag(&full_tag)
                            .in_loop(each_loop.category()).row(number));
                    }
                }
            }
        }
    }
    issues
}

/// Report sample components that do not say what they are or how much (CheckSampleSaveframe).
fn check_sample_saveframe(entry: &Entry, schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for saveframe in entry {
        if saveframe_category(schema, saveframe) != Some("sample") {
            continue;
        }
        for each_loop in saveframe {
            if each_loop.category() != Some("_Sample_component") {
                continue;
            }
            let columns: HashMap<String, usize> = each_loop.tags().iter().enumerate()
                .map(|(position, tag)| (pystr::lower(tag), position)).collect();
            let column = |name: &str| columns.get(name).copied();
            let (name, entity) = (column("mol_common_name"), column("entity_label"));
            let value = column("concentration_val");
            let (minimum, maximum) = (column("concentration_val_min"), column("concentration_val_max"));
            let null = |row: &[Value], position: Option<usize>| {
                position.is_none_or(|p| row.get(p).is_none_or(Value::is_null_value))
            };

            for (number, row) in each_loop.data.iter().enumerate() {
                if name.is_some() && entity.is_some() && null(row, name) && null(row, entity) {
                    issues.push(ValidationIssue::new(Severity::Error, "row.unidentified_sample_component", format!(
                        "A sample component in saveframe '{}' has neither a Mol_common_name nor an Entity_label.",
                        saveframe.name())).saveframe(saveframe.name()).category(Some("sample"))
                        .tag("_Sample_component.Mol_common_name").in_loop(each_loop.category()).row(number));
                }
                if value.is_some() && minimum.is_some() && maximum.is_some()
                    && null(row, value) && null(row, minimum) && null(row, maximum) {
                    issues.push(ValidationIssue::new(Severity::Error, "row.missing_concentration", format!(
                        "A sample component in saveframe '{}' has neither a Concentration_val nor both a \
                         Concentration_val_min and Concentration_val_max.", saveframe.name()))
                        .saveframe(saveframe.name()).category(Some("sample"))
                        .tag("_Sample_component.Concentration_val").in_loop(each_loop.category()).row(number));
                }
            }
        }
    }
    issues
}

/// One value of an entry, with everything a finding needs to locate it.
struct Located<'a> {
    saveframe: &'a str,
    category: Option<&'a str>,
    tag: String,
    loop_category: Option<&'a str>,
    row: Option<usize>,
    value: &'a Value,
}

impl Located<'_> {
    fn issue(&self, severity: Severity, check: &str, message: String) -> ValidationIssue {
        let mut issue = ValidationIssue::new(severity, check, message).saveframe(self.saveframe).category(self.category)
            .tag(&self.tag).in_loop(self.loop_category).value(self.value);
        issue.row = self.row;
        issue
    }
}

/// Every value in scope in an entry, saveframe tags and loop values alike.
fn scoped_values<'a>(entry: &'a Entry, schema: &'a Schema, metadata_only: bool) -> Vec<Located<'a>> {
    let mut scope = MetadataScope::new(schema, metadata_only);
    let mut values = Vec::new();
    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for tag in saveframe.tags() {
            let full_tag = format!("{}.{}", prefix_of(saveframe), tag.name);
            if scope.free(&full_tag) {
                values.push(Located { saveframe: saveframe.name(), category, tag: full_tag, loop_category: None,
                                      row: None, value: &tag.value });
            }
        }
        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (position, tag) in each_loop.tags().iter().enumerate() {
                let full_tag = format!("{}.{}", loop_category_of(each_loop), tag);
                for (number, row) in each_loop.data.iter().enumerate() {
                    if let Some(value) = row.get(position) {
                        values.push(Located { saveframe: saveframe.name(), category, tag: full_tag.clone(),
                                              loop_category: each_loop.category(), row: Some(number), value });
                    }
                }
            }
        }
    }
    values
}

/// A value without the newline that closed its `;` block.
fn measured(value: &str) -> &str {
    value.strip_suffix('\n').unwrap_or(value)
}

/// A value as it can appear in a one-line message.
fn shown(value: &str) -> String {
    measured(value).replace('\n', "\\n").replace('\r', "\\r")
}

/// Report values containing characters NMR-STAR cannot carry (CheckCharset).
fn check_charset(values: &[Located]) -> Vec<ValidationIssue> {
    values.iter().filter(|item| !item.value.is_none()).filter_map(|item| {
        let text = item.value.to_py_string();
        (!text.is_ascii()).then(|| item.issue(Severity::Error, "value.non_ascii", non_ascii_error(&item.tag, &shown(&text))))
    }).collect()
}

/// Report loop rows in which every value is null (CheckEmptyRows).
fn check_empty_rows(entry: &Entry, schema: &Schema, metadata_only: bool) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    let mut scope = MetadataScope::new(schema, metadata_only);
    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for each_loop in saveframe {
            if !scope.in_loop(each_loop.category()) {
                continue;
            }
            for (number, row) in each_loop.data.iter().enumerate() {
                if !row.is_empty() && row.iter().all(Value::is_null_value) {
                    issues.push(ValidationIssue::new(Severity::Error, "row.empty", format!(
                        "A row of loop '{}' in saveframe '{}' contains only null values.",
                        loop_category_of(each_loop), saveframe.name()))
                        .saveframe(saveframe.name()).category(category).in_loop(each_loop.category()).row(number));
                }
            }
        }
    }
    issues
}

/// Report loop rows with more or fewer values than the loop has tags.
fn check_loop_widths(entry: &Entry, schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for saveframe in entry {
        let category = saveframe_category(schema, saveframe);
        for each_loop in saveframe {
            let width = each_loop.tags().len();
            for (number, row) in each_loop.data.iter().enumerate() {
                if row.len() != width {
                    issues.push(ValidationIssue::new(Severity::Error, "row.wrong_width", format!(
                        "A row of loop '{}' in saveframe '{}' has {} values, but the loop has {} tags.",
                        loop_category_of(each_loop), saveframe.name(), row.len(), width))
                        .saveframe(saveframe.name()).category(category).in_loop(each_loop.category()).row(number)
                        .detail("values", row.len()).detail("tags", width));
                }
            }
        }
    }
    issues
}

/// Report values outside the closed enumeration their tag allows (CheckDataValues).
fn check_data_values(values: &[Located], schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for item in values {
        if item.value.is_null_value() {
            continue;
        }
        let Some(enumeration) = schema.enumerations.get(&pystr::lower(&item.tag)).filter(|e| e.closed) else { continue };
        let text = item.value.to_py_string();
        let value = measured(&text);
        if enumeration.values.contains(value) {
            continue;
        }
        issues.push(match enumeration.folded.get(&pystr::lower(value)) {
            Some(capitalized) => item.issue(Severity::Error, "value.miscapitalized", format!(
                "Value '{}' of '{}' is improperly capitalized but otherwise valid. Should be '{}'.",
                shown(value), item.tag, capitalized)).detail("correct", capitalized.as_str()),
            None => item.issue(Severity::Error, "value.not_in_enumeration", format!(
                "Value '{}' of '{}' is not one of the values the dictionary allows.", shown(value), item.tag)),
        });
    }
    issues
}

/// Whether a value is an integer, by the BMRB validator's rule: an optional leading sign, then
/// digits.
fn is_int(value: &str) -> bool {
    pystr::strip(value).chars().enumerate().all(|(position, c)| match c {
        '+' | '-' => position == 0,
        c => c.is_ascii_digit(),
    })
}

/// Whether a value is a floating-point number, by the BMRB validator's rule (TypeChecker.isFloat,
/// transliterated, including its quirks: a bare `inf` is not accepted, and an `i` not followed by
/// `nf` falls through to the decimal point case).
fn is_float(value: &str) -> bool {
    #[derive(PartialEq)]
    enum Previous { None, Digit, Exponent, Dot, Sign }
    let text: Vec<char> = pystr::strip(value).chars().collect();
    let (mut seen_dot, mut seen_exponent, mut has_exponent, mut need_digit) = (false, false, false, false);
    let mut previous = Previous::None;

    for (position, &c) in text.iter().enumerate() {
        match c {
            '+' | '-' => {
                if need_digit || (position != 0 && !matches!(text[position - 1], 'e' | 'E')) {
                    return false;
                }
                previous = Previous::Sign;
            }
            'e' | 'E' => {
                if seen_exponent || need_digit {
                    return false;
                }
                seen_exponent = true;
                previous = Previous::Exponent;
            }
            'i' | 'I' | '.' => {
                if c != '.' {
                    if position > 1 || previous != Previous::Sign || position + 2 >= text.len() {
                        return false;
                    }
                    if matches!(text[position + 1], 'n' | 'N') && matches!(text[position + 2], 'f' | 'F') {
                        return true;
                    }
                }
                if seen_dot {
                    return false;
                }
                if previous != Previous::Digit {
                    if position + 1 >= text.len() {
                        return false;
                    }
                    need_digit = true;
                }
                seen_dot = true;
                previous = Previous::Dot;
            }
            c if c.is_ascii_digit() => {
                if seen_exponent {
                    has_exponent = true;
                }
                need_digit = false;
                previous = Previous::Digit;
            }
            _ => return false,
        }
    }
    !(seen_exponent && !has_exponent)
}

/// Whether a value is a date by the BMRB validator's rule: yyyy-mm-dd with a month of 1-12 and a
/// day of 1-31.
fn is_iso_date(value: &str) -> bool {
    let text: Vec<char> = pystr::strip(value).chars().collect();
    if text.len() != 10 || text[4] != '-' || text[7] != '-' {
        return false;
    }
    if !text.iter().enumerate().all(|(i, c)| i == 4 || i == 7 || c.is_ascii_digit()) {
        return false;
    }
    let number = |range: std::ops::Range<usize>| text[range].iter().collect::<String>().parse::<u32>().unwrap_or(0);
    (1..=12).contains(&number(5..7)) && (1..=31).contains(&number(8..10))
}

/// The coarse type the BMRB validator checks a tag's values against.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ValueKind {
    Framecode,
    Integer,
    Float,
    Date,
    String,
}

/// A tag's value type and length limit, as the validator dictionary derives them from its SQL
/// type. A tag flagged as a saveframe pointer is a framecode whatever its column type says.
pub fn value_type(tag_data: &TagData) -> (ValueKind, Option<usize>) {
    if pystr::upper(tag_data.get("Sf pointer").trim()).starts_with('Y') {
        return (ValueKind::Framecode, None);
    }
    let sql_type = pystr::lower(tag_data.get("Data Type").trim());
    static SIZED: std::sync::OnceLock<Regex> = std::sync::OnceLock::new();
    let sized = SIZED.get_or_init(|| Regex::new(r"(?i)char(?:\((\d+)\))?\n?\z").unwrap());
    if let Some(found) = sized.captures(&sql_type) {
        return (ValueKind::String, found.get(1).and_then(|size| size.as_str().parse().ok()));
    }
    if sql_type.contains("text") {
        (ValueKind::String, None)
    } else if sql_type.contains("integer") {
        (ValueKind::Integer, None)
    } else if sql_type.contains("float") || sql_type.contains("real") {
        (ValueKind::Float, None)
    } else if sql_type.contains("date") {
        (ValueKind::Date, None)
    } else {
        (ValueKind::String, None)
    }
}

/// Report values that are not of the type their tag is declared to hold (CheckDataTypes), plus
/// impossible dates, values not matching the dictionary type's own pattern, and nulls in tags
/// declared NOT NULL.
fn check_data_types(values: &[Located], schema: &Schema) -> Vec<ValidationIssue> {
    let mut issues = Vec::new();
    for item in values {
        let Some(tag_data) = schema.get(&pystr::lower(&item.tag)) else { continue };
        let (kind, size) = value_type(tag_data);
        let bmrb_type = tag_data.get("BMRB data type");

        if item.value.is_null_value() {
            if !tag_data.nullable {
                issues.push(item.issue(Severity::Error, "value.null_not_allowed", format!(
                    "Tag '{}' in saveframe '{}' may not be null.", item.tag, item.saveframe)));
            }
            continue;
        }

        let text = item.value.to_py_string();
        let value = measured(&text);
        let shown_value = shown(value);
        let mut found: Vec<ValidationIssue> = Vec::new();
        match kind {
            ValueKind::Framecode => {
                if !value.starts_with('$') {
                    found.push(item.issue(Severity::Error, "value.not_a_framecode", format!(
                        "Value '{}' of '{}' should be a saveframe reference, which starts with '$'.", shown_value, item.tag)));
                    if value.chars().any(pystr::is_space) {
                        found.push(item.issue(Severity::Error, "value.framecode_whitespace", format!(
                            "Saveframe reference '{}' of '{}' contains whitespace.", shown_value, item.tag)));
                    }
                }
            }
            ValueKind::Integer => {
                if !is_int(value) {
                    found.push(item.issue(Severity::Error, "value.not_an_integer",
                                          format!("Value '{}' of '{}' is not an integer.", shown_value, item.tag)));
                }
            }
            ValueKind::Float => {
                if !is_float(value) {
                    found.push(item.issue(Severity::Error, "value.not_a_float",
                                          format!("Value '{}' of '{}' is not a number.", shown_value, item.tag)));
                }
            }
            ValueKind::Date => {
                if !is_iso_date(value) {
                    found.push(item.issue(Severity::Error, "value.not_a_date", format!(
                        "Value '{}' of '{}' is not a date of the form yyyy-mm-dd.", shown_value, item.tag)));
                } else if !is_valid_date(pystr::strip(value)) {
                    found.push(item.issue(Severity::Strict, "value.impossible_date",
                                          format!("Value '{}' of '{}' is not a real date.", shown_value, item.tag)));
                }
            }
            ValueKind::String => {
                if let Some(size) = size {
                    let length = pystr::char_len(value);
                    if length > size {
                        found.push(item.issue(Severity::Error, "value.too_long", format!(
                            "Value of '{}' is {} characters long; at most {} are allowed: '{}'.",
                            item.tag, length, size, shown_value)).detail("max_length", size));
                    }
                }
            }
        }

        if found.is_empty() && value.is_ascii() {
            if let Some(pattern) = schema.type_regex(bmrb_type) {
                if !pattern.is_match(value) {
                    found.push(item.issue(Severity::Error, "value.type_mismatch", format!(
                        "Value '{}' of '{}' is not a valid '{}'.", shown_value, item.tag, bmrb_type))
                        .detail("type", bmrb_type).detail("pattern", schema.data_types[bmrb_type].as_str()));
                }
            }
        }
        issues.extend(found);
    }
    issues
}

/// Run every check of [`Entry::validate_full`].
pub(crate) fn validate_full(entry: &Entry, schema: &Schema, profile: &str, severities: Option<&[Severity]>,
                            metadata_only: bool) -> Result<Vec<ValidationIssue>> {
    let mut issues = Vec::new();
    issues.extend(check_saveframes(entry, schema, profile)?);
    issues.extend(check_invalid_tags(entry, schema, profile)?);
    issues.extend(check_mandatory_tags(entry, schema, profile)?);
    issues.extend(check_tag_order(entry, schema));
    issues.extend(check_row_indexes(entry, schema));
    issues.extend(check_related_tags(entry, schema));
    issues.extend(check_local_ids(entry, schema, metadata_only));
    issues.extend(check_frame_codes(entry, schema, metadata_only));
    issues.extend(check_sample_saveframe(entry, schema));
    let values = scoped_values(entry, schema, metadata_only);
    issues.extend(check_data_types(&values, schema));
    issues.extend(check_data_values(&values, schema));
    issues.extend(check_empty_rows(entry, schema, metadata_only));
    issues.extend(check_charset(&values));
    issues.extend(check_loop_widths(entry, schema));

    // A value-mandatory tag that is null breaks two rules at once; one finding says it
    let missing_value: HashSet<(Option<String>, Option<String>)> = issues.iter()
        .filter(|issue| issue.check == "tag.missing_value")
        .map(|issue| (issue.saveframe.clone(), issue.tag.clone())).collect();
    issues.retain(|issue| !(issue.check == "value.null_not_allowed" && matches!(issue.row, None | Some(0))
        && missing_value.contains(&(issue.saveframe.clone(), issue.tag.clone()))));

    Ok(match severities {
        None => issues,
        Some(wanted) => issues.into_iter().filter(|issue| wanted.contains(&issue.severity)).collect(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn numbers_by_the_validators_rules() {
        for good in ["1", "+", "-12", " 3 ", ""] {
            assert!(is_int(good), "{}", good);
        }
        for bad in ["1-", "1.0", "a"] {
            assert!(!is_int(bad), "{}", bad);
        }
        for good in ["1.5", "-.1", "1.", "1e5", "+inf", "-1.5E-3"] {
            assert!(is_float(good), "{}", good);
        }
        for bad in ["inf", "1.2.3", "-.", "1e", "abc", "1e5e"] {
            assert!(!is_float(bad), "{}", bad);
        }
        assert!(is_iso_date("2024-02-31"));
        assert!(!is_iso_date("2010-13-01"));
    }
}
