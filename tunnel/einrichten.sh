#!/bin/bash
# SPDX-License-Identifier: BSD-3-Clause
#
# Richtet die Tunnelschicht zu Freifunk EN ein. Laeuft auf der Karten-VM als
# root: sudo ./einrichten.sh
#
# Danach laufen acht Tunneldigger-Instanzen, jede in ihrer eigenen
# batman-Instanz bat-<code>. Adressen vergeben wir keine, Gateway spielen wir
# nicht. Der Sammler kommt in einem zweiten Schritt dazu.
set -euo pipefail

HIER=$(cd "$(dirname "$0")" && pwd)
TD_COMMIT=9a9a42741837115d99dd9c398a9a3976d81727d2   # 09.11.2025, Stand 20.09.2026
BAU=/usr/local/src/tunneldigger

[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

echo "== Pakete =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq batctl cmake pkg-config build-essential git \
	libnl-3-dev libnl-genl-3-dev libasyncns-dev

echo "== Tunneldigger-Client bauen ($TD_COMMIT) =="
if [ ! -d "$BAU/.git" ]; then
	git clone -q https://github.com/wlanslovenija/tunneldigger.git "$BAU"
fi
git -C "$BAU" fetch -q origin
git -C "$BAU" checkout -q "$TD_COMMIT"
cmake -S "$BAU/client" -B "$BAU/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$BAU/build" -j"$(nproc)" >/dev/null
install -m 0755 "$BAU/build/tunneldigger" /usr/local/bin/tunneldigger
/usr/local/bin/tunneldigger -h 2>&1 | head -1 || true

echo "== Module =="
cat > /etc/modules-load.d/karte-en.conf <<'MOD'
# Tunnelschicht zu Freifunk EN: L2TPv3 ueber Tunneldigger, dahinter batman-adv.
l2tp_eth
l2tp_netlink
batman-adv
MOD
modprobe l2tp_eth
modprobe l2tp_netlink
modprobe batman-adv
echo "batman-adv: $(cat /sys/module/batman_adv/version 2>/dev/null || echo unbekannt)"

echo "== Dateien =="
install -d -m 0755 /etc/karte-en
install -m 0644 "$HIER/domains.conf"    /etc/karte-en/domains.conf
install -m 0755 "$HIER/tunnel-hook.sh"  /usr/local/sbin/karte-en-hook
install -m 0755 "$HIER/tunnel-start.sh" /usr/local/sbin/karte-en-tunnel
install -m 0644 "$HIER/systemd/karte-en-tunnel@.service" /etc/systemd/system/
systemctl daemon-reload

echo "== Dienste =="
codes=$(awk '!/^#/ && NF { print $1 }' /etc/karte-en/domains.conf)
for c in $codes; do
	systemctl enable --now "karte-en-tunnel@$c.service"
done

sleep 10
echo
echo "== Stand =="
for c in $codes; do
	printf '%-7s %-10s %s\n' "$c" \
		"$(systemctl is-active "karte-en-tunnel@$c.service")" \
		"$(batctl meshif "bat-$c" interface 2>/dev/null | tr '\n' ' ')"
done
