"""CLI entry point and application wiring."""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from sage.cli.commands import register_commands


class CLIApplication:
    """Central orchestrator for the Sage Typer application."""

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()
        self._app = typer.Typer(add_completion=False, rich_markup_mode="rich")
        register_commands(self._app, self.console)

    @property
    def app(self) -> typer.Typer:
        """Return the underlying Typer application instance."""

        return self._app

    def run(self, *, prog_name: Optional[str] = None, args: Optional[list[str]] = None) -> None:
        """Invoke the Typer application with optional overrides."""

        self._app(prog_name=prog_name, args=args)


def create_app(console: Optional[Console] = None) -> typer.Typer:
    """Factory helper that returns the configured Typer application."""

    return CLIApplication(console=console).app


def main() -> None:
    """Console script entry point for `python -m sage` or installed CLI."""

    CLIApplication().run()


__all__ = ["CLIApplication", "create_app", "main"]

