"""Scy-Shell Unified Lossless Config Store & Complete 14-Target Bidirectional Engine Sync."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .schema import (
    DEFAULT_ACTIVE_PROVIDERS,
    DEFAULT_PRESENTATIONS,
    ScySchema,
    SettingMeta,
)
from .toml_io import atomic_write_text, dumps_toml, get_pointer, load_toml, set_pointer

MOJI_CONFIG_KEYS = frozenset({"giphyKey", "tenorKey", "gifDir", "pasteApps"})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _lua_val(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return repr(val)
    s = str(val).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def _parse_ini_general(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    out: dict[str, Any] = {}
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.lower() == "true":
            out[k] = True
        elif v.lower() == "false":
            out[k] = False
        else:
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
    return out


class ScyConfigStore:
    """Owns `~/.config/scy-shell/config.toml` and syncs two-way with all 14 Lucid & Mandara engine stores.

    Crucial Guarantee:
    - Every one of the 1,875 settings (643 Lucid + 1,232 Mandara) persists to both
      `config.toml` AND its native engine file (`prefs.json`, `lucid-settings.lua`,
      `blur.json`, `lucidwidgets/widgets.json`, `lucidmoji/{config,state}.json`,
      `lucidkeys/state.json`, `{lumen,lens,clock,shot}.json`, `staged-sddm-theme.conf`,
      `mandara/config.toml`, `mandara/wallgen.toml`, `staged-greeter.toml`).
    - Inactive provider settings are NEVER erased, clobbered, or reset when switching
      `active_providers` or `presentations`.
    """

    def __init__(
        self,
        home_dir: Path | None = None,
        schema: ScySchema | None = None,
        skip_init_load: bool = False,
    ) -> None:
        self.home = (home_dir or Path.home()).resolve()
        self.config_dir = self.home / ".config" / "scy-shell"
        self.state_dir = self.home / ".local" / "state" / "scy-shell"
        self.backup_root = self.home / ".local" / "share" / "scy-shell" / "backups"
        self.config_path = self.config_dir / "config.toml"
        self.runtime_state_path = self.state_dir / "runtime-state.json"
        self.live_values_path = self.state_dir / "live-values.json"
        self.pinned_apps_path = self.config_dir / "pinned-apps.json"

        # Complete native Lucid engine paths
        self.lucid_prefs_path = self.home / ".config" / "quickshell" / "lucidprefs" / "prefs.json"
        self.lucid_hypr_lua_path = self.home / ".config" / "hypr" / "lucid-settings.lua"
        self.lucid_blur_path = self.home / ".config" / "quickshell" / "blur.json"
        self.lucid_widgets_path = self.home / ".config" / "quickshell" / "lucidwidgets" / "widgets.json"
        self.lucid_widgets_legacy_path = self.home / ".config" / "quickshell" / "widgets.json"
        self.lucid_pinned_path = self.home / ".config" / "quickshell" / "pinned.json"
        self.lucid_moji_config_path = self.home / ".config" / "quickshell" / "lucidmoji" / "config.json"
        self.lucid_moji_state_path = self.home / ".config" / "quickshell" / "lucidmoji" / "state.json"
        self.lucid_app_paths = {
            "lumen": self.home / ".local" / "state" / "lucid" / "lumen.json",
            "lens": self.home / ".local" / "state" / "lucid" / "lens.json",
            "clock_app": self.home / ".local" / "state" / "lucid" / "clock.json",
            "shot_state": self.home / ".local" / "state" / "lucid" / "shot.json",
            "keys": self.home / ".config" / "quickshell" / "lucidkeys" / "state.json",
        }
        self.lucid_sddm_stage_path = self.state_dir / "staged-sddm-theme.conf"

        # Complete native Mandara engine paths
        self.mandara_config_path = self.home / ".config" / "mandara" / "config.toml"
        self.mandara_wallgen_path = self.home / ".config" / "mandara" / "wallgen.toml"
        self.mandara_greeter_stage_path = self.state_dir / "staged-greeter.toml"

        self.schema = schema or ScySchema()
        if skip_init_load:
            self.doc = self._default_doc()
        else:
            self.doc = self._load_or_init()
            self.import_existing_engine_configs()
            self.flush_all()

    def _default_doc(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "identity": {
                "primary_style": "scy-m3-expressive",
                "wallpaper": "",
                "matugen_scheme": "scheme-tonal-spot",
                "dark_mode": True,
                "accent_seed": "#ffb1c4",
                "font_family": "Google Sans",
                "mono_font_family": "JetBrains Mono",
                "reduced_motion": False,
            },
            "active_providers": dict(DEFAULT_ACTIVE_PROVIDERS),
            "presentations": dict(DEFAULT_PRESENTATIONS),
            "safety": {
                "conflict_policy": "prompt",
                "hyprland_trial_seconds": 15,
                "auto_backup": True,
            },
            "providers": {
                "lucid": {
                    "prefs": {},
                    "hypr": {},
                    "glass": {},
                    "apps": {},
                    "widget_opts": {},
                    "lock_widgets": {},
                    "sddm": {},
                },
                "mandara": {
                    "config": {},
                    "wallgen": {},
                    "greeter": {},
                },
            },
        }

    def _load_or_init(self) -> dict[str, Any]:
        base = self._default_doc()
        if self.config_path.exists():
            loaded = load_toml(self.config_path)
            self._deep_merge(base, loaded)
        return base

    @staticmethod
    def _deep_merge(dst: dict[str, Any], src: dict[str, Any]) -> None:
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                ScyConfigStore._deep_merge(dst[k], v)
            else:
                dst[k] = v

    def import_existing_engine_configs(self) -> None:
        """Non-destructively pull existing standalone Lucid or Mandara user settings on first run."""
        l_store = self.doc["providers"]["lucid"]
        if self.lucid_prefs_path.exists() and not l_store["prefs"]:
            l_store["prefs"] = _read_json(self.lucid_prefs_path)
            # Unpack embedded JSON strings `hyprOptions` & `lockWidgetOpts` if present!
            raw_ho = l_store["prefs"].get("hyprOptions")
            if isinstance(raw_ho, str) and raw_ho.strip().startswith("{") and not l_store["hypr"]:
                try:
                    ho = json.loads(raw_ho)
                    if isinstance(ho, dict):
                        l_store["hypr"].update(ho)
                except Exception:
                    pass
            raw_lo = l_store["prefs"].get("lockWidgetOpts")
            if isinstance(raw_lo, str) and raw_lo.strip().startswith("{") and not l_store["lock_widgets"]:
                try:
                    lo = json.loads(raw_lo)
                    if isinstance(lo, dict):
                        for wid, wmap in lo.items():
                            if isinstance(wmap, dict):
                                for ok, ov in wmap.items():
                                    l_store["lock_widgets"][f"lockOpts.{wid}.{ok}"] = ov
                except Exception:
                    pass

        if self.lucid_blur_path.exists() and not l_store["glass"]:
            l_store["glass"] = _read_json(self.lucid_blur_path)

        wpath = self.lucid_widgets_path if self.lucid_widgets_path.exists() else self.lucid_widgets_legacy_path
        if wpath.exists() and not l_store["widget_opts"]:
            wdoc = _read_json(wpath)
            for wtype, opts in (wdoc.get("scyWidgetDefaults") or {}).items():
                if isinstance(opts, dict):
                    for ok, ov in opts.items():
                        l_store["widget_opts"][f"widgets.{wtype}.{ok}"] = ov
            for inst in (wdoc.get("instances") or []):
                if isinstance(inst, dict) and isinstance(inst.get("opts"), dict) and inst.get("type"):
                    wtype = inst["type"]
                    for ok, ov in inst["opts"].items():
                        l_store["widget_opts"].setdefault(f"widgets.{wtype}.{ok}", ov)

        if (self.lucid_moji_config_path.exists() or self.lucid_moji_state_path.exists()) and "moji" not in l_store["apps"]:
            merged_moji: dict[str, Any] = {}
            merged_moji.update(_read_json(self.lucid_moji_state_path))
            merged_moji.update(_read_json(self.lucid_moji_config_path))
            if merged_moji:
                l_store["apps"]["moji"] = merged_moji

        for app_key, ap in self.lucid_app_paths.items():
            if ap.exists() and app_key not in l_store["apps"]:
                l_store["apps"][app_key] = _read_json(ap)

        if self.lucid_sddm_stage_path.exists() and not l_store["sddm"]:
            l_store["sddm"] = _parse_ini_general(self.lucid_sddm_stage_path)

        m_store = self.doc["providers"]["mandara"]
        if self.mandara_config_path.exists() and not m_store["config"]:
            m_store["config"] = load_toml(self.mandara_config_path)
        if self.mandara_wallgen_path.exists() and not m_store["wallgen"]:
            m_store["wallgen"] = load_toml(self.mandara_wallgen_path)
        if self.mandara_greeter_stage_path.exists() and not m_store["greeter"]:
            m_store["greeter"] = load_toml(self.mandara_greeter_stage_path)

    def _backup_targets(self) -> list[tuple[str, Path]]:
        targets: list[tuple[str, Path]] = [
            ("scy_config.toml", self.config_path),
            ("scy_pinned_apps.json", self.pinned_apps_path),
            ("lucid_prefs.json", self.lucid_prefs_path),
            ("lucid_pinned.json", self.lucid_pinned_path),
            ("lucid_settings.lua", self.lucid_hypr_lua_path),
            ("lucid_blur.json", self.lucid_blur_path),
            ("lucid_widgets.json", self.lucid_widgets_path),
            ("lucid_moji_config.json", self.lucid_moji_config_path),
            ("lucid_moji_state.json", self.lucid_moji_state_path),
            ("lucid_sddm_stage.conf", self.lucid_sddm_stage_path),
            ("mandara_config.toml", self.mandara_config_path),
            ("mandara_wallgen.toml", self.mandara_wallgen_path),
            ("mandara_greeter.toml", self.mandara_greeter_stage_path),
        ]
        for app_k, ap in self.lucid_app_paths.items():
            targets.append((f"lucid_app_{app_k}.json", ap))
        return targets

    def _validate_restore_destination(self, raw_dest: str) -> Path:
        if not isinstance(raw_dest, str) or not raw_dest.strip() or "\x00" in raw_dest:
            raise ValueError(f"Invalid destination path in backup manifest: {raw_dest!r}")
        dst_raw = Path(raw_dest)
        if not dst_raw.is_absolute():
            raise ValueError(f"Backup destination path must be absolute: {raw_dest!r}")
        if dst_raw.is_symlink():
            raise ValueError(f"Refusing to overwrite symlink destination: {dst_raw}")
        dst = dst_raw.resolve()
        allowed_roots = (
            (self.home / ".config").resolve(),
            (self.home / ".local" / "state").resolve(),
            (self.home / ".local" / "share" / "scy-shell").resolve(),
        )
        if not any(dst.is_relative_to(root) for root in allowed_roots):
            raise ValueError(f"Unsafe backup destination outside managed user directories: {raw_dest}")
        if dst.is_relative_to(self.backup_root.resolve()):
            raise ValueError(f"Refusing to restore into backup storage directory: {raw_dest}")
        return dst

    @staticmethod
    def _atomic_copy_file(src: Path, dst: Path) -> None:
        import os

        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.parent / f".{dst.name}.scy-restore-{os.getpid()}-{time.time_ns()}.tmp"
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def resolve_backup_dir(self, backup_ref: str | Path) -> Path:
        raw_str = str(backup_ref).strip() if backup_ref is not None else ""
        if not raw_str or "\x00" in raw_str:
            raise ValueError("Backup path or snapshot name must not be empty")
        candidate = Path(raw_str).expanduser()
        if not candidate.exists() and "/" not in raw_str and "\\" not in raw_str and raw_str not in (".", ".."):
            named = self.backup_root / raw_str
            if named.exists():
                candidate = named
        if candidate.is_symlink():
            raise ValueError(f"Refusing symlinked backup path: {candidate}")
        if not candidate.exists():
            raise FileNotFoundError(f"Backup directory does not exist: {candidate}")
        resolved = candidate.resolve()
        if not resolved.is_dir():
            raise ValueError(f"Backup path is not a directory: {resolved}")
        return resolved

    def create_backup(self, tag: str = "manual") -> Path:
        safe_tag = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in (tag or "manual")).strip("-") or "manual"
        ts = time.strftime("%Y%m%d-%H%M%S")
        bdir = self.backup_root / f"{ts}-{safe_tag}-{int(time.time_ns() % 100000)}"
        bdir.mkdir(parents=True, exist_ok=True)

        manifest_files: dict[str, str] = {}
        absent_files: list[str] = []
        for alias, src in self._backup_targets():
            if src.exists():
                self._atomic_copy_file(src, bdir / alias)
                manifest_files[alias] = str(src)
            else:
                absent_files.append(str(src))
        _write_json(
            bdir / "manifest.json",
            {
                "created_at": ts,
                "tag": safe_tag,
                "home": str(self.home),
                "files": manifest_files,
                "absent_files": absent_files,
            },
        )
        return bdir

    def restore_backup(self, backup_dir: str | Path) -> list[str]:
        bdir = self.resolve_backup_dir(backup_dir)
        mpath = bdir / "manifest.json"
        if mpath.is_symlink():
            raise ValueError(f"Refusing symlinked manifest in {bdir}")
        if not mpath.exists() or not mpath.is_file():
            raise FileNotFoundError(f"Backup manifest missing in {bdir}")

        try:
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid JSON in backup manifest {mpath}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise ValueError(f"Backup manifest in {bdir} must be a JSON object")

        raw_files = manifest.get("files")
        if not isinstance(raw_files, dict):
            raise ValueError(f"Backup manifest in {bdir} missing valid 'files' mapping")
        raw_absent = manifest.get("absent_files", [])
        if not isinstance(raw_absent, list):
            raise ValueError(f"Backup manifest in {bdir} has invalid 'absent_files' list")

        # Phase 1: Validate EVERY source payload and destination path BEFORE modifying anything on disk
        validated_copies: list[tuple[Path, Path, str]] = []
        seen_dests: set[Path] = set()
        for alias, orig_str in raw_files.items():
            if (
                not isinstance(alias, str)
                or not alias
                or alias in (".", "..")
                or "/" in alias
                or "\\" in alias
                or "\x00" in alias
                or Path(alias).name != alias
            ):
                raise ValueError(f"Unsafe backup file alias in manifest: {alias!r}")
            src_raw = bdir / alias
            if src_raw.is_symlink():
                raise ValueError(f"Refusing symlinked payload file in backup: {src_raw}")
            src = src_raw.resolve()
            if not src.is_relative_to(bdir) or not src.exists() or not src.is_file():
                raise ValueError(f"Missing or invalid backup payload file for '{alias}' in {bdir}")
            dst = self._validate_restore_destination(orig_str)
            seen_dests.add(dst)
            validated_copies.append((src, dst, orig_str))

        validated_absent: list[Path] = []
        for orig_str in raw_absent:
            dst = self._validate_restore_destination(orig_str)
            if dst not in seen_dests:
                validated_absent.append(dst)

        # Phase 2: Capture pre-restore rollback snapshot of all affected target paths for full recovery safety
        rollback_bytes: dict[Path, bytes | None] = {}
        for _, dst, _ in validated_copies:
            rollback_bytes[dst] = dst.read_bytes() if dst.exists() else None
        for dst in validated_absent:
            rollback_bytes[dst] = dst.read_bytes() if dst.exists() else None

        restored: list[str] = []
        try:
            for src, dst, orig_str in validated_copies:
                self._atomic_copy_file(src, dst)
                restored.append(orig_str)
            for dst in validated_absent:
                if dst.exists():
                    dst.unlink()

            self.doc = self._load_or_init()
            self.import_existing_engine_configs()
            self.flush_runtime_state()
        except Exception:
            # Roll back every touched path to exact pre-restore bytes so partial state never survives
            for dst, prev in rollback_bytes.items():
                try:
                    if prev is None:
                        dst.unlink(missing_ok=True)
                    else:
                        import os

                        dst.parent.mkdir(parents=True, exist_ok=True)
                        rtmp = dst.parent / f".{dst.name}.scy-rollback-{os.getpid()}-{time.time_ns()}.tmp"
                        rtmp.write_bytes(prev)
                        os.replace(rtmp, dst)
                except Exception:
                    pass
            try:
                self.doc = self._load_or_init()
                self.flush_runtime_state()
            except Exception:
                pass
            raise

        return restored

    # --- Provider & Presentation Switching ---
    def get_provider(self, domain: str) -> Any:
        return self.doc["active_providers"].get(domain)

    def set_provider(self, domain: str, provider: str | dict[str, str]) -> tuple[bool, str]:
        ok, msg = self.schema.validate_provider(domain, provider)
        if not ok:
            return False, msg
        if self.doc["safety"].get("auto_backup", True) and self.config_path.exists():
            self.create_backup(f"provider-{domain}")
        self.doc["active_providers"][domain] = provider
        self._apply_exclusive_gates_to_engine_configs()
        self.flush_all()
        return True, f"{domain} provider set to {provider}"

    def set_presentation(self, domain: str, value: str) -> tuple[bool, str]:
        ok, msg = self.schema.validate_presentation(domain, value)
        if not ok:
            return False, msg
        self.doc["presentations"][domain] = value
        if domain in ("primary_identity", "mandara_surface_look"):
            self.doc["identity"]["primary_style"] = value
            if get_pointer(self.doc["providers"]["mandara"]["config"], "/looks/active", None) is None:
                set_pointer(self.doc["providers"]["mandara"]["config"], "/looks/active", value)
        self.flush_all()
        return True, f"{domain} presentation set to {value}"

    def _apply_exclusive_gates_to_engine_configs(self) -> None:
        """Synchronize exclusive resource flags into Mandara's [scy_gates] without altering user settings!"""
        ap = self.doc["active_providers"]
        mcfg = self.doc["providers"]["mandara"]["config"]
        mcfg["scy_gates"] = {
            "managed_by_scy_shell": True,
            "owns_notifications": ap.get("notifications") == "mandara",
            "owns_polkit": ap.get("polkit") == "mandara",
            "owns_lock": ap.get("lock_screen") == "mandara",
            "owns_idle": ap.get("idle") == "mandara",
            "owns_night_light": ap.get("night_light") == "mandara",
            "owns_bt_agent": ap.get("bt_agent") == "mandara",
            "owns_clipboard": ap.get("clipboard") == "mandara",
            "owns_wallpaper": ap.get("wallpaper") == "mandara",
            "bar_mode": ap.get("bar", "lucid"),
            "dock_mode": ap.get("dock", "lucid"),
            "launcher_mode": ap.get("launcher", "lucid"),
            "desktop_widgets_mode": ap.get("desktop_widgets", "lucid"),
            "toast_renderer": self.doc["presentations"].get("toasts", "lucid"),
            "osd_renderer": ap.get("osd", "lucid"),
        }

    # --- Universal Type-Aware Setting Get / Set / Reset across all 1,875 Settings ---
    def get_setting(self, scy_id: str) -> Any:
        meta = self.schema.by_id.get(scy_id)
        if meta is None:
            raise KeyError(f"Unknown setting ID: {scy_id}")
        return self._read_meta_value(meta)

    def set_setting(
        self,
        scy_id: str,
        value: Any,
        flush: bool = True,
        validate: bool = True,
    ) -> SettingMeta:
        meta = self.schema.by_id.get(scy_id)
        if meta is None:
            raise KeyError(f"Unknown setting ID: {scy_id}")
        coerced = self.schema.validate_and_coerce(scy_id, value) if validate else value
        self._write_meta_value(meta, coerced)
        if flush:
            self.flush_all()
        return meta

    def reset_setting(self, scy_id: str, flush: bool = True) -> SettingMeta:
        meta = self.schema.by_id.get(scy_id)
        if meta is None:
            raise KeyError(f"Unknown setting ID: {scy_id}")
        self._write_meta_value(meta, meta.default_value)
        if flush:
            self.flush_all()
        return meta

    def get_all_values(self) -> dict[str, Any]:
        return {sid: self._read_meta_value(meta) for sid, meta in self.schema.by_id.items()}

    def _read_meta_value(self, meta: SettingMeta) -> Any:
        if meta.source_project == "lucid":
            l_store = self.doc["providers"]["lucid"]
            if meta.scy_id.startswith("scy.providers.lucid.prefs."):
                return l_store["prefs"].get(meta.original_key, meta.default_value)
            if meta.scy_id.startswith("scy.providers.lucid.hypr."):
                return l_store["hypr"].get(meta.original_key, meta.default_value)
            if meta.scy_id == "scy.providers.lucid.glass.blurValue":
                return l_store["glass"].get("value", meta.default_value)
            if meta.scy_id.startswith("scy.providers.lucid.widget_opts."):
                return l_store["widget_opts"].get(meta.original_key, meta.default_value)
            if meta.scy_id.startswith("scy.providers.lucid.lock_widgets."):
                return l_store["lock_widgets"].get(meta.original_key, meta.default_value)
            if meta.scy_id.startswith("scy.providers.lucid.sddm."):
                k = meta.original_key.split(".", 1)[1]
                return l_store["sddm"].get(k, meta.default_value)
            parts = meta.scy_id.split(".")
            app_name, prop = parts[3], parts[4]
            return l_store["apps"].get(app_name, {}).get(prop, meta.default_value)

        m_store = self.doc["providers"]["mandara"]
        if meta.scy_id.startswith("scy.providers.mandara.config."):
            val = get_pointer(m_store["config"], meta.original_key, None)
            return meta.default_value if val is None else val
        if meta.scy_id.startswith("scy.providers.mandara.wallgen."):
            ptr = "/" + meta.original_key.replace(".", "/").removeprefix("wallgen/")
            val = get_pointer(m_store["wallgen"], ptr, None)
            return meta.default_value if val is None else val
        if meta.scy_id.startswith("scy.providers.mandara.greeter."):
            ptr = "/" + meta.original_key.replace(".", "/").removeprefix("greeter/")
            val = get_pointer(m_store["greeter"], ptr, None)
            return meta.default_value if val is None else val
        return meta.default_value

    def _write_meta_value(self, meta: SettingMeta, value: Any) -> None:
        if meta.source_project == "lucid":
            l_store = self.doc["providers"]["lucid"]
            if meta.scy_id.startswith("scy.providers.lucid.prefs."):
                l_store["prefs"][meta.original_key] = value
                if meta.original_key == "hyprOptions" and isinstance(value, str):
                    try:
                        ho = json.loads(value)
                        if isinstance(ho, dict):
                            l_store["hypr"].update(ho)
                    except Exception:
                        pass
                elif meta.original_key == "lockWidgetOpts" and isinstance(value, str):
                    try:
                        lo = json.loads(value) if value.strip() else {}
                        if isinstance(lo, dict):
                            for wid, wmap in lo.items():
                                if isinstance(wmap, dict):
                                    for ok, ov in wmap.items():
                                        l_store["lock_widgets"][f"lockOpts.{wid}.{ok}"] = ov
                    except Exception:
                        pass
                return

            if meta.scy_id.startswith("scy.providers.lucid.hypr."):
                l_store["hypr"][meta.original_key] = value
                raw_ho = l_store["prefs"].get("hyprOptions", "{}")
                try:
                    parsed_ho = json.loads(raw_ho) if isinstance(raw_ho, str) and raw_ho.strip() else {}
                    if not isinstance(parsed_ho, dict):
                        parsed_ho = {}
                except Exception:
                    parsed_ho = {}
                parsed_ho[meta.original_key] = value
                if "hyprOptions" not in l_store["prefs"] or raw_ho == "{}" or str(raw_ho).startswith("{"):
                    l_store["prefs"]["hyprOptions"] = json.dumps(parsed_ho)
                return

            if meta.scy_id == "scy.providers.lucid.glass.blurValue":
                l_store["glass"]["value"] = float(value)
                return

            if meta.scy_id.startswith("scy.providers.lucid.widget_opts."):
                l_store["widget_opts"][meta.original_key] = value
                return

            if meta.scy_id.startswith("scy.providers.lucid.lock_widgets."):
                l_store["lock_widgets"][meta.original_key] = value
                raw_lo = l_store["prefs"].get("lockWidgetOpts", "")
                try:
                    parsed_lo = json.loads(raw_lo) if isinstance(raw_lo, str) and raw_lo.strip().startswith("{") else {}
                    if not isinstance(parsed_lo, dict):
                        parsed_lo = {}
                except Exception:
                    parsed_lo = {}
                # original_key: lockOpts.<widget>.<opt>
                kparts = meta.original_key.split(".", 2)
                if len(kparts) == 3:
                    _, wid, opt = kparts
                    parsed_lo.setdefault(wid, {})[opt] = value
                    if "lockWidgetOpts" not in l_store["prefs"] or raw_lo == "" or str(raw_lo).startswith("{"):
                        l_store["prefs"]["lockWidgetOpts"] = json.dumps(parsed_lo)
                return

            if meta.scy_id.startswith("scy.providers.lucid.sddm."):
                k = meta.original_key.split(".", 1)[1]
                l_store["sddm"][k] = value
                return

            parts = meta.scy_id.split(".")
            app_name, prop = parts[3], parts[4]
            l_store["apps"].setdefault(app_name, {})[prop] = value
            return

        # Mandara
        m_store = self.doc["providers"]["mandara"]
        if meta.scy_id.startswith("scy.providers.mandara.config."):
            if meta.value_type == "table":
                if not isinstance(value, dict):
                    raise TypeError(f"Setting {meta.scy_id} ({meta.original_key}) is a TOML table; expected dict")
                existing = get_pointer(m_store["config"], meta.original_key, {})
                merged = dict(existing) if isinstance(existing, dict) else {}
                self._deep_merge(merged, value)
                set_pointer(m_store["config"], meta.original_key, merged)
            else:
                set_pointer(m_store["config"], meta.original_key, value)
            return
        if meta.scy_id.startswith("scy.providers.mandara.wallgen."):
            ptr = "/" + meta.original_key.replace(".", "/").removeprefix("wallgen/")
            set_pointer(m_store["wallgen"], ptr, value)
            return
        if meta.scy_id.startswith("scy.providers.mandara.greeter."):
            ptr = "/" + meta.original_key.replace(".", "/").removeprefix("greeter/")
            set_pointer(m_store["greeter"], ptr, value)

    # --- Sync Pinned Apps Across Lucid Dock & Mandara Dock ---
    def sync_pinned_apps(self, apps: list[str] | None = None) -> list[str]:
        if apps is None:
            if self.pinned_apps_path.exists():
                apps = json.loads(self.pinned_apps_path.read_text(encoding="utf-8"))
            elif self.lucid_pinned_path.exists():
                raw = json.loads(self.lucid_pinned_path.read_text(encoding="utf-8"))
                apps = raw if isinstance(raw, list) else raw.get("apps", [])
            else:
                apps = get_pointer(self.doc["providers"]["mandara"]["config"], "/dock/pinned", []) or []
        apps = [str(a) for a in apps]
        _write_json(self.pinned_apps_path, apps)
        _write_json(self.lucid_pinned_path, apps)
        set_pointer(self.doc["providers"]["mandara"]["config"], "/dock/pinned", apps)
        return apps

    def _collect_override_values(self) -> dict[str, Any]:
        """Compact map of every explicitly set / overridden value across all 1,875 settings for fast QML reactive loading."""
        overrides: dict[str, Any] = {}
        for sid, meta in self.schema.by_id.items():
            cur = self._read_meta_value(meta)
            if cur != meta.default_value:
                overrides[sid] = cur
        return overrides

    def flush_runtime_state(self) -> None:
        overrides = self._collect_override_values()
        state = {
            "updated_at_ms": int(time.time() * 1000),
            "identity": self.doc["identity"],
            "active_providers": self.doc["active_providers"],
            "presentations": self.doc["presentations"],
            "scy_gates": self.doc["providers"]["mandara"]["config"].get("scy_gates", {}),
            "override_count": len(overrides),
        }
        _write_json(self.runtime_state_path, state)
        _write_json(self.live_values_path, {"updated_at_ms": state["updated_at_ms"], "values": overrides})

    def flush_all(self) -> None:
        self._apply_exclusive_gates_to_engine_configs()
        atomic_write_text(
            self.config_path,
            dumps_toml(
                self.doc,
                header_comment="Scy-Shell Unified Configuration — Managed safely via `scy-shell` or Studio.",
            ),
        )

        # --- Write ALL Native Lucid Engine Stores ---
        l_store = self.doc["providers"]["lucid"]

        # 1. prefs.json (including synchronized lockWidgetOpts & hyprOptions JSON strings)
        if l_store["prefs"] or l_store["lock_widgets"] or l_store["hypr"]:
            merged_prefs = _read_json(self.lucid_prefs_path)
            merged_prefs.update(l_store["prefs"])
            if l_store["lock_widgets"] and "lockWidgetOpts" not in l_store["prefs"]:
                nested_lo: dict[str, dict[str, Any]] = {}
                for full_k, v in l_store["lock_widgets"].items():
                    kp = full_k.split(".", 2)
                    if len(kp) == 3:
                        nested_lo.setdefault(kp[1], {})[kp[2]] = v
                merged_prefs["lockWidgetOpts"] = json.dumps(nested_lo)
            _write_json(self.lucid_prefs_path, merged_prefs)

        # 2. ~/.config/hypr/lucid-settings.lua (native Lucid Hyprland options file)
        if l_store["hypr"]:
            opt_lines = ["return {", "  options = {"]
            for k in sorted(l_store["hypr"]):
                opt_lines.append(f"    [{_lua_val(k)}] = {_lua_val(l_store['hypr'][k])},")
            opt_lines.extend(["  }", "}"])
            atomic_write_text(self.lucid_hypr_lua_path, "\n".join(opt_lines) + "\n")

        # 3. blur.json
        if l_store["glass"]:
            merged_blur = _read_json(self.lucid_blur_path)
            merged_blur.update(l_store["glass"])
            _write_json(self.lucid_blur_path, merged_blur)

        # 4. lucidwidgets/widgets.json (both defaults and live instances)
        if l_store["widget_opts"]:
            wdoc = _read_json(self.lucid_widgets_path) or {
                "nextId": 1,
                "boardFull": True,
                "laidScale": 1,
                "preset": "",
                "saved": [],
                "last": [],
                "stash": [],
                "instances": [],
            }
            wdefs = wdoc.setdefault("scyWidgetDefaults", {})
            for full_k, v in l_store["widget_opts"].items():
                kp = full_k.split(".", 2)
                if len(kp) == 3:
                    _, wtype, opt = kp
                    wdefs.setdefault(wtype, {})[opt] = v
                    for inst in wdoc.get("instances", []):
                        if isinstance(inst, dict) and inst.get("type") == wtype:
                            inst.setdefault("opts", {})[opt] = v
            _write_json(self.lucid_widgets_path, wdoc)

        # 5. lucidmoji/{config,state}.json + standalone Lucid apps (lumen, lens, clock, shot, lucidkeys)
        installed_lucid_root = self.home / ".config" / "quickshell" / "lucid"
        if "moji" in l_store["apps"] and l_store["apps"]["moji"]:
            m_cfg = _read_json(self.lucid_moji_config_path)
            m_st = _read_json(self.lucid_moji_state_path)
            for k, v in l_store["apps"]["moji"].items():
                if k in MOJI_CONFIG_KEYS:
                    m_cfg[k] = v
                else:
                    m_st[k] = v
            if m_cfg:
                _write_json(self.lucid_moji_config_path, m_cfg)
                if installed_lucid_root.exists():
                    _write_json(installed_lucid_root / "lucidmoji" / "config.json", m_cfg)
            if m_st:
                _write_json(self.lucid_moji_state_path, m_st)
                if installed_lucid_root.exists():
                    _write_json(installed_lucid_root / "lucidmoji" / "state.json", m_st)

        for app_name, app_vals in l_store["apps"].items():
            if app_name == "moji" or not app_vals or app_name not in self.lucid_app_paths:
                continue
            ap = self.lucid_app_paths[app_name]
            cur = _read_json(ap)
            cur.update(app_vals)
            _write_json(ap, cur)
            if app_name == "keys" and installed_lucid_root.exists():
                _write_json(installed_lucid_root / "lucidkeys" / "state.json", cur)

        # 6. Staged SDDM theme.conf
        if l_store["sddm"]:
            lines = ["[General]"] + [
                f"{k}={str(v).lower() if isinstance(v, bool) else v}"
                for k, v in sorted(l_store["sddm"].items())
            ]
            atomic_write_text(self.lucid_sddm_stage_path, "\n".join(lines) + "\n")

        # --- Write ALL Native Mandara Engine Stores ---
        m_store = self.doc["providers"]["mandara"]
        atomic_write_text(
            self.mandara_config_path,
            dumps_toml(m_store["config"], header_comment="Synced by Scy-Shell Unified Core (inactive settings preserved)."),
        )
        if m_store["wallgen"]:
            atomic_write_text(self.mandara_wallgen_path, dumps_toml(m_store["wallgen"]))
        if m_store["greeter"]:
            atomic_write_text(self.mandara_greeter_stage_path, dumps_toml(m_store["greeter"]))

        self.flush_runtime_state()
