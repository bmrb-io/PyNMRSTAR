//! The values held by tags and loops.
//!
//! NMR-STAR values are text, and parsing a file produces only [`Value::Str`]. But values may also
//! be set programmatically, and converted to typed values using the dictionary (see
//! `convert_data_types`), so a value can be any of the types PyNMR-STAR allowed: `None`, text, an
//! integer, a float, a boolean, a `decimal.Decimal`, or a `datetime.date`. Equality, ordering, and
//! conversion to text follow the Python semantics PyNMR-STAR relied upon, so that `1`, `1.0` and
//! `Decimal('1.0')` are equal to each other, but not to `"1"`.

use std::borrow::Cow;
use std::cmp::Ordering;
use std::fmt;
use std::hash::{Hash, Hasher};

use compact_str::CompactString;

use crate::pystr;

/// A tag or loop value.
#[derive(Clone, Debug, Default)]
pub enum Value {
    /// No value (Python's `None`). Written as `.` in NMR-STAR.
    #[default]
    Null,
    /// Text. Every value read from a file is text. Short text is stored without allocating.
    Str(CompactString),
    /// An integer.
    Int(i64),
    /// A floating point number.
    Float(f64),
    /// A boolean.
    Bool(bool),
    /// An exact decimal number, which is what FLOAT tags become when converting data types.
    Decimal(Decimal),
    /// A date, which is what date tags become when converting data types.
    Date(Date),
}

impl Value {
    /// Create a text value.
    pub fn str(s: impl AsRef<str>) -> Value {
        Value::Str(CompactString::new(s.as_ref()))
    }

    /// Whether this is [`Value::Null`] (Python's `None`). Note that NMR-STAR has other ways of
    /// writing null values (`.` and `?`); see [`Value::is_null_value`] for those.
    pub fn is_none(&self) -> bool {
        matches!(self, Value::Null)
    }

    /// Whether this value is one of the null-equivalent values in
    /// [`crate::definitions::null_values`]: by default `None`, `""`, `"."` and `"?"`.
    pub fn is_null_value(&self) -> bool {
        crate::definitions::is_null(self)
    }

    /// The text of a text value.
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::Str(s) => Some(s),
            _ => None,
        }
    }

    /// Whether this is a text value.
    pub fn is_str(&self) -> bool {
        matches!(self, Value::Str(_))
    }

    /// The value as Python's `str()` would render it: `None` for a null value, `True` and
    /// `False` for booleans, and Python's formatting of numbers and dates.
    pub fn to_py_string(&self) -> Cow<'_, str> {
        match self {
            Value::Str(s) => Cow::Borrowed(s.as_str()),
            Value::Null => Cow::Borrowed("None"),
            Value::Bool(true) => Cow::Borrowed("True"),
            Value::Bool(false) => Cow::Borrowed("False"),
            Value::Int(i) => Cow::Owned(i.to_string()),
            Value::Float(f) => Cow::Owned(float_repr(*f)),
            Value::Decimal(d) => Cow::Owned(d.to_string()),
            Value::Date(d) => Cow::Owned(d.to_string()),
        }
    }

    /// Python's `int(value)`. Text is parsed as an integer (surrounding whitespace and
    /// underscores between digits allowed), and numbers are truncated towards zero.
    pub fn py_int(&self) -> Result<i64, ConversionError> {
        match self {
            Value::Str(s) => parse_int(s).ok_or(ConversionError::Value),
            Value::Int(i) => Ok(*i),
            Value::Bool(b) => Ok(*b as i64),
            Value::Float(f) => {
                if f.is_finite() && f.trunc().abs() < 9.2e18 {
                    Ok(f.trunc() as i64)
                } else {
                    Err(ConversionError::Value)
                }
            }
            Value::Decimal(d) => d.trunc_i64().ok_or(ConversionError::Value),
            Value::Null | Value::Date(_) => Err(ConversionError::Type),
        }
    }

    /// Python's `float(value)`.
    pub fn py_float(&self) -> Result<f64, ConversionError> {
        match self {
            Value::Str(s) => parse_float(s).ok_or(ConversionError::Value),
            Value::Int(i) => Ok(*i as f64),
            Value::Bool(b) => Ok(*b as i64 as f64),
            Value::Float(f) => Ok(*f),
            Value::Decimal(d) => Ok(d.to_f64()),
            Value::Null | Value::Date(_) => Err(ConversionError::Type),
        }
    }

    /// Python's `value < other`, as an ordering. `None` when Python would raise a `TypeError`
    /// (the values are of incomparable types), or the values are unordered (NaN).
    pub fn py_cmp(&self, other: &Value) -> Option<Ordering> {
        match (self, other) {
            (Value::Str(a), Value::Str(b)) => Some(a.cmp(b)),
            (Value::Date(a), Value::Date(b)) => Some(a.cmp(b)),
            _ => match (self.as_number(), other.as_number()) {
                (Some(a), Some(b)) => a.partial_cmp(&b),
                _ => None,
            },
        }
    }

    /// A total ordering of values: Python's where it has one, and otherwise by type (null, then
    /// numbers, then text, then dates). Used where Python would have raised an exception
    /// comparing values of different types.
    pub fn total_cmp(&self, other: &Value) -> Ordering {
        fn rank(value: &Value) -> u8 {
            match value {
                Value::Null => 0,
                Value::Bool(_) | Value::Int(_) | Value::Float(_) | Value::Decimal(_) => 1,
                Value::Str(_) => 2,
                Value::Date(_) => 3,
            }
        }
        match rank(self).cmp(&rank(other)) {
            Ordering::Equal => self.py_cmp(other).unwrap_or(Ordering::Equal),
            unequal => unequal,
        }
    }

    fn as_number(&self) -> Option<Number<'_>> {
        match self {
            Value::Int(i) => Some(Number::Int(*i as i128)),
            Value::Bool(b) => Some(Number::Int(*b as i128)),
            Value::Float(f) => Some(Number::Float(*f)),
            Value::Decimal(d) => Some(Number::Decimal(Cow::Borrowed(d))),
            _ => None,
        }
    }
}

/// Why a value could not be converted: the equivalent of Python's `ValueError` (the value is of
/// the right type, but does not represent a number) or `TypeError` (it is of the wrong type).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConversionError {
    Value,
    Type,
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.to_py_string())
    }
}

impl PartialEq for Value {
    fn eq(&self, other: &Value) -> bool {
        match (self, other) {
            (Value::Null, Value::Null) => true,
            (Value::Str(a), Value::Str(b)) => a == b,
            (Value::Date(a), Value::Date(b)) => a == b,
            _ => match (self.as_number(), other.as_number()) {
                (Some(a), Some(b)) => a.partial_cmp(&b) == Some(Ordering::Equal),
                _ => false,
            },
        }
    }
}

impl Eq for Value {}

impl Hash for Value {
    fn hash<H: Hasher>(&self, state: &mut H) {
        // Equal values must hash equally, and numbers of different types can be equal. So
        // integral numbers hash as the integer, and other numbers all hash alike.
        match self {
            Value::Null => 0u8.hash(state),
            Value::Str(s) => {
                1u8.hash(state);
                s.hash(state);
            }
            Value::Date(d) => {
                2u8.hash(state);
                d.hash(state);
            }
            _ => {
                let integral = match self {
                    Value::Int(i) => Some(*i),
                    Value::Bool(b) => Some(*b as i64),
                    Value::Float(f) if f.fract() == 0.0 && f.abs() < 9.2e18 => Some(*f as i64),
                    Value::Decimal(d) if d.is_integral() => d.trunc_i64(),
                    _ => None,
                };
                match integral {
                    Some(i) => {
                        3u8.hash(state);
                        i.hash(state);
                    }
                    None => 4u8.hash(state),
                }
            }
        }
    }
}

impl PartialEq<str> for Value {
    fn eq(&self, other: &str) -> bool {
        matches!(self, Value::Str(s) if s == other)
    }
}

impl PartialEq<&str> for Value {
    fn eq(&self, other: &&str) -> bool {
        matches!(self, Value::Str(s) if s == other)
    }
}

impl PartialEq<String> for Value {
    fn eq(&self, other: &String) -> bool {
        matches!(self, Value::Str(s) if s == other)
    }
}

impl PartialEq<i64> for Value {
    fn eq(&self, other: &i64) -> bool {
        *self == Value::Int(*other)
    }
}

impl PartialEq<i32> for Value {
    fn eq(&self, other: &i32) -> bool {
        *self == Value::Int(*other as i64)
    }
}

impl PartialEq<Value> for &str {
    fn eq(&self, other: &Value) -> bool {
        other == self
    }
}

impl From<&str> for Value {
    fn from(s: &str) -> Value {
        Value::Str(CompactString::new(s))
    }
}

impl From<&String> for Value {
    fn from(s: &String) -> Value {
        Value::Str(CompactString::new(s))
    }
}

impl From<String> for Value {
    fn from(s: String) -> Value {
        Value::Str(CompactString::from(s))
    }
}

impl From<i64> for Value {
    fn from(i: i64) -> Value {
        Value::Int(i)
    }
}

impl From<i32> for Value {
    fn from(i: i32) -> Value {
        Value::Int(i as i64)
    }
}

impl From<usize> for Value {
    fn from(i: usize) -> Value {
        Value::Int(i as i64)
    }
}

impl From<f64> for Value {
    fn from(f: f64) -> Value {
        Value::Float(f)
    }
}

impl From<bool> for Value {
    fn from(b: bool) -> Value {
        Value::Bool(b)
    }
}

impl From<Decimal> for Value {
    fn from(d: Decimal) -> Value {
        Value::Decimal(d)
    }
}

impl From<Date> for Value {
    fn from(d: Date) -> Value {
        Value::Date(d)
    }
}

impl<T: Into<Value>> From<Option<T>> for Value {
    fn from(value: Option<T>) -> Value {
        match value {
            Some(value) => value.into(),
            None => Value::Null,
        }
    }
}

/// Build a row of values: `row!["a", 1, None::<&str>]`.
#[macro_export]
macro_rules! row {
    ($($value:expr),* $(,)?) => {
        vec![$($crate::Value::from($value)),*]
    };
}

/// Python's `repr()` of a value.
pub fn py_repr(value: &Value) -> String {
    match value {
        Value::Str(s) => py_repr_str(s),
        Value::Decimal(d) => format!("Decimal('{}')", d),
        Value::Date(d) => format!("datetime.date({}, {}, {})", d.year(), d.month(), d.day()),
        other => other.to_py_string().into_owned(),
    }
}

/// Python's `repr()` of a list of values.
pub fn py_repr_list(values: &[Value]) -> String {
    format!("[{}]", values.iter().map(py_repr).collect::<Vec<_>>().join(", "))
}

/// Python's `repr()` of a string.
pub fn py_repr_str(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// A number of any of the numeric types, for comparing them with each other.
enum Number<'a> {
    Int(i128),
    Float(f64),
    Decimal(Cow<'a, Decimal>),
}

impl Number<'_> {
    fn to_decimal(&self) -> Cow<'_, Decimal> {
        match self {
            Number::Int(i) => Cow::Owned(Decimal::from_i128(*i)),
            Number::Float(f) => Cow::Owned(Decimal::from_f64(*f)),
            Number::Decimal(d) => Cow::Borrowed(d.as_ref()),
        }
    }

    fn partial_cmp(&self, other: &Number) -> Option<Ordering> {
        match (self, other) {
            (Number::Int(a), Number::Int(b)) => Some(a.cmp(b)),
            (Number::Float(a), Number::Float(b)) => a.partial_cmp(b),
            (Number::Int(i), Number::Float(f)) => int_float_cmp(*i, *f),
            (Number::Float(f), Number::Int(i)) => int_float_cmp(*i, *f).map(Ordering::reverse),
            _ => self.to_decimal().partial_cmp(&other.to_decimal()),
        }
    }
}

fn int_float_cmp(i: i128, f: f64) -> Option<Ordering> {
    if f.is_nan() {
        None
    } else if f.is_infinite() {
        Some(if f > 0.0 { Ordering::Less } else { Ordering::Greater })
    } else if f.fract() == 0.0 && f.abs() < 1e38 {
        Some(i.cmp(&(f as i128)))
    } else {
        Decimal::from_i128(i).partial_cmp(&Decimal::from_f64(f))
    }
}

/// Python's `repr()` (and `str()`) of a float: the shortest representation which reads back as
/// the same float, in positional notation for exponents from -4 to 15, and scientific otherwise.
pub fn float_repr(f: f64) -> String {
    if f.is_nan() {
        return "nan".to_string();
    }
    if f.is_infinite() {
        return if f > 0.0 { "inf".to_string() } else { "-inf".to_string() };
    }
    if f == 0.0 {
        return if f.is_sign_negative() { "-0.0".to_string() } else { "0.0".to_string() };
    }
    // Rust's {:e} gives the shortest round-tripping digits, as d.ddddde<exp>
    let sci = format!("{:e}", f);
    let (mantissa, exponent) = sci.split_once('e').expect("{:e} always has an exponent");
    let exponent: i32 = exponent.parse().expect("the exponent is an integer");
    let (sign, mantissa) = match mantissa.strip_prefix('-') {
        Some(rest) => ("-", rest),
        None => ("", mantissa),
    };
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();

    if (-4..16).contains(&exponent) {
        let point = exponent + 1;
        let body = if point <= 0 {
            format!("0.{}{}", "0".repeat((-point) as usize), digits)
        } else if point as usize >= digits.len() {
            format!("{}{}.0", digits, "0".repeat(point as usize - digits.len()))
        } else {
            format!("{}.{}", &digits[..point as usize], &digits[point as usize..])
        };
        format!("{}{}", sign, body)
    } else {
        let fraction = if digits.len() > 1 { format!(".{}", &digits[1..]) } else { String::new() };
        let exp_sign = if exponent < 0 { '-' } else { '+' };
        format!("{}{}{}e{}{:02}", sign, &digits[..1], fraction, exp_sign, exponent.abs())
    }
}

/// Remove the underscores Python allows between the digits of a number, returning None if any
/// is not between two digits.
fn strip_digit_underscores(s: &str) -> Option<Cow<'_, str>> {
    if !s.contains('_') {
        return Some(Cow::Borrowed(s));
    }
    let bytes = s.as_bytes();
    for (i, &b) in bytes.iter().enumerate() {
        if b == b'_' {
            let before = i > 0 && bytes[i - 1].is_ascii_digit();
            let after = i + 1 < bytes.len() && bytes[i + 1].is_ascii_digit();
            if !before || !after {
                return None;
            }
        }
    }
    Some(Cow::Owned(s.replace('_', "")))
}

/// Python's `int(text)`.
pub fn parse_int(s: &str) -> Option<i64> {
    let s = pystr::strip(s);
    let s = strip_digit_underscores(s)?;
    let (negative, digits) = match s.as_bytes().first() {
        Some(b'-') => (true, &s[1..]),
        Some(b'+') => (false, &s[1..]),
        _ => (false, &s[..]),
    };
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let magnitude: i128 = digits.parse().ok()?;
    let value = if negative { -magnitude } else { magnitude };
    i64::try_from(value).ok()
}

/// Python's `float(text)`.
pub fn parse_float(s: &str) -> Option<f64> {
    let s = pystr::strip(s);
    let s = strip_digit_underscores(s)?;
    let body = s.trim_start_matches(['+', '-']);
    if s.len() - body.len() > 1 {
        return None;
    }
    let lower = body.to_ascii_lowercase();
    if matches!(lower.as_str(), "inf" | "infinity" | "nan") {
        return s.parse().ok();
    }
    // Rust accepts the same syntax as Python for everything else, except that it is stricter
    // about nothing Python allows
    if body.is_empty() || !body.bytes().all(|b| b.is_ascii_digit() || matches!(b, b'.' | b'e' | b'E' | b'+' | b'-')) {
        return None;
    }
    s.parse().ok()
}

/// An exact decimal number, equivalent to Python's `decimal.Decimal`: it keeps the digits it was
/// written with, so `Decimal("1.50")` prints as `1.50`, though it equals `Decimal("1.5")`.
#[derive(Clone, Debug)]
pub struct Decimal(Box<DecimalInner>);

/// Boxed, so that decimals (which are rare) do not make every value larger.
#[derive(Clone, Debug)]
struct DecimalInner {
    negative: bool,
    kind: DecimalKind,
}

#[derive(Clone, Debug)]
enum DecimalKind {
    /// The value is digits × 10^exponent. The digits have no leading zeros, unless the
    /// coefficient is zero, which is "0".
    Finite { digits: String, exponent: i64 },
    Infinite,
    NaN { signaling: bool, payload: String },
}

impl Decimal {
    fn new(negative: bool, kind: DecimalKind) -> Decimal {
        Decimal(Box::new(DecimalInner { negative, kind }))
    }

    /// Parse a decimal number written as Python's `Decimal()` accepts it.
    pub fn parse(s: &str) -> Option<Decimal> {
        let s = pystr::strip(s);
        let (negative, body) = match s.as_bytes().first() {
            Some(b'-') => (true, &s[1..]),
            Some(b'+') => (false, &s[1..]),
            _ => (false, s),
        };
        let lower = body.to_ascii_lowercase();
        if lower == "inf" || lower == "infinity" {
            return Some(Decimal::new(negative, DecimalKind::Infinite));
        }
        for (prefix, signaling) in [("snan", true), ("nan", false)] {
            if let Some(payload) = lower.strip_prefix(prefix) {
                if payload.bytes().all(|b| b.is_ascii_digit()) {
                    let payload = payload.trim_start_matches('0').to_string();
                    return Some(Decimal::new(negative, DecimalKind::NaN { signaling, payload }));
                }
                return None;
            }
        }

        let body = strip_digit_underscores(body)?;
        let (mantissa, exponent) = match body.find(['e', 'E']) {
            Some(at) => {
                let exponent = &body[at + 1..];
                let exponent_digits = exponent.trim_start_matches(['+', '-']);
                if exponent_digits.is_empty() || exponent.len() - exponent_digits.len() > 1
                    || !exponent_digits.bytes().all(|b| b.is_ascii_digit()) {
                    return None;
                }
                (&body[..at], exponent.parse::<i64>().ok()?)
            }
            None => (&body[..], 0),
        };
        let (whole, fraction) = match mantissa.split_once('.') {
            Some((whole, fraction)) => (whole, fraction),
            None => (mantissa, ""),
        };
        if whole.is_empty() && fraction.is_empty() {
            return None;
        }
        if !whole.bytes().chain(fraction.bytes()).all(|b| b.is_ascii_digit()) {
            return None;
        }
        let digits = format!("{}{}", whole, fraction);
        let digits = digits.trim_start_matches('0');
        let digits = if digits.is_empty() { "0".to_string() } else { digits.to_string() };
        Some(Decimal::new(negative, DecimalKind::Finite { digits, exponent: exponent - fraction.len() as i64 }))
    }

    /// The decimal equal to an integer.
    pub fn from_i64(i: i64) -> Decimal {
        Decimal::from_i128(i as i128)
    }

    fn from_i128(i: i128) -> Decimal {
        Decimal::new(i < 0, DecimalKind::Finite { digits: i.unsigned_abs().to_string(), exponent: 0 })
    }

    /// The decimal exactly equal to a float, as Python's `Decimal(float)` gives.
    pub fn from_f64(f: f64) -> Decimal {
        let negative = f.is_sign_negative();
        if f.is_nan() {
            return Decimal::new(negative, DecimalKind::NaN { signaling: false, payload: String::new() });
        }
        if f.is_infinite() {
            return Decimal::new(negative, DecimalKind::Infinite);
        }
        let bits = f.abs().to_bits();
        let exponent_bits = ((bits >> 52) & 0x7ff) as i64;
        let fraction = bits & ((1u64 << 52) - 1);
        let (mut mantissa, mut exponent) = if exponent_bits == 0 {
            (fraction, -1074)
        } else {
            (fraction | (1u64 << 52), exponent_bits - 1075)
        };
        if mantissa == 0 {
            return Decimal::new(negative, DecimalKind::Finite { digits: "0".to_string(), exponent: 0 });
        }
        // Reduce the fraction mantissa / 2^-exponent, as float.as_integer_ratio() does
        while mantissa % 2 == 0 && exponent < 0 {
            mantissa /= 2;
            exponent += 1;
        }
        // Big integer arithmetic in base 10^9, least significant limb first
        let mut limbs: Vec<u64> = vec![mantissa % 1_000_000_000, mantissa / 1_000_000_000 % 1_000_000_000,
                                        mantissa / 1_000_000_000_000_000_000];
        let multiply = |limbs: &mut Vec<u64>, by: u64, times: i64| {
            for _ in 0..times {
                let mut carry = 0;
                for limb in limbs.iter_mut() {
                    let product = *limb * by + carry;
                    *limb = product % 1_000_000_000;
                    carry = product / 1_000_000_000;
                }
                while carry > 0 {
                    limbs.push(carry % 1_000_000_000);
                    carry /= 1_000_000_000;
                }
            }
        };
        let decimal_exponent = if exponent >= 0 {
            multiply(&mut limbs, 2, exponent);
            0
        } else {
            // m / 2^k = m × 5^k / 10^k
            multiply(&mut limbs, 5, -exponent);
            exponent
        };
        while limbs.len() > 1 && *limbs.last().unwrap() == 0 {
            limbs.pop();
        }
        let mut digits = limbs.last().unwrap().to_string();
        for limb in limbs.iter().rev().skip(1) {
            digits.push_str(&format!("{:09}", limb));
        }
        Decimal::new(negative, DecimalKind::Finite { digits, exponent: decimal_exponent })
    }

    fn is_integral(&self) -> bool {
        match &self.0.kind {
            DecimalKind::Finite { digits, exponent } => {
                *exponent >= 0 || digits.bytes().rev().take((-exponent) as usize).all(|b| b == b'0')
            }
            _ => false,
        }
    }

    /// The integer part, if it fits in an i64.
    fn trunc_i64(&self) -> Option<i64> {
        match &self.0.kind {
            DecimalKind::Finite { digits, exponent } => {
                let whole: String = if *exponent >= 0 {
                    if *exponent > 20 && digits != "0" {
                        return None;
                    }
                    format!("{}{}", digits, "0".repeat(*exponent as usize))
                } else {
                    let keep = digits.len() as i64 + exponent;
                    if keep <= 0 { "0".to_string() } else { digits[..keep as usize].to_string() }
                };
                let magnitude: i128 = whole.parse().ok()?;
                i64::try_from(if self.0.negative { -magnitude } else { magnitude }).ok()
            }
            _ => None,
        }
    }

    fn to_f64(&self) -> f64 {
        match &self.0.kind {
            DecimalKind::Finite { .. } => self.to_string().parse().unwrap_or(f64::NAN),
            DecimalKind::Infinite => if self.0.negative { f64::NEG_INFINITY } else { f64::INFINITY },
            DecimalKind::NaN { .. } => f64::NAN,
        }
    }

    /// Compare two decimals numerically. None if either is NaN.
    fn partial_cmp(&self, other: &Decimal) -> Option<Ordering> {
        use DecimalKind::*;
        let sign = |d: &Decimal| -> i8 {
            match &d.0.kind {
                Finite { digits, .. } if digits == "0" => 0,
                _ => if d.0.negative { -1 } else { 1 },
            }
        };
        match (&self.0.kind, &other.0.kind) {
            (NaN { .. }, _) | (_, NaN { .. }) => None,
            _ => {
                let (a, b) = (sign(self), sign(other));
                if a != b {
                    return Some(a.cmp(&b));
                }
                if a == 0 {
                    return Some(Ordering::Equal);
                }
                let magnitude = match (&self.0.kind, &other.0.kind) {
                    (Infinite, Infinite) => Ordering::Equal,
                    (Infinite, _) => Ordering::Greater,
                    (_, Infinite) => Ordering::Less,
                    (Finite { digits: da, exponent: ea }, Finite { digits: db, exponent: eb }) => {
                        let adjusted_a = ea + da.len() as i64;
                        let adjusted_b = eb + db.len() as i64;
                        adjusted_a.cmp(&adjusted_b).then_with(|| {
                            let da = da.trim_end_matches('0');
                            let db = db.trim_end_matches('0');
                            da.cmp(db)
                        })
                    }
                    _ => unreachable!(),
                };
                Some(if a < 0 { magnitude.reverse() } else { magnitude })
            }
        }
    }
}

impl PartialEq for Decimal {
    fn eq(&self, other: &Decimal) -> bool {
        self.partial_cmp(other) == Some(Ordering::Equal)
    }
}

impl fmt::Display for Decimal {
    /// Python's `str(Decimal)`, with a lowercase exponent marker (PyNMR-STAR sets
    /// `decimal.getcontext().capitals = 0`).
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let sign = if self.0.negative { "-" } else { "" };
        match &self.0.kind {
            DecimalKind::Infinite => write!(f, "{}Infinity", sign),
            DecimalKind::NaN { signaling, payload } => {
                write!(f, "{}{}NaN{}", sign, if *signaling { "s" } else { "" }, payload)
            }
            DecimalKind::Finite { digits, exponent } => {
                let left_digits = exponent + digits.len() as i64;
                let dot_place = if *exponent <= 0 && left_digits > -6 { left_digits } else { 1 };
                let (int_part, frac_part) = if dot_place <= 0 {
                    ("0".to_string(), format!(".{}{}", "0".repeat((-dot_place) as usize), digits))
                } else if dot_place as usize >= digits.len() {
                    (format!("{}{}", digits, "0".repeat(dot_place as usize - digits.len())), String::new())
                } else {
                    (digits[..dot_place as usize].to_string(), format!(".{}", &digits[dot_place as usize..]))
                };
                let exponent = if left_digits == dot_place {
                    String::new()
                } else {
                    format!("e{:+}", left_digits - dot_place)
                };
                write!(f, "{}{}{}{}", sign, int_part, frac_part, exponent)
            }
        }
    }
}

/// A calendar date, equivalent to Python's `datetime.date`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Date {
    year: i32,
    month: u32,
    day: u32,
}

impl Date {
    /// A date, if it exists (and its year is from 1 to 9999, as Python requires).
    pub fn new(year: i32, month: u32, day: u32) -> Option<Date> {
        if !(1..=9999).contains(&year) || !(1..=12).contains(&month) || day < 1 {
            return None;
        }
        let leap = (year % 4 == 0 && year % 100 != 0) || year % 400 == 0;
        let days = match month {
            2 => if leap { 29 } else { 28 },
            4 | 6 | 9 | 11 => 30,
            _ => 31,
        };
        if day > days {
            return None;
        }
        Some(Date { year, month, day })
    }

    pub fn year(&self) -> i32 {
        self.year
    }

    pub fn month(&self) -> u32 {
        self.month
    }

    pub fn day(&self) -> u32 {
        self.day
    }
}

impl fmt::Display for Date {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:04}-{:02}-{:02}", self.year, self.month, self.day)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decimal_strings_match_python() {
        for (input, expected) in [("1.2", "1.2"), ("007.50", "7.50"), ("0.00", "0.00"), ("-0", "-0"),
                                  ("1E3", "1e+3"), ("1.2e-7", "1.2e-7"), ("0.000001", "0.000001"),
                                  ("0.0000001", "1e-7"), ("123e2", "1.23e+4"), ("1_000", "1000"),
                                  (" 5 ", "5"), ("inf", "Infinity"), ("-nan", "-NaN"), (".5", "0.5"),
                                  ("5.", "5")] {
            assert_eq!(Decimal::parse(input).unwrap().to_string(), expected, "{}", input);
        }
        for invalid in ["", ".", "1.2.3", "e5", "1e", "abc", "1_", "--1"] {
            assert!(Decimal::parse(invalid).is_none(), "{}", invalid);
        }
        assert_eq!(Decimal::from_f64(0.5).to_string(), "0.5");
        assert_eq!(Decimal::from_f64(1.2).to_string(), "1.1999999999999999555910790149937383830547332763671875");
        assert_eq!(Decimal::from_f64(1e20).to_string(), "100000000000000000000");
    }

    #[test]
    fn numeric_equality_crosses_types() {
        assert_eq!(Value::Int(1), Value::Float(1.0));
        assert_eq!(Value::Int(5), Value::Decimal(Decimal::parse("5.00").unwrap()));
        assert_eq!(Value::Bool(true), Value::Int(1));
        assert_ne!(Value::Int(1), Value::from("1"));
        assert_ne!(Value::Decimal(Decimal::parse("1.2").unwrap()), Value::Float(1.2));
        assert_eq!(Value::Decimal(Decimal::parse("0.5").unwrap()), Value::Float(0.5));
        assert_eq!(Value::Null, Value::Null);
        assert_ne!(Value::Null, Value::from("."));
    }

    #[test]
    fn float_repr_matches_python() {
        for (input, expected) in [(1.2, "1.2"), (123.0, "123.0"), (1e16, "1e+16"), (1.5e-5, "1.5e-05"),
                                  (0.0001, "0.0001"), (-2.5, "-2.5"), (1e15, "1000000000000000.0")] {
            assert_eq!(float_repr(input), expected);
        }
    }

    #[test]
    fn int_and_float_parsing_match_python() {
        assert_eq!(parse_int(" 12 "), Some(12));
        assert_eq!(parse_int("-1_000"), Some(-1000));
        assert_eq!(parse_int("1.0"), None);
        assert_eq!(parse_int(""), None);
        assert_eq!(parse_int("+"), None);
        assert_eq!(parse_float("1e5"), Some(1e5));
        assert_eq!(parse_float(" .5 "), Some(0.5));
        assert!(parse_float("abc").is_none());
        assert!(parse_float("Infinity").unwrap().is_infinite());
    }
}
