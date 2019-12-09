#!/bin/sh

while true; do
    read -p "Have you updated the version number in bmrb.py? " yn
    case $yn in
        [Yy]* ) break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done

while true; do
    read -p "Do release or test? " rt
    case $rt in
        [Rr]* ) python3 -m twine upload dist/*.tar.gz --sign; rm -rfv pynmrstar pynmrstar.egg-info; break;;
        [Tt]* ) mkdir pynmrstar; cp bmrb.py pynmrstar/__init__.py; cp -rv reference_files pynmrstar; touch pynmrstar/.nocompile; cp README.md pynmrstar; python3 setup.py sdist; rm -rfv pynmrstar pynmrstar.egg-info; break;;
        * ) echo "Please answer r or t.";;
    esac
done

