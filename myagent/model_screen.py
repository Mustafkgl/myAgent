"""
ModelScreen — Textual full-screen model selection for Planner and Worker.
Allows selecting ANY model (Claude or Gemini) for either role.
"""

from __future__ import annotations

import asyncio
import os

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, RadioButton, RadioSet, Static

from myagent.config.auth import get_claude_model, get_gemini_model, save_config
from myagent.models import fetch_all_models, ModelInfo


def _radio_select(radio_set: RadioSet, index: int) -> None:
    buttons = list(radio_set.query(RadioButton))
    if 0 <= index < len(buttons):
        buttons[index].value = True


class ModelScreen(Screen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
        ("ctrl+s", "save", "Save"),
    ]

    CSS = """
    ModelScreen { background: $surface; }
    #model-scroll { padding: 1 4; }
    .model-title { text-style: bold; color: $primary; margin-top: 1; }
    .nav-hint { margin-bottom: 1; color: $text-muted; }
    RadioSet { margin: 0 0 1 2; width: auto; max-width: 80; }
    .loading { margin: 0 1 1 2; color: $text-muted; }
    .save-btn { margin-top: 2; margin-bottom: 1; width: 30; align-horizontal: center; }
    .divider { margin: 1 0; border-bottom: solid $primary; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="model-scroll"):
            yield Static("Universal Model Selection", classes="model-title")
            yield Static("  You can now cross-mix models. Choose the 'Brain' and the 'Hands'.\n", classes="nav-hint")

            # ── Planner (Brain) ──
            yield Static("STRATEGIC PLANNER  —  The Brain", classes="model-title")
            yield Static("  Loading latest models from APIs...", id="planner-loading", classes="loading")
            yield RadioSet(id="planner-radio")

            yield Static(" " * 60, classes="divider")

            # ── Worker (Hands) ──
            yield Static("EXECUTION WORKER  —  The Hands", classes="model-title")
            yield Static("  Loading latest models from APIs...", id="worker-loading", classes="loading")
            yield RadioSet(id="worker-radio")

            yield Button("Save and Apply Configuration", id="save-btn", classes="save-btn", variant="success")

        yield Footer()

    def on_mount(self) -> None:
        self._current_planner = get_claude_model()
        self._current_worker = get_gemini_model()
        self._all_models: list[ModelInfo] = []
        self._load_live_models()

    @work(thread=True)
    def _load_live_models(self) -> None:
        """Fetch all models from APIs in a background thread."""
        try:
            models = fetch_all_models()
            self.app.call_from_thread(self._populate_ui, models)
        except Exception:
            pass

    def _populate_ui(self, models: list[ModelInfo]) -> None:
        self._all_models = models
        
        # UI Elements
        p_load = self.query_one("#planner-loading", Static)
        w_load = self.query_one("#worker-loading", Static)
        p_radio = self.query_one("#planner-radio", RadioSet)
        w_radio = self.query_one("#worker-radio", RadioSet)

        p_load.display = False
        w_load.display = False

        # Mount radio buttons for both sets
        for m in models:
            provider_icon = "🟣" if m.provider == "claude" else "🔵"
            label = f"{provider_icon} {m.id}"
            
            # Add to Planner
            p_radio.mount(RadioButton(label, id=f"p-{m.id}"))
            # Add to Worker
            w_radio.mount(RadioButton(label, id=f"w-{m.id}"))

        # Set initial selections
        self.call_after_refresh(self._set_initial_selections)

    def _set_initial_selections(self) -> None:
        ids = [m.id for m in self._all_models]
        
        # Planner
        p_idx = ids.index(self._current_planner) if self._current_planner in ids else 0
        _radio_select(self.query_one("#planner-radio", RadioSet), p_idx)

        # Worker
        w_idx = ids.index(self._current_worker) if self._current_worker in ids else 0
        _radio_select(self.query_one("#worker-radio", RadioSet), w_idx)
        
        self.query_one("#planner-radio", RadioSet).focus()

    @on(Button.Pressed, "#save-btn")
    def action_save(self) -> None:
        p_idx = self.query_one("#planner-radio", RadioSet).pressed_index or 0
        w_idx = self.query_one("#worker-radio", RadioSet).pressed_index or 0

        planner_id = self._all_models[p_idx].id
        worker_id = self._all_models[w_idx].id

        # Update Config
        save_config({
            "claude_model": planner_id,
            "gemini_model": worker_id
        })

        # Update Runtime Environment
        os.environ["CLAUDE_MODEL"] = planner_id
        os.environ["GEMINI_MODEL"] = worker_id

        self.app.notify(f"✓ Configured: Planner={planner_id} | Worker={worker_id}", severity="information")
        self.app.pop_screen()
