#!/usr/bin/env python
from setuptools import find_packages, setup

setup(
    name='nameko-tracer',
    version='1.3.0',
    description='Nameko extension logging entrypoint processing metrics',
    author='student.com',
    author_email='wearehiring@student.com',
    url='https://github.com/nameko/nameko-tracer',
    packages=find_packages(exclude=['test', 'test.*']),
    install_requires=[
        "nameko>=2.8.5",
    ],
    extras_require={
        'dev': [
            "coverage",
            "flake8",
            "pylint",
            "pytest",
        ]
    },
    dependency_links=[],
    zip_safe=True,
    license='Apache License, Version 2.0'
)
