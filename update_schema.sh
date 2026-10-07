#!/bin/sh
#
# Refresh the packaged dictionary files from the NMR-STAR dictionary
# distribution (the built files, not the source spreadsheet).
#
#     ./update_schema.sh [version]
#
# With no argument, the newest release (the nmr-star-production branch);
# with a version, the release tagged nmr-star-v<version>.
#
# The packaged distribution is what pynmrstar uses by default -- it only goes to
# the network when asked for Schema(version='latest') or for a version it has
# neither packaged nor cached (see _internal.load_dictionary). Run this before
# each release so that the default is the newest dictionary. Only dictionary
# versions 3.2.14.0 and above are supported.

gitref=${1:+nmr-star-v$1}
base="https://raw.githubusercontent.com/bmrb-io/nmr-star-dictionary/${gitref:-nmr-star-production}/NMR-STAR/internal_106_distribution"
ref="pynmrstar/reference_files"

for f in xlschem_ann.csv adit_enum_hdr.csv adit_enum_dtl.csv adit_cat_grp_o.csv adit_tag_validation.csv; do
    curl "$base/$f" > "$ref/$f"
    mac2unix "$ref/$f"
done
