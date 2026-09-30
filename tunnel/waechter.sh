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

# Zweiter Fall: die Schnittstelle ist da, aber batman sieht darueber keinen
# Nachbarn. Am 30.09.2026 beobachtet: amalthea baute den Tunnel fuer Velbert
# um 06:33 ab und nahm ihn sofort wieder an ("Tunnel successfully
# established"), hing seine Seite aber nicht an die batman-Instanz. Senden
# lief weiter, empfangen kam nichts, und die ganze Domain stand stundenlang
# auf offline. Ein neuer Tunnel ist eine neue Sitzung beim Broker.
# Ausgenommen sind Domains aus ruhend.conf: dort ist ein leerer Tunnel
# erwartet (Freischaltung steht aus, Domain nicht belegt). Auch hier erst
# beim zweiten Fund in Folge, und hoechstens einmal je halbe Stunde, damit
# ein kaputter Broker nicht im Fuenf-Minuten-Takt angefragt wird.
RUHEND=/etc/karte-en/ruhend.conf
PAUSE=1800
leer_pruefen() {
	code=$1 dienst=$2
	if grep -q "^$code[[:space:]]" "$RUHEND" 2>/dev/null; then
		rm -f "$MERK/$code.leer"
		return
	fi
	nachbarn=$(batctl meshif "bat-$code" n -H 2>/dev/null | wc -l)
	if [ "${nachbarn:-0}" -gt 0 ]; then
		rm -f "$MERK/$code.leer"
		return
	fi
	if [ ! -f "$MERK/$code.leer" ]; then
		: > "$MERK/$code.leer"
		logger -t karte-en "Waechter: td-$code ohne batman-Nachbarn, beim naechsten Lauf wird neu gestartet"
		return
	fi
	jetzt=$(date +%s)
	zuletzt=$(cat "$MERK/$code.neustart" 2>/dev/null || echo 0)
	if [ $((jetzt - zuletzt)) -lt "$PAUSE" ]; then
		return
	fi
	logger -t karte-en "Waechter: td-$code weiterhin ohne batman-Nachbarn, $dienst wird neu gestartet"
	echo "$jetzt" > "$MERK/$code.neustart"
	rm -f "$MERK/$code.leer"
	systemctl restart "$dienst" || true
}
for code in $(awk '!/^#/ && NF { print $2 }' "$KONF"); do
	dienst="karte-en-tunnel@$code.service"
	[ "$(systemctl is-active "$dienst" 2>/dev/null)" = active ] || continue
	if [ -d "/sys/class/net/td-$code" ]; then
		rm -f "$MERK/$code"
		leer_pruefen "$code" "$dienst"
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
