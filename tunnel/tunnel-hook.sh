#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Hook des Tunneldigger-Clients. Aufruf durch l2tp_client:
#   tunnel-hook.sh session.up|session.down <iface>
# Der Schnittstellenname traegt die Domain: td-ffwit -> Domain ffwit.
#
# Wir sind in fremden Netzen ein Knoten, der nur fragt. Deshalb:
#   - keine Bridge, kein DHCP, keine Clients,
#   - forwarding aus und gw_mode off, sonst zoegen wir Verkehr auf uns,
#     den wir gar nicht bedienen wollen,
#   - aus ihren Router Advertisements nehmen wir das Praefix, aber keine
#     Router: kein Standardweg, keine Route-Information-Optionen, keine
#     Router-Praeferenz. Sonst koennte eigener Verkehr dieser VM, im
#     schlimmsten Fall die Tunnel selbst, in ihr Netz hinauslaufen
#     (adorfer 20.09.2026).
set -e

HOOK="$1"
IF="$2"
KONF=/etc/karte-en/domains.conf
CODE="${IF#td-}"
BAT="bat-$CODE"

zeile=$(awk -v c="$CODE" '$2 == c { print; exit }' "$KONF" 2>/dev/null || true)
if [ -z "$zeile" ]; then
	logger -t karte-en "Hook $HOOK fuer unbekannte Domain '$CODE' ($IF)"
	exit 1
fi
ID=$(echo "$zeile" | awk '{ print $5 }')
MTU=$(echo "$zeile" | awk '{ print $7 }')

# Feste, lokal verwaltete MACs: 02 = locally administered, 45:4e = "EN" in
# ASCII. Die MAC der L2TP-Schnittstelle ist unsere Originator-Adresse in ihrem
# batman, die soll ueber Neustarts gleich bleiben und erkennbar keine
# Hersteller-MAC sein.
#
# Das vierte Byte ist die Kennungsserie aus /etc/karte-en/kennung. Sie wird
# nur dann hochgezaehlt, wenn wir eine neue Identitaet im fremden Netz
# brauchen, etwa um zu pruefen, ob eine Sperre oder ein Limit an unserer
# bisherigen Kennung haengt (kennung-wechseln.sh). Mit ihr wechseln beide
# MACs und der Name am Broker gemeinsam, sonst waere die Probe nichts wert.
SERIE=$(cat /etc/karte-en/kennung 2>/dev/null || echo 0)
MAC_IF=$(printf '02:45:4e:%02x:00:%02x' "$SERIE" "$ID")
MAC_BAT=$(printf '02:45:4e:%02x:01:%02x' "$SERIE" "$ID")

setze() {
	[ -e "/proc/sys/$1" ] && printf '%s' "$2" > "/proc/sys/$1" || true
}

case "$HOOK" in
session.up)
	ip link set dev "$IF" down
	ip link set dev "$IF" address "$MAC_IF"
	# MTU aus ihrer site.json (mesh_vpn.<art>.mtu), je Community anders.
	ip link set dev "$IF" mtu "${MTU:-1420}"
	setze "net/ipv6/conf/$IF/accept_ra" 0
	setze "net/ipv6/conf/$IF/autoconf" 0
	setze "net/ipv6/conf/$IF/forwarding" 0
	ip link set dev "$IF" up

	# Muss vor dem Anlegen der ersten Mesh-Schnittstelle stehen; EN faehrt
	# BATMAN_IV (mesh.batman_adv.routing_algo in ihrer site.json).
	batctl routing_algo BATMAN_IV 2>/dev/null || true
	batctl meshif "$BAT" interface add "$IF"
	batctl meshif "$BAT" gw_mode off

	# Die MAC nur setzen, wenn sie nicht schon stimmt: die bat-Instanz
	# ueberlebt inzwischen den Abbau des Tunnels (siehe session.down), und ein
	# unnoetiges down/up wirft ihre Adressen kurz weg.
	if [ "$(cat "/sys/class/net/$BAT/address" 2>/dev/null)" != "$MAC_BAT" ]; then
		ip link set dev "$BAT" down 2>/dev/null || true
		ip link set dev "$BAT" address "$MAC_BAT"
	fi
	# Praefix ja, Router nein. Reihenfolge zaehlt: erst die Verbote, dann
	# accept_ra einschalten, sonst verarbeiten wir das erste RA noch mit
	# den Vorgabewerten.
	setze "net/ipv6/conf/$BAT/forwarding" 0
	setze "net/ipv6/conf/$BAT/accept_ra_defrtr" 0
	setze "net/ipv6/conf/$BAT/accept_ra_rt_info_max_plen" 0
	setze "net/ipv6/conf/$BAT/accept_ra_rtr_pref" 0
	setze "net/ipv6/conf/$BAT/accept_ra_mtu" 0
	setze "net/ipv6/conf/$BAT/use_tempaddr" 0
	setze "net/ipv6/conf/$BAT/accept_ra_pinfo" 1
	setze "net/ipv6/conf/$BAT/autoconf" 1
	setze "net/ipv6/conf/$BAT/accept_ra" 1
	ip link set dev "$BAT" up
	logger -t karte-en "$CODE: $IF an $BAT, Originator $MAC_IF"
	;;
session.down)
	# Nur die L2TP-Schnittstelle loesen, die bat-Instanz bleibt stehen.
	# yanic bindet je Domain einen Socket an die bat-Instanz, und zwar an
	# ihren ifindex. Wird sie geloescht und beim naechsten session.up neu
	# angelegt, hat sie einen neuen Index, und yanic hoert in dieser Domain
	# nie wieder etwas, ohne sich zu beschweren. So geschehen am 22.09.2026
	# um 06:27: elara schickte allen Tunneln einen Teardown, der Client
	# verband sich binnen Sekunden neu, und fuenfzehn Domains blieben zwoelf
	# Stunden lang stumm, obwohl Tunnel und Mesh einwandfrei liefen.
	batctl meshif "$BAT" interface del "$IF" 2>/dev/null || true
	logger -t karte-en "$CODE: $IF abgebaut, $BAT bleibt"
	;;
esac
