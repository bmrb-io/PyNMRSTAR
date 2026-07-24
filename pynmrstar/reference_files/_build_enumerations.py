#!/usr/bin/env python3
"""Build reference_files/enumerations.csv for the Schema.

The BMRB dictionary distribution stores enumerations across three files:

  * ``xlschem_ann.csv``   -- one row per tag; the "Item enumerated" /
                             "Item enumeration closed" flags live here.
  * ``adit_enum_hdr.csv`` -- maps an "Enumeration ID" to its tag.
  * ``adit_enum_dtl.csv`` -- the allowed values for each "Enumeration ID".

``schema.csv`` (the annotated tag table) already ships in reference_files but
carries only the flags, not the values -- so ``Schema`` cannot check enumeration
membership. This script joins the three files into a single self-contained
``enumerations.csv`` (``Tag,Enumeration_closed,Value``, one row per value) that
``Schema`` loads directly. It is deliberately self-contained -- carrying its own
closed flag -- so it stays correct even if ``schema.csv`` is a slightly different
dictionary release.

Run via update_schema.sh, or:

    python3 _build_enumerations.py <distribution_dir> > enumerations.csv
"""
import csv
import sys


def build(dist_dir: str, out) -> None:
    # tag -> 'Y'/'N' closed flag, for enumerated tags only
    closed = {}
    with open(f"{dist_dir}/xlschem_ann.csv", newline="") as fh:
        started = False
        for row in csv.DictReader(fh):
            if row.get("Dictionary sequence") == "TBL_BEGIN":
                started = True
                continue
            if not started or row.get("Dictionary sequence") == "TBL_END":
                continue
            if row.get("Item enumerated") == "Y":
                closed[row["Tag"]] = "Y" if row.get("Item enumeration closed") == "Y" else "N"

    # Enumeration ID -> tag
    id_to_tag = {}
    with open(f"{dist_dir}/adit_enum_hdr.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            eid = row.get("Enumeration ID")
            if eid in (None, "TBL_BEGIN", "TBL_END", "?"):
                continue
            id_to_tag[eid] = row.get("Tag")

    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Tag", "Enumeration_closed", "Value"])
    seen = set()
    with open(f"{dist_dir}/adit_enum_dtl.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            eid = row.get("Enumeration ID")
            if eid in (None, "TBL_BEGIN", "TBL_END", "?"):
                continue
            tag = id_to_tag.get(eid)
            if tag is None:
                continue
            value = (row.get("Enum value") or "").strip()
            if value == "":
                continue
            key = (tag, value)
            if key in seen:
                continue
            seen.add(key)
            writer.writerow([tag, closed.get(tag, "N"), value])


if __name__ == "__main__":
    dist = sys.argv[1] if len(sys.argv) > 1 else "."
    build(dist, sys.stdout)
