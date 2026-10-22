"""Build the Cython extensions in place:  python setup.py build_ext --inplace

Every src/chronosmatch/*.pyx becomes a compiled module importable as chronosmatch.<name>.
"""

from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

PYX_FILES = sorted(Path("src/chronosmatch").glob("*.pyx"))

extensions = [
    Extension(f"chronosmatch.{pyx.stem}", [str(pyx)], extra_compile_args=["-O3"])
    for pyx in PYX_FILES
]

setup(
    name="chronosmatch",
    package_dir={"": "src"},
    ext_modules=cythonize(extensions, compiler_directives={"language_level": "3"}),
)
