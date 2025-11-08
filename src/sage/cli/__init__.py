"""Command-line interface package for Sage."""

from rich.console import Console

from sage.cli.main import CLIApplication, create_app

console = Console()

__all__ = ["CLIApplication", "console", "create_app"]

