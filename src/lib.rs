use pyo3::prelude::*;

mod accelerators;
mod parser;
mod utils;

#[pymodule]
fn pynmrstar_parser(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(parser::parse, m)?)?;
    m.add_function(wrap_pyfunction!(utils::quote_value, m)?)?;
    m.add_function(wrap_pyfunction!(accelerators::format_loop, m)?)?;
    m.add_function(wrap_pyfunction!(accelerators::format_saveframe, m)?)?;
    Ok(())
}
