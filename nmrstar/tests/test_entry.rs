//! Ported from pynmrstar/unit_tests/test_entry.py.

mod common;

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use common::*;
use nmrstar::repair::insert_mandatory_tags;
use nmrstar::utils::get_schema;
use nmrstar::validation::row_index_tag;
use nmrstar::{Entry, Loop, Saveframe, Severity, ValidationIssue, Value};
use rand::seq::SliceRandom;

fn frame_of<'a>(entry: &'a mut Entry, category: &str) -> &'a mut Saveframe {
    entry.get_saveframes_by_category_mut(category).into_iter().next().unwrap()
}

fn set_tag_value(frame: &mut Saveframe, tag: &str, value: impl Into<Value>) {
    frame.tag_mut(tag).unwrap().value = value.into();
}

fn details(pairs: &[(&str, Value)]) -> BTreeMap<String, Value> {
    pairs.iter().map(|(k, v)| (k.to_string(), v.clone())).collect()
}

fn validate_full(entry: &Entry, profile: Option<&str>) -> Vec<ValidationIssue> {
    entry.validate_full(None, profile, None, false).unwrap()
}

fn internal(entry: &Entry) -> Vec<ValidationIssue> {
    validate_full(entry, Some("internal"))
}

fn checks(issues: &[ValidationIssue]) -> Vec<&str> {
    issues.iter().map(|i| i.check.as_str()).collect()
}

/// The loop of a category in the first saveframe of a category.
fn loop_in<'a>(entry: &'a mut Entry, category: &str, loop_category: &str) -> &'a mut Loop {
    frame_of(entry, category).get_loop_mut(loop_category).unwrap()
}

/// The loop of a category in the saveframe with a name.
fn named_loop<'a>(entry: &'a mut Entry, name: &str, loop_category: &str) -> &'a mut Loop {
    entry.get_saveframe_by_name_mut(name).unwrap().get_loop_mut(loop_category).unwrap()
}

/// Remove a column from a loop, leaving its rows as wide as its tags.
fn drop_column(each_loop: &mut Loop, tag: &str) {
    let position = each_loop.tag_index(tag).unwrap();
    for row in &mut each_loop.data {
        row.remove(position);
    }
    each_loop.tags_mut().remove(position);
}

#[test]
fn test_edge_cases() {
    for name in ["edge_cases.str", "dos.str", "nonewlines.str", "onlynewlines.str"] {
        Entry::from_file(sample(name)).unwrap();
    }
}

#[test]
fn test_entry_delitem() {
    let mut file_entry = file_entry();
    let mut tmp_entry = file_entry.clone();
    tmp_entry.frame_list.remove(0);
    file_entry.remove_saveframe_at(0).unwrap();
    assert_eq!(file_entry, tmp_entry);
}

#[test]
fn test_duplicate_saveframe_errors() {
    let mut tmp_entry = file_entry();
    let first = tmp_entry.frame_list[0].clone();
    assert_value_error(tmp_entry.add_saveframe(first.clone()));
    tmp_entry.frame_list.push(first);
    assert_value_error(tmp_entry.frame_dict());
}

#[test]
fn test_entry_eq() {
    let mut db_copy = database_entry();
    db_copy.normalize(None).unwrap();
    let mut file_entry = file_entry();
    file_entry.normalize(None).unwrap();
    assert_eq!(file_entry, db_copy);
}

#[test]
fn test_getitem() {
    let file_entry = file_entry();
    assert_eq!(file_entry.get_saveframe_by_name("entry_information").unwrap(), &file_entry.frame_list[0]);
    assert_eq!(&file_entry.frame_list[0..2], &file_entry.frame_list.clone()[0..2]);
    assert_eq!(file_entry.frame_at(1).unwrap(), &file_entry.frame_list[1]);
    assert_key_error(file_entry.get_saveframe_by_name("no_such_saveframe"));
    assert_index_error(file_entry.frame_at(10000));
    // (Python refuses indexes of other types; Rust's types rule them out.)
}

#[test]
fn test_init() {
    let file_entry = file_entry();
    assert_parsing_error(Entry::from_str("test"));
    // String parsing
    assert_eq!(file_entry, Entry::from_str(&file_entry.to_star().unwrap()).unwrap());
    assert_eq!(file_entry.to_star().unwrap(), Entry::from_str(&file_entry.to_star().unwrap()).unwrap().to_star().unwrap());
    assert!(matches!(Entry::from_database("0"), Err(nmrstar::Error::Io(_))));
    // Chemcomps are found whatever the case of the ligand code or prefix
    for chemcomp_id in ["chemcomp_ATP", "chemcomp_atp", "ChemComp_Atp"] {
        let chemcomp = Entry::from_database(chemcomp_id).unwrap();
        assert_eq!(chemcomp.get_saveframes_by_category("chem_comp")[0].get_tag_required("ID").unwrap(), strs(&["ATP"]));
        assert_eq!(chemcomp.source.as_deref(), Some("from_database(chemcomp_ATP)"));
    }
    assert!(matches!(Entry::from_database("chemcomp_NOTALIGAND"), Err(nmrstar::Error::Io(_))));

    assert_eq!(Entry::from_scratch(15000).to_star().unwrap(), "data_15000\n\n");
    assert_eq!(Entry::from_file(sample("bmr15000_3.str.gz")).unwrap(), file_entry);
}

#[test]
fn test_from_file_path_support() {
    assert_eq!(Entry::from_file(Path::new(&sample_file_location())).unwrap(), file_entry());
}

#[test]
fn test_setitem() {
    let file_entry = file_entry();
    let mut tmp_entry = file_entry.clone();
    let info = tmp_entry.get_saveframe_by_name("entry_information").unwrap().clone();
    tmp_entry.set_saveframe_at(0, info.clone()).unwrap();
    assert_eq!(tmp_entry, file_entry);
    tmp_entry.set_saveframe("entry_information", info.clone()).unwrap();
    assert_eq!(tmp_entry, file_entry);
    assert_value_error(tmp_entry.set_saveframe("entry_informations", info));
    // (Python refuses assigning something other than a saveframe; Rust's types rule it out.)
}

#[test]
fn test_compare() {
    let file_entry = file_entry();
    assert!(file_entry.compare_str(&file_entry.to_star().unwrap()).is_empty());
    assert!(file_entry.compare(&file_entry).is_empty());

    let mut mutated = file_entry.clone();
    mutated.frame_list.pop();
    assert_eq!(file_entry.compare(&mutated),
               vec!["The number of saveframes in the entries are not equal: '25' vs '24'.",
                    "No saveframe with name 'assigned_chem_shift_list_1' in other entry."]);
}

#[test]
fn test_getmethods() {
    let file_entry = file_entry();
    assert_eq!(file_entry.get_loops_by_category("_Vendor").len(), 5);
    assert_eq!(file_entry.get_loops_by_category("vendor").len(), 5);

    assert_eq!(file_entry.get_saveframe_by_name("assigned_chem_shift_list_1").unwrap(), file_entry.frame_list.last().unwrap());
    assert_key_error(file_entry.get_saveframe_by_name("no such saveframe"));

    assert_eq!(file_entry.get_saveframes_by_category("NMR_spectrometer").len(), 6);
    assert_eq!(file_entry.get_saveframes_by_category("nmr_SPectrometer").len(), 0);
    assert!(file_entry.get_saveframes_by_category("no such category").is_empty());

    let date = Value::from("2006-09-07");
    assert_eq!(file_entry.get_saveframes_by_tag_and_value("Submission_date", &date), vec![&file_entry.frame_list[0]]);
    assert_eq!(file_entry.get_saveframes_by_tag_and_value("submission_Date", &date), vec![&file_entry.frame_list[0]]);
    assert!(file_entry.get_saveframes_by_tag_and_value("test.submission_date", &date).is_empty());

    assert_value_error(file_entry.get_tag("bad_tag"));
    assert_eq!(file_entry.get_tag("entry.Submission_date").unwrap(), strs(&["2006-09-07"]));
    assert_eq!(file_entry.get_tag_whole("entry.Submission_date").unwrap(),
               vec![("Submission_date".to_string(), Value::from("2006-09-07"))]);
}

fn structural(entry: &Entry, profile: Option<&str>, severities: Option<&[Severity]>) -> Vec<ValidationIssue> {
    entry.validate_full(None, profile, severities, false).unwrap().into_iter()
        .filter(|i| i.check.starts_with("saveframe.")).collect()
}

#[test]
fn test_validate_full() {
    let file_entry = file_entry();
    // A real archived entry is structurally clean
    assert!(structural(&file_entry, None, None).is_empty());

    // The Sf_framecode tag disagreeing with the saveframe's own name
    let mut entry = file_entry.clone();
    let frame = frame_of(&mut entry, "entry_information");
    set_tag_value(frame, "Sf_framecode", "something_else");
    let name = frame.name().to_string();
    let issues = structural(&entry, None, None);
    assert_eq!(checks(&issues), vec!["saveframe.framecode_mismatch"]);
    assert_eq!(issues[0].severity, Severity::Error);
    assert_eq!(issues[0].saveframe.as_deref(), Some(name.as_str()));
    assert_eq!(issues[0].value, Value::from("something_else"));
    assert_eq!(issues[0].tag.as_deref(), Some("_Entry.Sf_framecode"));

    // An Sf_category value that disagrees with the dictionary
    let mut entry = file_entry.clone();
    set_tag_value(frame_of(&mut entry, "entry_information"), "Sf_category", "not_a_category");
    let issues = structural(&entry, None, None);
    assert_eq!(checks(&issues), vec!["saveframe.invalid_category"]);
    assert_eq!(issues[0].category.as_deref(), Some("entry_information"));

    // A missing mandatory saveframe category
    let mut entry = file_entry.clone();
    let citations = entry.get_saveframes_by_category("citations")[0].clone();
    entry.remove_saveframe_obj(&citations).unwrap();
    assert!(checks(&structural(&entry, None, None)).contains(&"saveframe.missing_mandatory_category"));

    // Profiles differ, and an unknown one is rejected
    assert!(structural(&file_entry, Some("internal"), None).is_empty());
    assert!(validate_full(&file_entry, Some("internal")).len() > validate_full(&file_entry, Some("public")).len());
    assert_value_error(file_entry.validate_full(None, Some("nope"), None, false));

    // Severity filtering
    let mut entry = file_entry.clone();
    set_tag_value(frame_of(&mut entry, "entry_information"), "Sf_framecode", "something_else");
    assert!(entry.validate_full(None, None, Some(&[Severity::Warning]), false).unwrap().is_empty());
    assert_eq!(structural(&entry, None, Some(&[Severity::Error])).len(), 1);
}

#[test]
fn test_validate_full_saveframe_details() {
    let file_entry = file_entry();
    let mut entry = file_entry.clone();
    let first = entry.get_saveframes_by_category("entry_information")[0].clone();
    let mut second = first.clone();
    second.set_name("entry_information_2").unwrap();
    // Appended after the citations etc., so it is also out of order
    entry.add_saveframe(second).unwrap();
    let issues: Vec<ValidationIssue> = validate_full(&entry, None).into_iter()
        .filter(|i| i.saveframe.as_deref() == Some("entry_information_2")).collect();
    let by_check = |check: &str| issues.iter().find(|i| i.check == check).unwrap().clone();
    assert_eq!(by_check("saveframe.duplicate_category").details,
               details(&[("previous_saveframe", first.name().into())]));
    let order = by_check("saveframe.order").details;
    assert_eq!(order["previous_saveframe"], Value::from(entry.frame_list[entry.len() - 2].name()));
    assert!(order["previous_ordinal"].py_cmp(&order["ordinal"]) == Some(std::cmp::Ordering::Greater));

    // Saveframe names are compared without regard to case
    let mut entry = file_entry.clone();
    let mut third = first.clone();
    third.set_name(&first.name().to_uppercase()).unwrap();
    entry.add_saveframe(third).unwrap();
    let issues: Vec<_> = validate_full(&entry, None).into_iter().filter(|i| i.check == "saveframe.duplicate_name").collect();
    assert_eq!(issues.iter().map(|i| i.details.clone()).collect::<Vec<_>>(),
               vec![details(&[("previous_saveframe", first.name().into())])]);
}

#[test]
fn test_validate_full_mandatory() {
    let mut entry = file_entry();
    let title_checks = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check.starts_with("tag.") && i.tag.as_deref() == Some("_Entry.Title")).collect()
    };

    // Emptying a value-mandatory tag is a missing value, and removing it a missing tag
    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.Title", ".");
    assert_eq!(checks(&title_checks(&entry)), vec!["tag.missing_value"]);

    let frame = frame_of(&mut entry, "entry_information");
    frame.remove_tag("Title").unwrap();
    let name = frame.name().to_string();
    let found = title_checks(&entry);
    assert_eq!(checks(&found), vec!["tag.missing"]);
    assert_eq!(found[0].saveframe.as_deref(), Some(name.as_str()));
    assert_eq!(found[0].category.as_deref(), Some("entry_information"));
    assert_eq!(found[0].details, details(&[("requires_value", true.into())]));
}

#[test]
fn test_validate_full_mandatory_first_value_only() {
    let mut entry = file_entry();
    let name = entry.get_saveframes_by_category("sample_conditions")[0].name().to_string();
    let missing_value = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter()
            .filter(|i| i.check == "tag.missing_value" && i.tag.as_deref() == Some("_Sample_condition_variable.Val")).collect()
    };
    let column = loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").tags().iter().position(|t| t == "Val").unwrap();
    let rows = loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").data.len();
    assert!(rows > 1, "the fixture needs a multi-row loop");

    // Every row populated: nothing to report
    assert!(missing_value(&entry).is_empty());

    // Null in a row that is not the first: never looked at
    let original = std::mem::replace(&mut loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").data[rows - 1][column], ".".into());
    assert!(missing_value(&entry).is_empty());
    loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").data[rows - 1][column] = original;

    // Null in the first row: reported, even though every other row has one
    let original = std::mem::replace(&mut loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").data[0][column], ".".into());
    let found = missing_value(&entry);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].saveframe.as_deref(), Some(name.as_str()));
    loop_in(&mut entry, "sample_conditions", "_Sample_condition_variable").data[0][column] = original;
}

#[test]
fn test_fix_framecodes() {
    let mut entry = file_entry();
    // Sf_framecode is set to the saveframe's own name
    set_tag_value(frame_of(&mut entry, "entry_information"), "Sf_framecode", "something_else");
    entry.fix_framecodes(None);
    let frame = frame_of(&mut entry, "entry_information");
    assert_eq!(frame.get_tag("Sf_framecode").unwrap()[0], Value::from(frame.name()));

    // Whitespace inside a saveframe-pointer value collapses to a single underscore
    set_tag_value(frame_of(&mut entry, "assigned_chemical_shifts"), "Sample_condition_list_label", "$a b\tc");
    entry.fix_framecodes(None);
    assert_eq!(frame_of(&mut entry, "assigned_chemical_shifts").get_tag("Sample_condition_list_label").unwrap()[0],
               Value::from("$a_b_c"));
}

#[test]
fn test_fix_framecodes_leaves_nulls_alone() {
    let mut entry = file_entry();
    for null in [".", "?"] {
        set_tag_value(frame_of(&mut entry, "assigned_chemical_shifts"), "Sample_condition_list_label", null);
        entry.fix_framecodes(None);
        assert_eq!(frame_of(&mut entry, "assigned_chemical_shifts").get_tag("Sample_condition_list_label").unwrap()[0],
                   Value::from(null));
    }
}

#[test]
fn test_mark_framecode_values() {
    let mut entry = file_entry();
    let pointer = frame_of(&mut entry, "assigned_chemical_shifts").get_tag("Sample_condition_list_label").unwrap()[0].to_string();
    assert!(pointer.starts_with('$'));

    set_tag_value(frame_of(&mut entry, "assigned_chemical_shifts"), "Sample_condition_list_label", pointer.trim_start_matches('$'));
    entry.mark_framecode_values(None);
    assert_eq!(frame_of(&mut entry, "assigned_chemical_shifts").get_tag("Sample_condition_list_label").unwrap()[0],
               Value::from(pointer.as_str()));

    // Idempotent: running it again must not stack markers
    entry.mark_framecode_values(None);
    assert!(!frame_of(&mut entry, "assigned_chemical_shifts").get_tag("Sample_condition_list_label").unwrap()[0]
        .to_string().starts_with("$$"));
}

#[test]
fn test_normalize_repairs_framecodes() {
    let mut entry = file_entry();
    set_tag_value(frame_of(&mut entry, "entry_information"), "Sf_framecode", "something_else");
    let mismatches = |entry: &Entry| internal(entry).into_iter().filter(|i| i.check == "saveframe.framecode_mismatch").count();
    assert_eq!(mismatches(&entry), 1);

    entry.normalize(None).unwrap();
    let frame = frame_of(&mut entry, "entry_information");
    assert_eq!(frame.get_tag("Sf_framecode").unwrap()[0], Value::from(frame.name()));
    assert_eq!(mismatches(&entry), 0);
}

#[test]
fn test_add_row_indexes() {
    let mut entry = file_entry();
    let position = loop_in(&mut entry, "entry_information", "_Entry_author").tags().iter().position(|t| t == "Ordinal").unwrap();
    let rows = loop_in(&mut entry, "entry_information", "_Entry_author").data.len();
    let expected: Vec<Value> = (1..=rows).map(|i| Value::from(i.to_string())).collect();
    let column = |entry: &mut Entry| loop_in(entry, "entry_information", "_Entry_author").data.iter().map(|r| r[position].clone()).collect::<Vec<_>>();

    // A gap is filled
    loop_in(&mut entry, "entry_information", "_Entry_author").data[1][position] = ".".into();
    entry.add_row_indexes(None).unwrap();
    assert_eq!(column(&mut entry), expected);

    // ... and so is a column that is complete but wrong
    for (i, row) in loop_in(&mut entry, "entry_information", "_Entry_author").data.iter_mut().enumerate() {
        row[position] = Value::from(((i + 1) * 10).to_string());
    }
    entry.add_row_indexes(None).unwrap();
    assert_eq!(column(&mut entry), expected);
}

#[test]
fn test_normalize_renumbers_a_referenced_row_index() {
    let mut entry = file_entry();
    let times_ten = |value: &mut Value| *value = Value::from((value.py_int().unwrap() * 10).to_string());

    let index = frame_of(&mut entry, "entity").get_loop_mut("_Entity_comp_index").unwrap();
    let at_index = index.tags().iter().position(|t| t == "ID").unwrap();
    for row in &mut index.data {
        times_ten(&mut row[at_index]);
    }
    let shifts = entry.get_saveframe_by_name_mut("assigned_chem_shift_list_1").unwrap().get_loop_mut("_Atom_chem_shift").unwrap();
    let at_shift = shifts.tags().iter().position(|t| t == "Comp_index_ID").unwrap();
    for row in &mut shifts.data {
        times_ten(&mut row[at_shift]);
    }

    entry.normalize(None).unwrap();
    let index = entry.get_saveframes_by_category("entity")[0].get_loop("_Entity_comp_index").unwrap();
    let ids: Vec<Value> = index.data.iter().map(|r| r[at_index].clone()).collect();
    assert_eq!(ids, (1..=index.data.len()).map(|i| Value::from(i.to_string())).collect::<Vec<_>>());
    let shifts = entry.get_saveframe_by_name("assigned_chem_shift_list_1").unwrap().get_loop("_Atom_chem_shift").unwrap();
    let shift_ids: HashSet<String> = shifts.data.iter().map(|r| r[at_shift].to_string()).collect();
    let index_ids: HashSet<String> = ids.iter().map(|v| v.to_string()).collect();
    assert!(shift_ids.is_subset(&index_ids));
}

#[test]
fn test_normalize_will_not_renumber_an_ambiguous_row_index() {
    let mut entry = file_entry();
    let mut second = entry.get_saveframes_by_category("entity")[0].clone();
    second.set_name("entity_2").unwrap();
    entry.add_saveframe(second).unwrap();

    for frame in entry.get_saveframes_by_category_mut("entity") {
        drop_column(frame.get_loop_mut("_Entity_comp_index").unwrap(), "Entity_ID");
    }

    let first_loop = frame_of(&mut entry, "entity").get_loop_mut("_Entity_comp_index").unwrap();
    let at_index = first_loop.tags().iter().position(|t| t == "ID").unwrap();
    let scrambled: Vec<Value> = first_loop.data.iter().map(|r| Value::from((r[at_index].py_int().unwrap() * 10).to_string())).collect();
    for (row, value) in first_loop.data.iter_mut().zip(&scrambled) {
        row[at_index] = value.clone();
    }

    entry.normalize(None).unwrap();
    let first_loop = entry.get_saveframes_by_category("entity")[0].get_loop("_Entity_comp_index").unwrap();
    assert_eq!(first_loop.data.iter().map(|r| r[at_index].clone()).collect::<Vec<_>>(), scrambled);
}

#[test]
fn test_normalize_leaves_a_duplicated_row_index_alone() {
    let mut entry = file_entry();
    let index_loop = frame_of(&mut entry, "entity").get_loop_mut("_Entity_comp_index").unwrap();
    let at_index = index_loop.tags().iter().position(|t| t == "ID").unwrap();
    index_loop.data[1][at_index] = index_loop.data[0][at_index].clone();
    let before: Vec<Value> = index_loop.data.iter().map(|r| r[at_index].clone()).collect();

    entry.normalize(None).unwrap();
    let index_loop = entry.get_saveframes_by_category("entity")[0].get_loop("_Entity_comp_index").unwrap();
    assert_eq!(index_loop.data.iter().map(|r| r[at_index].clone()).collect::<Vec<_>>(), before);
}

#[test]
fn test_normalize_renumbers_each_atom_from_its_own_entity() {
    fn entity(entity_id: i32, residues: &[i32]) -> String {
        let rows: Vec<String> = residues.iter().map(|r| format!("{} {} 1", r, entity_id)).collect();
        format!("save_entity_{id}\n_Entity.Sf_category entity\n_Entity.Sf_framecode entity_{id}\n_Entity.ID {id}\n\
                 _Entity.Entry_ID 1\nloop_\n_Entity_comp_index.ID\n_Entity_comp_index.Entity_ID\n_Entity_comp_index.Entry_ID\n\
                 {rows}\nstop_\nsave_\n", id = entity_id, rows = rows.join("\n"))
    }

    // Both entities' residues are misnumbered, and differently
    let mut entry = Entry::from_str(&format!(
        "data_1\n{}{}save_constraints\n_Gen_dist_constraint_list.Sf_category general_distance_constraints\n\
         _Gen_dist_constraint_list.Sf_framecode constraints\n_Gen_dist_constraint_list.ID 1\n\
         _Gen_dist_constraint_list.Entry_ID 1\nloop_\n_Gen_dist_constraint.ID\n\
         _Gen_dist_constraint.Member_ID\n_Gen_dist_constraint.Entity_ID_1\n\
         _Gen_dist_constraint.Comp_index_ID_1\n_Gen_dist_constraint.Entity_ID_2\n\
         _Gen_dist_constraint.Comp_index_ID_2\n_Gen_dist_constraint.Entry_ID\n\
         _Gen_dist_constraint.Gen_dist_constraint_list_ID\n1 1 2 5 1 5 1 1\nstop_\nsave_\n",
        entity(1, &[3, 4, 5]), entity(2, &[5, 6, 7]))).unwrap();

    entry.normalize(None).unwrap();
    let constraint = entry.get_loops_by_category("_Gen_dist_constraint")[0];
    assert_eq!(constraint.get_tags(&["Entity_ID_1", "Comp_index_ID_1", "Entity_ID_2", "Comp_index_ID_2"]).unwrap(),
               vec![strs(&["2", "1", "1", "3"])]);
}

#[test]
fn test_normalize_keeps_blank_references_to_a_row_index_blank() {
    let mut entry = Entry::from_str(
        "data_1\nsave_entity_1\n_Entity.Sf_category entity\n_Entity.Sf_framecode entity_1\n\
         _Entity.ID 1\n_Entity.Entry_ID 1\n\
         loop_\n_Entity_comp_index.ID\n_Entity_comp_index.Comp_ID\n_Entity_comp_index.Entity_ID\n\
         _Entity_comp_index.Entry_ID\n1 ALA 1 1\n. GLY 1 1\nstop_\n\
         loop_\n_Entity_poly_seq.Hetero\n_Entity_poly_seq.Mon_ID\n_Entity_poly_seq.Num\n\
         _Entity_poly_seq.Comp_index_ID\n_Entity_poly_seq.Entity_ID\n_Entity_poly_seq.Entry_ID\n\
         . ALA 1 1 1 1\n. GLY 2 . 1 1\nstop_\nsave_\n").unwrap();

    entry.normalize(None).unwrap();
    let frame = entry.get_saveframe_by_name("entity_1").unwrap();
    assert_eq!(frame.get_loop("_Entity_comp_index").unwrap().get_tag("ID").unwrap(), strs(&["1", "2"]));
    assert_eq!(frame.get_loop("_Entity_poly_seq").unwrap().get_tag("Comp_index_ID").unwrap(), strs(&["1", "."]));
}

#[test]
fn test_normalize_numbers_several_blank_row_indexes() {
    let mut entry = Entry::from_str(
        "data_1\nsave_entity_1\n_Entity.Sf_category entity\n_Entity.Sf_framecode entity_1\n\
         _Entity.ID 1\n_Entity.Entry_ID 1\n\
         loop_\n_Entity_comp_index.ID\n_Entity_comp_index.Comp_ID\n_Entity_comp_index.Entity_ID\n\
         _Entity_comp_index.Entry_ID\n. ALA 1 1\n7 GLY 1 1\n. SER 1 1\nstop_\n\
         loop_\n_Entity_poly_seq.Hetero\n_Entity_poly_seq.Mon_ID\n_Entity_poly_seq.Num\n\
         _Entity_poly_seq.Comp_index_ID\n_Entity_poly_seq.Entity_ID\n_Entity_poly_seq.Entry_ID\n\
         . ALA 1 . 1 1\n. GLY 2 7 1 1\n. SER 3 . 1 1\nstop_\nsave_\n").unwrap();

    entry.normalize(None).unwrap();
    let frame = entry.get_saveframe_by_name("entity_1").unwrap();
    assert_eq!(frame.get_loop("_Entity_comp_index").unwrap().get_tag("ID").unwrap(), strs(&["1", "2", "3"]));
    assert_eq!(frame.get_loop("_Entity_poly_seq").unwrap().get_tag("Comp_index_ID").unwrap(), strs(&[".", "2", "."]));
}

#[test]
fn test_normalize_keeps_an_id_its_label_cannot_supply() {
    let mut entry = Entry::from_str(
        "data_1\nsave_entity_1\n_Entity.Sf_category entity\n_Entity.Sf_framecode entity_1\n\
         _Entity.ID 1\n_Entity.Entry_ID 1\n_Entity.Type non-polymer\n\
         _Entity.Nonpolymer_comp_ID ZN\n_Entity.Nonpolymer_comp_label $chem_comp_ZN\n\
         loop_\n_Entity_comp_index.ID\n_Entity_comp_index.Comp_ID\n_Entity_comp_index.Comp_label\n\
         _Entity_comp_index.Entity_ID\n_Entity_comp_index.Entry_ID\n1 ZN $chem_comp_ZN 1 1\nstop_\nsave_\n\
         save_chem_comp_ZN\n_Chem_comp.Sf_category chem_comp\n_Chem_comp.Sf_framecode chem_comp_ZN\n\
         _Chem_comp.ID .\n_Chem_comp.Entry_ID 1\nsave_\n").unwrap();

    entry.normalize(None).unwrap();
    let frame = entry.get_saveframe_by_name("entity_1").unwrap();
    assert_eq!(frame.get_tag("Nonpolymer_comp_ID").unwrap(), strs(&["ZN"]));
    assert_eq!(frame.get_loop("_Entity_comp_index").unwrap().get_tag("Comp_ID").unwrap(), strs(&["ZN"]));

    // ... and an ID the target does carry still wins
    entry.get_saveframe_by_name_mut("chem_comp_ZN").unwrap().set_tag("ID", "ZN2").unwrap();
    entry.normalize(None).unwrap();
    let frame = entry.get_saveframe_by_name("entity_1").unwrap();
    assert_eq!(frame.get_tag("Nonpolymer_comp_ID").unwrap(), strs(&["ZN2"]));
    assert_eq!(frame.get_loop("_Entity_comp_index").unwrap().get_tag("Comp_ID").unwrap(), strs(&["ZN2"]));
}

#[test]
fn test_repair_insert_mandatory_tags() {
    let mut entry = file_entry();
    let frame = frame_of(&mut entry, "entry_information");
    assert_eq!(frame.get_tag("Title").unwrap(), file_entry().get_tag("_Entry.Title").unwrap());
    frame.remove_tag("Title").unwrap();

    insert_mandatory_tags(&mut entry, None, Some("internal"), true, None).unwrap();
    assert_eq!(frame_of(&mut entry, "entry_information").get_tag("Title").unwrap(), strs(&["?"]));
}

#[test]
fn test_repair_insert_mandatory_tags_skips_optional_and_auto() {
    let mut entry = file_entry();
    let schema = get_schema(None);
    let codes = schema.validation_profile(Some("internal")).unwrap();

    let entry_tags = |kind: &dyn Fn(char, bool) -> bool| -> HashSet<String> {
        schema.tags().filter(|(tag, data)| data.get("SFCategory") == "entry_information"
            && data.get("Loopflag").trim() != "Y"
            && kind(codes.tags.get(*tag).copied().unwrap_or(' '), schema.auto_inserted_tags.contains(*tag)))
            .map(|(tag, _)| tag.to_string()).collect()
    };
    let optional = entry_tags(&|code, auto| code == 'O' && !auto);
    let auto = entry_tags(&|code, auto| (code == 'M' || code == 'V') && auto);
    assert!(!optional.is_empty() && !auto.is_empty());

    let present = |entry: &mut Entry| -> HashSet<String> {
        let frame = frame_of(entry, "entry_information");
        let prefix = frame.tag_prefix.clone().unwrap();
        frame.tags().iter().map(|t| format!("{}.{}", prefix, t.name).to_lowercase()).collect()
    };
    let before = present(&mut entry);
    insert_mandatory_tags(&mut entry, None, Some("internal"), true, None).unwrap();
    let added: HashSet<String> = present(&mut entry).difference(&before).cloned().collect();
    assert!(!added.is_empty());
    assert!(added.is_disjoint(&optional.union(&auto).cloned().collect()));
}

#[test]
fn test_repair_insert_mandatory_tags_creates_a_missing_loop() {
    let mut entry = file_entry();
    frame_of(&mut entry, "entry_information").remove_loop("_Entry_author").unwrap();

    insert_mandatory_tags(&mut entry, None, Some("internal"), true, Some("NEED_ACC_NUM".into())).unwrap();
    let author = frame_of(&mut entry, "entry_information").get_loop("_Entry_author").unwrap().clone();
    assert_eq!(author.data.len(), 1);
    assert_eq!(author.data[0][author.tag_index("Ordinal").unwrap()], "0");
    assert_eq!(author.data[0][author.tag_index("Entry_ID").unwrap()], "NEED_ACC_NUM");
    assert_eq!(author.data[0][author.tag_index("Family_name").unwrap()], "?");
    // Optional columns come along too
    assert!(author.tags().iter().any(|t| t.to_lowercase() == "middle_initials"));
    // Sf_ID is bookkeeping, not a column for anyone to fill in
    assert!(!author.tags().iter().any(|t| t.to_lowercase() == "sf_id"));
}

#[test]
fn test_repair_insert_mandatory_tags_fills_an_existing_loop() {
    let mut entry = file_entry();
    let author = frame_of(&mut entry, "entry_information").get_loop_mut("_Entry_author").unwrap();
    assert!(author.data.len() > 1);
    drop_column(author, "Family_name");

    insert_mandatory_tags(&mut entry, None, Some("internal"), true, None).unwrap();
    let author = frame_of(&mut entry, "entry_information").get_loop("_Entry_author").unwrap();
    let position = author.tag_index("Family_name").unwrap();
    assert_eq!(author.data.iter().map(|r| r[position].clone()).collect::<Vec<_>>(), vec![Value::from("?"); author.data.len()]);
}

#[test]
fn test_repair_insert_mandatory_tags_honours_a_conditional_rule() {
    let mut entry = file_entry();
    let mut non_polymer = entry.get_saveframes_by_category("entity")[0].clone();
    non_polymer.set_name("entity_non_polymer").unwrap();
    non_polymer.remove_tag("Nstd_monomer").unwrap();
    non_polymer.set_tag("Type", "non-polymer").unwrap();
    let polymer = frame_of(&mut entry, "entity");
    polymer.remove_tag("Nstd_monomer").unwrap();
    polymer.set_tag("Type", "polymer").unwrap();
    entry.add_saveframe(non_polymer).unwrap();

    insert_mandatory_tags(&mut entry, None, Some("internal"), true, None).unwrap();
    let entities = entry.get_saveframes_by_category("entity");
    assert_eq!(entities[0].get_tag("Nstd_monomer").unwrap(), strs(&["?"]));
    assert!(entry.get_saveframe_by_name("entity_non_polymer").unwrap().get_tag("Nstd_monomer").unwrap().is_empty());
}

#[test]
fn test_validate_full_invalid_tags() {
    let mut entry = file_entry();
    let invalid = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| ["tag.unknown", "tag.miscapitalized", "tag.free_in_loop",
                                                "tag.duplicate", "tag.invalid"].contains(&i.check.as_str())).collect()
    };

    // An archived entry uses no tag it should not
    assert!(invalid(&entry).is_empty());

    // A tag the dictionary has never heard of
    let frame = frame_of(&mut entry, "entry_information");
    frame.add_tag("_Entry.Bogus_invented_tag", "fnord").unwrap();
    let name = frame.name().to_string();
    let found = invalid(&entry);
    assert_eq!(checks(&found), vec!["tag.unknown"]);
    assert_eq!(found[0].tag.as_deref(), Some("_Entry.Bogus_invented_tag"));
    assert_eq!(found[0].saveframe.as_deref(), Some(name.as_str()));
    frame_of(&mut entry, "entry_information").remove_tag("Bogus_invented_tag").unwrap();

    // A real tag spelled with the wrong capitalization
    frame_of(&mut entry, "entry_information").tag_mut("_Entry.Submission_date").unwrap().name = "SUBMISSION_date".to_string();
    let found = invalid(&entry);
    assert_eq!(checks(&found), vec!["tag.miscapitalized"]);
    assert!(found[0].message.contains("Should be '_Entry.Submission_date'"));
    assert_eq!(found[0].details, details(&[("correct", "_Entry.Submission_date".into())]));
    frame_of(&mut entry, "entry_information").tag_mut("SUBMISSION_date").unwrap().name = "Submission_date".to_string();

    // A tag the profile forbids outright
    frame_of(&mut entry, "entry_information").add_tag("_Entry.Sf_ID", "1").unwrap();
    assert_eq!(checks(&invalid(&entry)), vec!["tag.invalid"]);
    frame_of(&mut entry, "entry_information").remove_tag("Sf_ID").unwrap();

    // A loop whose columns are all tags the dictionary marks as free, and which are already free
    //  tags of the saveframe
    let mut free_loop = Loop::from_scratch(Some("_Entry")).unwrap();
    free_loop.add_tags(&["_Entry.Experimental_method", "_Entry.Origination"]).unwrap();
    free_loop.add_row(strs(&["NMR", "author"])).unwrap();
    frame_of(&mut entry, "entry_information").add_loop(free_loop).unwrap();
    let found = invalid(&entry);
    let mut found_checks = checks(&found);
    found_checks.sort();
    assert_eq!(found_checks, ["tag.duplicate"; 4].iter().chain(["tag.free_in_loop"; 2].iter()).copied().collect::<Vec<_>>());
    let tags: HashSet<&str> = found.iter().map(|i| i.tag.as_deref().unwrap()).collect();
    assert_eq!(tags, HashSet::from(["_Entry.Experimental_method", "_Entry.Origination"]));
}

#[test]
fn test_validate_full_tag_order() {
    let mut entry = file_entry();
    let order = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check == "tag.order").collect()
    };
    assert!(order(&entry).is_empty());

    // Move the fourth of four consecutive tags to the front of them: exactly one finding
    let frame = frame_of(&mut entry, "entry_information");
    let prefix = frame.tag_prefix.clone().unwrap();
    let name = frame.name().to_string();
    let tags = frame.tags_mut();
    let start = (0..tags.len() - 3).find(|&i| (0..4).all(|n| !tags[i + n].name.contains('.'))).unwrap();
    let run: Vec<_> = tags[start..start + 4].to_vec();
    tags.splice(start..start + 4, [run[0].clone(), run[3].clone(), run[1].clone(), run[2].clone()]);

    let found = order(&entry);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].tag, Some(format!("{}.{}", prefix, run[1].name)));
    assert_eq!(found[0].saveframe.as_deref(), Some(name.as_str()));
    assert_eq!(found[0].loop_category, None);
    assert_eq!(found[0].details["previous_tag"], Value::from(format!("{}.{}", prefix, run[3].name)));
}

#[test]
fn test_validate_full_row_indexes() {
    let mut entry = file_entry();
    let column = loop_in(&mut entry, "entity", "_Entity_comp_index").tag_index("ID").unwrap();
    let indexes = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check.starts_with("row.")).collect()
    };

    assert!(indexes(&entry).is_empty());

    // A non-numeric index
    loop_in(&mut entry, "entity", "_Entity_comp_index").data[2][column] = ".".into();
    let found = indexes(&entry);
    assert_eq!(checks(&found), vec!["row.index_not_a_number"]);
    assert_eq!(found[0].row, Some(2));
    assert_eq!(found[0].tag.as_deref(), Some("_Entity_comp_index.ID"));
    assert_eq!(found[0].loop_category.as_deref(), Some("_Entity_comp_index"));
    loop_in(&mut entry, "entity", "_Entity_comp_index").data[2][column] = "3".into();

    // A lone wrong index costs two findings
    loop_in(&mut entry, "entity", "_Entity_comp_index").data[2][column] = "99".into();
    let found = indexes(&entry);
    assert_eq!(checks(&found), vec!["row.index_wrong"; 2]);
    assert_eq!(found.iter().map(|i| i.details.clone()).collect::<Vec<_>>(),
               vec![details(&[("expected", 3.into())]), details(&[("expected", 100.into())])]);
    loop_in(&mut entry, "entity", "_Entity_comp_index").data[2][column] = "3".into();

    // A whole loop numbered from zero is reported once
    for (number, row) in loop_in(&mut entry, "entity", "_Entity_comp_index").data.iter_mut().enumerate() {
        row[column] = number.to_string().into();
    }
    let found = indexes(&entry);
    assert_eq!(checks(&found), vec!["row.index_wrong"]);
    assert_eq!(found[0].details, details(&[("expected", 1.into())]));
    for (number, row) in loop_in(&mut entry, "entity", "_Entity_comp_index").data.iter_mut().enumerate() {
        row[column] = (number + 1).to_string().into();
    }

    // A negative index only advances the count
    loop_in(&mut entry, "entity", "_Entity_comp_index").data[2][column] = "-1".into();
    assert!(indexes(&entry).is_empty());
}

#[test]
fn test_row_index_tag_prefers_the_dictionary_order() {
    let mut first = Loop::from_scratch(Some("_Chem_comp_bond")).unwrap();
    first.add_tags(&["ID", "Ordinal"]).unwrap();
    assert_eq!(row_index_tag(&first, get_schema(None)).as_deref(), Some("ID"));

    let mut swapped = Loop::from_scratch(Some("_Chem_comp_bond")).unwrap();
    swapped.add_tags(&["Ordinal", "ID"]).unwrap();
    assert_eq!(row_index_tag(&swapped, get_schema(None)).as_deref(), Some("ID"));
}

#[test]
fn test_validate_full_related_tags() {
    let mut entry = file_entry();
    let related = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check == "tag.parent_value_missing").collect()
    };
    assert!(related(&entry).is_empty());

    let column = loop_in(&mut entry, "sample", "_Sample_component").tag_index("Entity_label").unwrap();
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "$no_such_entity".into();
    let found = related(&entry);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].tag.as_deref(), Some("_Sample_component.Entity_label"));
    assert_eq!(found[0].loop_category.as_deref(), Some("_Sample_component"));
    assert_eq!(found[0].row, Some(0));
    assert_eq!(found[0].details, details(&[("parent", "_Entity.Sf_framecode".into())]));
    assert!(found[0].message.contains("'no_such_entity'"));
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "$F5-Phe-cVHP".into();
    assert!(related(&entry).is_empty());

    // ... and the same mistake in a saveframe's own tag
    frame_of(&mut entry, "assigned_chemical_shifts").set_tag("Sample_condition_list_label", "$no_such_conditions").unwrap();
    let found = related(&entry);
    assert_eq!(found.len(), 1);
    assert_eq!(found[0].loop_category, None);
    assert_eq!(found[0].tag.as_deref(), Some("_Assigned_chem_shift_list.Sample_condition_list_label"));
}

#[test]
fn test_validate_full_local_ids() {
    let mut entry = file_entry();
    let column = loop_in(&mut entry, "sample", "_Sample_component").tag_index("Sample_ID").unwrap();
    let local_ids = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check.ends_with("local_id") || i.check.ends_with("local_id_tag")).collect()
    };
    assert!(local_ids(&entry).is_empty());

    // A row filed under a different saveframe of the same category
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "2".into();
    let found = local_ids(&entry);
    assert_eq!(checks(&found), vec!["row.invalid_local_id"]);
    assert_eq!(found[0].row, Some(0));
    assert_eq!(found[0].tag.as_deref(), Some("_Sample_component.Sample_ID"));
    assert_eq!(found[0].details, details(&[("local_id", "1".into())]));

    // A null is not excused
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = ".".into();
    assert_eq!(checks(&local_ids(&entry)), vec!["row.invalid_local_id"]);
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "1".into();

    // A saveframe whose own ID is null: one finding, not one per row
    frame_of(&mut entry, "sample").set_tag("ID", ".").unwrap();
    assert_eq!(checks(&local_ids(&entry)), vec!["saveframe.invalid_local_id"]);

    // No ID tag at all is two findings
    frame_of(&mut entry, "sample").remove_tag("ID").unwrap();
    assert_eq!(checks(&local_ids(&entry)), vec!["saveframe.no_local_id_tag", "saveframe.invalid_local_id"]);
}

#[test]
fn test_validate_full_frame_codes() {
    let mut entry = file_entry();
    let dangling = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check == "value.dangling_framecode").collect()
    };
    assert!(dangling(&entry).is_empty());

    // Renaming a saveframe without updating the references to it leaves them dangling
    entry.get_saveframe_by_name_mut("sample_conditions").unwrap().set_name("sample_conditions_1").unwrap();
    let found = dangling(&entry);
    assert!(!found.is_empty());
    assert!(found.iter().all(|i| i.value == "$sample_conditions"));
    assert!(found.iter().any(|i| i.loop_category.as_deref() == Some("_Experiment")));
}

#[test]
fn test_validate_full_data_types() {
    let mut entry = file_entry();
    let typed = |entry: &Entry, severities: Option<&[Severity]>| -> Vec<ValidationIssue> {
        entry.validate_full(None, Some("internal"), severities, false).unwrap().into_iter()
            .filter(|i| i.check.starts_with("value.") && i.check != "value.miscapitalized").collect()
    };
    assert!(typed(&entry, None).is_empty());

    // A saveframe pointer without its '$', and with a space in it: two findings
    let column = loop_in(&mut entry, "sample", "_Sample_component").tag_index("Entity_label").unwrap();
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "F5 Phe cVHP".into();
    assert_eq!(checks(&typed(&entry, None)), vec!["value.not_a_framecode", "value.framecode_whitespace"]);
    loop_in(&mut entry, "sample", "_Sample_component").data[0][column] = "$F5-Phe-cVHP".into();

    // An integer, a float and a date that are none of those things
    let count = loop_in(&mut entry, "entry_information", "_Datum").tag_index("Count").unwrap();
    loop_in(&mut entry, "entry_information", "_Datum").data[0][count] = "six hundred".into();
    let found = typed(&entry, None);
    assert_eq!(checks(&found), vec!["value.not_an_integer"]);
    assert_eq!((found[0].loop_category.as_deref(), found[0].row), (Some("_Datum"), Some(0)));
    loop_in(&mut entry, "entry_information", "_Datum").data[0][count] = "602".into();

    frame_of(&mut entry, "entity").set_tag("Formula_weight", "1.2.3").unwrap();
    assert_eq!(checks(&typed(&entry, None)), vec!["value.not_a_float"]);
    frame_of(&mut entry, "entity").set_tag("Formula_weight", "3958.3").unwrap();

    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.Submission_date", "2010-13-01");
    assert_eq!(checks(&typed(&entry, None)), vec!["value.not_a_date"]);

    // A date of the right shape naming a day that does not exist: STRICT
    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.Submission_date", "2010-02-31");
    assert!(typed(&entry, Some(&[Severity::Critical, Severity::Error, Severity::Warning, Severity::Info])).is_empty());
    let strict = typed(&entry, None);
    assert_eq!(checks(&strict), vec!["value.impossible_date"]);
    assert_eq!(strict[0].tag.as_deref(), Some("_Entry.Submission_date"));
    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.Submission_date", "2010-02-19");

    // A value longer than its column; _Entry.Title is TEXT and so has no limit
    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.NMR_STAR_version", "v".repeat(40));
    let found = typed(&entry, None);
    assert_eq!(checks(&found), vec!["value.too_long"]);
    assert_eq!(found[0].details, details(&[("max_length", 31.into())]));
    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.NMR_STAR_version", "3.1.1.61");

    set_tag_value(frame_of(&mut entry, "entry_information"), "_Entry.Title", "t".repeat(5000));
    assert!(typed(&entry, None).is_empty());
}

#[test]
fn test_validate_full_data_values() {
    let mut entry = file_entry();
    let enumerated = |entry: &Entry| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check == "value.not_in_enumeration" || i.check == "value.miscapitalized").collect()
    };

    // The sample entry writes two closed-enumeration values in the wrong case
    let found = enumerated(&entry);
    assert_eq!(checks(&found), vec!["value.miscapitalized"; 2]);
    assert_eq!(found.iter().map(|i| i.tag.as_deref().unwrap()).collect::<Vec<_>>(),
               vec!["_Chem_comp.Type", "_Chem_comp.Processing_site"]);
    assert_eq!(found[0].details, details(&[("correct", "NON-POLYMER".into())]));

    // A value not in the list at any capitalization
    set_tag_value(frame_of(&mut entry, "chem_comp"), "_Chem_comp.Type", "gaseous");
    let found: Vec<_> = enumerated(&entry).into_iter().filter(|i| i.tag.as_deref() == Some("_Chem_comp.Type")).collect();
    assert_eq!(checks(&found), vec!["value.not_in_enumeration"]);
    assert_eq!(found[0].value, "gaseous");
    assert!(found[0].details.is_empty());

    // An open enumeration is not enforced
    assert!(!get_schema(None).enumerations["_software.name"].closed);
    frame_of(&mut entry, "software").set_tag("Name", "A program nobody has used before").unwrap();
    assert!(!enumerated(&entry).iter().any(|i| i.tag.as_deref() == Some("_Software.Name")));
}

#[test]
fn test_validate_full_reaches_the_data() {
    let mut entry = file_entry();
    let value = named_loop(&mut entry, "assigned_chem_shift_list_1", "_Atom_chem_shift").tag_index("Val").unwrap();
    let found = |entry: &Entry, check: &str, metadata_only: bool| -> Vec<ValidationIssue> {
        entry.validate_full(None, None, None, metadata_only).unwrap().into_iter().filter(|i| i.check == check).collect()
    };
    let located = |issues: Vec<ValidationIssue>| issues.into_iter().map(|i| (i.tag.unwrap(), i.row)).collect::<Vec<_>>();

    named_loop(&mut entry, "assigned_chem_shift_list_1", "_Atom_chem_shift").data[0][value] = "abc".into();
    assert_eq!(located(found(&entry, "value.not_a_float", false)), vec![("_Atom_chem_shift.Val".to_string(), Some(0))]);
    assert!(found(&entry, "value.not_a_float", true).is_empty());
    named_loop(&mut entry, "assigned_chem_shift_list_1", "_Atom_chem_shift").data[0][value] = "1.5".into();

    // A null in a NOT NULL column
    named_loop(&mut entry, "assigned_chem_shift_list_1", "_Atom_chem_shift").data[3][value] = ".".into();
    assert_eq!(located(found(&entry, "value.null_not_allowed", false)), vec![("_Atom_chem_shift.Val".to_string(), Some(3))]);
    named_loop(&mut entry, "assigned_chem_shift_list_1", "_Atom_chem_shift").data[3][value] = "1.5".into();

    // A value that passes the coarse type test but not the dictionary type's own pattern
    let author = entry.get_loops_by_category_mut("_Entry_author").into_iter().next().unwrap();
    let initials = author.tag_index("Middle_initials").unwrap();
    author.data[0][initials] = "A B".into();
    let issues = found(&entry, "value.type_mismatch", false);
    assert_eq!(issues.iter().map(|i| i.tag.as_deref().unwrap()).collect::<Vec<_>>(), vec!["_Entry_author.Middle_initials"]);
    assert_eq!(issues[0].details["type"], "code");
}

#[test]
fn test_validate_full_null_reported_once() {
    let mut entry = file_entry();
    frame_of(&mut entry, "entry_information").set_tag("NMR_STAR_version", ".").unwrap();
    let found: Vec<String> = validate_full(&entry, None).into_iter()
        .filter(|i| i.tag.as_deref() == Some("_Entry.NMR_STAR_version")).map(|i| i.check).collect();
    assert_eq!(found, vec!["tag.missing_value"]);
}

#[test]
fn test_validate_full_loop_widths() {
    let mut entry = file_entry();
    let comp_index = frame_of(&mut entry, "entity").get_loop_mut("_Entity_comp_index").unwrap();
    comp_index.data[1].push("extra".into());
    let width = comp_index.tags().len();
    let issues: Vec<_> = validate_full(&entry, None).into_iter().filter(|i| i.check == "row.wrong_width").collect();
    assert_eq!(issues.iter().map(|i| (i.loop_category.clone().unwrap(), i.row)).collect::<Vec<_>>(),
               vec![("_Entity_comp_index".to_string(), Some(1))]);
    assert_eq!(issues[0].details, details(&[("values", (width + 1).into()), ("tags", width.into())]));
}

#[test]
fn test_validate_full_empty_rows_and_charset() {
    let mut entry = file_entry();
    let found = |entry: &Entry, check: &str| -> Vec<ValidationIssue> {
        internal(entry).into_iter().filter(|i| i.check == check).collect()
    };

    assert!(found(&entry, "row.empty").is_empty());
    assert!(found(&entry, "value.non_ascii").is_empty());

    // A row of nothing but nulls, in all the spellings of null
    let width = loop_in(&mut entry, "entity", "_Entity_comp_index").tags().len();
    let mut row = vec![Value::from("."), Value::from("?"), Value::from(""), Value::Null];
    row.extend(std::iter::repeat_n(Value::from("."), width - 4));
    loop_in(&mut entry, "entity", "_Entity_comp_index").data.push(row);
    let empty = found(&entry, "row.empty");
    assert_eq!(empty.len(), 1);
    assert_eq!(empty[0].row, Some(loop_in(&mut entry, "entity", "_Entity_comp_index").data.len() - 1));
    assert_eq!(empty[0].loop_category.as_deref(), Some("_Entity_comp_index"));

    // One non-null value is enough
    loop_in(&mut entry, "entity", "_Entity_comp_index").data.last_mut().unwrap()[0] = "x".into();
    assert!(found(&entry, "row.empty").is_empty());
    loop_in(&mut entry, "entity", "_Entity_comp_index").data.pop();

    // NMR-STAR is ASCII
    frame_of(&mut entry, "entry_information").set_tag("Title", "Solution structure of a ubiquitin–like protein").unwrap();
    let non_ascii = found(&entry, "value.non_ascii");
    assert_eq!(non_ascii.iter().map(|i| i.tag.as_deref().unwrap()).collect::<Vec<_>>(), vec!["_Entry.Title"]);
    assert!(non_ascii[0].message.contains("'–' (U+2013)"));

    // A multi-line value must not put a newline in the message
    frame_of(&mut entry, "entry_information").set_tag("Title", "Two\nlines–long\n").unwrap();
    let non_ascii = found(&entry, "value.non_ascii");
    assert_eq!(non_ascii.len(), 1);
    assert!(!non_ascii[0].message.contains('\n'));
}

#[test]
fn test_validate_full_conditional() {
    // _Citation.Journal_abbrev is required only of a journal citation
    let mut entry = file_entry();
    set_tag_value(frame_of(&mut entry, "citations"), "_Citation.Class", "entry citation");
    let abbrev_reported = |entry: &Entry| internal(entry).iter().any(|i| i.tag.as_deref() == Some("_Citation.Journal_abbrev"));

    set_tag_value(frame_of(&mut entry, "citations"), "_Citation.Type", "journal");
    frame_of(&mut entry, "citations").remove_tag("Journal_abbrev").unwrap();
    assert!(abbrev_reported(&entry));

    set_tag_value(frame_of(&mut entry, "citations"), "_Citation.Type", "thesis");
    assert!(!abbrev_reported(&entry));
}

#[test]
fn test_validate() {
    let mut entry = file_entry();
    let mut validation = vec![
        "Value 'non-polymer' of tag '_Chem_comp.Type' is improperly capitalized but otherwise valid. Should be 'NON-POLYMER'.".to_string(),
        "Value 'PDBe' of tag '_Chem_comp.Processing_site' is improperly capitalized but otherwise valid. Should be 'PDBE'.".to_string()];
    assert_eq!(entry.validate(true, None, true), validation);

    entry.frame_list.last_mut().unwrap().loops.last_mut().unwrap().data[0][0] = "a".into();
    validation.push("Value does not match specification: '_Atom_chem_shift.ID':'a'.\n     Type specified: int\n     \
                     Regular expression for type: '^(?:-?[0-9]*)?$'".to_string());
    assert_eq!(entry.validate(true, None, true), validation);
}

#[test]
fn test_entry_setitem_duplicates() {
    let mut test_entry = Entry::from_scratch("test");
    let test_saveframe = Saveframe::from_scratch("test", Some("test"));
    test_entry.frame_list = vec![test_saveframe.clone(), test_saveframe.clone()];
    assert_value_error(test_entry.set_saveframe("test", test_saveframe));
}

#[test]
fn test_category_list() {
    let mut tmp = file_entry();
    let expected = ["entry_information", "citations", "assembly", "entity", "natural_source", "experimental_source",
                    "chem_comp", "sample", "sample_conditions", "software", "NMR_spectrometer", "NMR_spectrometer_list",
                    "experiment_list", "chem_shift_reference", "assigned_chemical_shifts"];
    assert_eq!(tmp.category_list(), expected);
    tmp.add_saveframe(Saveframe::from_scratch("test", None)).unwrap();
    assert_eq!(tmp.category_list(), expected);
}

#[test]
fn test_rename_saveframe() {
    let file_entry = file_entry();
    let mut tmp = file_entry.clone();
    tmp.rename_saveframe("F5-Phe-cVHP", "jons_frame").unwrap();
    tmp.rename_saveframe("jons_frame", "F5-Phe-cVHP").unwrap();
    assert_eq!(tmp, file_entry);
}

#[test]
fn test_normalize() {
    let file_entry = file_entry();
    let mut db_tmp = file_entry.clone();
    let mut denormalized = Entry::from_file(sample("bmr15000_3_denormalized.str")).unwrap();
    denormalized.normalize(None).unwrap();
    assert!(db_tmp.compare(&denormalized).is_empty());

    // Shuffle the entry
    let mut rng = rand::thread_rng();
    db_tmp.frame_list.shuffle(&mut rng);
    for frame in &mut db_tmp.frame_list {
        frame.loops.shuffle(&mut rng);
        frame.tags_mut().shuffle(&mut rng);
    }
    // Equality ignores the order
    assert!(db_tmp.compare(&file_entry).is_empty());
    assert_ne!(db_tmp.frame_list, file_entry.frame_list);
    db_tmp.normalize(None).unwrap();
    assert_eq!(db_tmp.frame_list, file_entry.frame_list);

    // The ordering of saveframes when tags may be missing
    let mut b = Saveframe::from_scratch("not_real2", None);
    b.add_tag("_help.Sf_category", "a").unwrap();
    b.add_tag("_help.ID", 1).unwrap();
    let mut c = Saveframe::from_scratch("not_real", None);
    c.add_tag("_help.Sf_category", "a").unwrap();
    c.add_tag("_help.ID", "a").unwrap();
    let mut d = Saveframe::from_scratch("not_real3", None);
    d.add_tag("_help.borg", "a").unwrap();
    db_tmp.add_saveframe(b).unwrap();
    db_tmp.add_saveframe(c).unwrap();
    db_tmp.add_saveframe(d).unwrap();

    // (Python's copy of the list shared its saveframes, so only their order was compared; the
    //  tags of the saveframes the dictionary does not know are sorted arbitrarily.)
    let names = |entry: &Entry| entry.iter().map(|f| f.name().to_string()).collect::<Vec<_>>();
    let correct_order = names(&db_tmp);
    db_tmp.frame_list.shuffle(&mut rng);
    db_tmp.normalize(None).unwrap();
    assert_eq!(names(&db_tmp), correct_order);
}

#[test]
fn test_json_round_trip() {
    let file_entry = file_entry();
    assert_eq!(Entry::from_json(&file_entry.to_json()).unwrap(), file_entry);
}
