from setuptools import setup, find_packages

setup(
    name="codeiq",
    version="1.0.0",
    description="OpenCode-like AI coding assistant running entirely in the terminal using a rich TUI",
    author="CodeIq Team",
    packages=find_packages(),
    install_requires=[
        "textual>=0.80.0",
        "rich>=13.7.0",
        "google-genai>=1.0.0",
        "openai>=1.20.0",
        "anthropic>=0.40.0",
        "pydantic>=2.0.0",
    ],
    entry_points={
        "console_scripts": [
            "codeiq=codeiq.cli:main",
        ],
    },
    python_requires=">=3.9",
)
