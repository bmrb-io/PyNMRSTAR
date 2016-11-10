from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                    sources = ['cnmrstar/cnmrstarmodule.c'],
                    extra_compile_args=["-funroll-loops", "-O3"])

setup(name='pynmrstar',
      version = '2.1',
      download_url = 'https://github.com/uwbmrb/PyNMRSTAR/tarball/v2.1',
      packages = ['pynmrstar'],
      author = 'Jon Wedell',
      author_email = 'wedell@bmrb.wisc.edu',
      description = 'PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files.',
      long_description=open('README.md').read(),
      keywords = ['bmrb','parser','nmr', 'nmrstar', 'biomagresbank', 'biological magnetic resonance bank'],
      url = 'https://github.com/uwbmrb/PyNMRSTAR',
      license = 'GPL',
    )

setup (name = 'cnmrstar',
       packages = ['cnmrstar'],
       version = '1.0',
       description = 'This contains a really fast NMR-STAR tokenizer and value sanitizer. While you can use this module yourself, it is intended for use by the PyNMR-STAR module.',
       ext_modules = [cnmrstar],
       author="Jon Wedell",
       author_email="wedell@bmrb.wisc.edu",
       url='https://github.com/uwbmrb/PyNMRSTAR/tree/master/c')
