#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Setup script for Jupyter Notebook"""

#-----------------------------------------------------------------------------
#  Copyright (c) 2015-, Jupyter Development Team.
#  Copyright (c) 2008-2015, IPython Development Team.
#
#  Distributed under the terms of the Modified BSD License.
#
#  The full license is in the file COPYING.md, distributed with this software.
#-----------------------------------------------------------------------------

from __future__ import print_function

import os
import sys

if sys.version_info < (3, 4):
    pip_message = 'This may be due to an out of date pip. Make sure you have pip >= 9.0.1.'
    try:
        import pip
        pip_version = tuple([int(x) for x in pip.__version__.split('.')[:3]])
        if pip_version < (9, 0, 1) :
            pip_message = 'Your pip version is out of date, please install pip >= 9.0.1. '\
            'pip {} detected.'.format(pip.__version__)
        else:
            # pip is new enough - it must be something else
            pip_message = ''
    except Exception:
        pass


    error = """
Jupyter Notebook 6.0+ requires Python 3.4 or above.
You can still install Notebook version 5.x on Python 2.7, but moving to the
new version is recommended. You can run Python 2 notebooks by installing a
kernel for Python 2.

Python {py} detected.
{pip}
""".format(py=sys.version_info, pip=pip_message )

    print(error, file=sys.stderr)
    sys.exit(1)

# At least we're on the python version we need, move on.

# BEFORE importing distutils, remove MANIFEST. distutils doesn't properly
# update it when the contents of directories change.
if os.path.exists('MANIFEST'): os.remove('MANIFEST')

from setuptools import setup

from setupbase import (
    version,
    find_packages,
    find_package_data,
    check_package_data_first,
    CompileCSS,
    CompileJS,
    Bower,
    JavascriptVersion,
    css_js_prerelease,
)

setup_args = dict(
    name            = "notebook",
    description     = "A web-based notebook environment for interactive computing",
    long_description = """
The Jupyter Notebook is a web application that allows you to create and
share documents that contain live code, equations, visualizations, and
explanatory text. The Notebook has support for multiple programming
languages, sharing, and interactive widgets.

Read `the documentation <https://jupyter-notebook.readthedocs.io>`_
for more information.
    """,
    version         = version,
    packages        = find_packages(),
    package_data    = find_package_data(),
    author          = 'Jupyter Development Team',
    author_email    = 'jupyter@googlegroups.com',
    url             = 'http://jupyter.org',
    license         = 'BSD',
    platforms       = "Linux, Mac OS X, Windows",
    keywords        = ['Interactive', 'Interpreter', 'Shell', 'Web'],
    classifiers     = [
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    zip_safe = False,
    python_requires = ">=3.4",
    install_requires = [
        'jinja2',
        'tornado>=4',
        'ipython_genutils',
        'traitlets>=4.2.1',
        'jupyter_core>=4.4.0',
        'jupyter_client>=5.2.0',
        'nbformat',
        'nbconvert',
        'ipykernel', # bless IPython kernel for now
        'Send2Trash',
        'terminado>=0.8.1'
    ],
    extras_require = {
        'test': ['nose', 'coverage', 'requests', 'nose_warnings_filters', 'nbval'],
        'test:sys_platform == "win32"': ['nose-exclude'],
    },
    entry_points = {
        'console_scripts': [
            'jupyter-notebook = notebook.notebookapp:main',
            'jupyter-nbextension = notebook.nbextensions:main',
            'jupyter-serverextension = notebook.serverextensions:main',
            'jupyter-bundlerextension = notebook.bundler.bundlerextensions:main',
        ]
    },
)

# Custom distutils/setuptools commands ----------
from distutils.command.build_py import build_py
from distutils.command.sdist import sdist
from setuptools.command.bdist_egg import bdist_egg
from setuptools.command.develop import develop

class bdist_egg_disabled(bdist_egg):
    """Disabled version of bdist_egg

    Prevents setup.py install from performing setuptools' default easy_install,
    which it should never ever do.
    """
    def run(self):
        sys.exit("Aborting implicit building of eggs. Use `pip install .` to install from source.")

setup_args['cmdclass'] = {
    'build_py': css_js_prerelease(
            check_package_data_first(build_py)),
    'sdist' : css_js_prerelease(sdist, strict=True),
    'develop': css_js_prerelease(develop),
    'css' : CompileCSS,
    'js' : CompileJS,
    'jsdeps' : Bower,
    'jsversion' : JavascriptVersion,
    'bdist_egg': bdist_egg if 'bdist_egg' in sys.argv else bdist_egg_disabled,
}

try:
    from wheel.bdist_wheel import bdist_wheel
except ImportError:
    pass
else:
    setup_args['cmdclass']['bdist_wheel'] = css_js_prerelease(bdist_wheel)

# Run setup --------------------
def main():
    setup(**setup_args)

if __name__ == '__main__':
    main()
