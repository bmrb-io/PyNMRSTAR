# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PyNMRSTAR is a Python library for reading, writing, and manipulating NMR-STAR data files, maintained by BMRB (Biological Magnetic Resonance Bank). It uses a hybrid Rust+Python implementation where the Rust code (via PyO3/maturin) handles parsing and formatting for performance.

## Build and Test Commands

All commands should be run in the virtual environment:

```bash
# Activate virtual environment (managed by uv)
source .venv/bin/activate

# Development install (builds Rust extension)
uv pip install -e .

# Build just the Rust extension
maturin develop

# Run full test suite
python -m pynmrstar.unit_tests

# Run specific test module
python -m unittest pynmrstar.unit_tests.test_entry

# Run with coverage
coverage run --source=pynmrstar -m pynmrstar.unit_tests
coverage report

# Build documentation
cd docs && make html
```

## Architecture

### Core Data Model Hierarchy

```
Entry (represents an NMR-STAR entry, e.g., BMRB entry 15000)
  └── Saveframe (groups related data, e.g., "entry_information")
        ├── Tags (single-value key-value pairs)
        └── Loop (tabular data with rows/columns)
```

### Key Source Files

| File | Purpose |
|------|---------|
| `pynmrstar/entry.py` | Entry class - main container for NMR-STAR data |
| `pynmrstar/saveframe.py` | Saveframe class - groups tags and loops |
| `pynmrstar/loop.py` | Loop class - tabular data handling |
| `pynmrstar/schema.py` | Schema validation using BMRB dictionary |
| `pynmrstar/_internal.py` | File I/O, network requests, JSON serialization |
| `src/parser.rs` | Rust parser (performance-critical) |
| `src/accelerators.rs` | Rust formatting for loops/saveframes |

### Rust/Python Boundary

The Rust code in `src/` provides:
- `parse()` - Tokenize and parse NMR-STAR text
- `quote_value()` - Proper quoting of values for output
- `format_loop()` / `format_saveframe()` - Fast string formatting

Python code handles the object model, validation, and public API.

### Construction Patterns

All core classes use factory methods for construction:
- `from_file()`, `from_string()`, `from_database()`, `from_scratch()`, `from_json()`, `from_template()`

Container protocol is fully supported (`__getitem__`, `__iter__`, `__len__`, etc.).

### Tag Format

Tags follow the pattern `_Category.tag_name`. Categories are extracted/formatted via `format_category()` which adds the `_` prefix and strips the tag suffix.

## Test Structure

Tests are in `pynmrstar/unit_tests/`:
- `test_entry.py`, `test_saveframe.py`, `test_loop.py` - Core class tests
- `test_schema.py`, `test_parser.py`, `test_utils.py` - Supporting tests
- `sample_files/` - Test data files
- `naughty-strings/` - Edge case string testing

## External Dependencies

- BMRB API at `https://api.bmrb.io/v2` for fetching entries
- Schema loaded from packaged reference or BMRB GitHub
