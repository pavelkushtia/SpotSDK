#!/usr/bin/env python3
"""
Spot SDK - Universal Spot Instance Management for Application Developers
"""

from setuptools import setup, find_packages
import os

# Read version from version file
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'spot_sdk', 'version.py')
    with open(version_file, 'r') as f:
        exec(f.read())
    return locals()['__version__']

# Read README for long description
def get_long_description():
    with open('README.md', 'r', encoding='utf-8') as f:
        return f.read()

# Core dependencies
install_requires = [
    'pydantic>=1.8.0',
    'pyyaml>=5.4.0',
    'requests>=2.25.0',
    'boto3>=1.17.0',
    'dataclasses-json>=0.5.0',
    'click>=8.0.0',
    'prometheus-client>=0.12.0',
    'structlog>=21.1.0',
    'tenacity>=8.0.0',
    'psutil>=5.8.0',
]

# Optional dependencies for different integrations
extras_require = {
    'ray': [
        'ray[default]>=2.0.0',
    ],
    'kubernetes': [
        'kubernetes>=18.20.0',
        'kopf>=1.35.0',
    ],
    'slurm': [
        'pyslurm>=20.11.0',
    ],
    'aws': [
        'boto3>=1.17.0',
        'botocore>=1.20.0',
    ],
    'gcp': [
        'google-cloud-storage>=1.42.0',
        'google-cloud-compute>=1.5.0',
    ],
    'azure': [
        'azure-storage-blob>=12.8.0',
        'azure-mgmt-compute>=22.0.0',
        'azure-identity>=1.6.0',
    ],
    'monitoring': [
        'prometheus-client>=0.12.0',
        'grafana-api>=1.0.3',
    ],
    'dev': [
        'pytest>=6.2.0',
        'pytest-cov>=2.12.0',
        'pytest-asyncio>=0.15.0',
        'black>=21.6.0',
        'isort>=5.9.0',
        'flake8>=3.9.0',
        'mypy>=0.910',
        'pre-commit>=2.13.0',
        'sphinx>=4.0.0',
        'sphinx-rtd-theme>=0.5.0',
        'mock>=4.0.0',
        'responses>=0.13.0',
    ],
    'docs': [
        'sphinx>=4.0.0',
        'sphinx-rtd-theme>=0.5.0',
        'myst-parser>=0.15.0',
    ],
    'all': [
        'ray[default]>=2.0.0',
        'kubernetes>=18.20.0',
        'kopf>=1.35.0',
        'google-cloud-storage>=1.42.0',
        'google-cloud-compute>=1.5.0',
        'azure-storage-blob>=12.8.0',
        'azure-mgmt-compute>=22.0.0',
        'azure-identity>=1.6.0',
        'prometheus-client>=0.12.0',
        'grafana-api>=1.0.3',
    ]
}

setup(
    name='spot-sdk',
    version=get_version(),
    author='Spot SDK Team',
    author_email='team@spot-sdk.org',
    description='Universal Spot Instance Management for Application Developers',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    url='https://github.com/your-org/spot-sdk',
    project_urls={
        'Documentation': 'https://spot-sdk.readthedocs.io/',
        'Source': 'https://github.com/your-org/spot-sdk',
        'Tracker': 'https://github.com/your-org/spot-sdk/issues',
    },
    packages=find_packages(exclude=['tests*', 'examples*']),
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Distributed Computing',
        'Topic :: System :: Systems Administration',
    ],
    python_requires='>=3.8',
    install_requires=install_requires,
    extras_require=extras_require,
    entry_points={
        'console_scripts': [
            'spot-sdk=spot_sdk.cli:main',
            'spot-monitor=spot_sdk.monitoring.cli:main',
        ],
    },
    include_package_data=True,
    package_data={
        'spot_sdk': ['config/*.yaml', 'templates/*.yaml'],
    },
    zip_safe=False,
    keywords='spot instances, cloud computing, kubernetes, ray, cost optimization',
)