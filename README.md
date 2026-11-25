# Scy-Shell v1.0.0

**Unified Material 3 Expressive Wayland Desktop Shell (`Lucid` Quickshell QML + `Mandara` Rust GPUI) for Hyprland (`0.55+`) on CachyOS / Arch Linux.**

## Highlights

- **100% Feature & Setting Preservation:** Unifies all **41** subsystems and all **1,875** settings (**643** Lucid + **1,232** Mandara) under a single lossless store (`~/.config/scy-shell/scy-shell.toml`) with automatic two-way sync to Lucid `prefs.json` and Mandara `config.toml`.
- **Material 3 Expressive Default + All 20 Looks:** Ships `scy-m3-expressive` (`Google Sans` + `JetBrains Mono`, WCAG AA contrast, spring physics) alongside all **19** original Mandara Looks and **28** SHA-256 tamper-protected external app theme targets.
- **Zero-Conflict Single-Owner Arbitration:** Enforces single ownership across all **11** exclusive Wayland/DBus/PAM resources (`notifications`, `osd`, `tray`, `polkit`, `lock_screen`, `idle`, `wallpaper`, `night_light`, `audio_control`, `display_manager`, `portals`). When Mandara visual surfaces are delegated to Lucid, Mandara runs in zero-swapchain headless mode (`ScyGatesConfig::needs_shell_surface() == false`).
- **89 Plugins, Local AI Agent & 13-Style Wallgen Inside Lucid:** Mounts `ScyPluginPill` directly in Lucid's bar, federates `!ai <prompt>` and `@<plugin>` live into Lucid's `Dock.qml` launcher, and adds **8** native `Scy*Page.qml` Studio pages (**38** total Studio pages).
- **Complete Shortcut Accounting (`0` Collisions):** Preserves all **61** Lucid Hyprland binds + **6** conflict-free Mandara superpower binds (**67** compositor binds), all **17** grouped (**22** QML `keyActions` slots: `19` default-bound + `3` user-bindable) `DesktopIcons.qml` canvas shortcuts, and all **25** Mandara `default_keybinds()`.
- **Phase 1 Verifiable Upstream Provenance:** Includes `3,708` SHA-256 upstream file digests (`provenance/*.sha256`) and reversible unified git patches (`adapters/*/*.patch`) verified by `scy-shell provenance`.

---

## Quick Start (CachyOS / Arch Linux)

```bash
unzip scy-shell-v1.0.0.zip
cd scy-shell

# 1. Verify Phase 1 upstream SHA-256 baseline & run portable test suite
make provenance
make test

# 2. Build native Mandara Rust GPUI binary (requires rust, clang, wayland, pipewire, pam)
./scripts/build-clean.sh

# 3. Preview non-destructive install & migration
./install.sh --dry-run --profile full --with-hypr

# 4. Install & migrate existing Lucid / Mandara user configs safely (creates backups first)
./install.sh --profile full --with-hypr

# 5. Inside an active CachyOS Hyprland session, run live compositor verification
./scripts/verify-cachyos-live.sh
```

Or build and install as a tracked Arch / CachyOS package:

```bash
cd packaging/arch && makepkg -si
```

---

## Test Suites (Portable vs. Host Hardware/Compositor)

- **`make test-portable`** (`tests/test_phase*.py`): Runs anywhere with Python 3.11+ and POSIX `patch`/`sh` — zero GUI, Rust, or Wayland host dependencies, and zero hard-coded paths.
- **`make test-hardware`** (`tests/hardware/test_cachyos_host_integration.py`): Runs `cargo test` / `cargo check --workspace --locked`, `qmllint`, and live `hyprctl` / `quickshell` checks on CachyOS, cleanly reporting `SKIPPED` for any toolchain/compositor capability absent in headless environments.

---

## License

**`GPL-3.0-or-later`** (preserving upstream MIT notices on Lucid components and OFL/Apache-2.0 notices on bundled fonts; see `LICENSE` and `THIRD_PARTY_NOTICES.md`). Optional local LLM weights (`FunctionGemma-270M`, `Qwen3-0.6B`) are never bundled and remain opt-in downloads.
