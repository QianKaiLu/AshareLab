# setup.py
from setuptools import setup

setup(
    name="ashare-cli",
    version="0.1.0",
    py_modules=["tools.cli"],
    install_requires=["click"],  # 可后续升级用 click
    entry_points={
        "console_scripts": [
            "stock-info=tools.cli:main",
        ]
    },
    author="qiankai",
    description="A-share stock info CLI tool",
)
