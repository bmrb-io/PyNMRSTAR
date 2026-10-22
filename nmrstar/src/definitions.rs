//! NMR-STAR definitions and other library-wide settings.
//!
//! Like PyNMR-STAR's `definitions` module, a few of these can be changed at run time, and the
//! change applies to the whole program:
//!
//! * [`null_values`]: the values treated as null. By default `None`, `""`, `"."` and `"?"`.
//! * [`str_conversion`]: values which are written as some other text. By default `None` is
//!   written as `.`. Setting, for example, `(Value::Bool(true), "yes")` writes booleans as words.
//! * The URLs data is fetched from.
//!
//! As with Python, a conversion table may not hold both booleans and numbers, as `true == 1`.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{LazyLock, RwLock};

use crate::value::Value;

/// The base URL of the BMRB API.
pub const DEFAULT_API_URL: &str = "https://api.bmrb.io/v2";
/// The base URL of the BMRB FTP site, served over HTTPS.
pub const FTP_URL: &str = "https://bmrb.io/ftp/pub/bmrb";
/// Base location of the NMR-STAR dictionary distribution (the built files, not the source
/// spreadsheet). Only read when a [`crate::Schema`] is asked for the newest release, or for a
/// version that is neither packaged nor cached. Override it with the
/// `PYNMRSTAR_DICTIONARY_SOURCE` environment variable (a URL base or a local directory holding
/// the distribution files).
pub const DEFAULT_DICTIONARY_URL: &str =
    "https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/nmr-star-production/NMR-STAR/internal_106_distribution";
/// Where one specific release's distribution lives: each release is tagged `nmr-star-v<version>`
/// in the dictionary repository. `{version}` is replaced with the version.
pub const DEFAULT_DICTIONARY_RELEASE_URL: &str =
    "https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/nmr-star-v{version}/NMR-STAR/internal_106_distribution";
/// The distribution files a Schema is built from.
pub const DICTIONARY_FILES: [&str; 5] =
    ["xlschem_ann.csv", "adit_enum_hdr.csv", "adit_enum_dtl.csv", "adit_cat_grp_o.csv", "adit_tag_validation.csv"];
/// The dictionary carries one set of validation flags per "view", in this order. A flag string
/// is indexed by the position of the profile in this list. BMRB's annotators use `internal`; a
/// depositor checking a file against the public archive's requirements wants `public`.
pub const VALIDATION_PROFILES: [&str; 6] =
    ["public", "internal", "small_molecule", "small_molecule_struct", "metabolomics", "entry_completeness"];
/// The profile used when none is given.
pub const DEFAULT_VALIDATION_PROFILE: &str = "public";

/// Whether the null values have been changed from the defaults, which can then be checked
/// without taking the lock.
static CUSTOM_NULL_VALUES: AtomicBool = AtomicBool::new(false);
static NULL_VALUES: LazyLock<RwLock<Vec<Value>>> = LazyLock::new(|| RwLock::new(default_null_values()));
/// Whether the conversion table is the default one, `None -> "."`.
static CUSTOM_STR_CONVERSION: AtomicBool = AtomicBool::new(false);
static STR_CONVERSION: LazyLock<RwLock<Vec<(Value, Value)>>> =
    LazyLock::new(|| RwLock::new(default_str_conversion()));
static API_URL: LazyLock<RwLock<String>> = LazyLock::new(|| RwLock::new(DEFAULT_API_URL.to_string()));
static DICTIONARY_URL: LazyLock<RwLock<String>> =
    LazyLock::new(|| RwLock::new(DEFAULT_DICTIONARY_URL.to_string()));
static DICTIONARY_RELEASE_URL: LazyLock<RwLock<String>> =
    LazyLock::new(|| RwLock::new(DEFAULT_DICTIONARY_RELEASE_URL.to_string()));

fn default_null_values() -> Vec<Value> {
    vec![Value::from(""), Value::from("."), Value::from("?"), Value::Null]
}

fn default_str_conversion() -> Vec<(Value, Value)> {
    vec![(Value::Null, Value::from("."))]
}

/// The values which are treated as null.
pub fn null_values() -> Vec<Value> {
    NULL_VALUES.read().unwrap().clone()
}

/// Replace the values which are treated as null.
pub fn set_null_values(values: Vec<Value>) {
    let custom = values != default_null_values();
    *NULL_VALUES.write().unwrap() = values;
    CUSTOM_NULL_VALUES.store(custom, Ordering::SeqCst);
}

/// Restore the default null values.
pub fn reset_null_values() {
    set_null_values(default_null_values());
}

/// Whether a value is one of the null values (Python's `value in NULL_VALUES`).
pub fn is_null(value: &Value) -> bool {
    if !CUSTOM_NULL_VALUES.load(Ordering::Relaxed) {
        return match value {
            Value::Null => true,
            Value::Str(s) => s.is_empty() || s == "." || s == "?",
            _ => false,
        };
    }
    NULL_VALUES.read().unwrap().iter().any(|null| null == value)
}

/// Whether a text value is one of the null values.
pub fn is_null_str(value: &str) -> bool {
    if !CUSTOM_NULL_VALUES.load(Ordering::Relaxed) {
        return value.is_empty() || value == "." || value == "?";
    }
    NULL_VALUES.read().unwrap().iter().any(|null| null == value)
}

/// The table of values which are written as other text: the first of each pair is written as
/// the second.
pub fn str_conversion() -> Vec<(Value, Value)> {
    STR_CONVERSION.read().unwrap().clone()
}

/// Whether the conversion table is the default one, which only converts `None`.
pub(crate) fn str_conversion_is_default() -> bool {
    !CUSTOM_STR_CONVERSION.load(Ordering::Relaxed)
}

/// Replace the table of values which are written as other text.
pub fn set_str_conversion(table: Vec<(Value, Value)>) {
    let custom = table != default_str_conversion();
    *STR_CONVERSION.write().unwrap() = table;
    CUSTOM_STR_CONVERSION.store(custom, Ordering::SeqCst);
}

/// Restore the default conversion table.
pub fn reset_str_conversion() {
    set_str_conversion(default_str_conversion());
}

/// The base URL of the BMRB API.
pub fn api_url() -> String {
    API_URL.read().unwrap().clone()
}

pub fn set_api_url(url: impl Into<String>) {
    *API_URL.write().unwrap() = url.into();
}

/// The location of the newest dictionary distribution. See [`DEFAULT_DICTIONARY_URL`].
pub fn dictionary_url() -> String {
    DICTIONARY_URL.read().unwrap().clone()
}

pub fn set_dictionary_url(url: impl Into<String>) {
    *DICTIONARY_URL.write().unwrap() = url.into();
}

/// The location of one dictionary release, with `{version}` standing for its version. See
/// [`DEFAULT_DICTIONARY_RELEASE_URL`].
pub fn dictionary_release_url() -> String {
    DICTIONARY_RELEASE_URL.read().unwrap().clone()
}

pub fn set_dictionary_release_url(url: impl Into<String>) {
    *DICTIONARY_RELEASE_URL.write().unwrap() = url.into();
}
