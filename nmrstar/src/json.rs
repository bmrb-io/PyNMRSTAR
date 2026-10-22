//! JSON, written exactly as Python's `json.dumps()` writes it, so that the output of
//! `get_json()` is unchanged.

use crate::error::{Error, Result};
use crate::value::{float_repr, Value};

/// A JSON document, with object keys kept in order.
#[derive(Clone, Debug, PartialEq)]
pub enum Json {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Array(Vec<Json>),
    Object(Vec<(String, Json)>),
}

impl Json {
    /// Look up a key of an object.
    pub fn get(&self, key: &str) -> Option<&Json> {
        match self {
            Json::Object(members) => members.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    /// Whether this is an object with the key.
    pub fn has(&self, key: &str) -> bool {
        self.get(key).is_some()
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Json::Str(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&Vec<Json>> {
        match self {
            Json::Array(items) => Some(items),
            _ => None,
        }
    }

    /// Parse a JSON document.
    pub fn parse(text: &str) -> Result<Json> {
        let value: serde_json::Value = serde_json::from_str(text)
            .map_err(|error| Error::value(format!("Invalid JSON: {}", error)))?;
        Ok(Json::from_serde(value))
    }

    fn from_serde(value: serde_json::Value) -> Json {
        match value {
            serde_json::Value::Null => Json::Null,
            serde_json::Value::Bool(b) => Json::Bool(b),
            serde_json::Value::Number(n) => match n.as_i64() {
                Some(i) => Json::Int(i),
                None => Json::Float(n.as_f64().unwrap_or(f64::NAN)),
            },
            serde_json::Value::String(s) => Json::Str(s),
            serde_json::Value::Array(items) => Json::Array(items.into_iter().map(Json::from_serde).collect()),
            serde_json::Value::Object(members) => {
                Json::Object(members.into_iter().map(|(k, v)| (k, Json::from_serde(v))).collect())
            }
        }
    }

    /// The JSON for a tag or loop value. Decimals and dates are written as text.
    pub fn from_value(value: &Value) -> Json {
        match value {
            Value::Null => Json::Null,
            Value::Str(s) => Json::Str(s.to_string()),
            Value::Int(i) => Json::Int(*i),
            Value::Float(f) => Json::Float(*f),
            Value::Bool(b) => Json::Bool(*b),
            Value::Decimal(_) | Value::Date(_) => Json::Str(value.to_py_string().into_owned()),
        }
    }

    /// The tag or loop value for a JSON scalar.
    pub fn to_value(&self) -> Result<Value> {
        Ok(match self {
            Json::Null => Value::Null,
            Json::Bool(b) => Value::Bool(*b),
            Json::Int(i) => Value::Int(*i),
            Json::Float(f) => Value::Float(*f),
            Json::Str(s) => Value::from(s.as_str()),
            Json::Array(_) | Json::Object(_) => {
                return Err(Error::value("Only text, numbers, booleans and null can be tag or loop values."))
            }
        })
    }

    /// Optional text: a string, or null.
    pub(crate) fn to_optional_string(&self) -> Option<String> {
        match self {
            Json::Null => None,
            Json::Str(s) => Some(s.clone()),
            other => Some(other.to_value().map(|v| v.to_py_string().into_owned()).unwrap_or_default()),
        }
    }

    /// Write the document as Python's `json.dumps()` does by default.
    pub fn dumps(&self) -> String {
        let mut out = String::new();
        self.write(&mut out);
        out
    }

    fn write(&self, out: &mut String) {
        match self {
            Json::Null => out.push_str("null"),
            Json::Bool(true) => out.push_str("true"),
            Json::Bool(false) => out.push_str("false"),
            Json::Int(i) => out.push_str(&i.to_string()),
            Json::Float(f) => {
                if f.is_nan() {
                    out.push_str("NaN");
                } else if f.is_infinite() {
                    out.push_str(if *f > 0.0 { "Infinity" } else { "-Infinity" });
                } else {
                    out.push_str(&float_repr(*f));
                }
            }
            Json::Str(s) => write_string(s, out),
            Json::Array(items) => {
                out.push('[');
                for (i, item) in items.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    item.write(out);
                }
                out.push(']');
            }
            Json::Object(members) => {
                out.push('{');
                for (i, (key, value)) in members.iter().enumerate() {
                    if i > 0 {
                        out.push_str(", ");
                    }
                    write_string(key, out);
                    out.push_str(": ");
                    value.write(out);
                }
                out.push('}');
            }
        }
    }
}

fn write_string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (c as u32) > 0x7e => {
                let mut buffer = [0u16; 2];
                for unit in c.encode_utf16(&mut buffer) {
                    out.push_str(&format!("\\u{:04x}", unit));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dumps_like_python() {
        let doc = Json::Object(vec![
            ("a".to_string(), Json::Array(vec![Json::Int(1), Json::Float(1.5), Json::Null])),
            ("b".to_string(), Json::Str("é\n\"😀".to_string())),
        ]);
        assert_eq!(doc.dumps(), "{\"a\": [1, 1.5, null], \"b\": \"\\u00e9\\n\\\"\\ud83d\\ude00\"}");
    }
}
