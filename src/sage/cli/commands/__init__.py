"""Command registration utilities for the Sage CLI."""

from __future__ import annotations

import typer
from rich.console import Console

from sage.cli.commands import ingest_youtube


def register_commands(app: typer.Typer, console: Console) -> None:
    """Attach command groups to the provided Typer application."""

    ingest_youtube.register(app, console)

    @app.callback(invoke_without_command=True)
    def main_callback() -> None:
        """Display a default message when no subcommand is provided."""

        console.print("[bold green]Sage CLI ready for commands.[/bold green]")


__all__ = ["register_commands"]

