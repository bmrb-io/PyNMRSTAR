//! Ported from pynmrstar/unit_tests/test_parser_fast_path.py.
//!
//! PyNMR-STAR's parser added tags which `add_tag()` would accept unchanged without calling it,
//! and these tests checked that the result was what those methods produce. The Rust parser has
//! no separate fast path, but the same tests check that parsing gives exactly what building the
//! entry through the API does, and rejects what the API rejects.

mod common;

use common::*;
use nmrstar::{definitions, Data, Entry, Loop, ParseOptions, Saveframe, Value};

type LoopState = (Option<String>, Vec<String>, Vec<Vec<Value>>, Vec<Option<usize>>);
type FrameState = (String, Option<String>, Option<String>, Vec<(String, Value)>, Vec<LoopState>);

/// Everything about an entry's saveframes and loops which adding tags affects.
fn state(entry: &Entry) -> Vec<FrameState> {
    entry.iter().map(|sf| {
        let tags = sf.tags().iter().map(|t| (t.name.clone(), t.value.clone())).collect();
        let loops = sf.iter().map(|lp| {
            let positions = lp.tags().iter().map(|t| lp.tag_index(t)).collect();
            (lp.category().map(str::to_string), lp.tags().to_vec(), lp.data.clone(), positions)
        }).collect();
        (sf.name().to_string(), sf.category().map(str::to_string), sf.tag_prefix.clone(), tags, loops)
    }).collect()
}

/// A copy of an entry, built through the public API.
fn rebuild(entry: &Entry) -> Entry {
    let mut new_entry = Entry::from_scratch(entry.entry_id.clone());
    for sf in entry {
        let mut new_sf = Saveframe::from_scratch(sf.name(), None);
        let prefix = sf.tag_prefix.clone().unwrap();
        let tags: Vec<(String, Value)> = sf.tags().iter().map(|t| (format!("{}.{}", prefix, t.name), t.value.clone())).collect();
        new_sf.add_tags(&tags).unwrap();
        for lp in sf {
            let mut new_loop = Loop::new();
            let names: Vec<String> = lp.tags().iter().map(|t| format!("{}.{}", lp.category().unwrap(), t)).collect();
            new_loop.add_tags(&names).unwrap();
            if !lp.data.is_empty() {
                new_loop.add_data(Data::Rows(lp.data.clone())).unwrap();
            }
            new_sf.add_loop(new_loop).unwrap();
        }
        new_entry.add_saveframe(new_sf).unwrap();
    }
    new_entry
}

fn assert_same_as_api(star: &str) -> Entry {
    let entry = Entry::from_str(star).unwrap();
    assert_eq!(state(&entry), state(&rebuild(&entry)));
    entry
}

#[test]
fn test_sample_files() {
    for name in ["bmr15000_3.str", "bmr15000_3_denormalized.str", "dos.str", "nonewlines.str", "edge_cases.str"] {
        let text = std::fs::read_to_string(sample(name)).unwrap();
        assert_same_as_api(&text);
    }
}

#[test]
fn test_tags_split_by_loops() {
    let entry = assert_same_as_api("data_1 save_a _A.Sf_category cat _A.Sf_framecode a \
                                    loop_ _L.x _L.Y 1 2 stop_ _A.after 3 loop_ _M.z 4 stop_ _A.last 5 save_");
    let frame = entry.get_saveframe_by_name("a").unwrap();
    assert_eq!(frame.category(), Some("cat"));
    assert_eq!(frame.get_tag_required("_A.After").unwrap(), strs(&["3"]));
    assert_eq!(frame.get_loop("_L").unwrap().tag_index("y"), Some(1));
}

#[test]
fn test_unusual_tags() {
    assert_same_as_api("data_1 save_a _A.Sf_category cat _A.é 1 _A.b 2 loop_ _L.é _L.x 1 2 stop_ save_");
    // Loop::add_tag() strips this from the tag name, as Python considers it whitespace
    assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 1 loop_ _L.x\u{1c} 1 stop_ save_");
    assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 2 loop_ _L.x _l.Y 1 2 stop_ save_");
    assert_same_as_api("data_1 save_a _A.Sf_category cat _A.b 2 loop_ _L.x _L.y 1 2 stop_ loop_ _M.x _M.Y 1 2 stop_ save_");
}

#[test]
fn test_rejected_tags() {
    for star in ["data_1 save_a _A.b 1 _A.B 2 save_",
                 "data_1 save_a _A.b 1 loop_ _L.x 1 stop_ _A.B 2 save_",
                 "data_1 save_a _A.b 1 _a.c 2 save_",
                 "data_1 save_a _A.b 1 _A.? 2 save_",
                 "data_1 save_a _A.b 1 _A. 2 save_",
                 "data_1 save_a _A.b 1 _A.c.d 2 save_",
                 // Not whitespace to the tokenizer, but it is to Python's str.split()
                 "data_1 save_a _A.b\u{1c} 1 save_",
                 "data_1 save_a _A.b 1 loop_ _L.x _L.X 1 2 stop_ save_",
                 "data_1 save_a _A.b 1 loop_ _L.x _M.y 1 2 stop_ save_",
                 "data_1 save_a _A.b 1 loop_ _L.x _L.? 1 2 stop_ save_"] {
        assert_parsing_error(Entry::from_str(star));
    }
}

#[test]
fn test_sf_framecode() {
    assert_same_as_api("data_1 save_a _A.Sf_framecode a _A.b 1 save_");
    assert_parsing_error(Entry::from_str_opts("data_1 save_a _A.Sf_framecode b _A.c 1 save_",
                                              ParseOptions::new().raise_parse_warnings(true)));
}

#[test]
fn test_null_values_respected() {
    let _guard = lock_global_state();
    let star = "data_1 save_a _A.b 1 _A.N/A 2 loop_ _L.x 1 stop_ save_";
    Entry::from_str(star).unwrap();
    let mut null_values = definitions::null_values();
    null_values.push(Value::from("N/A"));
    definitions::set_null_values(null_values);
    let star_result = Entry::from_str(star);
    let loop_result = Entry::from_str("data_1 save_a _A.b 1 loop_ _L.N/A 1 stop_ save_");
    definitions::reset_null_values();
    assert_parsing_error(star_result);
    assert_parsing_error(loop_result);
}

#[test]
fn test_duplicate_saveframe_names() {
    assert_parsing_error(Entry::from_str("data_1 save_a _A.b 1 save_ save_b _B.b 1 save_ save_a _C.b 1 save_"));
}
