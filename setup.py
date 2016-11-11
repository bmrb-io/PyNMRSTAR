from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                    sources = ['c/cnmrstarmodule.c'],
                    extra_compile_args = ["-funroll-loops", "-O3"],
                    optional = True)

setup(name='pynmrstar',
      version = '2.2.1',
      packages = ['pynmrstar'],
      ext_modules = [cnmrstar],
      author = 'Jon Wedell',
      author_email = 'wedell@bmrb.wisc.edu',
      description = 'PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files. Maintained by the BMRB.',
      long_description=open('README').read(),
      keywords = ['bmrb','parser','nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
      url = 'https://github.com/uwbmrb/PyNMRSTAR',
      license = 'GPL',
      package_data = {'pynmrstar': ['reference_files/schema', 'reference_files/comments']}
    )
