#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
mkdir -p "$TOOLS_DIR" "$ROOT_DIR/public/static/css"

OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}:${ARCH}" in
  Darwin:arm64) TW_BIN="tailwindcss-macos-arm64" ;;
  Darwin:x86_64) TW_BIN="tailwindcss-macos-x64" ;;
  Linux:x86_64) TW_BIN="tailwindcss-linux-x64" ;;
  Linux:aarch64|Linux:arm64) TW_BIN="tailwindcss-linux-arm64" ;;
  *)
    echo "Unsupported platform: ${OS} ${ARCH}" >&2
    exit 1
    ;;
esac

TAILWIND_EXE="$TOOLS_DIR/tailwindcss"

if [ ! -x "$TAILWIND_EXE" ]; then
  echo "Downloading $TW_BIN..."
  curl -fsSL "https://github.com/tailwindlabs/tailwindcss/releases/latest/download/$TW_BIN" -o "$TAILWIND_EXE"
  chmod +x "$TAILWIND_EXE"
  if [ "$OS" = "Darwin" ]; then
    xattr -d com.apple.quarantine "$TAILWIND_EXE" >/dev/null 2>&1 || true
  fi
fi

if [ ! -f "$TOOLS_DIR/daisyui.mjs" ]; then
  echo "Downloading daisyui.mjs..."
  curl -fsSL "https://github.com/saadeghi/daisyui/releases/latest/download/daisyui.mjs" -o "$TOOLS_DIR/daisyui.mjs"
fi

if [ ! -f "$TOOLS_DIR/daisyui-theme.mjs" ]; then
  echo "Downloading daisyui-theme.mjs..."
  curl -fsSL "https://github.com/saadeghi/daisyui/releases/latest/download/daisyui-theme.mjs" -o "$TOOLS_DIR/daisyui-theme.mjs"
fi

"$TAILWIND_EXE" \
  -i "$ROOT_DIR/static_src/input.css" \
  -o "$ROOT_DIR/public/static/css/app.css" \
  --minify "$@"
