#!/bin/sh

curl https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/nmr-star-development/NMR-STAR/internal_106_distribution/xlschem_ann.csv > pynmrstar/reference_files/schema.csv
mac2unix pynmrstar/reference_files/schema.csv