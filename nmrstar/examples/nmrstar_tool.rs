//! Read an NMR-STAR file and write it back out: `nmrstar_tool [star|json|validate|normalize] FILE`.

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: {} [star|json|validate|normalize] FILE", args[0]);
        std::process::exit(2);
    }
    let mut entry = match nmrstar::Entry::from_file(args[2].as_str()) {
        Ok(entry) => entry,
        Err(error) => {
            eprintln!("{}", error);
            std::process::exit(1);
        }
    };
    let output = match args[1].as_str() {
        "star" => entry.to_star().unwrap(),
        "json" => entry.to_json(),
        "validate" => entry.validate_full(None, Some("internal"), None, false).unwrap()
            .iter().map(|issue| format!("{}\n", issue)).collect(),
        "normalize" => {
            entry.normalize(None).unwrap();
            entry.to_star().unwrap()
        }
        other => panic!("unknown mode {}", other),
    };
    print!("{}", output);
}
