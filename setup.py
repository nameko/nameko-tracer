#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name='nameko-entrypoint-logger',
    version='0.0.1',
    description='Nameko extension sends entrypoint monitoring events to AMPQ',
    packages=find_packages(exclude=['test', 'test.*']),
    author='student.com',
    author_email='wearehiring@student.com',
    url='https://github.com/Overseas-Student-Living/nameko-entrypoint-logger',
    py_modules=['nameko_entrypoint_logger'],
    install_requires=[
        "nameko>=2.2.0",
    ],
    extras_require={
        'dev': [
            "coverage==4.0a1",
            "pytest==2.8.2",
            "isort==4.0.0"
        ]
    },
    dependency_links=[],
    zip_safe=True,
    license='Apache License, Version 2.0'
)
