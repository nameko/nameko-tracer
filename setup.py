#!/usr/bin/env python
from setuptools import find_packages, setup

setup(
    name='nameko-tracer',
    version='1.0.6',
    description='Nameko extension logging entrypoint processing metrics',
    author='student.com',
    author_email='wearehiring@student.com',
    url='https://github.com/Overseas-Student-Living/nameko-tracer',
    packages=find_packages(exclude=['test', 'test.*']),
    install_requires=[
        "nameko>=2.2.0",
    ],
    extras_require={
        'dev': [
            "coverage==4.4.1",
            "flake8==3.4.1",
            "pylint==1.7.2",
            "pytest==3.2.0",
        ]
    },
    dependency_links=[],
    zip_safe=True,
    license='Apache License, Version 2.0'
)
