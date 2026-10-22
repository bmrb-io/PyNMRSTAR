//! Ported from pynmrstar/unit_tests/test_schema.py.

mod common;

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use common::*;
use nmrstar::internal::{load_dictionary, packaged_dictionary_version};
use nmrstar::{definitions, Schema, Source, Value};

#[test]
fn test_schema() {
    let default = Schema::new().unwrap();
    let expected_headers = [
        "Dictionary sequence", "SFCategory", "ADIT category mandatory", "ADIT category view type",
        "ADIT super category ID", "ADIT super category", "ADIT category group ID",
        "ADIT category view name", "Tag", "BMRB current", "Query prompt", "Query interface",
        "SG Mandatory", "", "ADIT exists", "User full view", "Metabolomics", "Metabolites", "SENCI",
        "Fragment library", "Item enumerated", "Item enumeration closed", "Enum parent SFcategory",
        "Enum parent tag", "Derived enumeration mantable", "Derived enumeration",
        "ADIT item view name", "Data Type", "Nullable", "Non-public", "ManDBTableName",
        "ManDBColumnName", "Row Index Key", "Saveframe ID tag", "Source Key", "Table Primary Key",
        "Foreign Key Group", "Foreign Table", "Foreign Column", "Secondary index", "Sub category",
        "Units", "Loopflag", "Seq", "Adit initial rows", "Enumeration ties",
        "Mandatory code overides", "Overide value", "Overide view value", "ADIT auto insert",
        "Example", "Prompt", "Interface", "bmrbPdbMatchID", "bmrbPdbTransFunc", "STAR flag",
        "DB flag", "SfNamelFlg", "Sf category flag", "Sf pointer", "Natural primary key",
        "Natural foreign key", "obsolete tag", "Parent tag", "public", "internal", "small molecule",
        "small molecule", "metabolomics", "Entry completeness", "Overide public", "internal",
        "small molecule", "small molecule", "metabolomic", "metabolomic", "default value",
        "Adit form code", "Tag category", "Tag field", "Local key", "Datum count flag",
        "NEF equivalent", "mmCIF equivalent", "Meta data", "Tag delete", "BMRB data type",
        "STAR vs Curated DB", "Key group", "Reference table", "Reference column",
        "Dictionary description", "variableTypeMatch", "entryIdFlg", "outputMapExistsFlg",
        "lclSfIdFlg", "Met ADIT category view name", "Met Example", "Met Prompt", "Met Description",
        "SM Struct ADIT-NMR category view name", "SM Struct Example", "SM Struct Prompt",
        "SM Struct Description", "Met default value", "SM default value"];
    assert_eq!(default.headers, expected_headers);

    assert!(default.val_type("_Entity.ID", &Value::Int(1), None).is_empty());
    assert_eq!(default.val_type("_Entity.ID", &"test".into(), None), vec![
        "Value does not match specification: '_Entity.ID':'test'.\n     Type specified: int\n     \
         Regular expression for type: '^(?:-?[0-9]*)?$'"]);
    assert!(default.val_type("_Atom_chem_shift.Val", &Value::Float(1.2), None).is_empty());
    assert_eq!(default.val_type("_Atom_chem_shift.Val", &"invalid".into(), None), vec![
        "Value does not match specification: '_Atom_chem_shift.Val':'invalid'.\n     Type specified: float\n     \
         Regular expression for type: '^(?:-?[0-9]*\\.?[0-9]+(?:[eE][-+]?[0-9]+)?)?$'"]);
    assert_eq!(default.val_type("_Entry.ID", &"this should be far too long - much too long".into(), None), vec![
        "Length of '43' is too long for 'CHAR(12)': '_Entry.ID':'this should be far too long - much too long'."]);
}

#[test]
fn test_dates() {
    let default = Schema::new().unwrap();
    assert!(default.val_type("_Release.Date", &"2006-09-07".into(), None).is_empty());
    // The type pattern allows these, but they are not dates
    for bad_date in ["10-11-67", "1066-13-32", "2023-02-31"] {
        assert_eq!(default.val_type("_Release.Date", &bad_date.into(), None),
                   vec![format!("Value is not a valid date: '_Release.Date':'{}'.", bad_date)]);
    }
}

#[test]
fn test_enumerations() {
    let default = Schema::new().unwrap();
    assert!(!default.enumerations.is_empty());

    let subtype = &default.enumerations["_entry.experimental_method_subtype"];
    assert!(subtype.closed);
    assert!(subtype.values.contains("solution"));

    assert!(default.val_type("_Entry.Experimental_method_subtype", &"solution".into(), None).is_empty());
    assert_eq!(default.val_type("_Entry.Experimental_method_subtype", &"SOLUTION".into(), None), vec![
        "Value 'SOLUTION' of tag '_Entry.Experimental_method_subtype' is improperly capitalized but otherwise valid. \
         Should be 'solution'."]);
    assert_eq!(default.val_type("_Entry.Experimental_method_subtype", &"not_a_real_subtype".into(), None), vec![
        "Value 'not_a_real_subtype' is not in the closed enumeration for tag '_Entry.Experimental_method_subtype'."]);

    // Open enumerations are advisory only
    let db_code = &default.enumerations["_assembly_db_link.database_code"];
    assert!(!db_code.closed);
    assert!(default.val_type("_Assembly_db_link.Database_code", &"NOT_A_REAL_DATABASE".into(), None).is_empty());

    let comp_type = &default.enumerations["_chem_comp.type"];
    assert!(comp_type.values.contains("D-SACCHARIDE 1,4 AND 1,4 LINKING"));
    assert!(!comp_type.values.iter().any(|v| v.contains('$')));
    assert!(default.val_type("_Chem_comp.Type", &"D-SACCHARIDE 1,4 AND 1,4 LINKING".into(), None).is_empty());
}

#[test]
fn test_validation_profiles() {
    let default = Schema::new().unwrap();
    assert!(!default.saveframe_categories.is_empty());
    assert!(default.saveframe_categories.contains_key("entry_information"));

    let internal = default.validation_profile(Some("internal")).unwrap();
    let public = default.validation_profile(Some("public")).unwrap();

    assert_eq!(internal.tags.len(), default.len());
    assert_eq!(internal.categories.len(), default.saveframe_categories.len());
    assert!(internal.tags.values().all(|c| "IOMVCR".contains(*c)));
    assert!(internal.categories.values().all(|c| "IOMVCR".contains(*c)));

    assert_eq!(internal.categories["entry_information"], 'M');
    assert_eq!(internal.tags["_entry.sf_category"], 'V');

    assert_ne!(internal.tags, public.tags);

    // Demotion in an optional category
    assert_eq!(internal.categories["study_list"], 'O');
    let study_codes: HashSet<char> = default.tags().filter(|(_, d)| d.get("SFCategory") == "study_list")
        .map(|(t, _)| internal.tags[t]).collect();
    assert!(study_codes.contains(&'C'));
    assert!(!study_codes.contains(&'M') && !study_codes.contains(&'V'));

    // Only real categories are loaded
    assert!(default.saveframe_categories.keys().all(|c| c.chars().next().unwrap().is_alphabetic()));

    // The profile is memoized, and unknown profiles are rejected
    assert!(Arc::ptr_eq(&default.validation_profile(Some("internal")).unwrap(), &internal));
    assert_value_error(default.validation_profile(Some("no_such_profile")));
}

#[test]
fn test_conditional_rules() {
    let default = Schema::new().unwrap();
    assert!(!default.conditional_rules.is_empty());

    let rules = &default.conditional_rules["_citation.journal_abbrev"];
    let journal: Vec<_> = rules.iter().filter(|r| r.value == "journal").collect();
    assert_eq!(journal.len(), 1);
    assert_eq!(journal[0].control_tag, "_Citation.Type");
    assert_eq!(journal[0].control_category, "citations");
    assert!(rules.iter().all(|r| !r.flags.is_empty()));
}

#[test]
fn test_relationships() {
    let default = Schema::new().unwrap();
    assert_eq!(default.parent_tags["_sample_component.entity_label"], "_Entity.Sf_framecode");
    assert_eq!(default.parent_tags["_entity_comp_index.entry_id"], "_Entity.Entry_ID");
    assert_eq!(default.parent_tags["_entity.entry_id"], "_Entry.ID");

    assert!(default.parent_tags.keys().all(|t| default.contains(t)));
    assert!(default.parent_tags.values().all(|t| default.contains(&t.to_lowercase())));

    assert!(default.local_id_tags.contains("_sample.id"));
    assert!(default.local_id_tags.contains("_sample_component.sample_id"));
    assert!(!default.local_id_tags.contains("_entry.id"));
    assert!(!default.local_id_tags.contains("_sample.entry_id"));
}

/// Points the dictionary source and cache at throwaway locations until dropped, holding the
/// lock on process-wide state meanwhile.
struct Isolated {
    cache: tempfile::TempDir,
    saved: Vec<(&'static str, Option<String>)>,
    _guard: std::sync::MutexGuard<'static, ()>,
}

impl Isolated {
    fn new(source: Option<&str>) -> Isolated {
        let guard = lock_global_state();
        let saved = ["XDG_CACHE_HOME", "PYNMRSTAR_DICTIONARY_SOURCE"].into_iter()
            .map(|key| (key, std::env::var(key).ok())).collect();
        let cache = tempfile::Builder::new().prefix("pynmrstar-cache-test-").tempdir().unwrap();
        std::env::set_var("XDG_CACHE_HOME", cache.path());
        match source {
            Some(source) => std::env::set_var("PYNMRSTAR_DICTIONARY_SOURCE", source),
            None => std::env::remove_var("PYNMRSTAR_DICTIONARY_SOURCE"),
        }
        Isolated { cache, saved, _guard: guard }
    }

    /// The cache root.
    fn root(&self) -> PathBuf {
        self.cache.path().join("pynmrstar")
    }
}

impl Drop for Isolated {
    fn drop(&mut self) {
        for (key, value) in &self.saved {
            match value {
                Some(value) => std::env::set_var(key, value),
                None => std::env::remove_var(key),
            }
        }
        definitions::set_dictionary_url(definitions::DEFAULT_DICTIONARY_URL);
        definitions::set_dictionary_release_url(definitions::DEFAULT_DICTIONARY_RELEASE_URL);
    }
}

fn sorted_listing(directory: &Path) -> Vec<String> {
    let mut names: Vec<String> = fs::read_dir(directory).unwrap().map(|e| e.unwrap().file_name().into_string().unwrap()).collect();
    names.sort();
    names
}

fn sorted_files() -> Vec<String> {
    let mut names: Vec<String> = definitions::DICTIONARY_FILES.iter().map(|s| s.to_string()).collect();
    names.sort();
    names
}

#[test]
fn test_default_dictionary_is_packaged() {
    // The default never touches the network or the cache, even with an unreachable source
    let isolated = Isolated::new(Some("http://invalid.invalid/none"));
    let (files, version) = load_dictionary(None, None).unwrap();
    assert_eq!(version, packaged_dictionary_version());
    let mut names: Vec<String> = files.keys().cloned().collect();
    names.sort();
    assert_eq!(names, sorted_files());
    assert!(!isolated.root().exists());

    let schema = Schema::new().unwrap();
    assert_eq!(schema.version, packaged_dictionary_version());
    assert!(!schema.enumerations.is_empty());
    assert_eq!(schema.repr(), format!("pynmrstar.Schema(version='{}')", schema.version));
    assert!(!isolated.root().exists());

    // Asking for the packaged version by number does not go anywhere either
    assert_eq!(Schema::from_version(&schema.version).unwrap().version, schema.version);
}

#[test]
fn test_latest_dictionary_is_downloaded_and_cached() {
    let isolated = Isolated::new(Some(reference_files().to_str().unwrap()));
    let (files, version) = load_dictionary(Some("latest"), None).unwrap();
    assert_eq!(version, packaged_dictionary_version());
    // Cached complete, with nothing left over from writing it
    assert_eq!(sorted_listing(&isolated.root()), vec![version.clone()]);
    assert_eq!(sorted_listing(&isolated.root().join(&version)), sorted_files());
    for (name, text) in &files {
        assert_eq!(&fs::read_to_string(isolated.root().join(&version).join(name)).unwrap(), text);
    }

    // Asking for the newest release when it cannot be fetched is an error
    std::env::set_var("PYNMRSTAR_DICTIONARY_SOURCE", "http://invalid.invalid/none");
    assert_value_error(load_dictionary(Some("latest"), None));
}

#[test]
fn test_specific_dictionary_version() {
    let isolated = Isolated::new(Some("http://invalid.invalid/none"));

    // Neither packaged, cached nor downloadable
    assert_value_error(Schema::from_version("3.2.15.0"));

    // Found in the cache without the network
    let cached = isolated.root().join("3.2.15.0");
    fs::create_dir_all(&cached).unwrap();
    for name in definitions::DICTIONARY_FILES {
        fs::copy(reference_files().join(name), cached.join(name)).unwrap();
    }
    assert_eq!(load_dictionary(Some("3.2.15.0"), None).unwrap().1, "3.2.15.0");

    // Only the newest release can be downloaded
    fs::remove_dir_all(&cached).unwrap();
    std::env::set_var("PYNMRSTAR_DICTIONARY_SOURCE", reference_files());
    assert_value_error(load_dictionary(Some("3.2.15.0"), None));
}

/// Write a copy of the packaged distribution, relabelled as `version`, to `directory`.
fn release(directory: &Path, version: &str) {
    fs::create_dir_all(directory).unwrap();
    for name in definitions::DICTIONARY_FILES {
        let mut text = fs::read_to_string(reference_files().join(name)).unwrap();
        if name == "xlschem_ann.csv" {
            text = text.replacen(&format!("TBL_BEGIN,,new,{},", packaged_dictionary_version()),
                                 &format!("TBL_BEGIN,,new,{},", version), 1);
        }
        fs::write(directory.join(name), text).unwrap();
    }
}

#[test]
fn test_tagged_dictionary_release() {
    let isolated = Isolated::new(None);

    // Stand-ins for the dictionary repository: one directory per tag, and one for the
    //  production branch
    let releases = tempfile::Builder::new().prefix("pynmrstar-releases-test-").tempdir().unwrap();
    let releases = releases.path().to_path_buf();
    definitions::set_dictionary_release_url(releases.join("nmr-star-v{version}").to_str().unwrap());
    definitions::set_dictionary_url(releases.join("production").to_str().unwrap());
    release(&releases.join("nmr-star-v3.2.15.0"), "3.2.15.0");
    release(&releases.join("production"), "3.2.16.0");

    // An older release is downloaded by its tag, and cached
    assert_eq!(load_dictionary(Some("3.2.15.0"), None).unwrap().1, "3.2.15.0");
    assert_eq!(sorted_listing(&isolated.root().join("3.2.15.0")), sorted_files());
    assert_eq!(Schema::from_version("3.2.15.0").unwrap().version, "3.2.15.0");

    // The newest release is found even before it is tagged
    assert_eq!(load_dictionary(Some("3.2.16.0"), None).unwrap().1, "3.2.16.0");

    // Neither tagged nor the newest
    assert_value_error(load_dictionary(Some("3.2.17.0"), None));

    // A tag that holds some other version is an error
    release(&releases.join("nmr-star-v3.2.18.0"), "3.2.15.1");
    assert_value_error(load_dictionary(Some("3.2.18.0"), None));

    // An explicit source is the only place looked
    release(&releases.join("nmr-star-v3.2.19.0"), "3.2.19.0");
    assert_value_error(load_dictionary(Some("3.2.19.0"), Some(releases.join("production").to_str().unwrap())));
    assert_eq!(load_dictionary(Some("3.2.19.0"), None).unwrap().1, "3.2.19.0");
}

#[test]
fn test_schema_file() {
    let _isolated = Isolated::new(Some("http://invalid.invalid/none"));

    // A directory holding a whole distribution
    let schema = Schema::from_file(reference_files(), None).unwrap();
    assert_eq!(schema.version, packaged_dictionary_version());
    assert!(!schema.enumerations.is_empty());
    assert!(!schema.saveframe_categories.is_empty());
    assert_value_error(Schema::from_file(reference_files(), Some("latest")));

    // A single tag table brings the rest of its own version along
    let schema = Schema::from_file(reference_files().join("xlschem_ann.csv"), None).unwrap();
    assert!(!schema.enumerations.is_empty());
    assert!(!schema.conditional_rules.is_empty());

    // A tag table of a version that is not available stands alone
    let text = fs::read_to_string(reference_files().join("xlschem_ann.csv")).unwrap()
        .replacen(&format!(",{},", packaged_dictionary_version()), ",9.9.9.9,", 1);
    let schema = assert_logs(|| Schema::from_file(Source::from(text.into_bytes()), None).unwrap());
    assert_eq!(schema.version, "9.9.9.9");
    assert!(!schema.is_empty());
    assert!(schema.enumerations.is_empty());
    assert!(schema.saveframe_categories.is_empty());
}
