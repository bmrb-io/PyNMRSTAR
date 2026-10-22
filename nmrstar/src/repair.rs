//! Repairs that change an entry, and that a caller has to ask for.
//!
//! [`Entry::normalize`] already applies every repair that is safe to run unconditionally. What
//! lives here is a change large or opinionated enough that it should be a caller's explicit
//! decision.

use std::collections::{HashMap, HashSet};

use crate::entry::Entry;
use crate::error::Result;
use crate::pystr;
use crate::schema::Schema;
use crate::star_loop::Loop;
use crate::utils::get_schema;
use crate::validation::MandatoryResolver;
use crate::value::Value;

/// Add the tags the dictionary requires but the entry does not supply, each with its dictionary
/// default or `?`. A tag is added when the dictionary places it in the saveframe's category, it
/// is metadata, it is not inserted automatically by deposition tools, and its mandatory code
/// (after any conditional rule) is neither optional nor invalid.
///
/// A required tag whose whole loop is missing brings the loop with it, unless
/// `add_missing_loops` is false: every column the dictionary gives the category (but `Sf_ID`),
/// and one row, with the row index `0`, `*.Entry_ID` set to `entry_id`, and every other column
/// its default or `?`. `entry_id` defaults to the entry's own `_Entry.ID`, or `?` if that is
/// absent or null.
pub fn insert_mandatory_tags(entry: &mut Entry, schema: Option<&Schema>, profile: Option<&str>,
                             add_missing_loops: bool, entry_id: Option<Value>) -> Result<()> {
    let schema = get_schema(schema);
    // The rules are resolved against the entry as it was before anything was added
    let snapshot = entry.clone();
    let mut resolver = MandatoryResolver::new(&snapshot, schema, profile)?;

    let entry_id = match entry_id {
        Some(entry_id) => entry_id,
        None => {
            let first = entry.get_tag("_Entry.ID")?.into_iter().next();
            match first {
                Some(value) if !value.is_none() && !crate::definitions::is_null_str(pystr::strip(&value.to_py_string())) => value,
                _ => Value::from("?"),
            }
        }
    };
    let default_for = |tag: &str| -> Value {
        if tag.ends_with(".entry_id") {
            return entry_id.clone();
        }
        Value::from(schema.default_values.get(tag).map(String::as_str).unwrap_or("?"))
    };
    let sequence = |tag: &str| schema.get(tag).map(|d| d.get("Dictionary sequence").trim().parse::<i64>().unwrap_or(0)).unwrap_or(0);

    let mut by_category: HashMap<String, Vec<String>> = HashMap::new();
    let mut columns: HashMap<String, Vec<String>> = HashMap::new();
    for (tag, data) in schema.tags() {
        if data.get("Meta data") == "Y" && !schema.auto_inserted_tags.contains(tag) {
            let category = data.sf_category();
            if !category.is_empty() {
                by_category.entry(category.to_string()).or_default().push(tag.to_string());
            }
        }
        if data.get("Loopflag").trim() == "Y" && data.get("Saveframe ID tag").trim() != "Y" {
            let category = tag.rsplit_once('.').map(|(c, _)| c).unwrap_or(tag);
            columns.entry(format!("{}|{}", data.sf_category(), category)).or_default().push(tag.to_string());
        }
    }
    for tags in by_category.values_mut().chain(columns.values_mut()) {
        tags.sort_by_key(|tag| sequence(tag));
    }

    for (index, saveframe) in entry.frame_list.iter_mut().enumerate() {
        let prefix = pystr::lower(saveframe.tag_prefix.as_deref().unwrap_or("None"));
        let category = match schema.get(&format!("{}.sf_category", prefix)).map(|d| d.get("SFCategory")) {
            Some(category) if !category.is_empty() => category.to_string(),
            _ => continue,
        };

        let mut present: HashSet<String> = saveframe.tags().iter()
            .map(|tag| pystr::lower(&format!("{}.{}", saveframe.tag_prefix.as_deref().unwrap_or("None"), tag.name))).collect();
        for each_loop in &saveframe.loops {
            for name in each_loop.tags() {
                present.insert(pystr::lower(&format!("{}.{}", each_loop.category().unwrap_or("None"), name)));
            }
        }

        for tag in by_category.get(&category).map(Vec::as_slice).unwrap_or(&[]) {
            if present.contains(tag) {
                continue;
            }
            let code = resolver.code(tag, &snapshot.frame_list[index], Some(&category));
            if code == 'O' || code == 'I' {
                continue;
            }
            let tag_data = schema.get(tag).unwrap();
            let full_tag = tag_data.tag().to_string();
            if tag_data.get("Loopflag").trim() != "Y" {
                saveframe.add_tag(&full_tag, default_for(tag))?;
                present.insert(tag.clone());
                continue;
            }

            let loop_category = full_tag.rsplit_once('.').map(|(c, _)| c).unwrap_or(&full_tag).to_string();
            let lower_category = pystr::lower(&loop_category);
            if let Some(existing) = saveframe.loops.iter_mut()
                .find(|l| pystr::lower(l.category().unwrap_or("")) == lower_category) {
                existing.add_tag_with(&full_tag, false, true)?;
                let position = existing.tag_index(&full_tag).unwrap();
                let value = default_for(tag);
                for row in &mut existing.data {
                    row[position] = value.clone();
                }
                present.insert(tag.clone());
                continue;
            }

            if !add_missing_loops {
                continue;
            }
            let new_columns = columns.get(&format!("{}|{}", category, lower_category)).cloned()
                .unwrap_or_else(|| vec![tag.clone()]);
            let mut new_loop = Loop::from_scratch(Some(&loop_category))?;
            let mut row = Vec::with_capacity(new_columns.len());
            for column in &new_columns {
                let column_data = schema.get(column).unwrap();
                new_loop.add_tag(column_data.tag())?;
                row.push(if column_data.get("Row Index Key").trim() == "Y" { Value::from("0") } else { default_for(column) });
            }
            new_loop.data.push(row);
            saveframe.add_loop(new_loop)?;
            present.extend(new_columns);
        }
    }
    Ok(())
}
