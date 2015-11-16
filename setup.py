#!/usr/bin/env python
import os
from setuptools import setup, find_packages

ROOT_DIR = os.path.dirname(__file__)
SOURCE_DIR = os.path.join(ROOT_DIR)

test_requirements = [
    "nose==1.3.1",
    "mock==1.0.1",
    "rednose",
]
with open('./requirements.txt') as requirements_txt:
    requirements = [line for line in requirements_txt]

setup(name='Metallus',
      version='0.5',
      description='Build runner using docker',
      author='Ryan McGrath',
      author_email='ryan@madebymany.co.uk',
      url='http://www.madebymany.co.uk',
      packages=find_packages('.', exclude=['tests*']),
      package_dir={'metallus': 'metallus'},
      include_package_data=True,
      install_requires=requirements,
      tests_require=test_requirements,
      entry_points={
          'console_scripts': [
              'metallus = metallus.command:run'
          ]
      },
      )
