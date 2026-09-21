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
