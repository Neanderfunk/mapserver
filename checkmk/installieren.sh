#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Local checks auf einen Rechner spielen. Als root auf dem Zielrechner:
#   sudo ./installieren.sh [nur-dieser-check ...]
#
# Ohne Argumente kommt alles unter local/ mit. Das Verzeichnis hier bildet die
# Struktur des Agenten ab: local/<name> laeuft bei jedem Lauf, local/<sekunden>/<name>
# hoechstens in diesem Abstand.
set -euo pipefail
HIER=$(cd "$(dirname "$0")" && pwd)
ZIEL=${CHECKMK_LOCAL:-/usr/lib/check_mk_agent/local}

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[ -d "$ZIEL" ] || { echo "$ZIEL gibt es nicht, laeuft hier ein Checkmk-Agent?" >&2; exit 1; }

muster=("$@")
[ ${#muster[@]} -eq 0 ] && muster=('*')

cd "$HIER/local"
for f in $(find . -type f -perm -u+x | sed 's#^\./##' | sort); do
    name=$(basename "$f")
    treffer=0
    for m in "${muster[@]}"; do
        # shellcheck disable=SC2053
        [[ $name == $m ]] && treffer=1
    done
    [ "$treffer" = 1 ] || continue
    install -d -m 0755 "$ZIEL/$(dirname "$f")"
    install -m 0755 "$f" "$ZIEL/$f"
    echo "  $ZIEL/$f"
done

echo
echo "Probelauf:"
for f in $(find "$ZIEL" -type f -perm -u+x -name 'mapserver*' | sort); do
    echo "--- $f"
    "$f" | sed 's/^/    /'
done
