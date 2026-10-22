//! Read, write, manipulate and validate NMR-STAR files.
//!
//! A pure Rust implementation of PyNMR-STAR, maintained by the BMRB. The object model is the
//! same: an [`Entry`] holds [`Saveframe`]s, which hold tags and [`Loop`]s.
//!
//! ```no_run
//! use nmrstar::Entry;
//!
//! let entry = Entry::from_file("bmr15000_3.str").unwrap();
//! for saveframe in &entry {
//!     println!("{} {:?}", saveframe.name(), saveframe.category());
//! }
//! println!("{:?}", entry.get_tag("_Entry.Title").unwrap());
//! print!("{}", entry.to_star().unwrap());
//! ```

pub mod definitions;
pub mod entry;
pub mod error;
pub mod internal;
pub mod json;
pub mod parser;
pub mod repair;
pub mod saveframe;
pub mod schema;
pub mod star_loop;
pub mod utils;
pub mod validation;
pub mod value;

mod csv;
mod format;
mod pyregex;
mod pystr;
mod quoting;
mod sha1;

pub use entry::Entry;
pub use error::{Error, Result};
pub use internal::Source;
pub use parser::ParseOptions;
pub use saveframe::{FileFormat, Saveframe, Tag};
pub use schema::Schema;
pub use star_loop::{Data, Loop};
pub use validation::{Severity, ValidationIssue};
pub use value::{Date, Decimal, Value};
/// The text type of [`Value::Str`]: a string stored inline when short.
pub use compact_str::CompactString;

/// The version of the library (that of the PyNMR-STAR release it implements).
pub const VERSION: &str = env!("CARGO_PKG_VERSION");
