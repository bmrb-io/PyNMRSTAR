//! Time parsing and writing a file: `bench FILE ITERATIONS`.

use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let text = std::fs::read_to_string(&args[1]).unwrap();
    let iterations: u32 = args[2].parse().unwrap();

    let start = Instant::now();
    let mut entry = None;
    for _ in 0..iterations {
        entry = Some(nmrstar::Entry::from_str(&text).unwrap());
    }
    let parse = start.elapsed() / iterations;

    let entry = entry.unwrap();
    let start = Instant::now();
    for _ in 0..iterations {
        std::hint::black_box(entry.to_star().unwrap());
    }
    let write = start.elapsed() / iterations;

    let start = Instant::now();
    for _ in 0..iterations.div_ceil(10) {
        std::hint::black_box(entry.validate_full(None, Some("internal"), None, false).unwrap());
    }
    let validate = start.elapsed() / iterations.div_ceil(10);
    println!("parse {:?}  write {:?}  validate_full {:?}", parse, write, validate);
}
