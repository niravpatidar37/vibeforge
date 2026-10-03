"""Rich terminal display for playlists."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .models import Playlist

console = Console()

ENERGY_COLOR = {"low": "cyan", "medium": "yellow", "high": "red"}


def print_playlist(playlist: Playlist) -> None:
    color = ENERGY_COLOR.get(playlist.energy_level, "magenta")

    # Header panel
    header = Text()
    header.append(f"  {playlist.name}\n", style=f"bold {color}")
    header.append(f"  {playlist.mood_summary}\n", style="italic white")
    tags = "  " + "  ".join(f"[{color}]#{t}[/]" for t in playlist.vibe_tags)
    console.print(Panel(header, title="[bold magenta]VibeForge[/]", border_style=color))
    console.print(tags)
    console.print()

    # Tracks table
    table = Table(box=box.ROUNDED, border_style=color, header_style=f"bold {color}")
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="bold white", min_width=24)
    table.add_column("Artist", style="cyan", min_width=18)
    table.add_column("Genre", style="yellow", min_width=14)
    table.add_column("BPM", style="dim", width=5)
    table.add_column("Links", style="blue")

    for i, track in enumerate(playlist.tracks, 1):
        links = ""
        if track.spotify_search_url:
            links += "[link=" + track.spotify_search_url + "]Spotify[/link]"
        if track.youtube_search_url:
            links += "  [link=" + track.youtube_search_url + "]YT[/link]"
        table.add_row(
            str(i),
            track.title,
            track.artist,
            track.genre,
            str(track.bpm) if track.bpm else "-",
            links,
        )

    console.print(table)
    console.print(f"\n  Genres: [yellow]{', '.join(playlist.genres)}[/]")
    console.print(f"  Energy: [{color}]{playlist.energy_level.upper()}[/]\n")


def collect_feedback(playlist: Playlist) -> tuple[list[dict], list[dict]]:
    """Ask user to rate tracks. Returns (loved, disliked) as lists of track dicts."""
    from rich.prompt import Prompt

    def _parse_numbers(raw: str, max_n: int) -> list[int]:
        result = []
        for part in raw.replace(",", " ").split():
            try:
                n = int(part)
                if 1 <= n <= max_n:
                    result.append(n - 1)  # convert to 0-indexed
            except ValueError:
                pass
        return result

    tracks = playlist.tracks
    n = len(tracks)

    console.print("[dim]─────────────────────────────────────────────[/]")
    loved_raw = Prompt.ask(
        "[bold green]♥ Loved any tracks?[/] Enter numbers (e.g. [dim]1 3 7[/]) or press Enter to skip",
        default="",
    )
    disliked_raw = Prompt.ask(
        "[bold red]✕ Never play again?[/] Enter numbers (e.g. [dim]2 5[/]) or press Enter to skip",
        default="",
    )
    console.print()

    loved_idxs = set(_parse_numbers(loved_raw, n))
    loved = [tracks[i].model_dump() for i in loved_idxs]
    disliked = [tracks[i].model_dump() for i in _parse_numbers(disliked_raw, n) if i not in loved_idxs]
    return loved, disliked
