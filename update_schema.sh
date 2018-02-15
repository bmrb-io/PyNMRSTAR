#!/bin/sh

curl http://svn.bmrb.wisc.edu/svn/nmr-star-dictionary/bmrb_only_files/adit_input/xlschem_ann.csv > reference_files/schema.csv
mac2unix reference_files/schema.csv