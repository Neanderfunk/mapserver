#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Startet den Tunneldigger-Client fuer eine Domain. Aufruf: tunnel-start.sh <code>
# Alle Werte kommen aus /etc/karte-en/domains.conf, damit es nur eine Quelle
# gibt und nicht acht generierte Unit-Dateien.
set -e

CODE="$1"
KONF=/etc/karte-en/domains.conf
zeile=$(awk -v c="$CODE" '$2 == c { print; exit }' "$KONF" 2>/dev/null || true)
if [ -z "$zeile" ]; then
	echo "unbekannte Domain '$CODE' in $KONF" >&2
	exit 1
fi
PORT=$(echo "$zeile" | awk '{ print $4 }')
ID=$(echo "$zeile" | awk '{ print $5 }')
BROKER=$(echo "$zeile" | awk '{ print $8 }' | tr ',' ' ')

# fastd statt Tunneldigger, wenn die Domain in fastd.conf steht (Freifunk
# Essen, 25.09.2026). Schnittstelle, Hook und batman-Instanz bleiben dieselben.
FASTD=/etc/karte-en/fastd.conf
fzeile=$(awk -v c="$CODE" '!/^#/ && $1 == c { print; exit }' "$FASTD" 2>/dev/null || true)
if [ -n "$fzeile" ]; then
	COMMUNITY=$(echo "$zeile" | awk '{ print $1 }')
	MTU=$(echo "$zeile" | awk '{ print $7 }')
	GEHEIM="/etc/karte-en/fastd/$COMMUNITY.secret"
	[ -r "$GEHEIM" ] || { echo "kein Schluessel $GEHEIM (tunnel/einrichten.sh)" >&2; exit 1; }
	# RuntimeDirectory der Unit; ProtectSystem=strict laesst sonst nichts zu.
	KONF_F="${RUNTIME_DIRECTORY:-/run/karte-en-tunnel-$CODE}/fastd.conf"
	{
		echo "log level info;"
		echo "interface \"td-$CODE\";"
		echo "mode tap;"
		for m in $(echo "$fzeile" | awk '{ print $2 }' | tr ',' ' '); do
			echo "method \"$m\";"
		done
		echo "secure handshakes yes;"
		echo "mtu $MTU;"
		echo "bind any;"
		echo "include \"$GEHEIM\";"
		echo "on up sync \"/usr/local/sbin/karte-en-hook session.up td-$CODE\";"
		echo "on down sync \"/usr/local/sbin/karte-en-hook session.down td-$CODE\";"
		echo "peer group \"backbone\" {"
		echo "	peer limit 1;"
		for p in $(echo "$fzeile" | awk '{ for (i = 3; i <= NF; i++) print $i }'); do
			name=${p%%=*}; rest=${p#*=}; host=${rest%%=*}; key=${rest#*=}
			echo "	peer \"$name\" { key \"$key\"; remote \"$host\" port $PORT; }"
		done
		echo "}"
	} > "$KONF_F"
	exec /usr/sbin/fastd --config "$KONF_F"
fi

# Je Broker ein -b. Der Client nimmt mit -g den ersten erreichbaren.
set --
for b in $BROKER; do set -- "$@" -b "$b:$PORT"; done

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
	"$@" \
	-s /usr/local/sbin/karte-en-hook \
	-g
