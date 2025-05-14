from setuptools import setup
from Cython.Build import cythonize
setup(
name='__init__',
ext_modules=cythonize('__init__.py')
)
