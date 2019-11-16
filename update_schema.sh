#!/bin/sh

curl https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/development/xlschem_ann.csv > pynmrstar/reference_files/schema.csv
mac2unix pynmrstar/reference_files/schema.csv