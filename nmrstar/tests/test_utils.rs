//! Ported from pynmrstar/unit_tests/test_utils.py.

mod common;

use common::*;
use nmrstar::internal::read_text;
use nmrstar::utils::{format_category, format_tag, quote_value};
use nmrstar::{definitions, Entry, Source, Value};

#[test]
fn test_clean_val() {
    let _guard = lock_global_state();
    let quote = |s: &str| quote_value(&Value::from(s)).unwrap();
    assert_eq!(quote("single quote test"), "'single quote test'");
    assert_eq!(quote("double quote' test"), "\"double quote' test\"");
    assert_eq!(quote("loop_"), "'loop_'");
    assert_eq!(quote("#comment"), "'#comment'");
    assert_eq!(quote("_tag"), "'_tag'");
    assert_eq!(quote("simple"), "simple");
    assert_eq!(quote("  "), "'  '");
    assert_eq!(quote("\nnewline\n"), "\nnewline\n");
    assert_eq!(quote_value(&Value::Null).unwrap(), ".");
    assert_value_error(quote_value(&Value::from("")));

    definitions::set_str_conversion(vec![(Value::from("loop_"), Value::from("noloop_"))]);
    let converted = quote("loop_");
    definitions::reset_str_conversion();
    assert_eq!(converted, "noloop_");
}

#[test]
fn test_format_category() {
    assert_eq!(format_category("test"), "_test");
    assert_eq!(format_category("_test"), "_test");
    assert_eq!(format_category("test.test"), "_test");
}

#[test]
fn test_format_tag() {
    assert_eq!(format_tag("test"), "test");
    assert_eq!(format_tag("_test.test"), "test");
    assert_eq!(format_tag("test.test"), "test");
}

#[test]
fn test_interpret_file() {
    let local_version = std::fs::read_to_string(sample_file_location()).unwrap();

    // Local files, by path and as data read from them
    assert_eq!(read_text(&Source::from(sample_file_location())).unwrap(), local_version);
    let file = std::fs::File::open(sample_file_location()).unwrap();
    assert_eq!(read_text(&Source::from_reader(file).unwrap()).unwrap(), local_version);
    let file = std::fs::File::open(sample("bmr15000_3.str.gz")).unwrap();
    assert_eq!(read_text(&Source::from_reader(file).unwrap()).unwrap(), local_version);

    // Over HTTPS
    let database_entry = database_entry();
    let entry_url = "https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr15000/bmr15000_3.str";
    assert_eq!(Entry::from_str(&read_text(&Source::from(entry_url)).unwrap()).unwrap(), database_entry);
    let raw_api_url = "https://api.bmrb.io/v2/entry/15000?format=rawnmrstar";
    assert_eq!(Entry::from_str(&read_text(&Source::from(raw_api_url)).unwrap()).unwrap(), database_entry);
}
