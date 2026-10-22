//! The NMR-STAR dictionary, used to validate entries, convert data types, and order tags.

use std::collections::{HashMap, HashSet};
use std::fmt;
use std::sync::{Arc, RwLock};

use log::warn;
use regex::Regex;

use crate::csv;
use crate::definitions;
use crate::error::{Error, Result};
use crate::internal::{self, Dictionary, Source};
use crate::pystr;
use crate::utils::{format_category, format_tag};
use crate::value::{parse_int, Date, Decimal, Value};

/// One tag of the dictionary: a row of its tag table, read by column name.
#[derive(Clone, Debug)]
pub struct TagData {
    row: Vec<String>,
    columns: Arc<HashMap<String, usize>>,
    /// Whether the tag may be null (the `Nullable` column is not `NOT NULL`)
    pub nullable: bool,
    /// The tag's validation flag per profile, indexed as [`definitions::VALIDATION_PROFILES`]
    pub validate_flags: String,
}

impl TagData {
    /// The value of a column of the tag table, or "" if the table has no such column.
    pub fn get(&self, column: &str) -> &str {
        self.columns.get(column).and_then(|&i| self.row.get(i)).map(String::as_str).unwrap_or("")
    }

    /// The tag, as the dictionary spells it.
    pub fn tag(&self) -> &str {
        self.get("Tag")
    }

    /// The saveframe category of the tag, trimmed.
    pub fn sf_category(&self) -> &str {
        self.get("SFCategory").trim()
    }

    /// The dictionary sequence number, if it is an integer.
    pub fn sequence(&self) -> Option<i64> {
        let raw = self.get("Dictionary sequence").trim();
        if !raw.is_empty() && raw.bytes().all(|b| b.is_ascii_digit()) { raw.parse().ok() } else { None }
    }

    fn set(&mut self, column: &str, value: &str) {
        if let Some(&i) = self.columns.get(column) {
            if i >= self.row.len() {
                self.row.resize(i + 1, String::new());
            }
            self.row[i] = value.to_string();
        }
    }
}

/// A closed or open list of the values a tag may have.
#[derive(Clone, Debug, Default)]
pub struct Enumeration {
    /// Whether only the listed values are allowed
    pub closed: bool,
    /// The values, as the dictionary spells them
    pub values: HashSet<String>,
    /// The values, keyed by their lowercase spelling
    pub folded: HashMap<String, String>,
}

/// A saveframe category of the dictionary.
#[derive(Clone, Debug)]
pub struct SaveframeCategory {
    /// The category's validation flag per profile
    pub flags: String,
    /// Whether an entry may hold only one saveframe of the category
    pub unique: bool,
    /// The category's ordinal: the lowest dictionary sequence number among its tags
    pub id: Option<i64>,
}

/// A conditional mandatory rule: when `control_tag` has `value`, the mandatory code of the
/// tag becomes the one in `flags`.
#[derive(Clone, Debug)]
pub struct ConditionalRule {
    pub control_category: String,
    pub control_tag: String,
    pub value: String,
    pub category: String,
    pub flags: String,
}

/// The mandatory codes of one validation profile: by tag (lowercase), and by saveframe
/// category.
#[derive(Clone, Debug, PartialEq)]
pub struct Profile {
    pub tags: HashMap<String, char>,
    pub categories: HashMap<String, char>,
}

/// The order a tag sorts in: its position in the dictionary, or after every dictionary tag.
pub type TagKey = u128;

/// A BMRB schema: the NMR-STAR dictionary. Used to validate entries, convert data types and
/// order tags. Unless a specific dictionary version is needed, the library uses the packaged
/// dictionary automatically (see [`crate::utils::get_schema`]).
#[derive(Debug)]
pub struct Schema {
    /// The column names of the tag table
    pub headers: Vec<String>,
    columns: Arc<HashMap<String, usize>>,
    /// The tags, keyed by their lowercase name, in dictionary order
    tags: Vec<(String, TagData)>,
    tag_positions: HashMap<String, usize>,
    /// The tags, as the dictionary spells them, in dictionary order
    pub schema_order: Vec<String>,
    order_index: HashMap<String, usize>,
    /// The categories of the tags (with leading underscores), in dictionary order
    pub category_order: Vec<String>,
    /// The dictionary version
    pub version: String,
    /// Value type name -> the regular expression its values must match
    pub data_types: HashMap<String, String>,
    compiled_types: HashMap<String, Regex>,
    /// Tag (lowercase) -> its enumeration
    pub enumerations: HashMap<String, Enumeration>,
    /// Saveframe category -> its flags
    pub saveframe_categories: HashMap<String, SaveframeCategory>,
    /// Child tag (lowercase) -> the tag whose values it must be drawn from
    pub parent_tags: HashMap<String, String>,
    /// The tags holding a saveframe's local ID (lowercase)
    pub local_id_tags: HashSet<String>,
    /// Tag (lowercase) -> the value to give it when creating it empty
    pub default_values: HashMap<String, String>,
    /// The tags a deposition tool fills in by itself (lowercase)
    pub auto_inserted_tags: HashSet<String>,
    /// Tag (lowercase) -> its conditional mandatory rules
    pub conditional_rules: HashMap<String, Vec<ConditionalRule>>,
    profiles: RwLock<HashMap<String, Arc<Profile>>>,
    /// Where the schema was loaded from, if not the packaged or a versioned dictionary
    pub schema_file: Option<String>,
}

impl Clone for Schema {
    fn clone(&self) -> Schema {
        Schema {
            headers: self.headers.clone(),
            columns: self.columns.clone(),
            tags: self.tags.clone(),
            tag_positions: self.tag_positions.clone(),
            schema_order: self.schema_order.clone(),
            order_index: self.order_index.clone(),
            category_order: self.category_order.clone(),
            version: self.version.clone(),
            data_types: self.data_types.clone(),
            compiled_types: self.compiled_types.clone(),
            enumerations: self.enumerations.clone(),
            saveframe_categories: self.saveframe_categories.clone(),
            parent_tags: self.parent_tags.clone(),
            local_id_tags: self.local_id_tags.clone(),
            default_values: self.default_values.clone(),
            auto_inserted_tags: self.auto_inserted_tags.clone(),
            conditional_rules: self.conditional_rules.clone(),
            profiles: RwLock::new(HashMap::new()),
            schema_file: self.schema_file.clone(),
        }
    }
}

/// Whether a value which already matched one of the dictionary's date type patterns is a real
/// date. The patterns accept a two digit year, month 13, day 32.
pub(crate) fn is_valid_date(value: &str) -> bool {
    let date_part = value.split_once(':').map(|(date, _)| date).unwrap_or(value);
    let fields: Vec<&str> = date_part.split('-').collect();
    if pystr::char_len(fields[0]) != 4 {
        return false;
    }
    let field = |i: usize| -> Option<i64> {
        match fields.get(i) {
            Some(text) => parse_int(text),
            None => Some(1),
        }
    };
    match (field(0), field(1), field(2)) {
        (Some(year), Some(month), Some(day)) => {
            i32::try_from(year).ok().zip(u32::try_from(month).ok()).zip(u32::try_from(day).ok())
                .and_then(|((y, m), d)| Date::new(y, m, d)).is_some()
        }
        _ => false,
    }
}

/// A deterministic hash, standing in for Python's `hash()` of a string when ordering tags the
/// dictionary does not know.
fn stable_hash(s: &str) -> u64 {
    let mut hash: u64 = 0xcbf29ce484222325;
    for b in s.bytes() {
        hash ^= b as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash >> 1
}

impl Schema {
    fn empty(schema_file: Option<String>) -> Schema {
        Schema {
            headers: Vec::new(),
            columns: Arc::new(HashMap::new()),
            tags: Vec::new(),
            tag_positions: HashMap::new(),
            schema_order: Vec::new(),
            order_index: HashMap::new(),
            category_order: Vec::new(),
            version: "unknown".to_string(),
            data_types: HashMap::new(),
            compiled_types: HashMap::new(),
            enumerations: HashMap::new(),
            saveframe_categories: HashMap::new(),
            parent_tags: HashMap::new(),
            local_id_tags: HashSet::new(),
            default_values: HashMap::new(),
            auto_inserted_tags: HashSet::new(),
            conditional_rules: HashMap::new(),
            profiles: RwLock::new(HashMap::new()),
            schema_file,
        }
    }

    /// The schema of the dictionary distribution packaged with the library. Never touches the
    /// network.
    pub fn new() -> Result<Schema> {
        Schema::load(None, None)
    }

    /// The schema of a dictionary release (3.2.14.0 or above). `"latest"` downloads the newest
    /// release, and caches it so that it can later be asked for by number without the network.
    /// A version number loads that release from the packaged copy or the cache, downloading
    /// (and caching) it only if neither has it. See [`internal::load_dictionary`].
    pub fn from_version(version: &str) -> Result<Schema> {
        Schema::load(None, Some(version))
    }

    /// Load the dictionary from somewhere else. `schema_file` may be a local directory holding
    /// the distribution files, in which case `version` may not be given as well; or a single
    /// `xlschem_ann.csv` tag table. A tag table carries only the tags, so the enumerations and
    /// validation rules are taken from the packaged or cached distribution of the same version -
    /// or, if `version` is given, of that version. If none is available, the schema is built
    /// from the tag table alone, and a warning is logged.
    pub fn from_file(schema_file: impl Into<Source>, version: Option<&str>) -> Result<Schema> {
        Schema::load(Some(schema_file.into()), version)
    }

    fn load(schema_file: Option<Source>, version: Option<&str>) -> Result<Schema> {
        let mut schema = Schema::empty(schema_file.as_ref().map(Source::label));
        let (xlschem_text, distribution): (String, Option<Dictionary>) = match &schema_file {
            Some(Source::Path(path)) if path.is_dir() => {
                if version.is_some() {
                    return Err(Error::value("Pass either a dictionary directory as schema_file or a version, not both."));
                }
                let distribution = internal::read_dictionary_directory(&path.to_string_lossy())?;
                (distribution["xlschem_ann.csv"].clone(), Some(distribution))
            }
            Some(source) => {
                let text = internal::read_text(source)?;
                let distribution = match version {
                    Some(version) => Some(internal::load_dictionary(Some(version), None)?.0),
                    None => {
                        let distribution = internal::local_dictionary(&internal::dictionary_version(&text));
                        if distribution.is_none() {
                            warn!("No dictionary distribution matching the tag table in '{}' is available, so the \
                                   schema has no enumerations or validation rules.", source.label());
                        }
                        distribution
                    }
                };
                (text, distribution)
            }
            None => {
                let (distribution, _) = internal::load_dictionary(version, None)?;
                (distribution["xlschem_ann.csv"].clone(), Some(distribution))
            }
        };

        schema.parse_tag_table(&xlschem_text)?;
        schema.parse_relationships();
        schema.load_data_types();
        if let Some(distribution) = distribution {
            schema.build_enumerations(&distribution["adit_enum_hdr.csv"], &distribution["adit_enum_dtl.csv"]);
            schema.parse_saveframe_categories(&distribution["adit_cat_grp_o.csv"]);
            schema.parse_conditional_rules(&distribution["adit_tag_validation.csv"]);
        }
        Ok(schema)
    }

    /// The dictionary's data for a tag, by its lowercase name.
    pub fn get(&self, tag_lower: &str) -> Option<&TagData> {
        self.tag_positions.get(tag_lower).map(|&i| &self.tags[i].1)
    }

    /// The dictionary's data for a tag, by its name in any case.
    pub fn get_tag(&self, tag: &str) -> Option<&TagData> {
        self.get(&pystr::lower(tag))
    }

    /// Whether the dictionary has a tag (given by its lowercase name).
    pub fn contains(&self, tag_lower: &str) -> bool {
        self.tag_positions.contains_key(tag_lower)
    }

    /// Every tag of the dictionary, by lowercase name, in dictionary order.
    pub fn tags(&self) -> impl Iterator<Item = (&str, &TagData)> {
        self.tags.iter().map(|(name, data)| (name.as_str(), data))
    }

    /// The number of tags in the dictionary.
    pub fn len(&self) -> usize {
        self.tags.len()
    }

    pub fn is_empty(&self) -> bool {
        self.tags.is_empty()
    }

    fn insert_tag(&mut self, key: String, data: TagData) {
        match self.tag_positions.get(&key) {
            Some(&i) => self.tags[i].1 = data,
            None => {
                self.tag_positions.insert(key.clone(), self.tags.len());
                self.tags.push((key, data));
            }
        }
    }

    fn rebuild_order_index(&mut self) {
        self.order_index.clear();
        for (i, tag) in self.schema_order.iter().enumerate() {
            self.order_index.entry(tag.clone()).or_insert(i);
        }
    }

    /// Populate the tag schema from an xlschem_ann.csv body. Read positionally, because the
    /// header repeats names across column groups, so the per-view validation flags have to be
    /// taken by index. The third header row labels the groups, which identifies the `Validate`
    /// block.
    fn parse_tag_table(&mut self, xlschem_text: &str) -> Result<()> {
        let normalized = pystr::splitlines(xlschem_text).join("\n");
        let mut rows = csv::rows(&normalized);
        let failure = || Error::value(format!("Could not parse a schema from: {}",
                                              self.schema_file.as_deref().unwrap_or("None")));
        self.headers = rows.next().ok_or_else(failure)?;
        let width = self.headers.len();
        let mut columns = HashMap::new();
        for (i, header) in self.headers.iter().enumerate() {
            columns.insert(header.clone(), i);
        }
        self.columns = Arc::new(columns);

        let mut validate_columns: Vec<usize> = Vec::new();
        loop {
            let row = rows.next().ok_or_else(failure)?;
            let found: Vec<usize> = row.iter().enumerate()
                .filter(|(_, group)| group.trim() == "Validate").map(|(i, _)| i).collect();
            if !found.is_empty() {
                validate_columns = found;
            }
            if row.first().map(String::as_str) == Some("TBL_BEGIN") {
                let mut row = row;
                row.resize(width.max(row.len()), String::new());
                self.version = self.columns.get("ADIT category view type")
                    .map(|&i| row[i].clone()).unwrap_or_default();
                break;
            }
        }

        let mut categories_seen: HashSet<String> = HashSet::new();
        for mut row in rows {
            if row.first().map(String::as_str) == Some("TBL_END") {
                break;
            }
            let validate_flags: String = validate_columns.iter().map(|&i| {
                match row.get(i) {
                    Some(value) => pystr::upper(value.trim()).chars().next().unwrap_or(' '),
                    None => ' ',
                }
            }).collect();
            row.resize(width, String::new());
            let data = TagData {
                nullable: self.columns.get("Nullable").map(|&i| row[i].as_str()) != Some("NOT NULL"),
                row,
                columns: self.columns.clone(),
                validate_flags,
            };
            let tag = data.tag().to_string();
            self.insert_tag(pystr::lower(&tag), data);
            let formatted = format_category(&tag);
            if categories_seen.insert(formatted.clone()) {
                self.category_order.push(formatted);
            }
            self.schema_order.push(tag);
        }
        self.rebuild_order_index();
        Ok(())
    }

    /// Derive the ties between tags from the tag table: which tag each tag's values must be
    /// drawn from, which tags carry a saveframe's local ID, the default values, and which tags
    /// are inserted automatically.
    fn parse_relationships(&mut self) {
        let mut by_field: HashMap<(String, String), String> = HashMap::new();
        for (_, data) in &self.tags {
            let category = data.get("Tag category").trim();
            let field = data.get("Tag field").trim();
            if !category.is_empty() && !field.is_empty() {
                by_field.insert((category.to_string(), field.to_string()), data.tag().to_string());
            }
        }

        for (tag, data) in &self.tags {
            let table = data.get("Foreign Table").trim().to_string();
            let column = data.get("Foreign Column").trim().to_string();
            if let Some(parent) = by_field.get(&(table, column)) {
                self.parent_tags.insert(tag.clone(), parent.clone());
            }

            if pystr::upper(data.get("lclSfIdFlg").trim()).starts_with('Y')
                && tag != "_entry.id" && !tag.ends_with(".entry_id") {
                self.local_id_tags.insert(tag.clone());
            }

            let default = data.get("default value").trim();
            let has_default = !matches!(default, "" | "?" | ".");
            if has_default {
                self.default_values.insert(tag.clone(), default.to_string());
            }
            if has_default || tag.ends_with(".entry_id") {
                self.auto_inserted_tags.insert(tag.clone());
            }

            // A form code rather than a flag: anything above zero means "inserted
            //  automatically", except 8, which the build excludes
            let auto = data.get("ADIT auto insert").trim();
            if !auto.is_empty() && auto.bytes().all(|b| b.is_ascii_digit()) {
                if let Ok(code) = auto.parse::<u64>() {
                    if code != 0 && code != 8 {
                        self.auto_inserted_tags.insert(tag.clone());
                    }
                }
            }
        }
    }

    /// Load the value type regular expressions.
    fn load_data_types(&mut self) {
        for row in csv::read(internal::DATA_TYPES) {
            if row.is_empty() {
                continue;
            }
            let name = row[0].clone();
            let definition = row.get(1).cloned().unwrap_or_default();
            if let Ok(regex) = crate::pyregex::compile_full(&definition) {
                self.compiled_types.insert(name.clone(), regex);
            }
            self.data_types.insert(name, format!("^{}$", definition));
        }
    }

    /// The compiled regular expression of a value type, anchored as `re.match('^...$')` is.
    pub(crate) fn type_regex(&self, type_name: &str) -> Option<&Regex> {
        self.compiled_types.get(type_name)
    }

    /// Build the enumeration value lists by joining adit_enum_hdr (enumeration id -> tag) with
    /// adit_enum_dtl (id -> values).
    fn build_enumerations(&mut self, enum_hdr_text: &str, enum_dtl_text: &str) {
        let skip = |eid: Option<&String>| matches!(eid.map(String::as_str), None | Some("TBL_BEGIN" | "TBL_END" | "?"));
        let mut id_to_tag: HashMap<String, Option<String>> = HashMap::new();
        for row in csv::dicts(enum_hdr_text) {
            let eid = row.get("Enumeration ID");
            if skip(eid) {
                continue;
            }
            id_to_tag.insert(eid.unwrap().clone(), row.get("Tag").cloned());
        }

        for row in csv::dicts(enum_dtl_text) {
            let eid = row.get("Enumeration ID");
            if skip(eid) {
                continue;
            }
            let tag = match id_to_tag.get(eid.unwrap()) {
                Some(Some(tag)) if !tag.is_empty() => tag,
                _ => continue,
            };
            let value = row.get("Enum value").map(|v| v.trim()).unwrap_or("");
            if value.is_empty() {
                continue;
            }
            let tag_lower = pystr::lower(tag);
            if !self.enumerations.contains_key(&tag_lower) {
                let closed = self.get(&tag_lower).map(|data| data.get("Item enumeration closed") == "Y").unwrap_or(false);
                self.enumerations.insert(tag_lower.clone(), Enumeration { closed, ..Default::default() });
            }
            let enumeration = self.enumerations.get_mut(&tag_lower).unwrap();
            enumeration.values.insert(value.to_string());
            enumeration.folded.insert(pystr::lower(value), value.to_string());
        }
    }

    /// Load the saveframe category table from adit_cat_grp_o.csv.
    fn parse_saveframe_categories(&mut self, cat_grp_text: &str) {
        let mut lowest: HashMap<String, i64> = HashMap::new();
        for (_, data) in &self.tags {
            let category = data.sf_category();
            let sequence = data.get("Dictionary sequence").trim();
            if category.is_empty() || sequence.is_empty() || !sequence.bytes().all(|b| b.is_ascii_digit()) {
                continue;
            }
            let Ok(value) = sequence.parse::<i64>() else { continue };
            let entry = lowest.entry(category.to_string()).or_insert(value);
            if value < *entry {
                *entry = value;
            }
        }

        let category_name = Regex::new(r"^[A-Za-z][A-Za-z0-9_]*\z").unwrap();
        let normalized = pystr::splitlines(cat_grp_text).join("\n");
        for row in csv::dicts(&normalized) {
            let field = |name: &str| row.get(name).map(|v| v.trim().to_string()).unwrap_or_default();
            let category = field("saveframe_category");
            if !category_name.is_match(&category) {
                continue;
            }
            let replicable = pystr::lower(&field("ADIT replicable")).starts_with('y');
            self.saveframe_categories.insert(category.clone(), SaveframeCategory {
                flags: pystr::upper(&field("validateFlgs")),
                unique: !replicable,
                id: lowest.get(&category).copied(),
            });
        }
    }

    /// Load the conditional mandatory rules from adit_tag_validation.csv.
    fn parse_conditional_rules(&mut self, tag_validation_text: &str) {
        let normalized = pystr::splitlines(tag_validation_text).join("\n");
        for row in csv::dicts(&normalized) {
            let field = |name: &str| row.get(name).map(|v| v.trim().to_string()).unwrap_or_default();
            let tag = field("Tag");
            if !tag.starts_with('_') {
                continue;
            }
            self.conditional_rules.entry(pystr::lower(&tag)).or_default().push(ConditionalRule {
                control_category: field("Control Sf category"),
                control_tag: field("Control tag"),
                value: field("Flag Value"),
                category: field("Sf category"),
                flags: pystr::upper(&field("validateFlgs")),
            });
        }
    }

    /// The position of a named validation profile in a dictionary flag string.
    pub fn profile_index(profile: Option<&str>) -> Result<usize> {
        let profile = profile.unwrap_or(definitions::DEFAULT_VALIDATION_PROFILE);
        definitions::VALIDATION_PROFILES.iter().position(|p| *p == profile).ok_or_else(|| {
            Error::value(format!("Unknown validation profile '{}'. Known profiles: {}", profile,
                                 definitions::VALIDATION_PROFILES.join(", ")))
        })
    }

    /// The mandatory codes for one view of the dictionary. Codes are:
    ///
    /// * `I` invalid - the tag may not appear here at all
    /// * `O` optional
    /// * `M` mandatory - the tag must be present
    /// * `V` value-mandatory - present *and* non-null
    /// * `C` conditional - mandatory if its saveframe is present
    /// * `R` value-conditional - non-null if its saveframe is present
    ///
    /// `M` and `V` are demoted to `C` and `R` for a tag whose saveframe category is itself
    /// optional, as the dictionary build does.
    pub fn validation_profile(&self, profile: Option<&str>) -> Result<Arc<Profile>> {
        let profile = profile.unwrap_or(definitions::DEFAULT_VALIDATION_PROFILE);
        if let Some(found) = self.profiles.read().unwrap().get(profile) {
            return Ok(found.clone());
        }
        let index = Schema::profile_index(Some(profile))?;
        let flag = |flags: &str| -> char {
            let code = flags.chars().nth(index).map(|c| c.to_ascii_uppercase()).filter(|c| !pystr::is_space(*c));
            code.unwrap_or('O')
        };

        let categories: HashMap<String, char> = self.saveframe_categories.iter()
            .map(|(category, data)| (category.clone(), flag(&data.flags))).collect();
        let tags: HashMap<String, char> = self.tags.iter().map(|(tag, data)| {
            let mut code = flag(&data.validate_flags);
            if matches!(code, 'M' | 'V') && categories.get(data.sf_category()) == Some(&'O') {
                code = if code == 'M' { 'C' } else { 'R' };
            }
            (tag.clone(), code)
        }).collect();

        let result = Arc::new(Profile { tags, categories });
        self.profiles.write().unwrap().entry(profile.to_string()).or_insert(result.clone());
        Ok(self.profiles.read().unwrap()[profile].clone())
    }

    /// How the schema can be created, as PyNMR-STAR's `repr()` described it.
    pub fn repr(&self) -> String {
        match &self.schema_file {
            None => format!("pynmrstar.Schema(version='{}')", self.version),
            Some(file) => format!("pynmrstar.Schema(schema_file='{}') version {}", file, self.version),
        }
    }

    /// Add a tag to the schema. Provide the full tag (`_Entry_interview.Sf_category`), its type
    /// (`INTEGER`, `FLOAT`, `CHAR(len)`, `VARCHAR(len)`, `TEXT`), whether null values are
    /// allowed, the category of its saveframe, whether it is a loop tag, and optionally the tag
    /// to order it after.
    pub fn add_tag(&mut self, tag: &str, tag_type: &str, null_allowed: bool, sf_category: &str, loop_flag: bool,
                   after: Option<&str>) -> Result<()> {
        let tag = if tag.starts_with('_') { tag.to_string() } else { format!("_{}", tag) };
        if self.contains(&pystr::lower(&tag)) {
            return Err(Error::value(format!("Cannot add a tag to the schema that is already in the schema: {}", tag)));
        }

        let mut tag_type = pystr::upper(tag_type);
        if !["INTEGER", "FLOAT", "TEXT", "DATETIME year to day"].contains(&tag_type.as_str()) {
            if tag_type.starts_with("CHAR(") || tag_type.starts_with("VARCHAR(") {
                let open = tag_type.find('(').unwrap();
                let close = tag_type.find(')').ok_or_else(|| Error::value("Illegal length specified in tag type."))?;
                let length = &tag_type[open + 1..close.max(open + 1)];
                match parse_int(length) {
                    Some(n) if n != 0 => {}
                    _ => return Err(Error::value(format!("Illegal length specified in tag type: {}", length))),
                }
                tag_type.truncate(close + 1);
            } else {
                return Err(Error::value("The tag type you provided is not valid. Please use a type as specified in \
                                         the help for this method."));
            }
        }
        if sf_category.is_empty() {
            return Err(Error::value("Please provide the sf_category of the parent saveframe."));
        }

        let mut position = self.schema_order.len();
        match after {
            Some(after) => {
                position = match self.schema_order.iter().position(|t| t == after) {
                    Some(at) => at + 1,
                    None => {
                        let lower = pystr::lower(after);
                        self.schema_order.iter().position(|t| pystr::lower(t) == lower).map(|at| at + 1)
                            .ok_or_else(|| Error::value(
                                "The tag you specified to insert this tag after does not exist in the schema."))?
                    }
                };
            }
            None => {
                let search = format_category(&pystr::lower(&tag));
                for (at, existing) in self.schema_order.iter().enumerate() {
                    if pystr::lower(existing).starts_with(&search) {
                        position = at + 1;
                    }
                }
            }
        }

        self.schema_order.insert(position, tag.clone());
        // PyNMR-STAR inserts this, not the category, at the tag's position; kept as it was
        let category_position = position.min(self.category_order.len());
        self.category_order.insert(category_position, format!("_{}", format_tag(&tag)));
        self.rebuild_order_index();

        // The dictionary sequence is the next free one from the tag's position
        let used: HashSet<i64> = self.tags.iter()
            .filter_map(|(_, data)| data.get("Dictionary sequence").trim().parse::<f64>().ok())
            .filter(|f| f.fract() == 0.0).map(|f| f as i64).collect();
        let mut sequence = (position as i64 - 1) * 10;
        while used.contains(&sequence) {
            sequence += 1;
        }

        let mut data = TagData {
            row: vec![String::new(); self.headers.len()],
            columns: self.columns.clone(),
            nullable: null_allowed,
            validate_flags: String::new(),
        };
        data.set("Data Type", &tag_type);
        data.set("Loopflag", if loop_flag { "Y" } else { "N" });
        data.set("Nullable", if null_allowed { "" } else { "NOT NULL" });
        data.set("public", "Y");
        data.set("SFCategory", sf_category);
        data.set("Tag", &tag);
        data.set("Dictionary sequence", &sequence.to_string());
        self.insert_tag(pystr::lower(&tag), data);
        self.profiles.write().unwrap().clear();
        Ok(())
    }

    /// Convert a value from text to the type the dictionary declares for its tag: an integer, a
    /// decimal, or a date. Text tags are unchanged, and null values become `None`.
    pub fn convert_tag(&self, tag: &str, value: &Value) -> Result<Value> {
        let full_tag = match self.get_tag(tag) {
            Some(data) => data,
            None => {
                if tag != "_internal.use" {
                    warn!("Couldn't convert tag data type because it is not in the dictionary: {}", tag);
                }
                return Ok(value.clone());
            }
        };
        if value.is_null_value() {
            return Ok(Value::Null);
        }
        let value_type = full_tag.get("Data Type");
        if value_type.contains("CHAR") || value_type.contains("TEXT") {
            return Ok(value.clone());
        }
        if value_type.contains("INTEGER") {
            return value.py_int().map(Value::Int).map_err(|_| Error::value(format!(
                "Could not parse the file because a value that should be an INTEGER is not. Either do not specify \
                 convert_data_types or fix the file. Tag: '{}'.", tag)));
        }
        if value_type.contains("FLOAT") {
            let decimal = match value {
                Value::Str(s) => Decimal::parse(s),
                Value::Int(i) => Some(Decimal::from_i64(*i)),
                Value::Bool(b) => Some(Decimal::from_i64(*b as i64)),
                Value::Float(f) => Some(Decimal::from_f64(*f)),
                Value::Decimal(d) => Some(d.clone()),
                Value::Null | Value::Date(_) => None,
            };
            return decimal.map(Value::Decimal).ok_or_else(|| Error::value(format!(
                "Could not parse the file because a value that should be a FLOAT is not. Either do not specify \
                 convert_data_types or fix the file. Tag: '{}'.", tag)));
        }
        if value_type.contains("DATETIME year to day") {
            let date = value.as_str().and_then(|s| {
                let fields: Vec<Option<i64>> = s.split('-').map(parse_int).collect();
                match fields.as_slice() {
                    [Some(year), Some(month), Some(day)] => Date::new(
                        i32::try_from(*year).ok()?, u32::try_from(*month).ok()?, u32::try_from(*day).ok()?),
                    _ => None,
                }
            });
            return date.map(Value::Date).ok_or_else(|| Error::value(format!(
                "Could not parse the file because a value that should be a DATETIME is not. Please do not specify \
                 convert_data_types or fix the file. Tag: '{}'.", tag)));
        }
        Ok(value.clone())
    }

    /// Every tag in the schema, or those containing `search`, as a table.
    pub fn string_representation(&self, search: Option<&str>) -> String {
        let tag_width = self.schema_order.iter().map(|x| pystr::char_len(format_tag(x))).max().unwrap_or(0);
        let column_width = |field: &dyn Fn(&TagData) -> String| {
            self.tags.iter().map(|(_, data)| pystr::char_len(&field(data))).max().unwrap_or(0)
        };
        let nullable = |data: &TagData| if data.nullable { "True".to_string() } else { "False".to_string() };
        let lengths = [
            tag_width,
            column_width(&|data| data.get("Data Type").to_string()),
            column_width(&nullable),
            column_width(&|data| data.get("SFCategory").to_string()),
            column_width(&|data| data.tag().to_string()),
        ];
        let source = self.schema_file.clone().unwrap_or_else(|| "the NMR-STAR dictionary distribution".to_string());
        let mut text = format!(
            "BMRB schema from: '{}' version '{}'\n\n  {:<w0$} {:<w1$} {:<w2$} {:<w3$} {}\n",
            source, self.version, "Tag_Prefix", "Tag", "Type", "Null_Allowed", "SF_Category",
            w0 = lengths[0], w1 = lengths[1].saturating_sub(6), w2 = lengths[2], w3 = lengths[3]);

        let mut last_category = String::new();
        for tag in &self.schema_order {
            if let Some(search) = search {
                if !search.is_empty() && !tag.contains(search) {
                    continue;
                }
            }
            if let Some(data) = self.get_tag(tag) {
                let category = format_category(tag);
                if category != last_category {
                    text.push_str(&format!("\n{:<30}\n", category));
                    last_category = category;
                }
                text.push_str(&format!("  {:<w0$} {:<w1$} {:<w2$}  {:<w3$}\n", format_tag(tag), data.get("Data Type"),
                                       nullable(data), data.get("SFCategory"),
                                       w0 = lengths[0], w1 = lengths[1], w2 = lengths[2], w3 = lengths[3]));
            }
        }
        text
    }

    /// Check that a value is of the type its tag should have. Returns the problems found.
    pub fn val_type(&self, tag: &str, value: &Value, category: Option<&str>) -> Vec<String> {
        let full_tag = match self.get_tag(tag) {
            Some(data) => data,
            None => return vec![format!("Tag '{}' not found in schema.", tag)],
        };

        let mut is_none = value.is_none();
        // Apply the conversion table, for a value of the type of one of its keys (Python's
        //  isinstance(value, type(key)), under which a boolean is an integer)
        let mut converted = value.clone();
        if !crate::definitions::str_conversion_is_default() || value.is_none() {
            let table = crate::definitions::str_conversion();
            let same_type = |key: &Value| std::mem::discriminant(key) == std::mem::discriminant(value)
                || matches!((key, value), (Value::Int(_), Value::Bool(_)));
            if table.iter().any(|(key, _)| key == value) && table.iter().any(|(key, _)| same_type(key)) {
                converted = table.iter().find(|(key, _)| key == value).unwrap().1.clone();
            }
        }
        let value = converted.to_py_string().into_owned();
        if crate::definitions::is_null_str(&value) {
            is_none = true;
        }

        let bmrb_type = full_tag.get("BMRB data type");
        let val_type = full_tag.get("Data Type");
        let allowed_category = full_tag.get("SFCategory");
        let capitalized_tag = full_tag.tag();

        if let Some(category) = category {
            if category != allowed_category {
                return vec![format!("The tag '{}' in category '{}' should be in category '{}'.",
                                    capitalized_tag, category, allowed_category)];
            }
        }

        if is_none {
            if !full_tag.nullable {
                return vec![format!("Value cannot be NULL but is: {}':'{}'.", capitalized_tag, value)];
            }
            return Vec::new();
        }

        if val_type.contains("CHAR") {
            let length = val_type.find('(').zip(val_type.find(')'))
                .and_then(|(open, close)| parse_int(&val_type[open + 1..close]));
            if let Some(length) = length {
                let actual = pystr::char_len(&value);
                if actual as i64 > length {
                    return vec![format!("Length of '{}' is too long for '{}': '{}':'{}'.",
                                        actual, val_type, capitalized_tag, value)];
                }
            }
        }

        if let Some(regex) = self.type_regex(bmrb_type) {
            if !regex.is_match(&value) {
                return vec![format!("Value does not match specification: '{}':'{}'.\n     Type specified: {}\n     \
                                     Regular expression for type: '{}'",
                                    capitalized_tag, value, bmrb_type, self.data_types[bmrb_type])];
            }
        }

        if bmrb_type.starts_with("yyyy-mm-dd") && !is_valid_date(&value) {
            return vec![format!("Value is not a valid date: '{}':'{}'.", capitalized_tag, value)];
        }

        if let Some(enumeration) = self.enumerations.get(&pystr::lower(tag)) {
            if enumeration.closed && !enumeration.values.contains(&value) {
                if let Some(capitalized) = enumeration.folded.get(&pystr::lower(&value)) {
                    return vec![format!("Value '{}' of tag '{}' is improperly capitalized but otherwise valid. \
                                         Should be '{}'.", value, capitalized_tag, capitalized)];
                }
                return vec![format!("Value '{}' is not in the closed enumeration for tag '{}'.", value, capitalized_tag)];
            }
        }

        if tag != capitalized_tag {
            return vec![format!("The tag '{}' is improperly capitalized but otherwise valid. Should be '{}'.",
                                tag, capitalized_tag)];
        }
        Vec::new()
    }

    /// The order a tag sorts in: its position in the dictionary or, for a tag the dictionary
    /// does not have, an arbitrary but stable position after every tag it does.
    pub fn tag_key(&self, tag: &str) -> TagKey {
        match self.order_index.get(tag) {
            Some(&position) => position as TagKey,
            None => self.schema_order.len() as TagKey + stable_hash(tag) as TagKey,
        }
    }
}

impl fmt::Display for Schema {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.string_representation(None))
    }
}
