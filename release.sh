#!/bin/bash

while true; do
    read -p "Have you updated the version number in pynmrstar/_internal.py? " yn
    case ${yn} in
        [Yy]* ) break;;
        [Nn]* ) exit;;
        * ) echo "Please answer yes or no.";;
    esac
done

while true; do
    read -p "Do [b]uild, [t]est, or [r]elease? " rt
    case ${rt} in
        [Tt]* ) python3 -m twine upload --repository testpypi dist/*.tar.gz --sign; break;;
        [Rr]* ) python3 -m twine upload dist/*.tar.gz --sign; break;;
        [Bb]* ) rm dist/*; touch pynmrstar/.nocompile; python3 setup.py sdist; rm -rfv pynmrstar.egg-info; break;;
        * ) echo "Please answer r or t.";;
    esac
done

