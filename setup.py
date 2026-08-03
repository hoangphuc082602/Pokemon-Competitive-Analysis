from setuptools import setup, find_packages

setup(
    name="POKEMON-ANALYTICS",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "pandas",
        "sqlalchemy",
        "streamlit",
        "pytest"
    ],
    description="A tool for analyzing Pokemon teams and battles",
    author="Hoang Phuc",
    author_email="hoangphuc0826@gmail.com"
)