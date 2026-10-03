"""CLI entry point — interactive loop and one-shot mode."""

from __future__ import annotations

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

load_dotenv()

from .application import GenerationRequest, generation_service
from .display import print_playlist, collect_feedback
from .memory import save_feedback
from .utils import DEFAULT_MODEL

app = typer.Typer(help="VibeForge — AI-powered mood-based playlist generator")
console = Console()


@app.command()
def run(
    mood: str = typer.Option(None, "--mood", "-m", help="Mood/activity description (skips interactive prompt)"),
    context: str = typer.Option("", "--context", "-c", help="Extra context, e.g. 'rainy day, studying'"),
    deep: bool = typer.Option(False, "--deep", help="Two-stage mode: Mood Analyst → Music Curator"),
    agentic: bool = typer.Option(False, "--agentic", help="LangGraph mode: Mood Analyst → Curator → Critic → (refine) → Finalise"),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Groq model to use"),
    no_spotify: bool = typer.Option(False, "--no-spotify", help="Skip Spotify enrichment"),
    seed: str = typer.Option("", "--seed", "-s", help="Seed track as vibe anchor, e.g. 'Blinding Lights by The Weeknd'"),
    no_feedback: bool = typer.Option(False, "--no-feedback", help="Skip the post-playlist feedback prompt"),
):
    """Generate a mood-based playlist."""
    if mood:
        _generate_and_display(mood, context, deep, agentic, model, not no_spotify, seed, not no_feedback)
    else:
        _interactive_loop(context, deep, agentic, model, not no_spotify, seed, not no_feedback)


def _generate_and_display(
    mood: str, context: str, deep: bool, agentic: bool, model: str, spotify: bool, seed: str, ask_feedback: bool
) -> None:
    console.print(f"\n[bold magenta]Generating playlist for:[/] [cyan]{mood}[/]\n")
    with console.status("[bold magenta]VibeForge is forging your playlist...[/]"):
        if agentic:
            current_state: dict = {}
            request = GenerationRequest(mood=mood, context=context, seed=seed, model=model, mode="agentic", spotify_enrich=spotify)
            for node_name, state in generation_service.stream(request):
                current_state = state
                if node_name == "analyse_mood":
                    ma = state.get("mood_analysis")
                    if ma:
                        console.log(f"[cyan]Mood Analyst[/] — {ma.primary_emotion}, {ma.energy_level} energy, BPM {ma.bpm_range}")
                elif node_name == "curate_playlist":
                    attempts = state.get("refinement_attempts", 0)
                    if attempts > 0:
                        console.log(f"[cyan]Music Curator[/] — refining (attempt {attempts + 1}/3)…")
                    else:
                        console.log("[cyan]Music Curator[/] — building your 10-track playlist…")
                elif node_name == "critique_playlist":
                    critique = state.get("critique")
                    if critique:
                        verdict = "✓ accepted" if critique.score >= 7 else "needs refinement"
                        console.log(f"[cyan]Critic[/] — {critique.score}/10 {verdict}")
                elif node_name == "finalise":
                    console.log("[cyan]Finalising[/] — enriching track links…")
            playlist = current_state.get("playlist")
            if playlist is None:
                raise RuntimeError("LangGraph pipeline failed to produce a playlist.")
        elif deep:
            playlist = generation_service.generate(
                GenerationRequest(mood=mood, context=context, seed=seed, model=model, mode="deep", spotify_enrich=spotify)
            )
        else:
            playlist = generation_service.generate(
                GenerationRequest(mood=mood, context=context, seed=seed, model=model, mode="fast", spotify_enrich=spotify)
            )
    print_playlist(playlist)
    if ask_feedback:
        loved, disliked = collect_feedback(playlist)
        if loved or disliked:
            save_feedback(loved, disliked)
            console.print(f"[dim]Saved feedback — {len(loved)} loved, {len(disliked)} disliked.[/]")


def _interactive_loop(context: str, deep: bool, agentic: bool, model: str, spotify: bool, seed: str, ask_feedback: bool) -> None:
    console.print(_panel_welcome())
    while True:
        mood = Prompt.ask("\n[bold cyan]How are you feeling? (or 'quit' to exit)[/]")
        if mood.lower() in {"quit", "exit", "q"}:
            console.print("[dim]Goodbye! Keep vibing.[/]")
            break
        if mood.strip():
            _generate_and_display(mood, context, deep, agentic, model, spotify, seed, ask_feedback)


def _panel_welcome() -> Panel:
    t = Text()
    t.append("  VibeForge\n", style="bold magenta")
    t.append("  AI-powered mood-based playlist generator\n", style="dim")
    t.append("  Describe your mood or activity and get a personalised playlist.\n", style="italic")
    return Panel(t, border_style="magenta")
