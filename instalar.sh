#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}"
DESTINATION="${RESTAURADOR_DESTINO:-$DATA_ROOT/restaurador-fotografico}"
DESKTOP_DIR="${RESTAURADOR_ACCESOS:-$DATA_ROOT/applications}"
if [[ ! -x "$SOURCE_DIR/runtime/bin/python3.14" ]]; then
    echo "El paquete está incompleto: falta runtime/bin/python3.14." >&2
    exit 1
fi
"$SOURCE_DIR/abrir.sh" --verificar
if [[ "$DESTINATION" != "$SOURCE_DIR" ]]; then
    mkdir -p -- "$DESTINATION"
    # Copia reversible sin eliminar otros archivos del destino.
    cp -a -- "$SOURCE_DIR/." "$DESTINATION/"
fi
mkdir -p -- "$DESKTOP_DIR"
"$SOURCE_DIR/runtime/bin/python3.14" -I - "$DESTINATION" "$DESKTOP_DIR" <<'PY'
from pathlib import Path
import sys
destination, desktop = map(Path, sys.argv[1:])
def escape(text):
    # Escapes exigidos por Desktop Entry; no invocar un shell en Exec.
    return str(text).replace('\\', '\\\\\\\\').replace('"', '\\\\"').replace('`', '\\\\`').replace('$', '\\\\$')
launcher = desktop / 'restaurador-fotografico.desktop'
launcher.write_text('[Desktop Entry]\nType=Application\n'
    'Name=Restaurador Fotográfico\nComment=Mejora fotografías localmente\n'
    f'Exec="{escape(destination / "abrir.sh")}" %f\n'
    f'Icon={destination / "icon.png"}\n'
    'Terminal=false\nCategories=Graphics;Photography;\n'
    'MimeType=image/jpeg;image/png;image/tiff;image/webp;\n', encoding='utf-8')
print(f'Acceso creado: {launcher}')
PY
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" || true
fi
echo "Instalado en: $DESTINATION"
echo "Abre Restaurador Fotográfico desde el menú de aplicaciones."
