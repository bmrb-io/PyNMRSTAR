from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                    sources = ['pynmrstar/cnmrstarmodule.c'],
                    extra_compile_args=["-funroll-loops", "-O3"])

setup(name='pynmrstar',
      version = '2.2',
      packages = ['pynmrstar'],
      ext_modules = [cnmrstar],
      author = 'Jon Wedell',
      author_email = 'wedell@bmrb.wisc.edu',
      description = 'PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files.',
      long_description=open('README').read(),
      keywords = ['bmrb','parser','nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
      url = 'https://github.com/uwbmrb/PyNMRSTAR',
      license = 'GPL',
    )
