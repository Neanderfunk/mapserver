# UniFi-Installationen und ihre Offloader

Stand 21.09.2026. Fuer unifi_respondd braucht es je Unifi-Site die MAC des
Freifunk-Knotens, hinter dem die Accesspoints haengen.

| Site | Freifunk-Domain | Offloader | MAC | Verwaltung |
| --- | --- | --- | --- | --- |
| `fflvr` | sieben LVR-Domains | 95 verschiedene | siehe Aufteilungsliste | in-band |
| ffdus-unterkunft-west | `24_dusukw` | GrafAdolf73-Offloader-2e5c | `00:9b:c8:f0:2e:5c` | out-of-band |
| Nef-Wlf (WIR-Haus) | `10_wlf` | WIR-Kelleroffl2-1367 | `80:af:ca:82:13:67` | out-of-band |

Die Sitenamen in der linken Spalte sind ungeprueft, sie stammen aus der
muendlichen Beschreibung; massgeblich ist, wie sie im Controller heissen.

## In-band oder out-of-band

Das entscheidet, ob wir die Zuordnung messen koennen.

**In-band** heisst: die Accesspoints beziehen ihre eigene Adresse aus dem
Freifunk-Netz, ihre MAC steht in der Uebersetzungstabelle von batman, und
`werkzeug/unifi-offloader.py` findet sie samt Offloader. So laeuft es beim
LVR, dort stehen hunderte Geraete in den Tabellen.

**Out-of-band** heisst: die Verwaltung liegt in einem eigenen VLAN, nur der
Verkehr der Freifunk-SSID wird ins Client-Netz gebrueckt. Im Mesh stehen dann
ausschliesslich die WLAN-Clients und kein einziger AP. So laeuft es in der
Graf-Adolf-Strasse und im WIR-Haus; dort ist die Offloader-MAC von Hand zu
ermitteln, am einfachsten ueber den Kartenlink des Knotens
(`map.eulenfunk.de/#!v:m;n:<node_id>`, die node_id ist die MAC ohne
Doppelpunkte).

**Out-of-band ist der Normalfall**, zwei von drei bekannten Installationen
arbeiten so. Die Messung aus den Tabellen ist die Ausnahme und lohnt vor
allem dort, wo viele Geraete auf viele Domains verteilt sind.

## Offene Punkte

- **Wuelfrath**: neben dem WIR-Knoten haengen drei Accesspoints hinter
  `UK-Rathaus-5-OG1` (`18:d6:c7:51:66:36`) und `UK-Maushaeuschen-2`
  (`18:d6:c7:51:66:5e`). Gehoeren die zur selben Site, zeichnet die Karte sie
  trotzdem am WIR-Keller, weil je Site nur eine MAC eingetragen wird.
- **Haan**: 30 Geraete mit Unifi-Herstellerpraefixen stehen dort in-band im
  Mesh, ohne dass eine zugehoerige Installation bekannt waere. Ungeklaert.
- **fflvr**: 615 Accesspoints in einer Site, Aufteilung in sieben noetig.
  Arbeitsliste in `unifi-fflvr-aufteilung.txt`, Anleitung fuer die dortige IT
  in `docs/howto-unifi-freifunk-lvr.md` der Router-Werkstatt.

## Betrieb von unifi_respondd

**Stand 24.09.2026: unifi_respondd läuft noch nicht.** Auf map6 gibt es weder
Installation noch Dienst. Vorbereitet sind die Zuordnung (dieses Dokument,
`werkzeug/unifi-offloader.py`), die Aufteilungsliste für den LVR und die
Anleitung für dessen IT. Solange die Site `fflvr` nicht aufgeteilt ist, lässt
sich der Block `offloader_mac` nicht sinnvoll füllen: unifi_respondd kennt je
Site genau einen Offloader und damit genau eine Domain.

### Controller und Zugang

- **Ein Controller für alle drei Sites:** `https://unifi.ffnef.de/`, betrieben
  von uns. `fflvr`, `ffdus-unterkunft-west` und `Nef-Wlf` liegen dort
  nebeneinander. Die Betreuenden beim LVR arbeiten in ihrer Site auf diesem
  Controller, nicht auf einem eigenen.
- **Erreichbarkeit:** öffentlich über IPv4 und IPv6, Port 443 und 8443 offen.
  Von map6 aus am 24.09.2026 geprüft. Es braucht also weder VPN noch eine
  Freigabe für eine bestimmte Adresse.
- **Konto:** ein Konto mit reinen Leserechten. Damit wurden am 21.09.2026 alle
  Sites, Geräte und Clients gelesen, daraus entstand
  `unifi-fflvr-aufteilung.txt`. unifi_respondd selbst liest nur Sites, Geräte
  und Clients und schreibt nichts, mehr Rechte braucht es also nicht.
- **Wo die Zugangsdaten liegen:** auf dem Arbeitsrechner unter
  `~/.config/neanderfunk/unifi-ffnef-login` (600), nicht auf map6 und nicht
  im Git. Beim Einrichten gehören sie in die Konfiguration von unifi_respondd
  auf map6, Datei 600, Eigentümer der Dienstbenutzer.

### Offene Einstellungen für die Inbetriebnahme

- **`ssid_regex`** ist noch nicht festgelegt. Es ist ein Pflichtfeld ohne
  Vorgabe im Code; `.*freifunk.*` steht nur in der Beispielkonfiguration.
  Geprüft wird ohne Beachtung von Groß- und Kleinschreibung. Ein AP, dessen
  SSID nicht passt, erscheint nicht auf der Karte. Vor dem Einrichten die
  tatsächlich ausgestrahlten SSIDs der drei Sites im Controller nachsehen.
- **`controller_port`** 443 für `unifi.ffnef.de`, nicht die 8443 aus dem
  Beispiel; beide sind offen, 443 ist der Weg, den auch der Browser nimmt.
- **`version`** passend zur Controller-Software setzen (`v5` im Beispiel,
  `UDMP-unifiOS` bei UniFi OS). Das entscheidet über die API-Pfade.
- **`nodelist`** auf unsere Karte:
  `https://neander.map.freifunk.space/data/meshviewer.json`. Daraus erbt jeder
  AP Domain und Gateway seines Offloaders.

### Koordinaten: Zahlen, kein Freitext

Steht im Feld SNMP Location ein Freitext statt eines Koordinatenpaars, schickt
unifi_respondd ihn an Nominatim, den Geocoder von OpenStreetMap. Das ist ein
fremder Dienst, und schlägt die Suche fehl, setzt er 0/0: der AP landet dann
auf "Null Island" im Golf von Guinea. Die Anleitung für die Betreuenden
verlangt deshalb Zahlen (`51.2506, 6.9746`).
