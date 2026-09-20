#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Wacht ueber die Tunnel: laeuft der Dienst, aber die L2TP-Schnittstelle ist
# weg, wird er neu gestartet.
#
# Am 20.09.2026 beobachtet: der Client meldete um 21:44 "Tunnel successfully
# established", die Schnittstelle td-ffen verschwand spaeter trotzdem, und der
# Prozess lief weiter, ohne es zu bemerken. Der Dienst stand also auf active,
# die Domain war aber aus der Karte verschwunden. Ein Neustart des Dienstes
# heilt das in Sekunden; nur merken muss es jemand.
#
# Bewusst geduldig: erst beim zweiten Fund in Folge wird neu gestartet, damit
# ein Neustart waehrend des normalen Auf- und Abbaus nichts kaputtmacht.
set -e
KONF=/etc/karte-en/domains.conf
MERK=/run/karte-en-waechter

mkdir -p "$MERK"
for code in $(awk '!/^#/ && NF { print $2 }' "$KONF"); do
	dienst="karte-en-tunnel@$code.service"
	[ "$(systemctl is-active "$dienst" 2>/dev/null)" = active ] || continue
	if [ -d "/sys/class/net/td-$code" ]; then
		rm -f "$MERK/$code"
		continue
	fi
	if [ -f "$MERK/$code" ]; then
		logger -t karte-en "Waechter: td-$code fehlt weiterhin, $dienst wird neu gestartet"
		systemctl restart "$dienst" || true
		rm -f "$MERK/$code"
	else
		: > "$MERK/$code"
		logger -t karte-en "Waechter: td-$code fehlt, beim naechsten Lauf wird neu gestartet"
	fi
done
