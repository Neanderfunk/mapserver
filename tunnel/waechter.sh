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

# Zweite Aufgabe: ein Sammler, der an einer verschwundenen Schnittstelle
# haengt. ss zeigt einen Socket, dessen Schnittstelle es nicht mehr gibt, mit
# ihrem blanken Index (%if100) statt mit Namen. Ein einziger solcher Socket
# heisst: eine Domain ist fuer diese yanic-Instanz stumm, bis sie neu startet
# (22.09.2026, zwoelf Stunden unbemerkt). Neustart kostet nichts, der Zustand
# liegt in /var/lib/yanic.
for dienst in $(systemctl list-units --no-legend --state=active 'yanic@*.service' | awk '{ print $1 }'); do
	pid=$(systemctl show -p MainPID --value "$dienst")
	[ "${pid:-0}" -gt 0 ] || continue
	tot=$(ss -uanp 2>/dev/null | grep "pid=$pid," | grep -c '%if[0-9]' || true)
	if [ "${tot:-0}" -gt 0 ]; then
		logger -t karte-en "Waechter: $dienst haengt an $tot verschwundenen Schnittstellen, Neustart"
		systemctl restart "$dienst" || true
	fi
done

# Dritte Aufgabe: mesh-announce (antwortet respondd fuer den Kartenserver
# selbst) tritt den Multicast-Gruppen nur beim Start bei und kennt nur die
# Domains aus seiner beim Start erzeugten Konfiguration. Ist eine Domain dazu
# gekommen oder fehlt einer batman-Instanz die Gruppe ff02::2:1001 (etwa nach
# ihrer Neuanlage), Neustart.
if systemctl is-active -q mesh-announce.service 2>/dev/null; then
	grund=''
	if ! /usr/local/sbin/karte-mesh-announce-conf 2>/dev/null | cmp -s - /etc/mesh-announce/respondd.conf; then
		grund='Domains geaendert'
	else
		for bat in $(awk -F': ' '/^BatmanInterface/ { print $2 }' /etc/mesh-announce/respondd.conf); do
			grep -q " $bat \+ff020000000000000000000000021001 " /proc/net/igmp6 || grund="$bat ohne Multicast-Gruppe"
		done
	fi
	if [ -n "$grund" ]; then
		logger -t karte-en "Waechter: mesh-announce, $grund, Neustart"
		systemctl restart mesh-announce.service || true
	fi
fi
