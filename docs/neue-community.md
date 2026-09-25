# Eine neue Community aufnehmen

Der Weg von "die haben keine Karte" bis zur laufenden Karte. Er beginnt nicht
bei uns, sondern bei ihren Firmware-Images: dort steht alles, was wir zum
Mitmessen brauchen.

## Warum die Images

Eine Community ohne Karte hat oft auch keinen brauchbaren Verzeichniseintrag,
keine offene Dokumentation und niemanden, der Zeit hat zu antworten. Ihre
Images aber liegen im Netz, weil ihre Knoten sie zum Aktualisieren brauchen.
Gluon legt die `site.json` unbehandelt ins squashfs. Ein einziges kleines
Image je Domain genuegt, um Domainname, Praefixe, VPN-Art, Brokeradressen und
Port zu lesen. Nichts davon muss geraten werden.

Was wir dabei **nicht** tun: aus einem Git-Repository auf Zugehoerigkeit
schliessen, oder von jemandem Quelltext verlangen. Ein `site.conf` in einem
Repo belegt nicht, dass ein Netz so laeuft; das Image belegt es.

## Schritt 1: site.json lesen

```bash
werkzeug/site-lesen.py https://images.example.net/ \
    --kuerzel xy --name "Freifunk Beispiel" > community-xy.json
```

Das Werkzeug geht den Imageserver durch, erkennt schlichte Verzeichnisse
ebenso wie Dateibrowser mit `?dir=`, nimmt je Domainordner das kleinste
sysupgrade-Image, schneidet die `site.json` heraus und faellt bei mehreren
Firmwarestaenden auf den neuesten zurueck, der tatsaechlich Images enthaelt.

Wenn die Erkennung scheitert, weil der Server ungewoehnlich gebaut ist, kann
man die Image-URLs auch zeilenweise auf der Standardeingabe uebergeben:

```bash
printf '%s\n' https://…/a.bin https://…/b.bin | werkzeug/site-lesen.py --kuerzel xy
```

Voraussetzung ist `unsquashfs` (Paket `squashfs-tools`).

## Das Uebergabeformat

`community-<kuerzel>.json` ist bewusst schlicht und soll auch dann lesbar
sein, wenn zwischen Erhebung und Aufbau Wochen liegen oder jemand anders
weitermacht. Ein Kopf, darunter eine Liste von Domains:

```json
{
 "community": "en",
 "name": "Freifunk im Ennepe-Ruhr-Kreis",
 "quelle": "https://images.freifunk-en.de/",
 "domains": [
  {
   "code": "ffha",
   "name": "Freifunk Hagen",
   "ordner": "images_hagen",
   "port": 10161,
   "prefix6": "2a11:6c6:7000:feed::/64",
   "prefix4": "10.61.0.0/16",
   "next_node": ["nn-ha.ff-en.de"],
   "domain_seed": "ed485e6e…",
   "routing_algo": "BATMAN_IV",
   "mtu": 1420,
   "vpn": "tunneldigger",
   "broker": ["broker1.ff-en.de", "broker2.ff-en.de"],
   "ntp": ["2a11:6c6:7000:feed:ff::1", "…"],
   "ssid": "Freifunk",
   "autoupdater": ["beta", "stable"],
   "spiegel": ["http://firmware.ff-en.de/hagen/stable/sysupgrade"],
   "weitere_domains": [],
   "image": "https://…/gluon-ffha-4.2-…-sysupgrade.bin"
  }
 ]
}
```

Bedeutung der weniger offensichtlichen Felder:

| Feld | wofuer |
| --- | --- |
| `code` | `site_code`, wird Instanzname, Interface-Suffix und yanic-Filter |
| `port` | Tunneldigger-Port dieser Domain, je Domain verschieden |
| `mtu` | aus ihrer site.json, wird im Hook gesetzt |
| `routing_algo` | muss zu unserem batman passen, sonst sieht man nichts |
| `weitere_domains` | Multidomain-Firmware: dann ist ein Image mehrere Domains |
| `ntp` | zeigt auf ihre Gateways, gute Probe fuer "laeuft die Domain noch" |
| `spiegel` | Autoupdater-Spiegel, zeigt ob ihre Infrastruktur lebt |
| `domain_seed` | nur zur Wiedererkennung, wir brauchen ihn nicht |

Das Format haelt auch fest, was wir **nicht** koennen: steht bei `vpn` etwas
anderes als `tunneldigger`, warnt der naechste Schritt. fastd kann die
Tunnelschicht seit 25.09.2026 (`tunnel/fastd.conf`, siehe betrieb.md); viele
Communities verlangen dabei eine Freischaltung des Schluessels, das
Mitmessen geht dann nicht einseitig. WireGuard fehlt noch.

## Schritt 2: erreichbar?

Bevor irgendetwas gebaut wird, pruefen, ob die Broker ueberhaupt antworten:

```bash
werkzeug/broker-probe.py --broker broker1.example.net:10161
```

Der Rahmen ist ein COOKIE-Kontrollpaket, zustandslos, der Broker legt nichts
an. Antwortet kein einziger Broker, ist an dieser Stelle Schluss, und das ist
eine wichtige Information ueber die Community, keine Niederlage.

Bei Freifunk EN sah das so aus: `broker1` antwortet auf allen acht Ports,
`broker2` pingt zwar, hat aber auf keinem der acht Ports einen Dienst. Aus
"zwei Peers je Domain" wurden dadurch acht Tunnel statt sechzehn.

## Schritt 3: Domaintabelle

```bash
werkzeug/domains-erzeugen.py community-xy.json > tunnel/domains.conf
```

Zwei Dinge danach von Hand durchsehen:

- **Hostnamen.** Der Vorschlag kommt aus dem Ordnernamen. Diese Namen stehen
  spaeter in oeffentlichen Adressen, also lesbar und ohne Umlaute.
- **IDs.** Fortlaufend vergeben. Sie stecken in den Tunnel-IDs und in den
  beiden MACs je Domain und duerfen sich danach nicht mehr aendern, sonst
  wechselt unsere Originator-Adresse in ihrem Mesh.

Die im Betrieb stehende Tabelle behaelt ihre urspruengliche Reihenfolge, auch
wenn eine Neuerzeugung anders sortieren wuerde.

## Schritt 4: aufbauen

Weiter in [einrichtung.md](einrichtung.md). Die drei Skripte in der Reihenfolge
Tunnel, Collector, Web.

## Schritt 5: gegenpruefen

```bash
# sehen wir ihr Mesh?
batctl meshif bat-<code> originators | head

# antwortet respondd?
werkzeug/respondd-probe.py bat-<code>
```

Erst wenn beides sitzt, lohnt der Blick auf die Karte. Wenn Originatoren da
sind, respondd aber schweigt, liegt es fast immer an der Abfrageadresse:
Stock-Gluon bedient `ff05::2:1001` auf `br-client` und `ff02::2:1001` auf den
Mesh-Schnittstellen. Unsere eigene Flotte kennt zusaetzlich `ff02::1`, weil
wir dort einen Patch fahren; fremde Netze haben den nicht, und yanic fragt
von sich aus die richtige Adresse.

## Schritt 6: in die Auswertung

Die Knoten koennen in die Gebietsberechnung des Community-Finders einfliessen,
ohne dass die Karte oeffentlich verlinkt wird. In `initiativen.yaml` der
Survey gehoert die Datenquelle dann unter `daten:` und nicht unter
`quellen.karte`, und in `finder.py` gehoert der Host in die Liste
`EIGENBETRIEB`. Warum das getrennt sein muss, steht in
[hintergrund.md](hintergrund.md).
