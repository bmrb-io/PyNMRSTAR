#!/bin/sh

while true; do
    read -p "Have you updated the version number in bmrb.py? " yn
    case $yn in
        [Yy]* ) rm -rfv pynmrstar; mkdir pynmrstar; cp bmrb.py pynmrstar/__init__.py; cp -rv reference_files pynmrstar; pandoc -o README.rst README.md; python3 setup.py sdist upload --sign; break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done