#!/usr/bin/env bash
# Scy-Shell v1.0.0 — Safe, Idempotent Installer for CachyOS & Arch Linux (+ Hyprland 0.55+/0.57+)
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

SCY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -d "$SCY_ROOT/engines/lucid" ]]; then
  DEFAULT_LUCID_SRC="$SCY_ROOT/engines/lucid"
else
  DEFAULT_LUCID_SRC="$SCY_ROOT/../sources/lucid-working"
fi
if [[ -d "$SCY_ROOT/engines/mandara" ]]; then
  DEFAULT_MANDARA_SRC="$SCY_ROOT/engines/mandara"
else
  DEFAULT_MANDARA_SRC="$SCY_ROOT/../sources/mandara-working"
fi
LUCID_SRC="${LUCID_WORKING_DIR:-$DEFAULT_LUCID_SRC}"
MANDARA_SRC="${MANDARA_WORKING_DIR:-$DEFAULT_MANDARA_SRC}"

DRY_RUN=0
SKIP_ENGINE_BUILD="${SCY_SKIP_ENGINE_BUILD:-0}"
PROFILE="balanced"
WITH_HYPR=0
ACTION="install"
RESTORE_DIR=""
TARGET_HOME="${HOME}"
INSTALL_PKGS=0

usage() {
  cat <<USAGE
Usage: ./install.sh [options]

Options:
  --dry-run                 Show every planned action without modifying any files
  --profile <p>             Installation profile: minimal | balanced | full (default: balanced)
  --with-hypr               Safely attach modular Scy-Shell hook to ~/.config/hypr (backs up first)
  --install-packages        Install CachyOS / Arch packages via pacman (requires sudo)
  --home <dir>              Override target HOME directory (default: \$HOME)
  --restore-backup <dir>    Restore configuration snapshot created by Scy-Shell
  --uninstall               Cleanly remove Scy-Shell hooks, binaries & user units (keeps backups)
  -h, --help                Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --skip-engine-build) SKIP_ENGINE_BUILD=1; shift ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --with-hypr) WITH_HYPR=1; shift ;;
    --install-packages) INSTALL_PKGS=1; shift ;;
    --home) TARGET_HOME="$2"; shift 2 ;;
    --restore-backup) ACTION="restore"; RESTORE_DIR="$2"; shift 2 ;;
    --uninstall) ACTION="uninstall"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
done

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

if [[ "$ACTION" == "restore" ]]; then
  [[ -d "$RESTORE_DIR" ]] || { echo "Backup directory not found: $RESTORE_DIR" >&2; exit 1; }
  echo "[Scy-Shell] Restoring snapshot from $RESTORE_DIR -> $TARGET_HOME/.config ..."
  if [[ -d "$RESTORE_DIR/hypr" ]]; then
    run_cmd rm -rf "$TARGET_HOME/.config/hypr"
    run_cmd cp -a "$RESTORE_DIR/hypr" "$TARGET_HOME/.config/hypr"
  fi
  for sub in scy-shell lucid mandara; do
    if [[ -d "$RESTORE_DIR/$sub" ]]; then
      run_cmd rm -rf "$TARGET_HOME/.config/$sub"
      run_cmd cp -a "$RESTORE_DIR/$sub" "$TARGET_HOME/.config/$sub"
    fi
  done
  echo "[Scy-Shell] Restore complete."
  exit 0
fi

if [[ "$ACTION" == "uninstall" ]]; then
  echo "[Scy-Shell] Uninstalling Scy-Shell user binaries, systemd units, and Hyprland hook (preserving backups)..."
  run_cmd rm -f "$TARGET_HOME/.local/bin/scy-shell" "$TARGET_HOME/.local/bin/scy-daemon" "$TARGET_HOME/.local/bin/scy-shell-ipc"
  run_cmd rm -rf "$TARGET_HOME/.local/share/scy-shell/runtime"
  run_cmd rm -f "$TARGET_HOME/.config/systemd/user/scy-daemon.service" \
                "$TARGET_HOME/.config/systemd/user/scy-lucid.service" \
                "$TARGET_HOME/.config/systemd/user/scy-mandara.service"
  if [[ -f "$TARGET_HOME/.config/hypr/hyprland.lua" && "$DRY_RUN" -eq 0 ]]; then
    sed -i '/-- Scy-Shell modular hook/d; /pcall(require, "scy-shell.init")/d' "$TARGET_HOME/.config/hypr/hyprland.lua"
  fi
  if [[ -f "$TARGET_HOME/.config/hypr/hyprland.conf" && "$DRY_RUN" -eq 0 ]]; then
    sed -i '/# Scy-Shell modular drop-in/d; /scy-shell\/scy-shell\.conf/d' "$TARGET_HOME/.config/hypr/hyprland.conf"
  fi
  run_cmd rm -rf "$TARGET_HOME/.config/hypr/scy-shell"
  echo "[Scy-Shell] Uninstall complete. Your backups remain safe in $TARGET_HOME/.local/share/scy-shell/backups/"
  exit 0
fi

echo "[Scy-Shell] Installing profile='$PROFILE' into HOME='$TARGET_HOME' (dry_run=$DRY_RUN)..."

# Optional CachyOS / Arch package installation
if [[ "$INSTALL_PKGS" -eq 1 ]]; then
  PKGS=(hyprland quickshell gcc make rust cargo pkgconf wayland-protocols clang qt6-declarative qt6-svg qt6-multimedia python awww matugen cliphist wl-clipboard xdg-desktop-portal-hyprland xdg-desktop-portal-gtk)
  if [[ "$PROFILE" == "full" ]]; then
    PKGS+=(tesseract wf-recorder ddcutil kdeconnect)
  fi
  run_cmd sudo pacman -S --needed "${PKGS[@]}"
fi

# 1. Build C11 IPC binary (gcc) & Mandara Rust GPUI engine (cargo) when available
if command -v gcc >/dev/null 2>&1; then
  run_cmd gcc -O3 -Wall -Wextra -Werror -std=c11 "$SCY_ROOT/csrc/scy_ipc_client.c" -o "$SCY_ROOT/bin/scy-shell-ipc"
fi
if [[ "$SKIP_ENGINE_BUILD" -eq 0 && -d "$MANDARA_SRC" ]] && command -v cargo >/dev/null 2>&1 && ! command -v mandara >/dev/null 2>&1; then
  echo "[Scy-Shell] Building Mandara Rust GPUI & WASM engine from bundled source ($MANDARA_SRC)..."
  if [[ "$DRY_RUN" -eq 0 ]]; then
    (cd "$MANDARA_SRC" && cargo build --release --locked)
    mkdir -p "$TARGET_HOME/.local/bin"
    for bin_name in mandara mandara-greeter wallgen; do
      if [[ -x "$MANDARA_SRC/target/release/$bin_name" ]]; then
        cp -f "$MANDARA_SRC/target/release/$bin_name" "$TARGET_HOME/.local/bin/$bin_name"
      fi
    done
  else
    echo "[DRY-RUN] (cd $MANDARA_SRC && cargo build --release) -> $TARGET_HOME/.local/bin/mandara"
  fi
fi

# 2. Install runtime tree & user binaries
RUNTIME_DEST="$TARGET_HOME/.local/share/scy-shell/runtime"
run_cmd mkdir -p "$TARGET_HOME/.local/bin" "$RUNTIME_DEST" "$TARGET_HOME/.config/systemd/user"
if [[ "$DRY_RUN" -eq 0 ]]; then
  cp -a "$SCY_ROOT/src" "$SCY_ROOT/schema" "$SCY_ROOT/studio" "$SCY_ROOT/bin" "$RUNTIME_DEST/"
  ln -sf "$RUNTIME_DEST/bin/scy-shell" "$TARGET_HOME/.local/bin/scy-shell"
  ln -sf "$RUNTIME_DEST/bin/scy-daemon" "$TARGET_HOME/.local/bin/scy-daemon"
  ln -sf "$RUNTIME_DEST/bin/scy-shell-ipc" "$TARGET_HOME/.local/bin/scy-shell-ipc"
  cp -a "$SCY_ROOT/packaging/systemd/"*.service "$TARGET_HOME/.config/systemd/user/"
else
  echo "[DRY-RUN] Copy runtime -> $RUNTIME_DEST and symlink scy-shell, scy-daemon, scy-shell-ipc -> $TARGET_HOME/.local/bin/"
fi

# 3. Install Lucid 2 working QML tree into ~/.config/quickshell/lucid (with backup if pre-existing)
if [[ -d "$LUCID_SRC" ]]; then
  QS_LUCID="$TARGET_HOME/.config/quickshell/lucid"
  if [[ -d "$QS_LUCID" && "$DRY_RUN" -eq 0 ]]; then
    BKP="$TARGET_HOME/.local/share/scy-shell/backups/quickshell-lucid-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BKP"
    cp -a "$QS_LUCID" "$BKP/"
  fi
  run_cmd mkdir -p "$TARGET_HOME/.config/quickshell"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    rm -rf "$QS_LUCID"
    mkdir -p "$QS_LUCID"
    for item in "$LUCID_SRC"/*; do
      base="$(basename "$item")"
      if [[ "$base" == "wallpapers" ]]; then
        ln -snf "$item" "$QS_LUCID/wallpapers"
      else
        cp -a "$item" "$QS_LUCID/"
      fi
    done
  else
    echo "[DRY-RUN] Install Lucid+Studio QML tree -> $QS_LUCID"
  fi
fi

# 4. Run lossless standalone config migration + initial palette/portal/greeter sync
if [[ "$DRY_RUN" -eq 0 ]]; then
  PYTHONPATH="$SCY_ROOT/src" python3 - "$TARGET_HOME" <<'PY'
import sys
from pathlib import Path
from scy_core.config_store import ScyConfigStore
from scy_core.migrator import ScyConfigMigrator
from scy_core.theme_engine import ScyThemeCoordinator
from scy_core.desktop_canvas import ScyDesktopCoordinator
from scy_core.security_preauth import ScyPreAuthCoordinator

home = Path(sys.argv[1])
store = ScyConfigStore(home_dir=home)
mig = ScyConfigMigrator(store).migrate_existing_configs()
thm = ScyThemeCoordinator(store)
thm.write_mandara_portable_m3_look()
thm.apply_palette(seed_hex=str(store.doc["providers"]["lucid"]["prefs"].get("themeColour", "#7AA2F7")))
ScyDesktopCoordinator(store).write_portal_config()
ScyPreAuthCoordinator(store).stage_display_manager_configs()
print(f"[Scy-Shell] Migrated standalone keys: Lucid={mig['imported_lucid_keys']}, Mandara={mig['imported_mandara_keys']}")
PY
else
  echo "[DRY-RUN] Migrate existing ~/.config/lucid & ~/.config/mandara into ~/.config/scy-shell/config.toml"
fi

# 5. Optional safe Hyprland modular hook
if [[ "$WITH_HYPR" -eq 1 ]]; then
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$SCY_ROOT/bin/scy-shell" --home "$TARGET_HOME" hypr emit >/dev/null
    echo "[Scy-Shell] Emitted validated Hyprland modular config + 67 keybinds (backup saved)."
  else
    echo "[DRY-RUN] Emit modular Hyprland config under $TARGET_HOME/.config/hypr/scy-shell/"
  fi
fi

echo "[Scy-Shell] Installation finished cleanly."
