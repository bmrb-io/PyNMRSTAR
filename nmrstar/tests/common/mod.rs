//! Shared by the tests, which are ported from PyNMR-STAR's unit tests and use its sample files.
#![allow(dead_code)]

use std::cell::RefCell;
use std::path::PathBuf;
use std::sync::{LazyLock, Mutex, Once};

use nmrstar::Entry;

/// A path in PyNMR-STAR's unit test directory.
pub fn unit_test_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../pynmrstar/unit_tests").join(name)
}

/// A path in the sample files directory.
pub fn sample(name: &str) -> PathBuf {
    unit_test_path("sample_files").join(name)
}

/// The directory of the packaged dictionary distribution.
pub fn reference_files() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../pynmrstar/reference_files")
}

pub fn sample_file_location() -> PathBuf {
    sample("bmr15000_3.str")
}

static FILE_ENTRY: LazyLock<Entry> = LazyLock::new(|| Entry::from_file(sample_file_location()).unwrap());
static DATABASE_ENTRY: LazyLock<Entry> = LazyLock::new(|| Entry::from_database("15000").unwrap());

/// A copy of BMRB entry 15000, read from the sample file.
pub fn file_entry() -> Entry {
    FILE_ENTRY.clone()
}

/// A copy of BMRB entry 15000, fetched from the BMRB.
pub fn database_entry() -> Entry {
    DATABASE_ENTRY.clone()
}

/// Serializes tests which change process-wide settings (environment variables and definitions).
pub static GLOBAL_STATE: Mutex<()> = Mutex::new(());

pub fn lock_global_state() -> std::sync::MutexGuard<'static, ()> {
    GLOBAL_STATE.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

thread_local! {
    static CAPTURED: RefCell<Option<Vec<String>>> = const { RefCell::new(None) };
}

struct CaptureLogger;

impl log::Log for CaptureLogger {
    fn enabled(&self, _: &log::Metadata) -> bool {
        true
    }

    fn log(&self, record: &log::Record) {
        CAPTURED.with(|captured| {
            if let Some(messages) = captured.borrow_mut().as_mut() {
                messages.push(format!("{}:{}", record.level(), record.args()));
            }
        });
    }

    fn flush(&self) {}
}

/// Run a function, returning what it logged at warning level or above (on this thread), as
/// Python's `assertLogs` captures it.
pub fn capture_logs<R>(f: impl FnOnce() -> R) -> (R, Vec<String>) {
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        log::set_logger(&CaptureLogger).unwrap();
        log::set_max_level(log::LevelFilter::Warn);
    });
    CAPTURED.with(|captured| *captured.borrow_mut() = Some(Vec::new()));
    let result = f();
    let messages = CAPTURED.with(|captured| captured.borrow_mut().take().unwrap());
    (result, messages)
}

/// Assert that a function logs at least one warning.
pub fn assert_logs<R>(f: impl FnOnce() -> R) -> R {
    let (result, messages) = capture_logs(f);
    assert!(!messages.is_empty(), "expected a warning to be logged");
    result
}

/// Assert that a result is an error which would have been a Python ValueError (or a subclass).
#[track_caller]
pub fn assert_value_error<T: std::fmt::Debug>(result: nmrstar::Result<T>) {
    match result {
        Err(error) if error.is_value_error() => {}
        other => panic!("expected a value error, got {:?}", other),
    }
}

/// Assert that a result is a parsing error.
#[track_caller]
pub fn assert_parsing_error<T: std::fmt::Debug>(result: nmrstar::Result<T>) -> nmrstar::Error {
    match result {
        Err(error) if error.is_parsing_error() => error,
        other => panic!("expected a parsing error, got {:?}", other),
    }
}

/// Assert that a result is a key error.
#[track_caller]
pub fn assert_key_error<T: std::fmt::Debug>(result: nmrstar::Result<T>) {
    match result {
        Err(nmrstar::Error::Key(_)) => {}
        other => panic!("expected a key error, got {:?}", other),
    }
}

/// Assert that a result is an index error.
#[track_caller]
pub fn assert_index_error<T: std::fmt::Debug>(result: nmrstar::Result<T>) {
    match result {
        Err(nmrstar::Error::Index(_)) => {}
        other => panic!("expected an index error, got {:?}", other),
    }
}

/// Assert that a result is an invalid state error.
#[track_caller]
pub fn assert_invalid_state<T: std::fmt::Debug>(result: nmrstar::Result<T>) {
    match result {
        Err(nmrstar::Error::InvalidState(_)) => {}
        other => panic!("expected an invalid state error, got {:?}", other),
    }
}

/// Text values.
pub fn strs(values: &[&str]) -> Vec<nmrstar::Value> {
    values.iter().map(|v| nmrstar::Value::from(*v)).collect()
}
