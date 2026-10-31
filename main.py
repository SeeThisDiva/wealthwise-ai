"""WealthWise entry point: starts the local web server and opens the browser."""

import sys
import threading
import time
import webbrowser

from rich.console import Console
from rich.panel import Panel

# Windows consoles need UTF-8 for the rupee symbol.
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from web.server import app, get_bind_address

console = Console()


def print_banner(host: str, port: int):
    content = (
        "[bold]Engine:[/bold] [green]Forward and backward chaining with MYCIN certainty factors[/green]\n"
        "[bold]Scoring:[/bold] [yellow]0-100 Financial Health Index with protective ceilings[/yellow]\n"
        f"[bold]URL:[/bold] [bold underline green]http://{host}:{port}[/bold underline green]\n"
        "[dim]Opening your browser. Press Ctrl+C to stop.[/dim]"
    )
    console.print(Panel(content, title="[bold cyan]WEALTHWISE[/bold cyan]", border_style="cyan", padding=(1, 2)))


def main():
    host, port = get_bind_address()   # refuses non-loopback unless explicitly allowed
    print_banner(host, port)
    browser_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host

    def open_browser():
        time.sleep(1.0)
        try:
            webbrowser.open(f"http://{browser_host}:{port}")
        except Exception:
            pass

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        console.print("\n[bold red]Shutting down WealthWise...[/bold red]")
        sys.exit(0)


if __name__ == "__main__":
    main()
