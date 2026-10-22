//! Reading files and URLs, fetching entries, and loading the dictionary distribution.

use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use log::warn;

use crate::csv;
use crate::definitions;
use crate::entry::Entry;
use crate::error::{Error, Result};
use crate::parser::ParseOptions;
use crate::schema::Schema;

/// Where to read NMR-STAR (or CSV) data from: a file, a URL, or bytes already in memory. Text
/// starting `http://`, `https://` or `ftp://` is a URL, and other text a path. Gzipped data is
/// decompressed.
#[derive(Clone, Debug)]
pub enum Source {
    Path(PathBuf),
    Url(String),
    Bytes(Vec<u8>),
}

impl Source {
    /// Read everything from a reader (an open file, for example).
    pub fn from_reader(mut reader: impl Read) -> Result<Source> {
        let mut bytes = Vec::new();
        reader.read_to_end(&mut bytes)?;
        Ok(Source::Bytes(bytes))
    }

    /// How the source is named in an object's `source` description.
    pub(crate) fn label(&self) -> String {
        match self {
            Source::Path(path) => path.display().to_string(),
            Source::Url(url) => url.clone(),
            Source::Bytes(_) => "<bytes>".to_string(),
        }
    }
}

impl From<&str> for Source {
    fn from(s: &str) -> Source {
        if s.starts_with("http://") || s.starts_with("https://") || s.starts_with("ftp://") {
            Source::Url(s.to_string())
        } else {
            Source::Path(PathBuf::from(s))
        }
    }
}

impl From<String> for Source {
    fn from(s: String) -> Source {
        Source::from(s.as_str())
    }
}

impl From<&String> for Source {
    fn from(s: &String) -> Source {
        Source::from(s.as_str())
    }
}

impl From<&Path> for Source {
    fn from(path: &Path) -> Source {
        Source::Path(path.to_path_buf())
    }
}

impl From<PathBuf> for Source {
    fn from(path: PathBuf) -> Source {
        Source::Path(path)
    }
}

impl From<&PathBuf> for Source {
    fn from(path: &PathBuf) -> Source {
        Source::Path(path.clone())
    }
}

impl From<Vec<u8>> for Source {
    fn from(bytes: Vec<u8>) -> Source {
        Source::Bytes(bytes)
    }
}

/// Read the text of a source, decompressing it if it is gzipped, with its line endings
/// normalized to newlines.
pub fn read_text(source: &Source) -> Result<String> {
    let bytes = match source {
        Source::Path(path) => fs::read(path).map_err(|error| Error::Io(format!("{}: {}", path.display(), error)))?,
        Source::Url(url) => get_url(url, 10, 0)?,
        Source::Bytes(bytes) => bytes.clone(),
    };
    let bytes = if bytes.starts_with(&[0x1f, 0x8b]) {
        let mut decompressed = Vec::new();
        match flate2::read::MultiGzDecoder::new(&bytes[..]).read_to_end(&mut decompressed) {
            Ok(_) => decompressed,
            Err(_) => bytes,
        }
    } else {
        bytes
    };
    let text = String::from_utf8(bytes).map_err(|error| Error::Io(format!("The data is not UTF-8: {}", error)))?;
    Ok(if text.contains('\r') { text.replace("\r\n", "\n").replace('\r', "\n") } else { text })
}

/// Why fetching a URL failed.
#[derive(Debug)]
enum FetchError {
    /// The server says there is no such thing
    NotFound,
    /// Anything else
    Failed(String),
}

impl From<FetchError> for Error {
    fn from(error: FetchError) -> Error {
        match error {
            FetchError::NotFound => Error::key("Server returned 404."),
            FetchError::Failed(message) => Error::Io(message),
        }
    }
}

/// Fetch a URL, retrying with an exponential backoff if rate limited.
fn get_url(url: &str, timeout: u64, retries: u32) -> Result<Vec<u8>> {
    fetch(url, 10.0, timeout, retries).map_err(Error::from)
}

#[cfg(feature = "network")]
fn fetch(url: &str, wait_time: f64, timeout: u64, retries: u32) -> std::result::Result<Vec<u8>, FetchError> {
    let agent = ureq::AgentBuilder::new().timeout(std::time::Duration::from_secs(timeout)).build();
    let request = || agent.get(url).set("Application", &format!("PyNMRSTAR {}", crate::VERSION)).call();
    // A connection error is tried once more, as PyNMR-STAR did with a fresh session
    let response = match request() {
        Err(ureq::Error::Transport(_)) => request(),
        other => other,
    };
    match response {
        Ok(response) => {
            let mut bytes = Vec::new();
            response.into_reader().read_to_end(&mut bytes)
                .map_err(|error| FetchError::Failed(error.to_string()))?;
            Ok(bytes)
        }
        Err(ureq::Error::Status(403, _)) => {
            if retries > 0 {
                warn!("We were rate limited. Sleeping for {} seconds.", wait_time);
                std::thread::sleep(std::time::Duration::from_secs_f64(wait_time));
                fetch(url, wait_time * 2.0, timeout, retries - 1)
            } else {
                Err(FetchError::Failed(
                    "Continued to receive 403 (forbidden, due to rate limit) after multiple wait times.".to_string()))
            }
        }
        Err(ureq::Error::Status(404, _)) => Err(FetchError::NotFound),
        Err(ureq::Error::Status(code, _)) => Err(FetchError::Failed(format!("HTTP error {} for url: {}", code, url))),
        Err(ureq::Error::Transport(_)) => Err(FetchError::Failed(
            "A ConnectionError was thrown during an attempt to load the entry.".to_string())),
    }
}

#[cfg(not(feature = "network"))]
fn fetch(url: &str, _wait_time: f64, _timeout: u64, _retries: u32) -> std::result::Result<Vec<u8>, FetchError> {
    Err(FetchError::Failed(format!("Cannot fetch '{}': the library was built without network support.", url)))
}

/// Fetch an entry from the BMRB API, falling back to the FTP site. Used by
/// [`Entry::from_database`].
pub(crate) fn get_entry_from_database(entry_num: &str, convert_data_types: bool, schema: Option<&Schema>) -> Result<Entry> {
    let entry_num = crate::pystr::strip(entry_num);
    // The API looks chemcomps up case-sensitively, by their uppercase PDB ligand code, so only the
    //  prefix can be normalized. Everything else is lowercase.
    let entry_num = if crate::pystr::lower(entry_num).starts_with("chemcomp_") {
        format!("chemcomp_{}", crate::pystr::upper(&entry_num[9..]))
    } else {
        let lower = crate::pystr::lower(entry_num);
        lower.strip_prefix("bmr").map(str::to_string).unwrap_or(lower)
    };

    let entry_url = format!("{}/entry/{}?format=zlib", definitions::api_url(), entry_num);
    let from_api = || -> std::result::Result<Entry, FetchError> {
        let compressed = fetch(&entry_url, 10.0, 10, 2)?;
        let mut text = String::new();
        flate2::read::ZlibDecoder::new(&compressed[..]).read_to_string(&mut text)
            .map_err(|error| FetchError::Failed(error.to_string()))?;
        let json = crate::json::Json::parse(&text).map_err(|error| FetchError::Failed(error.to_string()))?;
        if json.has("error") {
            return Err(FetchError::Failed("Something wrong with API response.".to_string()));
        }
        Entry::from_json_value(&json).map_err(|error| FetchError::Failed(error.to_string()))
    };

    let mut entry = match from_api() {
        Ok(entry) => entry,
        Err(FetchError::NotFound) => {
            return Err(Error::Io(format!("Entry {} does not exist in the public database.", entry_num)));
        }
        Err(FetchError::Failed(_)) => {
            if entry_num.starts_with("chemcomp") {
                return Err(Error::Io("Unable to load that chemcomp from the API.".to_string()));
            }
            warn!("Failed to download entry from the API, trying again from the FTP site.");
            let url = if entry_num.contains("bmse") || entry_num.contains("bmst") {
                format!("{}/metabolomics/entry_directories/{}/{}.str", definitions::FTP_URL, entry_num, entry_num)
            } else {
                format!("{}/entry_directories/bmr{}/bmr{}_3.str", definitions::FTP_URL, entry_num, entry_num)
            };
            let bytes = fetch(&url, 10.0, 20, 1).map_err(|_| {
                Error::Io(format!("Entry {} does not exist in the public database.", entry_num))
            })?;
            let text = String::from_utf8(bytes).map_err(|error| Error::Io(error.to_string()))?;
            Entry::from_str(&text)?
        }
    };

    let source = format!("from_database({})", entry_num);
    entry.source = Some(source.clone());
    for saveframe in &mut entry.frame_list {
        saveframe.source = source.clone();
        for each_loop in &mut saveframe.loops {
            each_loop.source = source.clone();
        }
    }

    if convert_data_types {
        let schema = crate::utils::get_schema(schema);
        for saveframe in &mut entry.frame_list {
            let prefix = saveframe.tag_prefix.clone().unwrap_or_else(|| "None".to_string());
            for tag in saveframe.tags_mut() {
                tag.value = schema.convert_tag(&format!("{}.{}", prefix, tag.name), &tag.value)?;
            }
            for each_loop in &mut saveframe.loops {
                let category = each_loop.category().unwrap_or("None").to_string();
                let tags: Vec<String> = each_loop.tags().to_vec();
                for row in &mut each_loop.data {
                    for (position, value) in row.iter_mut().enumerate() {
                        *value = schema.convert_tag(&format!("{}.{}", category, tags[position]), value)?;
                    }
                }
            }
        }
    }
    Ok(entry)
}

/// The BMRB API's list of entries in a database.
pub(crate) fn list_entries(metabolomics: bool) -> Result<Vec<String>> {
    let database = if metabolomics { "metabolomics" } else { "macromolecules" };
    let url = format!("{}/list_entries?database={}", definitions::api_url(), database);
    let text = read_text(&Source::Url(url))?;
    let json = crate::json::Json::parse(&text)?;
    Ok(json.as_array().map(|items| items.iter().map(|item| match item {
        crate::json::Json::Str(s) => s.clone(),
        other => other.dumps(),
    }).collect()).unwrap_or_default())
}

// ---------------------------------------------------------------------------------------------
// The dictionary distribution
// ---------------------------------------------------------------------------------------------

/// The distribution files a Schema is built from, by file name.
pub type Dictionary = HashMap<String, String>;

/// Pass as a version to fetch the newest dictionary release.
pub const LATEST_DICTIONARY: &str = "latest";

const PACKAGED: [(&str, &str); 5] = [
    ("xlschem_ann.csv", include_str!("../../pynmrstar/reference_files/xlschem_ann.csv")),
    ("adit_enum_hdr.csv", include_str!("../../pynmrstar/reference_files/adit_enum_hdr.csv")),
    ("adit_enum_dtl.csv", include_str!("../../pynmrstar/reference_files/adit_enum_dtl.csv")),
    ("adit_cat_grp_o.csv", include_str!("../../pynmrstar/reference_files/adit_cat_grp_o.csv")),
    ("adit_tag_validation.csv", include_str!("../../pynmrstar/reference_files/adit_tag_validation.csv")),
];

/// The value type definitions.
pub(crate) const DATA_TYPES: &str = include_str!("../../pynmrstar/reference_files/data_types.csv");
/// The comments written before saveframes.
const COMMENTS: &str = include_str!("../../pynmrstar/reference_files/comments.str");

/// The packaged copy of the dictionary distribution.
pub(crate) fn packaged_dictionary() -> Dictionary {
    PACKAGED.iter().map(|(name, text)| (name.to_string(), text.to_string())).collect()
}

/// The text of the packaged tag table.
pub(crate) fn packaged_xlschem() -> &'static str {
    PACKAGED[0].1
}

/// Directory that holds cached dictionary distributions, one subdirectory per release version.
fn dictionary_cache_root() -> PathBuf {
    let root = match std::env::var("XDG_CACHE_HOME") {
        Ok(root) if !root.is_empty() => PathBuf::from(root),
        _ => {
            let home = std::env::var("HOME").or_else(|_| std::env::var("USERPROFILE")).unwrap_or_else(|_| ".".into());
            PathBuf::from(home).join(".cache")
        }
    };
    root.join("pynmrstar")
}

/// Read the dictionary release version out of an xlschem_ann.csv body.
pub fn dictionary_version(xlschem_text: &str) -> String {
    for row in csv::dicts(xlschem_text) {
        if row.get("Dictionary sequence").map(String::as_str) == Some("TBL_BEGIN") {
            return match row.get("ADIT category view type") {
                Some(version) if !version.is_empty() => version.clone(),
                _ => "unknown".to_string(),
            };
        }
    }
    "unknown".to_string()
}

/// The version of the dictionary distribution packaged with the library.
pub fn packaged_dictionary_version() -> String {
    static VERSION: OnceLock<String> = OnceLock::new();
    VERSION.get_or_init(|| dictionary_version(packaged_xlschem())).clone()
}

fn is_url(location: &str) -> bool {
    location.starts_with("http://") || location.starts_with("https://") || location.starts_with("ftp://")
}

/// Read every distribution file from a local directory (or URL base). Fails if any of them is
/// missing: a partial distribution would quietly produce a schema without its enumerations or
/// validation rules.
pub fn read_dictionary_directory(directory: &str) -> Result<Dictionary> {
    let mut files = Dictionary::new();
    for name in definitions::DICTIONARY_FILES {
        let location = if is_url(directory) {
            Source::Url(format!("{}/{}", directory.trim_end_matches('/'), name))
        } else {
            Source::Path(Path::new(directory).join(name))
        };
        files.insert(name.to_string(), read_text(&location)?);
    }
    Ok(files)
}

/// Write a distribution to the cache, best effort. The files are written to a scratch directory
/// which is then renamed into place, so the cache only ever holds complete distributions.
fn cache_dictionary(files: &Dictionary, version: &str) {
    let root = dictionary_cache_root();
    let target = root.join(version);
    if target.is_dir() {
        return;
    }
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let scratch = root.join(format!(".partial-{}-{}", std::process::id(), nanos));
    let result = (|| -> std::io::Result<()> {
        fs::create_dir_all(&scratch)?;
        for (name, text) in files {
            fs::write(scratch.join(name), text)?;
        }
        fs::rename(&scratch, &target)
    })();
    if result.is_err() {
        // Caching is best effort; most likely another process won the race
        let _ = fs::remove_dir_all(&scratch);
    }
}

/// The distribution files for one release if they are on this machine - packaged with the
/// library or cached - and None otherwise. Never touches the network.
pub fn local_dictionary(version: &str) -> Option<Dictionary> {
    if version == packaged_dictionary_version() {
        return Some(packaged_dictionary());
    }
    let cached = dictionary_cache_root().join(version);
    if cached.is_dir() {
        return read_dictionary_directory(&cached.to_string_lossy()).ok();
    }
    None
}

/// Read a whole distribution from a URL base or local directory, with the version it contains.
fn fetch_dictionary(source: &str) -> Result<(Dictionary, String)> {
    let files = read_dictionary_directory(source)
        .map_err(|error| Error::value(format!("Could not fetch the dictionary from '{}': {}", source, error)))?;
    let version = dictionary_version(&files["xlschem_ann.csv"]);
    Ok((files, version))
}

/// The dictionary distribution files a [`Schema`] is built from, and their version.
///
/// * `version = None`: the distribution packaged with the library. Never touches the network
///   or the cache.
/// * `version = Some("latest")`: the newest release, fetched from `source` every time and cached
///   under `${XDG_CACHE_HOME:-~/.cache}/pynmrstar/<version>/` so it can be asked for by number
///   later.
/// * any other version: that release - the packaged one if it matches, else a cached copy, else
///   the release tagged for it in the dictionary repository, else `source` if that is what it
///   currently serves. A release downloaded either way is cached.
///
/// `source` defaults to the `PYNMRSTAR_DICTIONARY_SOURCE` environment variable, then
/// [`definitions::dictionary_url`]; it may be a URL base or a local directory. Passing `source`
/// or setting the environment variable means only it is read: tagged releases are not looked up.
pub fn load_dictionary(version: Option<&str>, source: Option<&str>) -> Result<(Dictionary, String)> {
    let version = match version {
        None => return Ok((packaged_dictionary(), packaged_dictionary_version())),
        Some(version) => version,
    };

    if version != LATEST_DICTIONARY {
        if let Some(local) = local_dictionary(version) {
            return Ok((local, version.to_string()));
        }
    }

    let mut source = source.map(str::to_string).or_else(|| std::env::var("PYNMRSTAR_DICTIONARY_SOURCE").ok());
    let mut release_error: Option<Error> = None;
    if version != LATEST_DICTIONARY && source.is_none() {
        let release = definitions::dictionary_release_url().replace("{version}", version);
        match fetch_dictionary(&release) {
            Ok((files, fetched_version)) => {
                if fetched_version != version {
                    return Err(Error::value(format!(
                        "The dictionary release tagged for version '{}' at '{}' contains version '{}'.",
                        version, release, fetched_version)));
                }
                cache_dictionary(&files, &fetched_version);
                return Ok((files, fetched_version));
            }
            // Not tagged (yet) - it may still be the newest release
            Err(error) => release_error = Some(error),
        }
    }

    let source = source.take().unwrap_or_else(definitions::dictionary_url);
    let (files, fetched_version) = fetch_dictionary(&source)?;

    if version != LATEST_DICTIONARY && version != fetched_version {
        let tagged = match &release_error {
            Some(error) => format!(" no release is tagged for it ({}),", error),
            None => String::new(),
        };
        return Err(Error::value(format!(
            "Dictionary version '{}' is unavailable: it is not the packaged version ({}), it is not cached,{} and \
             the newest release is '{}'.", version, packaged_dictionary_version(), tagged, fetched_version)));
    }

    cache_dictionary(&files, &fetched_version);
    Ok((files, fetched_version))
}

/// The comment written before each saveframe category: (comment, whether it is written before
/// every saveframe of the category rather than only the first).
pub(crate) fn comments() -> &'static HashMap<String, (String, bool)> {
    static COMMENT_MAP: OnceLock<HashMap<String, (String, bool)>> = OnceLock::new();
    COMMENT_MAP.get_or_init(|| {
        let mut comments = HashMap::new();
        let entry = match Entry::from_str_opts(COMMENTS, ParseOptions::new()) {
            Ok(entry) => entry,
            Err(_) => {
                warn!("Could not load comments. No comments will be shown.");
                return comments;
            }
        };
        if let Some(comment_loop) = entry.frame_list.first().and_then(|frame| frame.loops.first()) {
            if let Ok(rows) = comment_loop.get_tags(&["category", "comment", "every_flag"]) {
                for row in rows {
                    if row[1] != "." {
                        let comment = format!("{}\n\n", row[1].to_py_string().trim_end());
                        comments.insert(row[0].to_py_string().into_owned(), (comment, row[2] == "Y"));
                    }
                }
            }
        }
        comments
    })
}
