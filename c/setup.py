from distutils.core import setup, Extension

module1 = Extension('cnmrstarparser',
                    sources = ['cnmrstarparsermodule.c'])

setup (name = 'cNMR-STAR Parser',
       version = '1.0',
       description = 'This is a really fast NMR-STAR parser.',
       ext_modules = [module1])
