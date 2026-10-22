# nmrstar

A pure Rust implementation of [PyNMR-STAR](https://github.com/bmrb-io/PyNMRSTAR): read, write, manipulate and
validate NMR-STAR files. It has the same object model as the Python library (an `Entry` holds `Saveframe`s, which
hold tags and `Loop`s) and reproduces its behaviour: the same parsing rules and error messages, byte-identical
NMR-STAR and JSON output, the same `normalize()`, and the same `validate()`/`validate_full()` findings.

```rust
use nmrstar::{Entry, ParseOptions, Severity};

let mut entry = Entry::from_file("bmr15000_3.str")?;
println!("{:?}", entry.get_tag("_Entry.Title")?);
for issue in entry.validate_full(None, Some("internal"), None, false)? {
    println!("{}", issue);
}
entry.normalize(None)?;
print!("{}", entry.to_star()?);
```

## Building and testing

```bash
cd nmrstar
cargo build
cargo test
```

The tests in `tests/` are ports of the Python unit tests in `pynmrstar/unit_tests`, one file per Python test module
and one test per Python test (with the same names), using the same sample files. A handful of tests fetch entries
from the BMRB API, as the Python ones do. The packaged NMR-STAR dictionary and the comments file are read from
`pynmrstar/reference_files` at compile time, so the crate is built from this repository.

`examples/nmrstar_tool.rs` reads a file and writes it back (`star`, `json`, `validate` or `normalize`), which is
useful for comparing output with the Python library; `examples/bench.rs` times parsing, writing and validation.

## Mapping from the Python API

Python's dynamic typing becomes explicit types and methods:

* **Values** are `nmrstar::Value`: `Null` (`None`), `Str`, `Int`, `Float`, `Bool`, `Decimal` and `Date`. Equality,
  ordering and `str()` follow Python, so `Value::Int(1) == Value::Float(1.0)`, but neither equals `"1"`.
* **Errors** are `nmrstar::Error`, with one variant per Python exception (`Parsing`, `InvalidState`, `Value`, `Key`,
  `Index`, `Type`, `Io`). `Error::is_value_error()` is true where Python's exception was a `ValueError` subclass.
* **Overloaded methods** are split by what they take or return: `Loop::get_tag()` (one tag), `get_tags()` (several,
  as rows), `get_tag_whole()`/`get_tags_whole()` (`whole_tag=True`) and `get_tags_dict()` (`dict_result=True`);
  `Saveframe::remove_loop()` (by category) and `remove_loop_obj()` (by loop), and so on. `Loop::add_data()` takes a
  `Data`, one variant per input format Python accepted.
* **`__str__`** is `to_star()`, **`__getitem__`/`__setitem__`/`__delitem__`** are named methods (`get_loop()`,
  `get_tag_required()`, `set_tag()`, `set_loop()`, `delete()`, `frame_at()`, ...), **`__contains__`** is
  `contains()`, and **`get_json(serialize=False)`** is `to_json_value()`.
* Changing a tag in place, which Python did through the list `get_tag(..., whole_tag=True)` returned, is
  `Saveframe::tag_mut()`.
* **`definitions.NULL_VALUES` and `STR_CONVERSION_DICT`** are `definitions::set_null_values()` and
  `definitions::set_str_conversion()`; like the Python module attributes, they apply to the whole program.
* Keyword arguments become parameters (or `ParseOptions` when parsing); Python's defaults are used where a
  method has a shorter variant (`add_tag()` vs `add_tag_with()`).
* Logged warnings go through the `log` crate.

## Differences from the Python library

Deliberate, where the Python behaviour was an accident rather than a feature:

* Tags the dictionary does not know sort in a stable order. Python sorted them by `hash()`, which changes from
  run to run.
* `normalize()` does not fail on a loop which shares its saveframe's tag prefix but lacks one of the saveframe's
  tags (Python raised `KeyError` from `get_saveframes_by_category()`).
* `Schema::add_tag()` computes the new dictionary sequence in linear rather than quadratic time, and stores the loop
  flag as `Y`/`N`.
* Where Python would have raised a `TypeError` comparing values of different types while sorting loop data for
  `compare()`, values are ordered by type instead.
* Integers are 64-bit, and JSON `NaN`/`Infinity` literals are not accepted on input.
