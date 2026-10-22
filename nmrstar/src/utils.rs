//! Helper functions.

use std::sync::OnceLock;

use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::quoting::{quote_str, Converter};
use crate::schema::Schema;
use crate::value::Value;

/// Add a `_` to the front of a tag (if not present) and strip anything from the `.` on: the
/// category of a tag.
pub fn format_category(tag: &str) -> String {
    if tag.is_empty() {
        return String::new();
    }
    let category = match tag.find('.') {
        Some(dot) => &tag[..dot],
        None => tag,
    };
    if tag.starts_with('_') {
        category.to_string()
    } else {
        format!("_{}", category)
    }
}

/// Strip anything up to and including the first `.`: the name of a tag without its category.
pub fn format_tag(tag: &str) -> &str {
    match tag.find('.') {
        Some(dot) => &tag[dot + 1..],
        None => tag,
    }
}

/// The lowercase name of a tag without its category.
pub fn format_tag_lc(tag: &str) -> String {
    format_tag(&crate::pystr::lower(tag)).to_string()
}

/// Quote a value as it must be written in NMR-STAR. Don't quote values you set: they would be
/// written with the quotes as part of the value.
///
/// `quote_value("e. coli")` is `'e. coli'`, while `quote_value("\"e. coli\"")` is
/// `'"e. coli"'`. The conversion table of [`crate::definitions::str_conversion`] applies.
pub fn quote_value(value: &Value) -> Result<String> {
    let converter = Converter::new();
    let text = converter.convert_plain(value);
    if text.is_empty() {
        return Err(Error::value(
            "Empty strings are not allowed as values. Use the None singleton, or '.' to represent null values."));
    }
    Ok(quote_str(&text))
}

/// The schema to use: the one given, or the default one, which is the dictionary packaged with
/// the library (loaded once, and never from the network).
pub fn get_schema(schema: Option<&Schema>) -> &Schema {
    static DEFAULT: OnceLock<Schema> = OnceLock::new();
    match schema {
        Some(schema) => schema,
        None => DEFAULT.get_or_init(|| Schema::new().expect("the packaged dictionary is readable")),
    }
}

/// The differences between two entries, one per line. Non-equal entries are always detected,
/// but the specific differences reported depend on the order of the entries.
pub fn diff(entry1: &Entry, entry2: &Entry) -> String {
    let diffs = entry1.compare(entry2);
    if diffs.is_empty() {
        return "Identical entries.\n".to_string();
    }
    diffs.iter().map(|difference| format!("{}\n", difference)).collect()
}

/// A validation report of an entry.
pub fn validate(entry: &Entry, schema: Option<&Schema>) -> String {
    let validation = entry.validate(true, schema, true);
    if validation.is_empty() {
        return "No problems found during validation.\n".to_string();
    }
    validation.iter().enumerate().map(|(pos, error)| format!("{}: {}\n", pos + 1, error)).collect()
}

/// Every entry in the BMRB database: the macromolecule database, or with `metabolomics` the
/// metabolomics database. The entries are fetched one at a time as the iterator is advanced.
pub fn iter_entries(metabolomics: bool) -> Result<impl Iterator<Item = Result<Entry>>> {
    let ids = crate::internal::list_entries(metabolomics)?;
    Ok(ids.into_iter().map(|id| Entry::from_database(&id)))
}
