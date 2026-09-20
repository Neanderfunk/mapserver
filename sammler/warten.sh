#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Wartet, bis die batman-Instanzen einer Community da sind. Laeuft als
# ExecStartPre von yanic@<community>.
#
# yanic loest die Schnittstellennamen beim Start auf und beendet sich mit
# einem Panic, wenn eine fehlt (respond/collector.go: log.Panic). Nach einem
# Neustart der Maschine braucht der erste Tunnel ein paar Sekunden, yanic
# wuerde also erst einmal sterben. Statt darauf zu bauen, dass der
# Neustartzaehler das schon richtet, warten wir hier ab.
set -e
KONF=/etc/karte-en/domains.conf
GEDULD=${KARTE_EN_GEDULD:-180}

COMMUNITY=${1:?Community fehlt}
codes=$(awk -v g="$COMMUNITY" '!/^#/ && NF && $1 == g { print $2 }' "$KONF")
i=0
while [ "$i" -lt "$GEDULD" ]; do
	fehlen=''
	for c in $codes; do
		# Link-Local genuegt yanic, eine Adresse aus ihrem Praefix ist nicht noetig.
		ip -6 addr show dev "bat-$c" scope link 2>/dev/null | grep -q 'inet6 fe80' \
			|| fehlen="$fehlen $c"
	done
	if [ -z "$fehlen" ]; then
		[ "$i" -gt 0 ] && logger -t karte-en "yanic $COMMUNITY: alle bat-Instanzen nach $i s bereit"
		exit 0
	fi
	sleep 2
	i=$((i + 2))
done
logger -t karte-en "yanic $COMMUNITY startet trotz fehlender Instanzen:$fehlen"
exit 0
