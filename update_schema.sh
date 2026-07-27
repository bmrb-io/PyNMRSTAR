#!/bin/sh
#
# Refresh the packaged *offline-fallback* dictionary files from the NMR-STAR
# dictionary distribution (the built files, not the source spreadsheet).
#
# These are only the fallback used when there is no network and no cache. At
# runtime pynmrstar fetches the current distribution from definitions.DICTIONARY_URL
# and caches it under ~/.cache/pynmrstar/<version> (see _internal.load_dictionary),
# so this script only needs to be run occasionally to keep the shipped fallback
# reasonably current. Only dictionary versions 3.2.14.0 and above are supported.

base="https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/nmr-star-development/NMR-STAR/internal_106_distribution"
ref="pynmrstar/reference_files"

for f in xlschem_ann.csv adit_enum_hdr.csv adit_enum_dtl.csv; do
    curl "$base/$f" > "$ref/$f"
    mac2unix "$ref/$f"
done
