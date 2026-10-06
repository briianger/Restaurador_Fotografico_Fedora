#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONHOME="$APP_DIR/runtime"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
export LD_LIBRARY_PATH="$APP_DIR/runtime/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$APP_DIR/runtime/lib64/python3.14/site-packages/PySide6/Qt/plugins"
# Evita depender de plugins de temas Qt del sistema.
unset QT_QPA_PLATFORM_PLUGIN_PATH
unset QT_QPA_PLATFORMTHEME
if [[ "${1:-}" == "--verificar" ]]; then
    export QT_QPA_PLATFORM=offscreen
    exec "$APP_DIR/runtime/bin/python3.14" -s "$APP_DIR/app/selftest.py"
fi
exec "$APP_DIR/runtime/bin/python3.14" -s "$APP_DIR/app/main.py" "$@"
