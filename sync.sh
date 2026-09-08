#!/usr/bin/env bash
#
# sync.sh — wrapper para correr la sincronización ABSS -> Google Calendar desde cron.
#
# El logging lo hace el crontab, no este script:
#
#   0 * * * * /home/hsalinas/code/abss-calendar/sync.sh >> /home/hsalinas/code/abss-calendar/sync.log 2>&1
#
# Este script solo resuelve lo que cron no da: el directorio del repo y el PATH de uv.

set -euo pipefail

# Raíz del repo = carpeta donde vive este script (para no depender de un cd en el crontab).
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

# cron trae un PATH mínimo y no carga tu shell rc, así que uv puede no estar en el PATH.
for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    [[ -x "$dir/uv" ]] && PATH="$dir:$PATH"
done

exec uv run src/main.py "$@"
