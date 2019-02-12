#!/bin/sh

curl https://raw.githubusercontent.com/uwbmrb/nmr-star-dictionary/master/xlschem_ann.csv > reference_files/schema.csv
mac2unix reference_files/schema.csv