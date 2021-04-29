from distutils.core import setup, Extension

cnmrstar = Extension('cnmrstar',
                     sources = ['cnmrstarmodule.c'],
                     extra_compile_args=["-funroll-loops", "-O3"])

setup(name='cNMR-STAR Tools',
      version='3.2.0',
      description='This contains a really fast NMR-STAR tokenizer and value sanitizer.',
      ext_modules=[cnmrstar])
