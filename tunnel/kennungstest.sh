#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Einmalige Probe nach einer Pause: antworten die Knoten wieder?
#
# Am 20.09.2026 hoerten ab 21:02 alle acht Domains auf, uns zu antworten,
# waehrend die batman-Ebene einwandfrei blieb (Originatoren, Gateways,
# Uebersetzungstabellen, batctl ping zu Knoten). Zwei Erklaerungen blieben
# uebrig: ein Limit auf ihrer Seite, das an unserer Kennung haengt, oder
# etwas anderes. Dieses Skript trennt beides, ohne dass jemand um Mitternacht
# davorsitzen muss:
#
#   1. still sein, dann einmal fragen
#   2. kommt nichts, die Kennung wechseln und noch einmal fragen
#   3. kommen dann Antworten, hing es an der alten Kennung
#
# Kommen in Schritt 1 schon Antworten, war es ein Limit, das abgelaufen ist,
# und die Kennung bleibt, wie sie ist.
set -e
LOG=${1:-/var/log/karte-en-kennungstest.log}
PROBE=/usr/local/sbin/karte-en-respondd-probe
DOMAINS="bat-ffha bat-ffwit bat-ffhat"

sage() { echo "$(date '+%F %T') $*" >> "$LOG"; logger -t karte-en "$*"; }

antworten() {
	python3 "$PROBE" $DOMAINS 2>/dev/null | awk '{ s += $2 } END { print s + 0 }'
}

sage "Probe nach Funkstille beginnt"
a=$(antworten)
sage "ohne Wechsel: $a Antworten in drei Domains"

if [ "${a:-0}" -gt 0 ]; then
	sage "Es lag an der Zeit, nicht an der Kennung. yanic wird gestartet."
	systemctl start yanic
	exit 0
fi

sage "keine Antwort, Kennung wird gewechselt"
/usr/local/sbin/karte-en-kennung-wechseln >> "$LOG" 2>&1 || true
sleep 30
b=$(antworten)
sage "nach Kennungswechsel: $b Antworten in drei Domains"

if [ "${b:-0}" -gt 0 ]; then
	sage "Es hing an unserer bisherigen Kennung. yanic wird gestartet."
	systemctl start yanic
else
	sage "Auch mit neuer Kennung keine Antwort. yanic bleibt aus."
fi
