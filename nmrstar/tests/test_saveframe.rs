//! Ported from pynmrstar/unit_tests/test_saveframe.py.

mod common;

use std::path::Path;

use common::*;
use nmrstar::{definitions, json::Json, Data, FileFormat, Loop, Saveframe, Source, Value};

fn sample_saveframe_location() -> std::path::PathBuf {
    sample("saveframe.txt")
}

fn frame() -> Saveframe {
    file_entry().frame_list[0].clone()
}

#[test]
fn test_odd_strings() {
    // The naughty strings are a submodule, which is not always checked out
    if std::env::var("GITHUB_WORKFLOW").is_ok() {
        return;
    }
    let path = unit_test_path("naughty-strings/blns.json");
    let Ok(text) = std::fs::read_to_string(&path) else { return };
    let odd_strings = Json::parse(&text).unwrap();

    let mut saveframe = Saveframe::from_scratch("test", Some("citations"));
    for (x, string) in odd_strings.as_array().unwrap().iter().enumerate() {
        let string = string.as_str().unwrap();
        if string.is_empty() {
            continue;
        }
        // Use the string as the tag name too if possible; otherwise use a number for the name
        match saveframe.add_tag_with(string, string, true, false, None) {
            Ok(()) => {}
            Err(error) if error.is_value_error() => saveframe.add_tag(&x.to_string(), string).unwrap(),
            Err(error) => panic!("{}", error),
        }
    }
    assert_eq!(saveframe, Saveframe::from_str(&saveframe.to_star().unwrap()).unwrap());
}

#[test]
fn test_from_file_path_support() {
    assert_eq!(Saveframe::from_file(Path::new(&sample_saveframe_location())).unwrap(), frame());
}

#[test]
fn test_from_file_string_path() {
    assert_eq!(Saveframe::from_file(sample_saveframe_location().to_str().unwrap()).unwrap(), frame());
}

#[test]
fn test_from_file_file_handle() {
    let file = std::fs::File::open(sample_saveframe_location()).unwrap();
    assert_eq!(Saveframe::from_file(Source::from_reader(file).unwrap()).unwrap(), frame());
}

// (Python refuses Saveframe() without arguments; Rust has no such constructor.)

#[test]
fn test_init_multiple_saveframes_raises() {
    let entry = file_entry();
    let two_sf = format!("{}\n{}", entry.frame_list[0].to_star().unwrap(), entry.frame_list[1].to_star().unwrap());
    assert_value_error(Saveframe::from_str(&two_sf));
}

#[test]
fn test_from_scratch_basic() {
    let sf = Saveframe::from_scratch("test_sf", None);
    assert_eq!(sf.name(), "test_sf");
    assert_eq!(sf.tag_prefix, None);
    assert!(sf.tags().is_empty());
}

#[test]
fn test_from_scratch_with_tag_prefix() {
    let sf = Saveframe::from_scratch("test", Some("test"));
    assert_eq!(sf.tag_prefix.as_deref(), Some("_test"));
    assert_eq!(sf.to_star().unwrap(), "save_test\n\nsave_\n");
}

#[test]
fn test_from_string_roundtrip() {
    let frame = frame();
    assert_eq!(Saveframe::from_str(&frame.to_star().unwrap()).unwrap(), frame);
}

#[test]
fn test_from_string_csv() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.loops.clear();
    let csv_data = frame.get_data_as_csv(true, true);
    assert!(Saveframe::from_csv_str(&csv_data).unwrap().compare(&tmp).is_empty());
}

#[test]
fn test_from_string_csv_mismatched_columns() {
    assert_value_error(Saveframe::from_csv_str("test.1,test.2\n2,3,4"));
}

#[test]
fn test_from_json_dict() {
    let frame = frame();
    assert_eq!(frame, Saveframe::from_json_value(&frame.to_json_value()).unwrap());
}

#[test]
fn test_from_json_string() {
    let frame = frame();
    assert_eq!(frame, Saveframe::from_json(&frame.to_json()).unwrap());
}

#[test]
fn test_from_json_invalid_string() {
    assert_value_error(Saveframe::from_json("12345"));
}

#[test]
fn test_from_json_missing_key() {
    assert_value_error(Saveframe::from_json(r#"{"name": "test"}"#));
}

#[test]
fn test_from_template_basic() {
    let sf = Saveframe::from_template("assigned_chemical_shifts", None, None, false, false, None).unwrap();
    assert_eq!(sf.category(), Some("assigned_chemical_shifts"));
    assert!(sf.tags().iter().any(|t| t.name == "Sf_category"));
}

#[test]
fn test_from_template_with_name() {
    let sf = Saveframe::from_template("assigned_chemical_shifts", Some("my_shifts"), None, false, false, None).unwrap();
    assert_eq!(sf.name(), "my_shifts");
}

#[test]
fn test_from_template_with_entry_id() {
    let sf = Saveframe::from_template("assigned_chemical_shifts", Some("test"), Some("99999".into()), false, false, None).unwrap();
    assert!(sf.get_tag("Entry_ID").unwrap().contains(&Value::from("99999")));
}

#[test]
fn test_from_template_all_tags() {
    let sf_minimal = Saveframe::from_template("assigned_chemical_shifts", None, None, false, false, None).unwrap();
    let sf_all = Saveframe::from_template("assigned_chemical_shifts", None, None, true, false, None).unwrap();
    assert!(sf_all.tags().len() >= sf_minimal.tags().len());
}

#[test]
fn test_from_template_default_values() {
    Saveframe::from_template("assigned_chemical_shifts", None, None, false, true, None).unwrap();
}

#[test]
fn test_from_template_invalid_category() {
    assert_value_error(Saveframe::from_template("this_category_does_not_exist_ever", None, None, false, false, None));
}

#[test]
fn test_contains_tag_name() {
    let frame = frame();
    assert!(frame.contains("Sf_category"));
    assert!(!frame.contains("nonexistent_tag"));
}

#[test]
fn test_contains_loop_category() {
    let frame = frame();
    assert!(frame.contains("_SG_project"));
    assert!(!frame.contains("_Nonexistent_loop"));
}

#[test]
fn test_contains_loop_object() {
    let frame = frame();
    assert!(frame.contains_loop(&frame.loops[0]));
    assert!(!frame.contains_loop(&Loop::from_scratch(Some("not_in_frame")).unwrap()));
}

#[test]
fn test_contains_list() {
    let frame = frame();
    assert!(frame.contains_all(&["Sf_category", "Sf_framecode"]));
    assert!(!frame.contains_all(&["Sf_category", "nonexistent"]));
}

#[test]
fn test_contains_tuple() {
    assert!(frame().contains_all(&["Sf_category"]));
}

#[test]
fn test_delitem_by_int_index() {
    let mut frame = frame();
    let original_len = frame.len();
    frame.remove_loop_at(0).unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_delitem_by_int_index_out_of_range() {
    assert_index_error(frame().remove_loop_at(999));
}

#[test]
fn test_delitem_by_loop_object() {
    let mut frame = frame();
    let target = frame.get_loop("_SG_project").unwrap().clone();
    let original_len = frame.len();
    frame.remove_loop_obj(&target).unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_delitem_by_loop_category_string() {
    let mut frame = frame();
    let original_len = frame.len();
    frame.delete("_SG_project").unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_delitem_by_tag_name_string() {
    let mut frame = frame();
    frame.add_tag("test_tag", "value").unwrap();
    assert!(!frame.get_tag("test_tag").unwrap().is_empty());
    frame.delete("test_tag").unwrap();
    assert!(frame.get_tag("test_tag").unwrap().is_empty());
}

#[test]
fn test_delitem_by_qualified_tag_name() {
    let mut frame = frame();
    let original_tags = frame.tags().len();
    frame.delete("_Entry.DOI").unwrap();
    assert_eq!(frame.tags().len(), original_tags - 1);
}

#[test]
fn test_eq_same_content() {
    let frame = frame();
    assert_eq!(frame, frame.clone());
}

#[test]
fn test_getitem_int_returns_loop() {
    let frame = frame();
    assert_eq!(frame.loop_at(0).unwrap(), &frame.loops[0]);
}

#[test]
fn test_getitem_loop_category_string() {
    let frame = frame();
    assert_eq!(frame.loop_dict()["_sg_project"], frame.get_loop("_SG_project").unwrap());
}

#[test]
fn test_getitem_loop_category_not_found() {
    assert_key_error(frame().get_loop("_Nonexistent_category"));
}

#[test]
fn test_getitem_tag_name() {
    assert_eq!(frame().get_tag_required("Sf_category").unwrap(), strs(&["entry_information"]));
}

#[test]
fn test_getitem_tag_not_found() {
    assert_key_error(frame().get_tag_required("nonexistent_tag_xyz"));
}

#[test]
fn test_getitem_int_out_of_range() {
    assert_index_error(frame().loop_at(999));
}

#[test]
fn test_iter() {
    let frame = frame();
    let loops: Vec<&Loop> = frame.iter().collect();
    assert_eq!(loops.len(), frame.loops.len());
    assert!(loops.into_iter().eq(frame.loops.iter()));
}

#[test]
fn test_len() {
    let frame = frame();
    assert_eq!(frame.len(), frame.loops.len());
}

#[test]
fn test_lt_comparison() {
    let sf1 = Saveframe::from_scratch("a", Some("AAA"));
    let sf2 = Saveframe::from_scratch("b", Some("ZZZ"));
    assert!(sf1 < sf2);
    assert!(!(sf2 < sf1));
}

#[test]
fn test_repr() {
    assert_eq!(frame().repr(), "<pynmrstar.Saveframe 'entry_information'>");
}

#[test]
fn test_setitem_tag_new() {
    let mut frame = frame();
    frame.set_tag("test_setitem", 1).unwrap();
    assert_eq!(frame.tags().last().unwrap().value, Value::Int(1));
}

#[test]
fn test_setitem_tag_update() {
    let mut frame = frame();
    frame.set_tag("test_setitem", 1).unwrap();
    frame.set_tag("tESt_setitem", 2).unwrap();
    assert_eq!(frame.get_tag("test_setitem").unwrap(), vec![Value::Int(2)]);
}

#[test]
fn test_setitem_loop_by_int() {
    let mut frame = frame();
    let second = frame.loops[1].clone();
    frame.set_loop_at(0, second).unwrap();
    assert_eq!(frame.loops[0], frame.loops[1]);
}

#[test]
fn test_setitem_loop_by_category_string() {
    let mut frame = frame();
    let replacement = frame.get_loop("_SG_project").unwrap().clone();
    frame.set_loop("_SG_project", replacement.clone()).unwrap();
    assert_eq!(frame.get_loop("_SG_project").unwrap(), &replacement);
}

#[test]
fn test_setitem_loop_by_category_not_found() {
    let mut frame = frame();
    assert_key_error(frame.set_loop("_nonexistent", Loop::from_scratch(Some("nonexistent")).unwrap()));
}

#[test]
fn test_str_no_tag_prefix_raises() {
    assert_invalid_state(Saveframe::from_scratch("test", None).to_star());
}

#[test]
fn test_str_basic() {
    let output = frame().to_star().unwrap();
    assert!(output.contains("save_entry_information"));
    assert!(output.trim_end().ends_with("save_"));
}

#[test]
fn test_format_skip_empty_loops() {
    let mut frame = frame();
    frame.add_loop(Loop::new()).unwrap();
    let output_skip = frame.format(true, false, true).unwrap();
    let output_no_skip = frame.format(false, false, true).unwrap();
    assert!(output_no_skip.len() >= output_skip.len());
}

#[test]
fn test_format_skip_empty_tags() {
    let frame = frame();
    assert!(frame.format(true, false, true).unwrap().len() >= frame.format(true, true, true).unwrap().len());
}

#[test]
fn test_format_show_comments() {
    let frame = frame();
    assert!(frame.format(true, false, true).unwrap().len() >= frame.format(true, false, false).unwrap().len());
}

#[test]
fn test_category_getter() {
    assert_eq!(frame().category(), Some("entry_information"));
}

#[test]
fn test_category_setter() {
    let mut frame = frame();
    frame.set_category("new_category").unwrap();
    assert_eq!(frame.category(), Some("new_category"));
    assert_eq!(frame.get_tag("sf_category").unwrap(), strs(&["new_category"]));
}

#[test]
fn test_category_setter_null_raises() {
    let mut frame = frame();
    for null in ["", ".", "?"] {
        assert_value_error(frame.set_category(null));
    }
}

#[test]
fn test_category_setter_no_existing_tag() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.set_category("new_cat").unwrap();
    assert_eq!(sf.category(), Some("new_cat"));
    assert_eq!(sf.get_tag("Sf_category").unwrap(), strs(&["new_cat"]));
}

#[test]
fn test_empty_true() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tag("Sf_category", "test").unwrap();
    sf.add_tag("Sf_framecode", "test").unwrap();
    sf.add_tag("ID", ".").unwrap();
    sf.add_tag("Entry_ID", Value::Null).unwrap();
    assert!(sf.empty());
}

#[test]
fn test_empty_false_due_to_tag() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tag("Sf_category", "test").unwrap();
    sf.add_tag("Sf_framecode", "test").unwrap();
    sf.add_tag("Custom_tag", "has_value").unwrap();
    assert!(!sf.empty());
}

#[test]
fn test_empty_false_due_to_loop() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tag("Sf_category", "test").unwrap();
    sf.add_tag("Sf_framecode", "test").unwrap();
    let mut new_loop = Loop::from_scratch(Some("test_loop")).unwrap();
    new_loop.add_tag("col1").unwrap();
    new_loop.add_data(Data::Flat(strs(&["value"]))).unwrap();
    sf.add_loop(new_loop).unwrap();
    assert!(!sf.empty());
}

#[test]
fn test_name_getter() {
    assert_eq!(frame().name(), "entry_information");
}

#[test]
fn test_name_setter() {
    let mut frame = frame();
    frame.set_name("new_name").unwrap();
    assert_eq!(frame.name(), "new_name");
    assert_eq!(frame.get_tag("sf_framecode").unwrap(), strs(&["new_name"]));
}

#[test]
fn test_name_setter_whitespace_raises() {
    let mut frame = frame();
    assert_value_error(frame.set_name("has space"));
    assert_value_error(frame.set_name("has\ttab"));
}

#[test]
fn test_name_setter_null_raises() {
    let mut frame = frame();
    for null in ["", ".", "?"] {
        assert_value_error(frame.set_name(null));
    }
}

#[test]
fn test_tag_dict() {
    let td = frame().tag_dict();
    assert_eq!(td["sf_category"], "entry_information");
}

#[test]
fn test_loop_dict() {
    let frame = frame();
    assert!(frame.loop_dict().contains_key("_sg_project"));
}

#[test]
fn test_loops_property() {
    assert!(!frame().loops.is_empty());
}

#[test]
fn test_tags_property() {
    assert!(!frame().tags().is_empty());
}

#[test]
fn test_add_loop_success() {
    let mut frame = frame();
    let original_len = frame.len();
    frame.add_loop(Loop::from_scratch(Some("unique_test")).unwrap()).unwrap();
    assert_eq!(frame.len(), original_len + 1);
}

#[test]
fn test_add_loop_duplicate_raises() {
    let mut frame = frame();
    let first = frame.loops[0].clone();
    assert_value_error(frame.add_loop(first));
}

#[test]
fn test_add_loop_duplicate_named_category_raises() {
    let mut frame = Saveframe::from_scratch("1", None);
    frame.add_loop(Loop::from_scratch(Some("duplicate")).unwrap()).unwrap();
    assert_value_error(frame.add_loop(Loop::from_scratch(Some("duplicate")).unwrap()));
}

#[test]
fn test_add_tag_basic() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tag("mytag", "myvalue").unwrap();
    assert_eq!(sf.get_tag("mytag").unwrap(), strs(&["myvalue"]));
}

#[test]
fn test_add_tag_duplicate_raises() {
    assert_value_error(frame().add_tag("Sf_category", "test"));
}

#[test]
fn test_add_tag_update() {
    let mut frame = frame();
    frame.add_tag_with("Sf_category", "updated_cat", true, false, None).unwrap();
    assert_eq!(frame.get_tag("Sf_category").unwrap(), strs(&["updated_cat"]));
    assert_eq!(frame.category(), Some("updated_cat"));
}

#[test]
fn test_add_tag_update_sf_framecode_null_raises() {
    assert_value_error(frame().add_tag_with("Sf_framecode", Value::Null, true, false, None));
}

// (Python refuses a tag name which is not a string; Rust's types rule that out.)

#[test]
fn test_add_tag_null_name_raises() {
    assert_value_error(Saveframe::from_scratch("test", Some("test")).add_tag(".", "value"));
}

#[test]
fn test_add_tag_whitespace_in_name_raises() {
    assert_value_error(frame().add_tag("invalid test", 1));
}

#[test]
fn test_add_tag_double_dot_in_name_raises() {
    assert_value_error(frame().add_tag("invalid.test.test", 1));
}

#[test]
fn test_add_tag_mismatched_prefix_raises() {
    assert_value_error(frame().add_tag_with("invalid.test", 1, true, false, None));
}

#[test]
fn test_add_tag_sets_tag_prefix() {
    let mut sf = Saveframe::from_scratch("test", None);
    sf.add_tag("_MyPrefix.MyTag", "value").unwrap();
    assert_eq!(sf.tag_prefix.as_deref(), Some("_MyPrefix"));
}

#[test]
fn test_add_tag_sf_framecode_mismatch_raises() {
    assert_value_error(Saveframe::from_scratch("test", None).add_tag("sf_framecode", "different_name"));
}

#[test]
fn test_add_tag_sf_framecode_null_on_initial_add_raises() {
    assert_value_error(Saveframe::from_scratch("test", None).add_tag("sf_framecode", Value::Null));
}

#[test]
fn test_add_tag_convert_data_types() {
    let mut sf = Saveframe::from_scratch("test", Some("_Entry"));
    sf.add_tag_with("ID", "15000", false, true, None).unwrap();
    assert_eq!(sf.get_tag("ID").unwrap().len(), 1);
}

#[test]
fn test_add_tags_key_value_pairs() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tags(&[("tag1", "val1"), ("tag2", "val2")]).unwrap();
    assert_eq!(sf.get_tag("tag1").unwrap(), strs(&["val1"]));
    assert_eq!(sf.get_tag("tag2").unwrap(), strs(&["val2"]));
}

#[test]
fn test_add_tags_key_only() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tags_with(&[("tag1", None), ("tag2", None)], false, false, None).unwrap();
    assert_eq!(sf.get_tag("tag1").unwrap(), strs(&["."]));
    assert_eq!(sf.get_tag("tag2").unwrap(), strs(&["."]));
}

#[test]
fn test_add_tags_update() {
    let mut frame = frame();
    frame.add_tags_with(&[("example1", None), ("example2", None)], false, false, None).unwrap();
    let n = frame.tags().len();
    assert_eq!(frame.tags()[n - 2], nmrstar::Tag::new("example1", "."));
    frame.add_tags_with(&[("example1", Some(Value::Int(5))), ("example2", None)], true, false, None).unwrap();
    assert_eq!(frame.tags()[n - 2], nmrstar::Tag::new("example1", 5));
}

// (Python refuses a tag "pair" of three elements; Rust's types rule that out.)

#[test]
fn test_add_missing_tags() {
    let mut sf = Saveframe::from_template("assigned_chemical_shifts", Some("test"), None, false, false, None).unwrap();
    let original_count = sf.tags().len();
    let tag_to_remove = sf.tags().iter().map(|t| t.name.clone())
        .find(|name| !["sf_category", "sf_framecode"].contains(&name.to_lowercase().as_str()));
    if let Some(tag_to_remove) = tag_to_remove {
        sf.remove_tag(&tag_to_remove).unwrap();
        assert_eq!(sf.tags().len(), original_count - 1);
        sf.add_missing_tags(None, false, true).unwrap();
        assert_eq!(sf.tags().len(), original_count);
    }
}

#[test]
fn test_add_missing_tags_no_prefix_raises() {
    assert_invalid_state(Saveframe::from_scratch("test", None).add_missing_tags(None, false, true));
}

#[test]
fn test_add_missing_tags_all_tags() {
    let mut sf = Saveframe::from_template("assigned_chemical_shifts", Some("test"), None, false, false, None).unwrap();
    let count_before = sf.tags().len();
    sf.add_missing_tags(None, true, true).unwrap();
    assert!(sf.tags().len() >= count_before);
}

#[test]
fn test_add_missing_tags_non_recursive() {
    let mut sf = Saveframe::from_template("assigned_chemical_shifts", Some("test"), None, false, false, None).unwrap();
    sf.add_missing_tags(None, false, false).unwrap();
}

#[test]
fn test_compare_same_object() {
    let frame = frame();
    assert!(frame.compare(&frame).is_empty());
}

#[test]
fn test_compare_equal_different_objects() {
    let frame = frame();
    assert!(frame.compare(&frame.clone()).is_empty());
}

#[test]
fn test_compare_different_names() {
    let entry = file_entry();
    assert_eq!(entry.frame_list[0].compare(&entry.frame_list[1]),
               vec!["\tSaveframe names do not match: 'entry_information' vs 'citation_1'."]);
}

#[test]
fn test_compare_different_prefix() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.tag_prefix = Some("test".to_string());
    assert_eq!(frame.compare(&tmp), vec!["\tTag prefix does not match: '_Entry' vs 'test'."]);
}

#[test]
fn test_compare_missing_tag() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.tags_mut()[0].name = "broken".to_string();
    assert_eq!(frame.compare(&tmp), vec!["\tNo tag with name '_Entry.Sf_category' in compared entry."]);
}

#[test]
fn test_compare_with_string_equal() {
    let frame = frame();
    assert!(frame.compare_str(&frame.to_star().unwrap()).is_empty());
}

#[test]
fn test_compare_with_string_not_equal() {
    assert_eq!(frame().compare_str("not equal"), vec!["String was not exactly equal to saveframe."]);
}

#[test]
fn test_compare_mismatched_tag_values() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.add_tag_with("ID", "99999", true, false, None).unwrap();
    assert!(frame.compare(&tmp).iter().any(|d| d.contains("Mismatched tag values")));
}

#[test]
fn test_compare_mismatched_tag_counts() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.add_tag("extra_tag", "value").unwrap();
    assert!(frame.compare(&tmp).iter().any(|d| d.contains("Number of tags does not match")));
}

#[test]
fn test_compare_mismatched_loop_counts() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.remove_loop_at(0).unwrap();
    assert!(frame.compare(&tmp).iter().any(|d| d.contains("Number of children loops")));
}

#[test]
fn test_compare_missing_loop_category() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.loops[0] = Loop::from_scratch(Some("different_category")).unwrap();
    assert!(frame.compare(&tmp).iter().any(|d| d.contains("No loop with category")));
}

#[test]
fn test_compare_loop_differences() {
    let frame = frame();
    let mut tmp = frame.clone();
    tmp.loops[0].data[0][0] = "modified_value_xyz".into();
    assert!(frame.compare(&tmp).iter().any(|d| d.contains("Loops do not match")));
}

#[test]
#[allow(deprecated)]
fn test_delete_tag_deprecated() {
    let mut frame = frame();
    frame.add_tag("temp_tag", "value").unwrap();
    frame.delete_tag("temp_tag").unwrap();
    assert!(frame.get_tag("temp_tag").unwrap().is_empty());
}

#[test]
fn test_get_data_as_csv_with_header_and_category() {
    assert!(frame().get_data_as_csv(true, true).contains("_Entry.Sf_category"));
}

#[test]
fn test_get_data_as_csv_with_header_no_category() {
    let csv = frame().get_data_as_csv(true, false);
    assert!(csv.contains("Sf_category"));
    assert!(!csv.contains("_Entry.Sf_category"));
}

#[test]
fn test_get_data_as_csv_no_header() {
    assert!(frame().get_data_as_csv(false, true).starts_with("entry_information"));
}

#[test]
fn test_get_data_as_csv_no_header_no_category() {
    assert!(frame().get_data_as_csv(false, false).starts_with("entry_information"));
}

#[test]
fn test_get_json_serialized() {
    let parsed = Json::parse(&frame().to_json()).unwrap();
    assert_eq!(parsed.get("name").unwrap().as_str(), Some("entry_information"));
}

#[test]
fn test_get_json_unserialized() {
    let result = frame().to_json_value();
    assert_eq!(result.get("name").unwrap().as_str(), Some("entry_information"));
    for key in ["tags", "loops", "tag_prefix", "category"] {
        assert!(result.has(key));
    }
}

#[test]
fn test_get_json_roundtrip() {
    let frame = frame();
    assert_eq!(frame, Saveframe::from_json(&frame.to_json()).unwrap());
}

#[test]
fn test_get_loop_found() {
    assert_eq!(frame().get_loop("_SG_projecT").unwrap().repr(), "<pynmrstar.Loop '_SG_project'>");
}

#[test]
fn test_get_loop_not_found() {
    assert_key_error(frame().get_loop("this_loop_wont_be_found"));
}

#[test]
#[allow(deprecated)]
fn test_get_loop_by_category_deprecated() {
    let frame = frame();
    assert_eq!(frame.get_loop_by_category("_SG_project").unwrap(), frame.get_loop("_SG_project").unwrap());
}

#[test]
fn test_get_tag_simple() {
    assert_eq!(frame().get_tag("sf_category").unwrap(), strs(&["entry_information"]));
}

#[test]
fn test_get_tag_with_prefix() {
    assert_eq!(frame().get_tag("entry.sf_category").unwrap(), strs(&["entry_information"]));
}

#[test]
fn test_get_tag_whole_tag() {
    assert_eq!(frame().get_tag_whole("entry.sf_category").unwrap(),
               vec![("Sf_category".to_string(), Value::from("entry_information"))]);
}

#[test]
fn test_get_tag_from_loop() {
    let frame = frame();
    let first_loop = &frame.loops[0];
    let tag_name = format!("{}.{}", first_loop.category().unwrap(), first_loop.tags()[0]);
    assert!(!frame.get_tag(&tag_name).unwrap().is_empty());
}

#[test]
fn test_get_tag_not_found() {
    assert!(frame().get_tag("nonexistent_tag_xyz").unwrap().is_empty());
}

#[test]
fn test_loop_iterator() {
    let frame = frame();
    assert_eq!(frame.iter().count(), frame.loops.len());
}

#[test]
fn test_tag_iterator() {
    let frame = frame();
    assert_eq!(frame.tags().iter().count(), frame.tags().len());
}

#[test]
fn test_print_tree() {
    let frame = frame();
    let tree = frame.tree();
    assert!(tree.starts_with(&frame.repr()));
    assert_eq!(tree.lines().count(), 1 + frame.loops.len());
}

#[test]
fn test_remove_loop_by_object() {
    let mut frame = frame();
    let first = frame.loops[0].clone();
    let original_len = frame.len();
    frame.remove_loop_obj(&first).unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_remove_loop_by_string_category() {
    let mut frame = frame();
    let original_len = frame.len();
    frame.remove_loop("_SG_project").unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_remove_loop_by_string_without_underscore() {
    let mut frame = frame();
    let original_len = frame.len();
    frame.remove_loop("sg_project").unwrap();
    assert_eq!(frame.len(), original_len - 1);
}

#[test]
fn test_remove_loop_by_list() {
    let mut frame = frame();
    let to_remove = vec![frame.loops[0].clone(), frame.loops[1].clone()];
    let original_len = frame.len();
    frame.remove_loop_objs(&to_remove).unwrap();
    assert_eq!(frame.len(), original_len - 2);
}

#[test]
fn test_remove_loop_by_tuple() {
    let mut frame = frame();
    let categories = [frame.loops[0].category().unwrap().to_string(), frame.loops[1].category().unwrap().to_string()];
    let original_len = frame.len();
    frame.remove_loops(&categories).unwrap();
    assert_eq!(frame.len(), original_len - 2);
}

#[test]
fn test_remove_loop_string_not_found() {
    assert_value_error(frame().remove_loop("_nonexistent_loop_category"));
}

#[test]
fn test_remove_loop_object_not_found() {
    assert_value_error(frame().remove_loop_obj(&Loop::from_scratch(Some("not_in_frame")).unwrap()));
}

// (Python refuses removing a loop given as something other than a loop or a category; Rust's
//  types rule that out.)

#[test]
fn test_remove_tag_single() {
    let mut frame = frame();
    frame.add_tag("temp_tag", "value").unwrap();
    frame.remove_tag("temp_tag").unwrap();
    assert!(frame.get_tag("temp_tag").unwrap().is_empty());
}

#[test]
fn test_remove_tag_list() {
    let mut frame = frame();
    frame.add_tags(&[("tag1", "v1"), ("tag2", "v2")]).unwrap();
    frame.remove_tags(&["tag1", "tag2"]).unwrap();
    assert!(frame.get_tag("tag1").unwrap().is_empty());
    assert!(frame.get_tag("tag2").unwrap().is_empty());
}

#[test]
fn test_remove_tag_not_found_raises() {
    assert_key_error(frame().remove_tag("this_tag_will_not_exist"));
}

#[test]
fn test_set_tag_prefix() {
    let mut frame = frame();
    frame.set_tag_prefix("new_prefix");
    assert_eq!(frame.tag_prefix.as_deref(), Some("_new_prefix"));
}

#[test]
fn test_sort_tags() {
    let mut frame = frame();
    let first = frame.tags_mut().remove(0);
    frame.tags_mut().push(first);
    assert_ne!(frame.tags()[0].name, "Sf_category");
    frame.sort_tags(None);
    assert_eq!(frame.tags()[0].name, "Sf_category");
}

#[test]
fn test_validate_valid() {
    let entry = file_entry();
    assert!(entry.get_saveframe_by_name("assigned_chem_shift_list_1").unwrap().validate(true, None, true).is_empty());
}

#[test]
fn test_validate_no_category() {
    let mut sf = Saveframe::from_scratch("test", Some("test"));
    sf.add_tag("Sf_framecode", "test").unwrap();
    assert!(sf.validate(true, None, true).iter().any(|e| e.contains("Cannot properly validate")));
}

#[test]
fn test_validate_non_ascii() {
    let mut entry = file_entry();
    let frame = entry.get_saveframe_by_name_mut("entry_information").unwrap();
    frame.set_tag("Title", "Solution structure of ubiquitin–like protein").unwrap();
    assert_eq!(frame.validate(false, None, true),
               vec!["Non-ASCII character(s) '–' (U+2013) in tag '_Entry.Title': 'Solution structure of ubiquitin–like protein'."]);
}

#[test]
fn test_validate_schema_false() {
    frame().validate(false, None, true);
}

#[test]
fn test_write_to_file_nmrstar() {
    let frame = frame();
    let file = tempfile::NamedTempFile::new().unwrap();
    frame.write_to_file(file.path(), FileFormat::NmrStar, true, false, false).unwrap();
    assert_eq!(frame, Saveframe::from_file(file.path()).unwrap());
}

#[test]
fn test_write_to_file_json() {
    let frame = frame();
    let file = tempfile::NamedTempFile::new().unwrap();
    frame.write_to_file(file.path(), FileFormat::Json, true, false, false).unwrap();
    let data = Json::parse(&std::fs::read_to_string(file.path()).unwrap()).unwrap();
    assert_eq!(data.get("name").unwrap().as_str(), Some("entry_information"));
}

#[test]
fn test_write_to_file_path_object() {
    let frame = frame();
    let file = tempfile::NamedTempFile::new().unwrap();
    frame.write_to_file(file.path().to_path_buf(), FileFormat::NmrStar, true, false, false).unwrap();
    assert_eq!(frame, Saveframe::from_file(file.path().to_str().unwrap()).unwrap());
}

#[test]
fn test_write_to_file_invalid_format_raises() {
    assert_value_error(FileFormat::from_name("xml"));
}

#[test]
fn test_add_tag_update_sf_framecode_valid() {
    let mut frame = frame();
    frame.add_tag_with("Sf_framecode", "new_name", true, false, None).unwrap();
    assert_eq!(frame.name(), "new_name");
    assert_eq!(frame.get_tag("Sf_framecode").unwrap(), strs(&["new_name"]));
}

// (test_compare_attribute_error deletes an attribute from a Python object; there is no Rust
//  equivalent.)

#[test]
fn test_from_template_with_default_values_non_null() {
    let sf = Saveframe::from_template("assigned_chemical_shifts", Some("test"), None, true, true, None).unwrap();
    assert!(!sf.tags().is_empty());
}

#[test]
fn test_null_values_are_the_defaults() {
    // The tests above which loop over the null values use the defaults
    assert_eq!(definitions::null_values(), vec![Value::from(""), Value::from("."), Value::from("?"), Value::Null]);
}
