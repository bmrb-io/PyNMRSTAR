//! Ported from pynmrstar/unit_tests/test_parser.py.

mod common;

use std::time::Instant;

use common::*;
use nmrstar::{Entry, Loop, ParseOptions, Saveframe, Value};

fn strict() -> ParseOptions<'static> {
    ParseOptions::new().raise_parse_warnings(true)
}

#[test]
fn test_parser() {
    // The various parsing errors, in the order of the parser code when they were written
    assert_parsing_error(Entry::from_str("data_1\nsave_1\n\"loop\"_\n_tag.tag\ndata_\nstop_\nsave_\n"));

    // File start
    assert_parsing_error(Entry::from_str("whatever test"));
    assert_parsing_error(Entry::from_str("data_"));
    assert_parsing_error(Entry::from_str("'data_1'\nsave_1\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n"));

    // Saveframes
    assert_parsing_error(Entry::from_str("data_frame invalid"));
    assert_parsing_error(Entry::from_str("data_frame save_ invalid"));
    assert_parsing_error(Entry::from_str("data_1\n'save_1'\nloop_\n_tag.tag\ndata_\nstop_\nsave_\n"));

    // Loops
    assert_parsing_error(Entry::from_str("data_1\nsave_1\n'loop_'\n_tag.tag\ndata_\nstop_\nsave_\n"));
    assert_parsing_error(Entry::from_str("data_1 save_1 loop_ _tag.one _tag2.one stop_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 loop_ _tag.one stop_ loop_ _tag.one stop_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 loop_ _tag.one 'stop_'"));
    assert_parsing_error(Entry::from_str_opts("data_1 save_1 _saveframe.tag value loop_ stop_ save_", strict()));
    assert_parsing_error(Entry::from_str_opts("data_1 save_1 _saveframe.tag value loop_ _tag.one stop_ save_", strict()));
    assert_logs(|| Entry::from_str("data_1 save_1 _saveframe.tag value loop_ stop_ save_").unwrap());
    assert_logs(|| Entry::from_str("data_1 save_1 _saveframe.tag value loop_ _tag.one stop_ save_").unwrap());
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data stop_ save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data _tag.three stop_ save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value loop_ data stop_ save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data data2 loop_ stop_ save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value loop_ _tag.one _tag.two data data2"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value 'save_'"));
    // The closing save_ cannot be semicolon-delimited
    assert_parsing_error(Entry::from_str("data_1\nsave_1\n_saveframe.tag value\n;\nsave_\n;\n"));
    assert_parsing_error(Entry::from_str("data_1 save_1 save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 stop_"));

    // Back to saveframes
    assert_parsing_error(Entry::from_str("data_1\nsave_1\n'_tag.example' save_\nsave_\n"));
    assert_parsing_error(Entry::from_str("data_1\nsave_1\n_tag.example save_\nsave_\n"));
    assert_parsing_error(Loop::from_str("d"));
    assert_parsing_error(Saveframe::from_str("save_1\n_tag.1 _tag.2"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _savef.rame.tag value save_"));
    assert_parsing_error(Entry::from_str("data_1 save_1 _saveframe.tag value"));
}

#[test]
fn test_parse_outliers() {
    let test_string = "data_#pound
save_entry_information  _Entry.Sf_category entry_information _Entry.Sf_framecode entry_information
_Entry.sameline_comment value #ignore this all
_Entry.ID    \".-!?\"
_Entry.Invalid_tag            \"This tag doesn't exist.\"
_Entry.Title
; Solution structure of chicken villin headpiece subdomain contain;ing a fluorinated side chain in the cores;
;
_Entry.Submi#ssion_date                \"check inn\"er \"quoted vals\"
_Entry.Accession_date                 'check inner quoted vals'
_Entry.Original_NMR_STAR_version      '_.'
   _Entry.Experimental_method            $
   _Entry.Details                        \"1#\"
   _Entry.Experimental_method_subtype    solution
   _Entry.BMRB_internal_directory_name   ;data;
_Entry.pointer $it
_Entry.multi
;

   nothing
   to shift
;
_Entry.multi2
;

   ;
   something
   to shift
;
save_
";
    // As in PyNMR-STAR, this only checks that it parses
    let entry = Entry::from_str(test_string).unwrap();
    assert_eq!(entry.entry_id, Value::from("#pound"));
    let frame = &entry.frame_list[0];
    assert_eq!(frame.get_tag("sameline_comment").unwrap(), strs(&["value"]));
    assert_eq!(frame.get_tag("Submi#ssion_date").unwrap(), strs(&["check inn\"er \"quoted vals"]));
    assert_eq!(frame.get_tag("multi2").unwrap(), strs(&["\n;\nsomething\nto shift"]));
}

#[test]
fn test_unicode_whitespace_warning() {
    for star in ["data_test save_test\u{3000}_sf.sf_category test _sf.sf_framecode test save_",
                 "data_test save_test _sf.sf_category\u{a0}test _sf.sf_framecode test save_",
                 "data_test\u{1680}save_test _sf.sf_category test _sf.sf_framecode test save_"] {
        let (result, messages) = capture_logs(|| Entry::from_str(star));
        result.unwrap();
        assert!(messages.iter().any(|m| m.contains("Non-standard whitespace")), "{:?}", messages);
    }
}

#[test]
fn test_unicode_whitespace_raises_with_flag() {
    assert_parsing_error(Entry::from_str_opts("data_test save_test\u{3000}_sf.sf_category test _sf.sf_framecode test save_", strict()));
}

#[test]
fn test_standard_whitespace_no_warning() {
    let star = "data_test\n save_test\t_sf.sf_category test\r\n_sf.sf_framecode test\n save_\n";
    let (entry, messages) = capture_logs(|| Entry::from_str(star).unwrap());
    assert!(messages.is_empty());
    assert_eq!(entry.entry_id, Value::from("test"));
}

#[test]
fn test_unicode_whitespace_in_quoted_value_no_warning() {
    let star = "data_test save_test _sf.sf_category test _sf.sf_framecode test _sf.value '\u{3000}test\u{3000}' save_";
    let (entry, messages) = capture_logs(|| Entry::from_str(star).unwrap());
    assert!(messages.is_empty());
    assert_eq!(entry.frame_list[0].get_tag_required("value").unwrap(), strs(&["\u{3000}test\u{3000}"]));

    let star = "data_test save_test _sf.sf_category test _sf.sf_framecode test _sf.value\n;\n\u{3000}value\u{3000}\n;\nsave_";
    let (entry, messages) = capture_logs(|| Entry::from_str(star).unwrap());
    assert!(messages.is_empty());
    assert!(entry.frame_list[0].get_tag("value").unwrap()[0].to_string().contains('\u{3000}'));
}

#[test]
fn test_sf_framecode_mismatch_is_a_parse_warning() {
    // A saveframe whose Sf_framecode differs from its save_ label is a thing a validator must be
    //  able to report, so parsing keeps both strings and warns
    let star = "data_1\nsave_the_name\n_sf.Sf_category cat\n_sf.Sf_framecode a_different_name\nsave_\n";
    let entry = assert_logs(|| Entry::from_str(star).unwrap());
    assert_eq!(entry.frame_list[0].name(), "the_name");
    assert_eq!(entry.frame_list[0].get_tag("Sf_framecode").unwrap(), strs(&["a_different_name"]));

    // ... and it survives a write/re-parse
    let reparsed = Entry::from_str(&entry.format(true, false, true).unwrap()).unwrap();
    assert_eq!(reparsed.frame_list[0].name(), "the_name");
    assert_eq!(reparsed.frame_list[0].get_tag("Sf_framecode").unwrap(), strs(&["a_different_name"]));
}

#[test]
fn test_sf_framecode_mismatch_raises_when_strict() {
    let star = "data_1\nsave_the_name\n_sf.Sf_category cat\n_sf.Sf_framecode a_different_name\nsave_\n";
    assert_parsing_error(Entry::from_str_opts(star, strict()));
}

#[test]
fn test_sf_framecode_mismatch_still_raises_outside_a_parse() {
    let mut saveframe = Saveframe::from_scratch("the_name", Some("_sf"));
    assert_value_error(saveframe.add_tag("_sf.Sf_framecode", "a_different_name"));
}

#[test]
fn test_structural_error_line_numbers() {
    let duplicate = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                     _Entry.Sf_framecode   entry_information\n    _Entry.Title          'first title'\n    \
                     _Entry.Title          'second title'\nsave_\n";
    // The *second* occurrence is the offending one
    assert_eq!(assert_parsing_error(Entry::from_str(duplicate)).line_number(), Some(7));

    let foreign = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                   _Entry.Sf_framecode   entry_information\n    _Entry.Title          'a title'\n    \
                   _Citation.Class       journal\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(foreign)).line_number(), Some(7));

    // A tag name inside a semicolon block is not the tag itself
    let semicolon = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                     _Entry.Sf_framecode   entry_information\n    _Entry.Details\n;\n_Entry.Title is discussed here\n;\n    \
                     _Entry.Title          'first title'\n    _Entry.Title          'second title'\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(semicolon)).line_number(), Some(11));
}

#[test]
fn test_loop_tag_line_numbers() {
    let header = "data_test\n\nsave_x\n    _Entry.Sf_category    entry_information\n    _Entry.Sf_framecode   x\n    \
                  loop_\n        _Entry_author.Ordinal\n        _Entry_author.Given_name\n";

    let duplicate = format!("{}        _Entry_author.Ordinal\n        1 Jon 2\n    stop_\nsave_\n", header);
    assert_eq!(assert_parsing_error(Entry::from_str(&duplicate)).line_number(), Some(9));

    let foreign = format!("{}        _Citation.Class\n        1 Jon journal\n    stop_\nsave_\n", header);
    assert_eq!(assert_parsing_error(Entry::from_str(&foreign)).line_number(), Some(9));
}

#[test]
fn test_tokenizer_error_line_numbers() {
    // Rejected mid-line
    let quoted_tag = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                      _Entry.Sf_framecode   entry_information\n    '_Entry.Title'        'x'\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(quoted_tag)).line_number(), Some(6));

    // Rejected at the end of a line
    let underscore_value = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                            _Entry.Sf_framecode   entry_information\n    _Entry.Title          _bad_value\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(underscore_value)).line_number(), Some(6));

    // A multi-line value is reported against the line it opens on
    let unterminated = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                        _Entry.Sf_framecode   entry_information\n    _Entry.Title\n;\nno closing semicolon\n";
    assert_eq!(assert_parsing_error(Entry::from_str(unterminated)).line_number(), Some(7));
}

#[test]
fn test_error_message_names_the_line_once() {
    let error = assert_parsing_error(Entry::from_str("data_test\nsave_x\n_A.x 'abc\nsave_\n"));
    assert_eq!(error.line_number(), Some(3));
    assert_eq!(error.to_string(), "Invalid file. Single quoted value was not terminated. Error detected on line 3.");

    let star = "data_test\nsave_test\n_sf.sf_category\u{3000}test\n_sf.sf_framecode test\nsave_\n";
    let error = assert_parsing_error(Entry::from_str_opts(star, strict()));
    assert_eq!(error.line_number(), Some(3));
    assert_eq!(error.to_string().matches(" line ").count(), 1);
}

#[test]
fn test_line_numbers_survive_semicolon_rewriting() {
    let star = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                _Entry.Sf_framecode   entry_information\n    _Entry.Details\n; some details on the semicolon line\n;\n    \
                _Entry.Title          'first title'\n    _Entry.Title          'second title'\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(star)).line_number(), Some(10));

    let star = "data_test\n\nsave_entry_information\n    _Entry.Sf_category    entry_information\n    \
                _Entry.Sf_framecode   entry_information\n    _Entry.Details\n; some details on the semicolon line\n;\n    \
                '_Entry.Title'        'x'\nsave_\n";
    assert_eq!(assert_parsing_error(Entry::from_str(star)).line_number(), Some(9));
}

#[test]
fn test_loop_with_many_tags_and_little_data() {
    // PyNMR-STAR reserved memory for a loop's data from its number of tags, which this checked
    //  was bounded. The Rust parser reserves nothing up front; the result must still be an error.
    let tags: Vec<String> = (0..200_000).map(|i| format!("_a.b{}", i)).collect();
    let star = format!("data_1 save_a loop_ {} 1 stop_ save_", tags.join(" "));
    // One value for 200,000 tags is not a whole row
    assert_parsing_error(Entry::from_str(&star));
}

#[test]
fn test_duplicate_loop_categories() {
    let error = assert_parsing_error(Entry::from_str("data_x save_s _S.Sf_category s loop_ _A.a 1 stop_ loop_ _a.b 2 stop_ save_"));
    assert!(error.to_string().contains("two loops with the same category") && error.to_string().contains("'_a'"));
    let error = assert_parsing_error(Entry::from_str("data_x save_s _S.Sf_category s loop_ _ÄB.a 1 stop_ loop_ _äb.b 2 stop_ save_"));
    assert!(error.to_string().contains("two loops with the same category") && error.to_string().contains("'_äb'"));

    // The same category in different saveframes is fine
    let entry = Entry::from_str("data_x save_s _S.Sf_category s loop_ _A.a 1 stop_ save_ \
                                 save_t _S.Sf_category t loop_ _A.a 1 stop_ save_").unwrap();
    let categories: Vec<Vec<Option<&str>>> = entry.iter().map(|f| f.iter().map(|l| l.category()).collect()).collect();
    assert_eq!(categories, vec![vec![Some("_A")], vec![Some("_A")]]);

    // As are several loops without tags, which have no category
    let entry = assert_logs(|| Entry::from_str("data_x save_s _S.Sf_category s loop_ stop_ loop_ stop_ save_").unwrap());
    assert_eq!(entry.frame_list[0].iter().map(|l| l.category()).collect::<Vec<_>>(), vec![None, None]);
}

#[test]
fn test_many_loops_in_one_saveframe() {
    // Adding a loop must not take time proportional to the loops already in the saveframe
    let loops: Vec<String> = (0..20000).map(|i| format!("loop_ _T{}.a _T{}.b\n1 2\nstop_", i, i)).collect();
    let start = Instant::now();
    let entry = Entry::from_str(&format!("data_x save_s _S.Sf_category s\n{}\nsave_\n", loops.join("\n"))).unwrap();
    assert!(start.elapsed().as_secs() < 10);
    assert_eq!(entry.frame_list[0].loops.len(), 20000);
    assert_eq!(entry.frame_list[0].loops.last().unwrap().category(), Some("_T19999"));
}
