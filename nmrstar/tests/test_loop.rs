//! Ported from pynmrstar/unit_tests/test_loop.py.

mod common;

use std::collections::BTreeMap;
use std::path::Path;

use common::*;
use nmrstar::{row, Data, Decimal, Error, Loop, Schema, Value};

fn sample_loop_location() -> std::path::PathBuf {
    sample("loop.txt")
}

/// The first loop of the first saveframe of the sample entry (_Entry_author).
fn test_loop() -> Loop {
    file_entry().frame_list[0].loops[0].clone()
}

fn second_loop() -> Loop {
    file_entry().frame_list[0].loops[1].clone()
}

fn simple_loop(category: &str, tags: &[&str], rows: Vec<Vec<Value>>) -> Loop {
    let mut new_loop = Loop::from_scratch(Some(category)).unwrap();
    new_loop.add_tags(tags).unwrap();
    if !rows.is_empty() {
        new_loop.add_data(Data::Rows(rows)).unwrap();
    }
    new_loop
}

#[test]
fn test_init() {
    // (Python refuses Loop() without arguments; Rust has no such constructor.)
    let test = Loop::from_scratch(Some("test")).unwrap();
    assert_eq!(test.category(), Some("_test"));
}

#[test]
fn test_category_whitespace_validation() {
    assert_value_error(Loop::from_scratch(Some("test category")));
    assert_value_error(Loop::from_scratch(Some("test\tcategory")));
    assert_value_error(Loop::from_scratch(Some("test\u{3000}category")));
    assert_value_error(Loop::from_scratch(Some("test\u{a0}category")));
    assert_value_error(Loop::from_scratch(Some("test\u{1680}category")));

    let mut test_loop = Loop::from_scratch(Some("test")).unwrap();
    assert_value_error(test_loop.set_category_raw(Some("_has space")));
    assert_value_error(test_loop.set_category_raw(Some("_has\u{3000}ideographic_space")));
    assert_value_error(test_loop.set_category("has space"));

    test_loop.set_category_raw(None).unwrap();
    assert_eq!(test_loop.category(), None);

    test_loop.set_category_raw(Some("_valid_category")).unwrap();
    assert_eq!(test_loop.category(), Some("_valid_category"));

    // Adding a tag with a category is also checked
    test_loop.set_category_raw(None).unwrap();
    assert_value_error(test_loop.add_tag("invalid tag.tag"));
}

#[test]
fn test_from_string() {
    let test_loop = test_loop();
    assert_eq!(Loop::from_str(&test_loop.to_star().unwrap()).unwrap(), test_loop);
    assert_eq!(test_loop, Loop::from_csv_str(&test_loop.get_data_as_csv(true, true)).unwrap());
}

#[test]
fn test_from_file() {
    let loop_from_str = Loop::from_file(sample_loop_location().to_str().unwrap()).unwrap();
    let loop_from_path = Loop::from_file(Path::new(&sample_loop_location())).unwrap();
    assert_eq!(loop_from_str, loop_from_path);
    assert_eq!(loop_from_path.category(), Some("_Test"));
    assert_eq!(loop_from_path.tags(), ["ID", "Name"]);
    assert_eq!(loop_from_path.data, vec![strs(&["1", "First"]), strs(&["2", "Second"])]);
}

#[test]
fn test_from_template() {
    let expected = Loop::from_str("
loop_
      _Atom_chem_shift.ID
      _Atom_chem_shift.Assembly_atom_ID
      _Atom_chem_shift.Entity_assembly_ID
      _Atom_chem_shift.Entity_assembly_asym_ID
      _Atom_chem_shift.Entity_ID
      _Atom_chem_shift.Comp_index_ID
      _Atom_chem_shift.Seq_ID
      _Atom_chem_shift.Comp_ID
      _Atom_chem_shift.Atom_ID
      _Atom_chem_shift.Atom_type
      _Atom_chem_shift.Atom_isotope_number
      _Atom_chem_shift.Val
      _Atom_chem_shift.Val_err
      _Atom_chem_shift.Assign_fig_of_merit
      _Atom_chem_shift.Ambiguity_code
      _Atom_chem_shift.Ambiguity_set_ID
      _Atom_chem_shift.Occupancy
      _Atom_chem_shift.Resonance_ID
      _Atom_chem_shift.Auth_entity_assembly_ID
      _Atom_chem_shift.Auth_asym_ID
      _Atom_chem_shift.Auth_seq_ID
      _Atom_chem_shift.Auth_comp_ID
      _Atom_chem_shift.Auth_atom_ID
      _Atom_chem_shift.Original_PDB_strand_ID
      _Atom_chem_shift.Original_PDB_residue_no
      _Atom_chem_shift.Original_PDB_residue_name
      _Atom_chem_shift.Original_PDB_atom_name
      _Atom_chem_shift.Details
      _Atom_chem_shift.Entry_ID
      _Atom_chem_shift.Assigned_chem_shift_list_ID


   stop_
").unwrap();
    assert_eq!(Loop::from_template("atom_chem_shift", false, None).unwrap(), expected);

    let expected_all = Loop::from_str("
   loop_
      _Atom_chem_shift.ID
      _Atom_chem_shift.Assembly_atom_ID
      _Atom_chem_shift.Entity_assembly_ID
      _Atom_chem_shift.Entity_assembly_asym_ID
      _Atom_chem_shift.Entity_ID
      _Atom_chem_shift.Comp_index_ID
      _Atom_chem_shift.Seq_ID
      _Atom_chem_shift.Comp_ID
      _Atom_chem_shift.Atom_ID
      _Atom_chem_shift.Atom_type
      _Atom_chem_shift.Atom_isotope_number
      _Atom_chem_shift.Val
      _Atom_chem_shift.Val_err
      _Atom_chem_shift.Assign_fig_of_merit
      _Atom_chem_shift.Ambiguity_code
      _Atom_chem_shift.Ambiguity_set_ID
      _Atom_chem_shift.Occupancy
      _Atom_chem_shift.Resonance_ID
      _Atom_chem_shift.Auth_entity_assembly_ID
      _Atom_chem_shift.Auth_asym_ID
      _Atom_chem_shift.Auth_seq_ID
      _Atom_chem_shift.Auth_comp_ID
      _Atom_chem_shift.Auth_atom_ID
      _Atom_chem_shift.PDB_record_ID
      _Atom_chem_shift.PDB_model_num
      _Atom_chem_shift.PDB_strand_ID
      _Atom_chem_shift.PDB_ins_code
      _Atom_chem_shift.PDB_residue_no
      _Atom_chem_shift.PDB_residue_name
      _Atom_chem_shift.PDB_atom_name
      _Atom_chem_shift.Original_PDB_strand_ID
      _Atom_chem_shift.Original_PDB_residue_no
      _Atom_chem_shift.Original_PDB_residue_name
      _Atom_chem_shift.Original_PDB_atom_name
      _Atom_chem_shift.Details
      _Atom_chem_shift.Sf_ID
      _Atom_chem_shift.Entry_ID
      _Atom_chem_shift.Assigned_chem_shift_list_ID


   stop_
").unwrap();
    assert_eq!(Loop::from_template("atom_chem_shift", true, None).unwrap(), expected_all);

    // Adding a tag to the schema
    let mut my_schema = Schema::new().unwrap();
    my_schema.add_tag("_Atom_chem_shift.New_Tag", "VARCHAR(100)", true, "assigned_chemical_shifts", true,
                      Some("_Atom_chem_shift.Atom_ID")).unwrap();
    assert_eq!(Loop::from_template("atom_chem_shift", true, Some(&my_schema)).unwrap(), Loop::from_str(
        "loop_ _Atom_chem_shift.ID _Atom_chem_shift.Assembly_atom_ID _Atom_chem_shift.Entity_assembly_ID \
         _Atom_chem_shift.Entity_assembly_asym_ID _Atom_chem_shift.Entity_ID _Atom_chem_shift.Comp_index_ID \
         _Atom_chem_shift.Seq_ID _Atom_chem_shift.Comp_ID _Atom_chem_shift.Atom_ID _Atom_chem_shift.New_Tag \
         _Atom_chem_shift.Atom_type _Atom_chem_shift.Atom_isotope_number _Atom_chem_shift.Val \
         _Atom_chem_shift.Val_err _Atom_chem_shift.Assign_fig_of_merit _Atom_chem_shift.Ambiguity_code \
         _Atom_chem_shift.Ambiguity_set_ID _Atom_chem_shift.Occupancy _Atom_chem_shift.Resonance_ID \
         _Atom_chem_shift.Auth_entity_assembly_ID _Atom_chem_shift.Auth_asym_ID _Atom_chem_shift.Auth_seq_ID \
         _Atom_chem_shift.Auth_comp_ID _Atom_chem_shift.Auth_atom_ID _Atom_chem_shift.PDB_record_ID \
         _Atom_chem_shift.PDB_model_num _Atom_chem_shift.PDB_strand_ID _Atom_chem_shift.PDB_ins_code \
         _Atom_chem_shift.PDB_residue_no _Atom_chem_shift.PDB_residue_name _Atom_chem_shift.PDB_atom_name \
         _Atom_chem_shift.Original_PDB_strand_ID _Atom_chem_shift.Original_PDB_residue_no \
         _Atom_chem_shift.Original_PDB_residue_name _Atom_chem_shift.Original_PDB_atom_name \
         _Atom_chem_shift.Details _Atom_chem_shift.Sf_ID _Atom_chem_shift.Entry_ID \
         _Atom_chem_shift.Assigned_chem_shift_list_ID stop_ ").unwrap());
}

#[test]
fn test_parsing_errors() {
    assert_parsing_error(Loop::from_str("loop_ _test.one _test.two 1 loop_"));
    assert_parsing_error(Loop::from_str("loop_ _test.one _test.two 1 stop_"));
    assert_parsing_error(Loop::from_str("loop_ _test.one _test.two 1 2 3 stop_"));
    assert_parsing_error(Loop::from_str("loop_ _test.one _test.two 1 2 3"));
    assert_parsing_error(Loop::from_str("loop_ _test.one _test.two 1 save_ stop_"));
}

#[test]
fn test_eq() {
    let test_loop = test_loop();
    assert!(test_loop == file_entry().frame_list[0].loops[0]);
    assert!(test_loop != second_loop());
    // (Comparing a loop to objects of other types is not possible in Rust.)
}

#[test]
fn test_len() {
    let test_loop = test_loop();
    assert_eq!(test_loop.len(), test_loop.data.len());
}

#[test]
fn test_lt() {
    assert!(test_loop() < second_loop());
    // A loop without a category is unordered (Python raised a TypeError)
    assert_eq!(Loop::new().partial_cmp(&test_loop()), None);
}

#[test]
fn test_contains() {
    let test_loop = test_loop();
    assert!(test_loop.contains_tag("Ordinal"));
    assert!(test_loop.contains_tag("_Entry_author.Ordinal"));
    assert!(!test_loop.contains_tag("NonexistentTag"));
    assert!(test_loop.contains_tags(&["Ordinal", "Family_name"]));
    assert!(!test_loop.contains_tags(&["Ordinal", "NonexistentTag"]));
}

#[test]
fn test_getitem() {
    let test_loop = test_loop();
    assert_eq!(test_loop.get_tag("_Entry_author.Ordinal").unwrap(), strs(&["1", "2", "3", "4", "5"]));
    let expected = vec![strs(&["1", "C."]), strs(&["2", "."]), strs(&["3", "B."]), strs(&["4", "H."]), strs(&["5", "L."])];
    assert_eq!(test_loop.get_tags(&["_Entry_author.Ordinal", "_Entry_author.Middle_initials"]).unwrap(), expected);
    assert_eq!(test_loop.data[0], test_loop.iter().next().unwrap().clone());
}

#[test]
fn test_setitem() {
    let mut test_loop = test_loop();
    test_loop.set_tag_values("_Entry_author.Ordinal", vec![Value::Int(1); 5]).unwrap();
    assert_eq!(test_loop.get_tag("_Entry_author.Ordinal").unwrap(), vec![Value::Int(1); 5]);
    test_loop.set_tag_values("_Entry_author.Ordinal", strs(&["1", "2", "3", "4", "5"])).unwrap();

    assert_value_error(test_loop.set_tag_values("_Entry_author.Ordinal", vec![Value::Int(1)]));
    assert_value_error(test_loop.set_tag_values("NonexistentTag", vec![Value::Int(1); 5]));
}

#[test]
fn test_str_and_format() {
    assert_eq!(Loop::new().format(false, false).unwrap(), "\n   loop_\n\n   stop_\n");
    assert_eq!(Loop::new().format(true, false).unwrap(), "");

    // Data but no tags
    let mut tmp_loop = Loop::new();
    tmp_loop.data = vec![row![1, 2, 3]];
    assert_value_error(tmp_loop.to_star());

    // Tags which do not match the data
    tmp_loop.add_tag("tag1").unwrap();
    assert_value_error(tmp_loop.to_star());
    tmp_loop.add_tag("tag2").unwrap();
    tmp_loop.add_tag("tag3").unwrap();
    assert_value_error(tmp_loop.to_star());

    // Once the category is set it works
    tmp_loop.set_category("test").unwrap();
    assert_eq!(tmp_loop.to_star().unwrap(),
               "\n   loop_\n      _test.tag1\n      _test.tag2\n      _test.tag3\n\n     1   2   3   \n\n   stop_\n");
    assert_eq!(tmp_loop.category(), Some("_test"));
}

#[test]
fn test_syntax_outliers() {
    // Semicolon-delimited data in a value must be properly escaped
    let mut ml = test_loop();
    ml.data[0][0] = Value::from(ml.to_star().unwrap());
    assert_eq!(ml, Loop::from_str(&ml.to_star().unwrap()).unwrap());
    // Twice could trigger a bug
    ml.data[0][0] = Value::from(ml.to_star().unwrap());
    assert_eq!(ml, Loop::from_str(&ml.to_star().unwrap()).unwrap());
    assert_eq!(ml.data[0][0], Loop::from_str(&ml.to_star().unwrap()).unwrap().data[0][0]);
    // Third time is a charm
    ml.data[0][0] = Value::from(ml.to_star().unwrap());
    assert_eq!(ml, Loop::from_str(&ml.to_star().unwrap()).unwrap());
    assert_eq!(ml.data[0][0], Loop::from_str(&ml.to_star().unwrap()).unwrap().data[0][0]);
}

#[test]
fn test_add_tag() {
    let mut tmp_loop = Loop::new();
    tmp_loop.set_category("test").unwrap();
    tmp_loop.data = vec![row![1, 2, 3]];
    tmp_loop.add_tags(&["tag1", "tag2", "tag3"]).unwrap();

    assert_value_error(tmp_loop.add_tag("invalid.tag"));
    assert_value_error(tmp_loop.add_tag("test.tag3"));
    tmp_loop.add_tag_with("test.tag3", true, false).unwrap();
    assert_value_error(tmp_loop.add_tag("test. tag"));
    assert_value_error(tmp_loop.add_tag("test.tag.test"));
}

#[test]
fn test_add_tag_with_update_data() {
    let mut tmp_loop = Loop::from_str("loop_ _Atom_chem_shift.ID stop_").unwrap();
    tmp_loop.data = vec![row![1]];
    tmp_loop.add_tag_with("Assembly_atom_ID", false, true).unwrap();
    assert_eq!(tmp_loop.data, vec![vec![Value::Int(1), Value::Null]]);
    assert_eq!(tmp_loop.tags(), ["ID", "Assembly_atom_ID"]);
}

fn pairs(values: &[(&str, Value)]) -> Vec<(String, Value)> {
    values.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
}

#[test]
fn test_add_data() {
    // Format 1: rows of (tag, value) pairs
    let mut test1 = Loop::from_scratch(Some("test")).unwrap();
    test1.add_tags(&["Name", "Location"]).unwrap();
    assert_value_error(test1.add_data(Data::Rows(vec![])));
    assert_value_error(test1.add_data(Data::Columns(vec![])));
    // (Python also refused None, and a dict whose values are not lists; Rust's types rule those out.)
    test1.add_data(Data::Dicts(vec![
        pairs(&[("name", "Jeff".into()), ("location", "Connecticut".into())]),
        pairs(&[("name", "Chad".into()), ("location", "Madison".into())]),
    ])).unwrap();

    // Format 2: columns
    let mut test2 = Loop::from_scratch(Some("test")).unwrap();
    test2.add_tags(&["Name", "Location"]).unwrap();
    test2.add_data(Data::Columns(vec![("name".to_string(), strs(&["Jeff", "Chad"])),
                                      ("location".to_string(), strs(&["Connecticut", "Madison"]))])).unwrap();

    // Format 3: rows
    let mut test3 = Loop::from_scratch(Some("test")).unwrap();
    test3.add_tags(&["Name", "Location"]).unwrap();
    assert_value_error(test3.add_data(Data::Rows(vec![strs(&["Jeff", "Connecticut"]), strs(&["Chad"])])));
    test3.add_data(Data::Rows(vec![strs(&["Jeff", "Connecticut"]), strs(&["Chad", "Madison"])])).unwrap();

    // Format 4: a flat list, rearranged
    let mut test4 = Loop::from_scratch(Some("test")).unwrap();
    test4.add_tags(&["Name", "Location"]).unwrap();
    assert_value_error(test4.add_data(Data::Flat(strs(&["Jeff", "Connecticut", "Chad", "Madison"]))));
    test4.add_data_with(Data::Flat(strs(&["Jeff", "Connecticut", "Chad", "Madison"])), true, false, None).unwrap();

    assert_eq!(test1, test2);
    assert_eq!(test2, test3);
    assert_eq!(test3, test4);
}

#[test]
fn test_add_data_simple() {
    let mut tmp_loop = Loop::new();
    tmp_loop.set_category("test").unwrap();
    tmp_loop.add_tags(&["tag1", "tag2", "tag3"]).unwrap();
    assert_value_error(tmp_loop.add_row(row![1, 2, 3, 4]));
    tmp_loop.add_row(row![1, 2, 3]).unwrap();
    tmp_loop.add_row(row![4, 5, 6]).unwrap();
    tmp_loop.add_row(row![7, 8, 9]).unwrap();
    assert_eq!(tmp_loop.data, vec![row![1, 2, 3], row![4, 5, 6], row![7, 8, 9]]);
}

#[test]
fn test_add_data_convert_data_types() {
    let mut test = Loop::from_scratch(Some("_Atom_chem_shift")).unwrap();
    test.add_tags(&["Val", "Entry_ID", "Details"]).unwrap();
    let data = Data::Dicts(vec![
        pairs(&[("details", "none".into()), ("vAL", "1.2".into())]),
        pairs(&[("val", 5.into()), ("details", ".".into())]),
    ]);
    test.add_data_with(data.clone(), false, true, None).unwrap();
    let decimal = |s: &str| Value::Decimal(Decimal::parse(s).unwrap());
    assert_eq!(test.data, vec![vec![decimal("1.2"), Value::Null, "none".into()],
                               vec![Value::Decimal(Decimal::from_i64(5)), Value::Null, Value::Null]]);
    // Decimals keep their digits
    assert_eq!(test.data[0][0].to_string(), "1.2");

    test.clear_data();
    test.add_data(data).unwrap();
    assert_eq!(test.data, vec![vec!["1.2".into(), Value::Null, "none".into()],
                               vec![Value::Int(5), Value::Null, ".".into()]]);
}

#[test]
fn test_add_missing_tags() {
    let mut tmp_loop = Loop::from_str("loop_ _Atom_chem_shift.ID stop_").unwrap();
    tmp_loop.add_missing_tags(None, false).unwrap();
    assert_eq!(tmp_loop, Loop::from_template("atom_chem_shift", false, None).unwrap());
}

#[test]
fn test_filter() {
    assert_eq!(test_loop().filter(&["_Entry_author.Ordinal", "_Entry_author.Middle_initials"], false).unwrap(),
               Loop::from_str("loop_ _Entry_author.Ordinal _Entry_author.Middle_initials 1 C. 2 . 3 B. 4 H. 5 L. stop_").unwrap());
}

#[test]
fn test_get_tag() {
    let tmp_loop = simple_loop("test", &["tag1", "tag2", "tag3"], vec![row![1, 5, 6], row![2, 8, 9]]);
    assert_value_error(tmp_loop.get_tag("invalid.tag1"));
    assert_eq!(tmp_loop.get_tag("tag1").unwrap(), row![1, 2]);
    assert_eq!(tmp_loop.get_tags(&["tag1", "tag2"]).unwrap(), vec![row![1, 5], row![2, 8]]);
    assert_eq!(tmp_loop.get_tag_whole("tag1").unwrap(),
               vec![("_test.tag1".to_string(), Value::Int(1)), ("_test.tag1".to_string(), Value::Int(2))]);
}

fn as_maps(rows: Vec<Vec<(String, Value)>>) -> Vec<BTreeMap<String, Value>> {
    rows.into_iter().map(|row| row.into_iter().collect()).collect()
}

fn maps(rows: &[&[(&str, &str)]]) -> Vec<BTreeMap<String, Value>> {
    rows.iter().map(|row| row.iter().map(|(k, v)| (k.to_string(), Value::from(*v))).collect()).collect()
}

#[test]
fn test_get_tag_dict_result() {
    let test_loop = test_loop();
    let expected = maps(&[
        &[("_Entry_author.Middle_initials", "C."), ("_Entry_author.Ordinal", "1")],
        &[("_Entry_author.Middle_initials", "."), ("_Entry_author.Ordinal", "2")],
        &[("_Entry_author.Middle_initials", "B."), ("_Entry_author.Ordinal", "3")],
        &[("_Entry_author.Middle_initials", "H."), ("_Entry_author.Ordinal", "4")],
        &[("_Entry_author.Middle_initials", "L."), ("_Entry_author.Ordinal", "5")],
    ]);
    assert_eq!(as_maps(test_loop.get_tags_dict(Some(&["_Entry_author.Ordinal", "_Entry_author.Middle_initials"]), false).unwrap()),
               expected);

    // The keys are the tags as given
    assert_eq!(as_maps(test_loop.get_tags_dict(Some(&["ORdinal", "MIddle_initials"]), false).unwrap()), maps(&[
        &[("MIddle_initials", "C."), ("ORdinal", "1")],
        &[("MIddle_initials", "."), ("ORdinal", "2")],
        &[("MIddle_initials", "B."), ("ORdinal", "3")],
        &[("MIddle_initials", "H."), ("ORdinal", "4")],
        &[("MIddle_initials", "L."), ("ORdinal", "5")],
    ]));

    // ... or with whole_tag, the tags as the loop spells them
    assert_eq!(as_maps(test_loop.get_tags_dict(Some(&["Ordinal", "Middle_initials"]), true).unwrap()), expected);
    assert_eq!(as_maps(test_loop.get_tags_dict(Some(&["_Entry_author.Ordinal", "_Entry_author.Middle_initials"]), true).unwrap()),
               expected);
}

#[test]
fn test_get_data_as_csv() {
    let tmp_loop = simple_loop("test", &["tag1", "tag2", "tag3"], vec![row![1, 5, 6], row![2, 8, 9]]);
    assert_eq!(tmp_loop.get_data_as_csv(true, true), "_test.tag1,_test.tag2,_test.tag3\n1,5,6\n2,8,9\n");
    assert_eq!(tmp_loop.get_data_as_csv(true, false), "tag1,tag2,tag3\n1,5,6\n2,8,9\n");
    assert_eq!(tmp_loop.get_data_as_csv(false, true), "1,5,6\n2,8,9\n");
    assert_eq!(tmp_loop.get_data_as_csv(false, false), "1,5,6\n2,8,9\n");
}

#[test]
fn test_remove_data_by_tag_value() {
    let mut tmp_loop = simple_loop("test", &["tag1", "tag2", "tag3"], vec![row![1, 2, 3], row![4, 5, 6], row![7, 8, 9]]);
    assert_eq!(tmp_loop.remove_data_by_tag_value("tag1", &Value::Int(1), Some("0")).unwrap(), vec![row![1, 2, 3]]);
    assert_eq!(tmp_loop.data, vec![row![1, 5, 6], row![2, 8, 9]]);
    assert_value_error(tmp_loop.remove_data_by_tag_value("tag4", &"data".into(), None));
}

#[test]
fn test_sort_rows() {
    let mut tmp_loop = simple_loop("test", &["tag1", "tag2", "tag3"], vec![row![1, 5, 6], row![2, 8, 9]]);
    tmp_loop.sort_rows_by_key(&["tag2"], |row| -row[2].py_int().unwrap()).unwrap();
    assert_eq!(tmp_loop.data, vec![row![2, 8, 9], row![1, 5, 6]]);
    tmp_loop.sort_rows(&["tag2"]).unwrap();
    assert_eq!(tmp_loop.data, vec![row![1, 5, 6], row![2, 8, 9]]);
}

#[test]
fn test_clear_data() {
    let mut tmp_loop = simple_loop("test", &["tag1", "tag2", "tag3"], vec![row![1, 2, 3], row![4, 5, 6]]);
    tmp_loop.clear_data();
    assert!(tmp_loop.data.is_empty());
}

#[test]
fn test_empty() {
    let mut tmp_loop = simple_loop("test", &["tag1", "tag2"], vec![]);
    assert!(tmp_loop.empty());
    tmp_loop.add_data(Data::Rows(vec![strs(&[".", "."]), strs(&["?", "?"])])).unwrap();
    assert!(tmp_loop.empty());
    tmp_loop.add_data(Data::Rows(vec![strs(&["value", "."])])).unwrap();
    assert!(!tmp_loop.empty());
}

#[test]
fn test_from_json() {
    let original = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"]), strs(&["c", "d"])]);

    let from_str = Loop::from_json(&original.to_json()).unwrap();
    assert_eq!(from_str.category(), original.category());
    assert_eq!(from_str.tags(), original.tags());
    assert_eq!(from_str.data, original.data);

    let from_value = Loop::from_json_value(&original.to_json_value()).unwrap();
    assert_eq!(from_value.category(), original.category());

    assert_value_error(Loop::from_json("not valid json"));
    assert_value_error(Loop::from_json(r#"{"tags": [], "category": "_test"}"#));
}

#[test]
fn test_get_json() {
    let tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    let json_str = tmp_loop.to_json();
    assert!(json_str.contains("\"category\""));
    assert!(json_str.contains("\"_test\""));
    assert_eq!(json_str, r#"{"category": "_test", "tags": ["tag1", "tag2"], "data": [["a", "b"]]}"#);

    let json = tmp_loop.to_json_value();
    assert_eq!(json.get("category").and_then(|c| c.as_str()), Some("_test"));
    assert_eq!(json.get("tags").unwrap().as_array().unwrap().len(), 2);
    assert_eq!(json.get("data").unwrap().as_array().unwrap().len(), 1);
}

#[test]
fn test_get_tag_names() {
    let tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    assert_eq!(tmp_loop.get_tag_names().unwrap(), vec!["_test.tag1", "_test.tag2"]);

    let mut tmp_loop2 = Loop::new();
    tmp_loop2.tags_mut().push("tag1".to_string());
    assert_invalid_state(tmp_loop2.get_tag_names());
}

#[test]
fn test_compare() {
    let test_loop = test_loop();
    assert!(test_loop.compare(&test_loop).is_empty());
    assert!(test_loop.compare_str(&test_loop.to_star().unwrap()).is_empty());
    assert_eq!(test_loop.compare_str(&(test_loop.to_star().unwrap() + "extra")), vec!["String was not exactly equal to loop."]);

    let loop1 = simple_loop("_test1", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    let loop2 = simple_loop("_test2", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    assert!(loop1.compare(&loop2).iter().any(|d| d.contains("Category of loops does not match")));

    let loop3 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    let loop4 = simple_loop("_test", &["tag1", "different"], vec![strs(&["a", "b"])]);
    assert!(loop3.compare(&loop4).iter().any(|d| d.contains("Loop tag names do not match")));

    let loop5 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"]), strs(&["c", "d"])]);
    let loop6 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["x", "y"]), strs(&["z", "w"])]);
    assert!(loop5.compare(&loop6).iter().any(|d| d.contains("Loop data does not match")));
}

#[test]
fn test_remove_tag() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2", "tag3"], vec![strs(&["a", "b", "c"]), strs(&["d", "e", "f"])]);
    tmp_loop.remove_tag("tag2").unwrap();
    assert_eq!(tmp_loop.tags(), ["tag1", "tag3"]);
    assert_eq!(tmp_loop.data, vec![strs(&["a", "c"]), strs(&["d", "f"])]);

    let mut tmp_loop2 = simple_loop("_test", &["tag1", "tag2", "tag3"], vec![strs(&["a", "b", "c"])]);
    tmp_loop2.remove_tags(&["tag1", "tag3"]).unwrap();
    assert_eq!(tmp_loop2.tags(), ["tag2"]);
    assert_eq!(tmp_loop2.data, vec![strs(&["b"])]);

    let mut tmp_loop3 = simple_loop("_test", &["tag1"], vec![]);
    assert_key_error(tmp_loop3.remove_tag("nonexistent_tag"));
}

#[test]
fn test_renumber_rows() {
    let mut tmp_loop = simple_loop("_test", &["ID", "Name"], vec![strs(&["5", "a"]), strs(&["10", "b"]), strs(&["15", "c"])]);
    tmp_loop.renumber_rows("ID", 1, false).unwrap();
    assert_eq!(tmp_loop.data, vec![strs(&["1", "a"]), strs(&["2", "b"]), strs(&["3", "c"])]);

    let mut tmp_loop2 = simple_loop("_test", &["ID", "Name"], vec![row![5, "a"], row![10, "b"], row![15, "c"]]);
    tmp_loop2.renumber_rows("ID", 10, false).unwrap();
    assert_eq!(tmp_loop2.data, vec![row![10, "a"], row![11, "b"], row![12, "c"]]);

    let mut tmp_loop3 = simple_loop("_test", &["ID", "Name"],
                                    vec![strs(&["2", "a"]), strs(&["3", "b"]), strs(&["3", "c"]), strs(&["5", "d"])]);
    tmp_loop3.renumber_rows("ID", 1, true).unwrap();
    assert_eq!(tmp_loop3.data, vec![strs(&["1", "a"]), strs(&["2", "b"]), strs(&["2", "c"]), strs(&["4", "d"])]);

    // By position
    let mut tmp_loop4 = simple_loop("_test", &["ID", "Name"], vec![row![5, "a"], row![10, "b"]]);
    tmp_loop4.renumber_rows("0", 1, false).unwrap();
    assert_eq!(tmp_loop4.data, vec![row![1, "a"], row![2, "b"]]);

    // An empty loop does nothing
    let mut tmp_loop5 = simple_loop("_test", &["ID", "Name"], vec![]);
    tmp_loop5.renumber_rows("ID", 1, false).unwrap();
    assert!(tmp_loop5.data.is_empty());

    let mut tmp_loop6 = simple_loop("_test", &["ID", "Name"], vec![row![1, "a"]]);
    assert_value_error(tmp_loop6.renumber_rows("nonexistent", 1, false));

    let mut tmp_loop7 = simple_loop("_test", &["ID", "Name"], vec![row![1, "a"]]);
    assert_value_error(tmp_loop7.renumber_rows("_different.ID", 1, false));

    let mut tmp_loop8 = simple_loop("_test", &["ID", "Name"], vec![strs(&["not_a_number", "a"])]);
    assert_value_error(tmp_loop8.renumber_rows("ID", 1, true));

    let mut tmp_loop9 = simple_loop("_test", &["ID", "Name"], vec![row![2, "a"], row![3, "b"], row![3, "c"], row![5, "d"]]);
    tmp_loop9.renumber_rows("ID", 1, true).unwrap();
    assert_eq!(tmp_loop9.data, vec![row![1, "a"], row![2, "b"], row![2, "c"], row![4, "d"]]);
}

#[test]
fn test_filter_edge_cases() {
    let tmp_loop = simple_loop("_test", &["tag1", "tag2", "tag3"], vec![strs(&["a", "b", "c"]), strs(&["d", "e", "f"])]);
    let result = tmp_loop.filter(&["tag1"], false).unwrap();
    assert_eq!(result.tags(), ["tag1"]);
    assert_eq!(result.data, vec![strs(&["a"]), strs(&["d"])]);

    assert_key_error(tmp_loop.filter(&["nonexistent_tag"], false));

    let result2 = tmp_loop.filter(&["tag1", "nonexistent_tag"], true).unwrap();
    assert_eq!(result2.tags(), ["tag1"]);
}

#[test]
fn test_str_skip_empty_tags() {
    let tmp_loop = simple_loop("_test", &["tag1", "tag2", "tag3"], vec![strs(&["a", ".", "c"]), strs(&["d", ".", "f"])]);
    assert!(tmp_loop.format(true, false).unwrap().contains("tag2"));
    let result_skip = tmp_loop.format(true, true).unwrap();
    assert!(!result_skip.contains("tag2"));
    assert!(result_skip.contains("tag1"));
    assert!(result_skip.contains("tag3"));
}

#[test]
fn test_parsing_edge_cases() {
    assert_parsing_error(Loop::from_str("loop_ _test1.tag1 a stop_ loop_ _test2.tag2 b stop_"));
    assert_parsing_error(Loop::from_str(""));
}

#[test]
fn test_get_tags_from_schema_invalid_prefix() {
    assert_invalid_state(Loop::tags_from_schema("nonexistent_category_xyz", None, false));
}

#[test]
fn test_add_data_edge_cases() {
    // Columns of uneven length
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop.add_data(Data::Columns(vec![("tag1".to_string(), strs(&["a", "b", "c"])),
                                         ("tag2".to_string(), strs(&["x"]))])).unwrap();
    assert_eq!(tmp_loop.data, vec![row!["a", "x"], row!["b", None::<&str>], row!["c", None::<&str>]]);

    let mut tmp_loop2 = simple_loop("_test", &["tag1", "tag2"], vec![]);
    assert_value_error(tmp_loop2.add_data(Data::Dicts(vec![pairs(&[("tag1", "a".into()), ("nonexistent", "b".into())])])));

    let mut tmp_loop3 = simple_loop("_test", &["tag1", "tag2"], vec![]);
    assert_value_error(tmp_loop3.add_data_with(Data::Flat(strs(&["a", "b", "c"])), true, false, None));
}

#[test]
#[allow(deprecated)]
fn test_add_data_by_tag_deprecated() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop.add_data_by_tag("tag1", "a".into()).unwrap();
    tmp_loop.add_data_by_tag("tag2", "b".into()).unwrap();
    tmp_loop.add_data_by_tag("tag1", "c".into()).unwrap();
    tmp_loop.add_data_by_tag("tag2", "d".into()).unwrap();
    assert_eq!(tmp_loop.data, vec![strs(&["a", "b"]), strs(&["c", "d"])]);

    assert_value_error(tmp_loop.add_data_by_tag("_different.tag1", "e".into()));
    assert_value_error(tmp_loop.add_data_by_tag("nonexistent", "e".into()));

    let mut tmp_loop2 = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop2.add_data_by_tag("tag1", "a".into()).unwrap();
    assert_value_error(tmp_loop2.add_data_by_tag("tag1", "c".into()));
}

#[test]
fn test_add_missing_tags_sort_exception() {
    let mut tmp_loop = Loop::from_str("loop_ _Atom_chem_shift.ID _Atom_chem_shift.Ordinal stop_").unwrap();
    tmp_loop.add_data(Data::Rows(vec![row!["1", None::<&str>], row!["2", None::<&str>]])).unwrap();
    // Sorting by the null Ordinal fails, so it is numbered instead
    tmp_loop.add_missing_tags(None, false).unwrap();
    let ordinal_idx = tmp_loop.tag_index("Ordinal").unwrap();
    assert_eq!(tmp_loop.data[0][ordinal_idx], Value::Int(1));
    assert_eq!(tmp_loop.data[1][ordinal_idx], Value::Int(2));
}

#[test]
fn test_add_tag_edge_cases() {
    let mut tmp_loop = Loop::from_scratch(Some("_test")).unwrap();
    tmp_loop.add_tag(".tag1").unwrap();
    assert_eq!(tmp_loop.tags(), ["tag1"]);

    let mut tmp_loop2 = Loop::from_scratch(Some("_test")).unwrap();
    assert_value_error(tmp_loop2.add_tag("."));
    assert_value_error(tmp_loop2.add_tag("?"));
}

#[test]
#[allow(deprecated)]
fn test_deprecated_delete_methods() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    tmp_loop.delete_tag("tag2").unwrap();
    assert_eq!(tmp_loop.tags(), ["tag1"]);

    let mut tmp_loop2 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"]), strs(&["c", "d"])]);
    tmp_loop2.delete_data_by_tag_value("tag1", &"a".into(), None).unwrap();
    assert_eq!(tmp_loop2.data, vec![strs(&["c", "d"])]);
}

#[test]
fn test_get_tag_edge_cases() {
    let tmp_loop = simple_loop("_test", &["tag1", "tag2", "tag3"], vec![strs(&["a", "b", "c"]), strs(&["d", "e", "f"])]);
    // Every tag: the data itself
    assert_eq!(tmp_loop.data, vec![strs(&["a", "b", "c"]), strs(&["d", "e", "f"])]);
    assert_eq!(as_maps(tmp_loop.get_tags_dict::<&str>(None, false).unwrap()), maps(&[
        &[("tag1", "a"), ("tag2", "b"), ("tag3", "c")],
        &[("tag1", "d"), ("tag2", "e"), ("tag3", "f")],
    ]));
    assert_key_error(tmp_loop.get_tag("nonexistent_tag"));
}

#[test]
fn test_print_tree() {
    let tmp_loop = simple_loop("_test", &["tag1"], vec![]);
    assert!(tmp_loop.repr().contains("_test"));
    tmp_loop.print_tree();
}

#[test]
fn test_remove_data_by_tag_value_category_mismatch() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    assert_value_error(tmp_loop.remove_data_by_tag_value("_different.tag1", &"a".into(), None));
}

#[test]
fn test_sort_rows_edge_cases() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["a", "b"])]);
    assert_value_error(tmp_loop.sort_rows(&["_different.tag1"]));

    // Values which are not numbers are sorted as text
    let mut tmp_loop2 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["b", "2"]), strs(&["a", "1"]), strs(&["c", "3"])]);
    tmp_loop2.sort_rows(&["tag1"]).unwrap();
    assert_eq!(tmp_loop2.data, vec![strs(&["a", "1"]), strs(&["b", "2"]), strs(&["c", "3"])]);

    let mut tmp_loop3 = simple_loop("_test", &["tag1", "tag2"], vec![strs(&["b", "2"]), strs(&["a", "1"]), strs(&["c", "3"])]);
    tmp_loop3.sort_rows_by_key(&["tag1"], |row| row[0].to_string()).unwrap();
    assert_eq!(tmp_loop3.data, vec![strs(&["a", "1"]), strs(&["b", "2"]), strs(&["c", "3"])]);

    // Null values can not be sorted
    let mut tmp_loop4 = simple_loop("_test", &["tag1"], vec![row![None::<&str>], row!["1"]]);
    assert!(matches!(tmp_loop4.sort_rows(&["tag1"]), Err(Error::Type(_))));
}

#[test]
fn test_validate_row_width_mismatch() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop.data = vec![strs(&["a", "b"]), strs(&["c"])];
    let errors = tmp_loop.validate(false, None, true, None);
    assert!(errors.iter().any(|e| e.contains("data width does not match")));
}

#[test]
fn test_validate_empty_rows() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop.data = vec![strs(&["a", "b"]), strs(&[".", "?"]), row!["", None::<&str>], strs(&[".", "b"])];
    assert_eq!(tmp_loop.validate(false, None, true, None),
               vec!["Loop '_test' row '1' contains only null values.", "Loop '_test' row '2' contains only null values."]);

    tmp_loop.data = vec![strs(&[".", "b"])];
    assert!(tmp_loop.validate(false, None, true, None).is_empty());
    tmp_loop.data = vec![];
    assert!(tmp_loop.validate(false, None, true, None).is_empty());
}

#[test]
fn test_validate_non_ascii() {
    let mut tmp_loop = simple_loop("_test", &["tag1", "tag2"], vec![]);
    tmp_loop.data = vec![strs(&["a", "b"]), strs(&["Ångström", "b"]), strs(&["a", "1–2"])];
    assert_eq!(tmp_loop.validate(false, None, true, None),
               vec!["Non-ASCII character(s) 'Å' (U+00C5), 'ö' (U+00F6) in tag '_test.tag1': 'Ångström'.",
                    "Non-ASCII character(s) '–' (U+2013) in tag '_test.tag2': '1–2'."]);
}
