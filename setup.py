try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

from pynmrstar import __version__

cnmrstar = Extension('cnmrstar',
                     sources=['c/cnmrstarmodule.c'],
                     extra_compile_args=["-funroll-loops", "-O3"],
                     optional=True)

try:
    long_description = open('README.md', 'r').read()
except IOError:
    long_description = open('pynmrstar/README.md', 'r').read()

setup(name='pynmrstar',
      version=__version__,
      packages=['pynmrstar'],
      ext_modules=[cnmrstar],
      author='Jon Wedell',
      author_email='wedell@bmrb.wisc.edu',
      description='PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files. '
                  'Maintained by the BMRB.',
      long_description=long_description,
      long_description_content_type='text/markdown',
      keywords=['bmrb', 'parser', 'nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
      url='https://github.com/uwbmrb/PyNMRSTAR',
      license='MIT',
      package_data={
          'pynmrstar': ['reference_files/schema.csv', 'reference_files/comments.str', 'reference_files/data_types.csv',
                        '.nocompile', 'README.md']},
      classifiers=[
          'Development Status :: 5 - Production/Stable',
          'Environment :: Console',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.6',
          'Programming Language :: Python :: 2.7',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3.3',
          'Programming Language :: Python :: 3.4',
          'Programming Language :: Python :: 3.5',
          'Programming Language :: Python :: 3.6',
          'Intended Audience :: Developers',
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Natural Language :: English',
          'Operating System :: MacOS',
          'Operating System :: POSIX :: Linux',
          'Topic :: Scientific/Engineering :: Bio-Informatics',
          'Topic :: Software Development :: Libraries',
          'Topic :: Software Development :: Libraries :: Python Modules'
      ]
      )
