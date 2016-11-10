from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                    sources = ['cnmrstar/cnmrstarmodule.c'],
                    extra_compile_args=["-funroll-loops", "-O3"])

setup (name = 'cnmrstar',
       packages = ['cnmrstar'],
       version = '1.0',
       description = 'This contains a really fast NMR-STAR tokenizer and value sanitizer. While you can use this module yourself, it is intended for use by the PyNMR-STAR module.',
       ext_modules = [cnmrstar],
       author="Jon Wedell",
       author_email="wedell@bmrb.wisc.edu",
       url='https://github.com/uwbmrb/PyNMRSTAR/tree/master/c')
