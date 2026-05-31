# setup.py
from setuptools import setup, find_packages

setup(
    name="ashare-cli",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["click"],  # 可后续升级用 click
    entry_points={
        "console_scripts": [
            "stock-info=tools.cli:main",
            "video-process=cli.video_process.main:main",
        ]
    },
    author="qiankai",
    description="A-share stock info CLI tool",
)
