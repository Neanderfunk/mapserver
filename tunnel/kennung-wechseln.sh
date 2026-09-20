#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
#
# Neue Kennung fuer alle Domains: zaehlt die Serie in /etc/karte-en/kennung
# hoch und startet die Tunnel neu. Damit wechseln in einem Zug
#   - die MAC der L2TP-Schnittstelle (unsere Originator-Adresse im Mesh),
#   - die MAC der batman-Instanz,
#   - der Name, unter dem der Broker uns fuehrt.
#
# Gedacht als Probe, nicht als Gewohnheit: sie beantwortet die Frage, ob eine
# ausbleibende Antwort an unserer bisherigen Kennung haengt. Wer sie benutzt,
# um eine bewusste Sperre zu umgehen, missbraucht sie.
set -e
[ "$(id -u)" = 0 ] || { echo "Bitte als root starten." >&2; exit 1; }

DATEI=/etc/karte-en/kennung
alt=$(cat "$DATEI" 2>/dev/null || echo 0)
neu=$(( (alt + 1) % 256 ))
echo "$neu" > "$DATEI"
echo "Kennungsserie $alt -> $neu"

for c in $(awk '!/^#/ && NF { print $2 }' /etc/karte-en/domains.conf); do
	systemctl restart "karte-en-tunnel@$c"
done
sleep 20
for c in $(awk '!/^#/ && NF { print $2 }' /etc/karte-en/domains.conf); do
	printf '%-7s %s  %s\n' "$c" \
		"$(cat "/sys/class/net/td-$c/address" 2>/dev/null || echo '-')" \
		"$(batctl meshif "bat-$c" originators 2>/dev/null | grep -c '^ \*') Originatoren"
done
