use pyo3::prelude::*;

mod accelerators;
mod parser;
mod utils;

// The module is safe to run without the GIL, so free-threaded Python (3.14t and later) can parse
//  and write entries in several threads at once
#[pymodule(gil_used = false)]
fn pynmrstar_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parser::parse, m)?)?;
    m.add_function(wrap_pyfunction!(utils::quote_value, m)?)?;
    m.add_function(wrap_pyfunction!(accelerators::format_loop, m)?)?;
    m.add_function(wrap_pyfunction!(accelerators::format_saveframe, m)?)?;
    Ok(())
}
