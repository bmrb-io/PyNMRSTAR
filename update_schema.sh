#!/bin/sh
#
# Refresh the packaged dictionary files from the NMR-STAR dictionary
# distribution (the built files, not the source spreadsheet).
#
# The packaged distribution is what pynmrstar uses by default -- it only goes to
# the network when asked for Schema(version='latest') or for a version it has
# neither packaged nor cached (see _internal.load_dictionary). Run this before
# each release so that the default is the newest dictionary. Only dictionary
# versions 3.2.14.0 and above are supported.

base="https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/nmr-star-development/NMR-STAR/internal_106_distribution"
ref="pynmrstar/reference_files"

for f in xlschem_ann.csv adit_enum_hdr.csv adit_enum_dtl.csv adit_cat_grp_o.csv adit_tag_validation.csv; do
    curl "$base/$f" > "$ref/$f"
    mac2unix "$ref/$f"
done
