#!/usr/bin/env python3

import os
from setuptools import setup, Extension


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

setup(name='pynmrstar',
      version=get_version(),
      packages=['pynmrstar'],
      ext_modules=[cnmrstar],
      install_requires=['requests>=2.21.0,<=3'],
      python_requires='>=3.6',
      author='Jon Wedell',
      author_email='wedell@uchc.edu',
      description='PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files. '
                  'Maintained by the BMRB.',
      long_description=long_des,
      long_description_content_type='text/x-rst',
      keywords=['bmrb', 'parser', 'nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
      url='https://github.com/uwbmrb/PyNMRSTAR',
      license='MIT',
      package_data={'pynmrstar': ['reference_files/schema.csv',
                                  'reference_files/comments.str',
                                  'reference_files/data_types.csv']},
      classifiers=[
          'Development Status :: 6 - Mature',
          'Environment :: Console',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
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
      )
