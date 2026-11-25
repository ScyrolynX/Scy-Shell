"""Phase 7 — Exclusive Session Lock (`ext-session-lock-v1`), SDDM & `greetd` Pre-Auth Coordinator."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_store import ScyConfigStore
from .theme_engine import generate_m3_expressive_tokens
from .toml_io import atomic_write_text, dumps_toml

LUCID_6_LOCK_PRESETS: tuple[str, ...] = ("centre", "split", "panel", "minimal", "bento", "deck")
MANDARA_6_AUTH_DESIGNS: tuple[str, ...] = (
    "Mandara",
    "MidnightCard",
    "MaterialYou",
    "Ghostline",
    "ChromeHalo",
    "Meridian",
)


class ScyPreAuthCoordinator:
    def __init__(self, store: ScyConfigStore) -> None:
        self.store = store

    def set_lock_design(self, provider: str, design_or_preset: str) -> dict[str, Any]:
        if provider == "lucid":
            if design_or_preset not in LUCID_6_LOCK_PRESETS:
                raise ValueError(f"Unknown Lucid lock preset: {design_or_preset}")
            self.store.set_provider("lock_screen", "lucid")
            self.store.set_setting("scy.providers.lucid.prefs.lockPreset", design_or_preset)
            return {"provider": "lucid", "preset": design_or_preset}
        if provider == "mandara":
            if design_or_preset not in MANDARA_6_AUTH_DESIGNS:
                raise ValueError(f"Unknown Mandara AuthDesign: {design_or_preset}")
            self.store.set_provider("lock_screen", "mandara")
            self.store.doc["providers"]["mandara"]["config"].setdefault("lock", {})["design"] = design_or_preset
            self.store.flush_all()
            return {"provider": "mandara", "design": design_or_preset}
        raise ValueError(f"Invalid lock provider: {provider}")

    def stage_display_manager_configs(self) -> dict[str, Path]:
        """Generates ready-to-install staged configs for BOTH Lucid SDDM and Mandara greetd
        synchronized with the user's current M3 Expressive palette & font."""
        ident = self.store.doc["identity"]
        tok = generate_m3_expressive_tokens(ident.get("accent_seed", "#ffb1c4"), dark=bool(ident.get("dark_mode", True)))

        # 1. Stage Lucid SDDM theme.conf
        sddm_lines = [
            "[General]",
            f"isLight={'false' if ident.get('dark_mode', True) else 'true'}",
            f"accent={tok['accent']}",
            f"accentHover={tok['accentHover']}",
            f"fgAccent={tok['fgAccent']}",
            f"accentMuted={tok['accentMuted']}",
            f"accentContainer={tok['accentContainer']}",
            f"fgAccentContainer={tok['fgAccentContainer']}",
            f"bgOpaque={tok['bgOpaque']}",
            f"bgHigh={tok['bgHigh']}",
            f"text={tok['text']}",
            f"subtext={tok['subtext']}",
            f"outline={tok['outline']}",
            f"fontFamily={ident.get('font_family', 'Google Sans')}",
        ]
        atomic_write_text(self.store.lucid_sddm_stage_path, "\n".join(sddm_lines) + "\n")

        # 2. Stage Mandara /etc/mandara/greeter.toml
        greeter_doc = dict(self.store.doc["providers"]["mandara"]["greeter"])
        greeter_doc.setdefault("font", ident.get("font_family", "Google Sans"))
        t_sec = greeter_doc.setdefault("theme", {})
        t_sec.setdefault("accent", tok["accent"])
        t_sec.setdefault("light", not bool(ident.get("dark_mode", True)))
        atomic_write_text(self.store.mandara_greeter_stage_path, dumps_toml(greeter_doc))

        return {
            "lucid_sddm_theme_conf": self.store.lucid_sddm_stage_path,
            "mandara_greeter_toml": self.store.mandara_greeter_stage_path,
        }
