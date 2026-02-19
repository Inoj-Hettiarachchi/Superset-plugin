"""
Setup configuration for superset-data-entry-plugin
"""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='superset-data-entry-plugin',
    version='1.0.0',
    author='99x Technology',
    description='Dynamic data entry forms plugin for Apache Superset',
    long_description=long_description,
    long_description_content_type="text/markdown",
    url='https://github.com/99x/superset-data-entry-plugin',
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'superset_data_entry': [
            'templates/**/*.html',
            'static/**/*.js',
            'static/**/*.css',
            'migrations/*.sql',
        ],
    },
    entry_points={
        'console_scripts': [
            'superset-data-entry-setup=superset_data_entry.setup_cli:main',
        ],
    },
    install_requires=[
        'Flask>=3.0.0',
        'Flask-AppBuilder>=4.0.0',
        'SQLAlchemy>=1.4.0',
        'psycopg2-binary>=2.9.0',
    ],
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    keywords='superset plugin data-entry forms flask-appbuilder',
    project_urls={
        'Bug Reports': 'https://github.com/99x/superset-data-entry-plugin/issues',
        'Source': 'https://github.com/99x/superset-data-entry-plugin',
    },
)
