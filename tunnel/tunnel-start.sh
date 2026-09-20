#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Startet den Tunneldigger-Client fuer eine Domain. Aufruf: tunnel-start.sh <code>
# Alle Werte kommen aus /etc/karte-en/domains.conf, damit es nur eine Quelle
# gibt und nicht acht generierte Unit-Dateien.
set -e

CODE="$1"
KONF=/etc/karte-en/domains.conf
zeile=$(awk -v c="$CODE" '$1 == c { print; exit }' "$KONF" 2>/dev/null || true)
if [ -z "$zeile" ]; then
	echo "unbekannte Domain '$CODE' in $KONF" >&2
	exit 1
fi
PORT=$(echo "$zeile" | awk '{ print $3 }')
ID=$(echo "$zeile" | awk '{ print $4 }')

# -u ist der Name, unter dem der Broker uns fuehrt. Wer bei EN ins Log oder in
# batctl o schaut, soll uns zuordnen koennen, statt zu raetseln. Die
# Kennungsserie haengt hinten dran, damit ein Wechsel der MACs auch am Broker
# sichtbar eine neue Kennung ist und nicht dieselbe mit anderer Adresse.
# -g nimmt den ersten erreichbaren Broker; broker2 steht schon drin, wird also
# automatisch genutzt, sobald dort wieder ein Tunneldigger antwortet
# (20.09.2026: nur broker1 antwortet).
SERIE=$(cat /etc/karte-en/kennung 2>/dev/null || echo 0)

exec /usr/local/bin/tunneldigger -f \
	-u "map-neanderfunk-$CODE-$SERIE" \
	-i "td-$CODE" \
	-t "$ID" \
	-b "broker1.ff-en.de:$PORT" \
	-b "broker2.ff-en.de:$PORT" \
	-s /usr/local/sbin/karte-en-hook \
	-g
