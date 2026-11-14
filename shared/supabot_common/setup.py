from setuptools import setup, find_packages

setup(
    name="supabot-common",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "cryptography>=41.0.0",
    ],
)
