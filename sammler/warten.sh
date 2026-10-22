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

# Link-Local-Adresse (EUI-64) zu einer MAC, so geschrieben, wie ip sie zeigt.
# Gleiche Funktion in tunnel/tunnel-hook.sh.
linklocal() {
	set -- $(echo "$1" | tr ':' ' ')
	printf 'fe80::%x:%x:%x:%x' $(((0x$1 ^ 2) << 8 | 0x$2)) $((0x$3 << 8 | 0xff)) \
		$((0xfe00 | 0x$4)) $((0x$5 << 8 | 0x$6))
}

# Bereit ist eine bat-Instanz erst, wenn der Hook ihre feste MAC (02:45:4e:...)
# gesetzt hat und sie genau die Link-Local-Adresse dieser MAC traegt. yanic
# bindet sich an irgendeine Link-Local-Adresse der Schnittstelle; ist es eine
# fremde, die spaeter verschwindet, bleibt die Domain stumm (22.10.2026,
# bat-02_met). Fremde Adressen werden deshalb hier entfernt.
bereit() {
	bat="bat-$1"
	mac=$(cat "/sys/class/net/$bat/address" 2>/dev/null) || return 1
	case "$mac" in 02:45:4e:*) ;; *) return 1 ;; esac
	soll=$(linklocal "$mac")
	da=1
	for a in $(ip -6 addr show dev "$bat" scope link 2>/dev/null | awk '/inet6 fe80/ { sub("/.*", "", $2); print $2 }'); do
		if [ "$a" = "$soll" ]; then
			da=0
		else
			ip -6 addr del "$a/64" dev "$bat" 2>/dev/null || true
			logger -t karte-en "yanic $COMMUNITY: fremde Link-Local-Adresse $a von $bat entfernt (soll $soll)"
		fi
	done
	return $da
}

COMMUNITY=${1:?Community fehlt}
codes=$(awk -v g="$COMMUNITY" '!/^#/ && NF && $1 == g { print $2 }' "$KONF")
i=0
while [ "$i" -lt "$GEDULD" ]; do
	fehlen=''
	for c in $codes; do
		# Link-Local genuegt yanic, eine Adresse aus ihrem Praefix ist nicht noetig.
		bereit "$c" || fehlen="$fehlen $c"
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
