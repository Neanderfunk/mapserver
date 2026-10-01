#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# WireGuard-Tunnel zu UniFi-Controllern, die von aussen nicht erreichbar sind
# (UDM hinter NAT, Cloud Key hinter einem OpenWrt). Die Gegenstelle baut den
# Tunnel als Client auf, die Karten-VM fragt den Controller darueber ab. Alle
# haengen als Peers an einer Schnittstelle wg-ctl, Port 51820: nur dieser
# Port muss erreichbar sein (IPv6 direkt, IPv4 per DNAT auf twin2).
#
# Auf der Karten-VM als root, je Controller einmal:
#
#   sudo ./controller-tunnel.sh NAME TUNNELADRESSE [ZIEL ...] > client.conf
#
#   NAME           Name des Controllers, steht als Kommentar am Peer und in
#                  Checkmk (mapserver-tunnel-NAME)
#   TUNNELADRESSE  Adresse der Gegenstelle im Tunnel, 172.31.253.2 bis .254
#   ZIEL           weitere Adressen hinter der Gegenstelle, die die VM
#                  erreichen soll, etwa der Cloud Key im LAN eines OpenWrt;
#                  bei einer UDM keine, sie hat die Tunneladresse selbst
#
# Schreibt die Client-Konfiguration (wg-quick-Format) auf stdout; sie wird
# hier nicht gespeichert. Gibt es den Peer schon, kommt nichts auf stdout:
# fuer einen neuen Schluessel erst seinen Block aus /etc/wireguard/wg-ctl.conf
# entfernen. Hintergrund: docs/unifi-sites.md ("Controller hinter NAT").
set -euo pipefail

NAME=${1:?Name des Controllers, etwa WIR-Haus}
DORT=${2:?Tunneladresse der Gegenstelle, etwa 172.31.253.2}
shift 2
ZIELE=("$@")

SCHNITTSTELLE=wg-ctl
HIER=172.31.253.1
NETZ=24
PORT=51820
# PPPoE (1492) minus WireGuard ueber IPv6 (80); die Antworten des Controllers
# sind gross, eine zu grosse MTU faellt erst bei der Client-Liste auf
MTU=1412
KONF=/etc/wireguard/$SCHNITTSTELLE.conf
# IPv4 hat die VM nur hinter twin2, dort leitet DNAT UDP 51820 hierher
IPV4_ENDPUNKT=137.74.94.20

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }
[[ $NAME =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Name nur aus Buchstaben, Ziffern, - und _" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
command -v wg >/dev/null || apt-get install -y -qq wireguard-tools >&2
umask 077
install -d -m 0700 /etc/wireguard

if [ ! -e "$KONF" ]; then
	cat > "$KONF" <<-K
		# UniFi-Controller als WireGuard-Clients, je Controller ein Peer.
		# Angelegt von sammler/controller-tunnel.sh.
		[Interface]
		Address = $HIER/$NETZ
		ListenPort = $PORT
		MTU = $MTU
		PrivateKey = $(wg genkey)
	K
fi

if grep -q "^# Controller: $NAME\$" "$KONF"; then
	echo "Peer $NAME gibt es schon, bleibt unveraendert" >&2
else
	client=$(wg genkey)
	erlaubt=$DORT/32
	for z in "${ZIELE[@]}"; do erlaubt="$erlaubt, ${z%/*}/32"; done
	cat >> "$KONF" <<-K

		# Controller: $NAME
		[Peer]
		PublicKey = $(printf '%s' "$client" | wg pubkey)
		AllowedIPs = $erlaubt
	K
	eigener=$(sed -n 's/^PrivateKey = //p' "$KONF" | head -1 | wg pubkey)
	endpunkt6=$(ip -6 route get 2001:4860:4860::8888 | grep -o 'src [0-9a-f:]*' | cut -d' ' -f2)
	cat <<-K
		# $NAME -> Karten-VM. Endpoint ueber IPv6; ohne IPv6 am Standort
		# stattdessen Endpoint = $IPV4_ENDPUNKT:$PORT
		[Interface]
		PrivateKey = $client
		Address = $DORT/32
		MTU = $MTU

		[Peer]
		PublicKey = $eigener
		Endpoint = [$endpunkt6]:$PORT
		AllowedIPs = $HIER/32
		PersistentKeepalive = 25
	K
fi

systemctl enable -q "wg-quick@$SCHNITTSTELLE"
# Neu starten statt syncconf: wg-quick legt die Routen zu den ZIELEN nur beim
# Start an. Die anderen Peers verlieren dabei einige Sekunden.
systemctl restart "wg-quick@$SCHNITTSTELLE"
wg show "$SCHNITTSTELLE" latest-handshakes >&2
