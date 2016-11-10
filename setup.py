from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                    sources = ['c/cnmrstarmodule.c'],
                    extra_compile_args=["-funroll-loops", "-O3"])

setup(name='pynmrstar',
      version = '2.1',
      download_url = 'git@github.com:uwbmrb/PyNMRSTAR.git',
      py_modules = ('bmrb',),
      author = 'Jon Wedell',
      author_email = 'wedell@bmrb.wisc.edu',
      description = 'PyNMR-STAR provides tools for reading, writing, modifying, and interacting with NMR-STAR files.',
      long_description=open('README.md').read(),
      keywords = 'email validation verification mx verify',
      url = 'http://github.com/syrusakbary/validate_email',
      license = 'GPL',
    )

setup (name = 'cNMR-STAR Tools',
       version = '1.0',
       description = 'This contains a really fast NMR-STAR tokenizer and value sanitizer. While you can use this module yourself, it is intended for use by the PyNMR-STAR module.',
       ext_modules = [cnmrstar])
