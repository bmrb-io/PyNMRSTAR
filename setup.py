#!/usr/bin/env python3

try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

from pynmrstar import __version__

cnmrstar = Extension('cnmrstar',
                     sources=['c/cnmrstarmodule.c'],
                     extra_compile_args=["-funroll-loops", "-O3"],
                     optional=True)

# Should fail if the readme is missing
long_des = open('README.rst', 'r').read()

setup(name='pynmrstar',
      version=__version__,
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
      package_data={'pynmrstar': ['reference_files/schema.csv', 'reference_files/comments.str',
                                  'reference_files/data_types.csv', '.nocompile']},
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
