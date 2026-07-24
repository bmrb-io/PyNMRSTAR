#!/bin/sh
#
# Refresh the packaged dictionary reference files from the NMR-STAR dictionary
# distribution. schema.csv is the annotated tag table; enumerations.csv is the
# joined enumeration value lists (built by _build_enumerations.py), which
# schema.csv itself does not carry.

base="https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/nmr-star-development/NMR-STAR/internal_106_distribution"
ref="pynmrstar/reference_files"

curl "$base/xlschem_ann.csv" > "$ref/schema.csv"
mac2unix "$ref/schema.csv"

# enumerations.csv is joined from three distribution files; fetch them to a temp
# dir and build it.
tmp="$(mktemp -d)"
for f in xlschem_ann.csv adit_enum_hdr.csv adit_enum_dtl.csv; do
    curl "$base/$f" > "$tmp/$f"
    mac2unix "$tmp/$f"
done
python3 "$ref/_build_enumerations.py" "$tmp" > "$ref/enumerations.csv"
rm -rf "$tmp"
