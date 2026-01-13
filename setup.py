#!/usr/bin/env python3

import os
from setuptools import setup, Extension

try:
    from setuptools_rust import Binding, RustExtension
    rust_available = True
except ImportError:
    rust_available = False


def get_version():
    internal_file_location = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'pynmrstar', '_internal.py')

    with open(internal_file_location, 'r') as internal_file:
        for line in internal_file:
            if line.startswith('__version__'):
                delim = '"' if '"' in line else "'"
                return line.split(delim)[1]
        else:
            raise RuntimeError("Unable to find version string.")


# Should fail if the readme is missing
long_des = open('README.rst', 'r').read()

cnmrstar = Extension('cnmrstar',
                     sources=['c/cnmrstarmodule.c'],
                     extra_compile_args=["-funroll-loops", "-O3"],
                     optional=True)

rust_extensions = []
if rust_available:
    rust_extensions = [
        RustExtension("pynmrstar_parser", binding=Binding.PyO3)
    ]

setup_kwargs = {
    'name': 'pynmrstar',
    'version': get_version(),
    'packages': ['pynmrstar'],
    'ext_modules': [cnmrstar],
    'install_requires': ['requests>=2.21.0,<=3'],
    'python_requires': '>=3.7',
    'author': 'Jon Wedell',
    'author_email': 'wedell@uchc.edu',
    'description': 'PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files. '
                   'Maintained by the BMRB.',
    'long_description': long_des,
    'long_description_content_type': 'text/x-rst',
    'keywords': ['bmrb', 'parser', 'nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
    'url': 'https://github.com/uwbmrb/PyNMRSTAR',
    'license': 'MIT',
    'package_data': {'pynmrstar': ['reference_files/schema.csv',
                                   'reference_files/comments.str',
                                   'reference_files/data_types.csv']},
    'classifiers': [
        'Development Status :: 6 - Mature',
        'Environment :: Console',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: MacOS',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Microsoft :: Windows',
        'Topic :: Scientific/Engineering :: Bio-Informatics',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
}

if rust_available:
    setup_kwargs['rust_extensions'] = rust_extensions

setup(**setup_kwargs)
