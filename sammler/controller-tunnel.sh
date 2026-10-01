#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# WireGuard-Tunnel zu einem UniFi-Controller, der von aussen nicht erreichbar
# ist (etwa eine UDM hinter NAT). Der Controller baut den Tunnel als
# VPN-Client auf, die Karten-VM fragt ihn darueber ab. Auf der Karten-VM als
# root:
#
#   sudo ./controller-tunnel.sh wg-udm 172.31.253.1/30 172.31.253.2 > client.conf
#
# Legt beim ersten Lauf beide Schluesselpaare an und schreibt die
# Client-Konfiguration auf stdout; die gehoert in den Controller (Settings ->
# VPN -> VPN Client -> WireGuard -> Upload File) und wird hier nicht
# gespeichert. Gibt es die Schnittstelle schon, bleibt sie, wie sie ist, und
# es kommt nichts auf stdout: fuer einen neuen Client-Schluessel erst
# /etc/wireguard/<schnittstelle>.conf entfernen.
#
# Im Controller zusaetzlich eine Firewall-Regel: von der Tunneladresse der
# Karten-VM auf TCP 443 der UDM selbst (alte Regeln: "Internet Local").
# Hintergrund: docs/unifi-sites.md ("Controller hinter NAT").
set -euo pipefail

SCHNITTSTELLE=${1:?Schnittstelle, etwa wg-udm}
HIER_ADRESSE=${2:?eigene Tunneladresse mit Netz, etwa 172.31.253.1/30}
DORT=${3:?Tunneladresse des Controllers, etwa 172.31.253.2}
PORT=${4:-51820}
# PPPoE (1492) minus WireGuard ueber IPv6 (80); die Antworten des Controllers
# sind gross, eine zu grosse MTU faellt erst bei der Client-Liste auf
MTU=${5:-1412}
KONF=/etc/wireguard/$SCHNITTSTELLE.conf

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
command -v wg >/dev/null || apt-get install -y -qq wireguard-tools >&2

if [ -e "$KONF" ]; then
	echo "$KONF gibt es schon, bleibt unveraendert" >&2
else
	umask 077
	install -d -m 0700 /etc/wireguard
	eigener=$(wg genkey)
	client=$(wg genkey)
	cat > "$KONF" <<-K
		# UniFi-Controller als WireGuard-Client; die Karten-VM fragt ihn ueber
		# den Tunnel ab. Angelegt von sammler/controller-tunnel.sh.
		[Interface]
		Address = $HIER_ADRESSE
		ListenPort = $PORT
		MTU = $MTU
		PrivateKey = $eigener

		[Peer]
		PublicKey = $(printf '%s' "$client" | wg pubkey)
		AllowedIPs = $DORT/32
	K
	# Oeffentliche IPv6 der VM als Endpunkt; die Karten-VM hat kein IPv4
	endpunkt=$(ip -6 route get 2001:4860:4860::8888 | grep -o 'src [0-9a-f:]*' | cut -d' ' -f2)
	cat <<-K
		[Interface]
		PrivateKey = $client
		Address = $DORT/${HIER_ADRESSE#*/}
		MTU = $MTU

		[Peer]
		PublicKey = $(printf '%s' "$eigener" | wg pubkey)
		Endpoint = [$endpunkt]:$PORT
		AllowedIPs = ${HIER_ADRESSE%/*}/32
		PersistentKeepalive = 25
	K
fi

systemctl enable -q --now "wg-quick@$SCHNITTSTELLE"
wg show "$SCHNITTSTELLE" latest-handshakes | awk -v n="$(date +%s)" \
	'{ print ($2 ? "letzter Handshake vor " n - $2 " s" : "noch kein Handshake") }' >&2
