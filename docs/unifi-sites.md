# UniFi-Installationen und ihre Offloader

Öffentliche Anleitung für die Betreuenden eines Controllers (Koordinaten
eintragen, Sites je Domain aufteilen):
[freifunk-docs: UniFi-Accesspoints auf die Freifunk-Karte](https://github.com/Neanderfunk/freifunk-docs/blob/main/unifi-accesspoints-freifunk-karte.md).
Ändert sich beim Einrichten etwas, das die Betreuenden betrifft, etwa Port,
Zugang oder SSID-Muster, muss sie nachgezogen werden; die Content-Session
pflegt sie.

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
- **fflvr**: 615 Accesspoints in einer Site. Die Aufteilung in sieben ist
  seit 24.09.2026 **nicht mehr vorgesehen**, siehe "Entscheidung" weiter unten.
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

### Gegenprobe vom 24.09.2026

Auf Nachfrage adorfers, der von einem laufenden Dienst ausging, am System
belegt:

- **Nirgends eine Installation.** map6: keine systemd-Unit (auch keine
  inaktive), kein Prozess, kein Container, kein Cronjob, kein Python-Paket.
  Dasselbe auf der Finder-VM. Weitere Rechner sind von hier nicht erreichbar,
  aber:
- **Auf keiner Karte steht ein UniFi-AP.** Unsere Karte führt 105
  Ubiquiti-Geräte, die alte Karte (alle 49 Domainquellen) 121, und jedes davon
  läuft mit Gluon. Ein AP aus unifi_respondd würde dort mit UniFi-Firmware
  stehen. Es gibt also auch anderswo keinen Dienst, der eine der Karten
  beliefert.

Beim Blick in den Controller (lesend, eigenes Konto):

| | |
| --- | --- |
| Controller-Version | 10.2.105 |
| Sites, die unser Lesekonto sieht | nur `fflvr` |
| APs in `fflvr` | 615, davon 547 online |
| davon mit Koordinaten in SNMP Location | **0** |
| ausgestrahlte SSIDs | `Freifunk`, `FreifunkStreaming` |

### Was fehlt, damit er läuft

1. **Zugang zu den beiden kleinen Sites.** Unser Lesekonto sieht sie nicht.
2. **LVR ausklammern oder aufteilen.** unifi_respondd kennt keine Auswahl von
   Sites, er verarbeitet jede, die das Konto sieht. Eine Site ohne
   eingetragenen Offloader fällt nicht heraus: ihre APs erscheinen mit der
   Ersatzdomain `fallback_domain` (Vorgabe `unifi_respondd_fallback`), ohne
   Gateway und ohne Verbindung zu einem Freifunk-Router. Die beiden kleinen Sites lassen sich deshalb vor
   der LVR-Aufteilung anbinden, wenn entweder ein eigenes Lesekonto nur sie
   sieht, oder ein kleiner lokaler Patch Sites ohne Offloader überspringt.
3. **Koordinaten.** Ohne sie stehen die APs nur in der Liste, nicht auf der
   Karte. Beim LVR fehlen sie noch vollständig; die kleinen Sites sind von
   hier nicht einsehbar.
4. **Einrichtung auf map6:** Installation, Konfiguration, und der Weg der
   Antworten zu `yanic@neander`. Letzteres ist noch zu entwerfen:
   unifi_respondd antwortet per Multicast auf einer Schnittstelle oder schickt
   per Unicast an einen festen Empfänger, und unser yanic hört bisher nur auf
   den bat-Schnittstellen.

### Entscheidung 24.09.2026: nicht aufteilen, Router je AP messen

Beim LVR hängen 511 UniFi-Geräte hinter 103 Freifunk-Routern (gemessen aus
der Übersetzungstabelle; 35 % der Router haben 1-3 Geräte, 80 % höchstens
6). Eine Site je Router wären rund 100 Sites, jede Umsteckung müsste im
Controller nachgezogen werden. adorfer: "das händisch zu pflegen wird...
ARBEIT".

Deshalb **keine Aufteilung**. Bei in-band verwalteten APs steht die AP-MAC in
der batman-Übersetzungstabelle, und die sagt, hinter welchem Router er hängt;
`werkzeug/unifi-offloader.py` liest das heute schon aus. Geplant (noch nicht
gebaut): ein Timer schreibt daraus eine Zuordnung AP-MAC → Router, und ein
kleiner Patch lässt unifi_respondd den Router je AP dort nachschlagen statt
aus der Site. Damit stimmen Domain, Gateway, nächster Sprung und Linie je AP,
auch nach einem Umstecken. Findet sich ein AP nicht (offline oder
out-of-band), gilt wie bisher `offloader_mac` der Site.

Die Betreuenden tragen nur Koordinaten ein. Sites mit getrenntem
Verwaltungsnetz (out-of-band, etwa GASt73 und WIR-Haus) ordnen wir selbst
über `offloader_mac` zu. Die Anleitungen (öffentlich in freifunk-docs, für den
LVR in freifunk-content) passt die Content-Session an.
`unifi-fflvr-aufteilung.txt` ist damit überholt.

#### Bauplan (Stand 24.09.2026, gebaut, noch nicht in Betrieb)

Gebaut und getestet:

- Schritt 1: `werkzeug/unifi-offloader.py --json` (1436329), auf map6
  geprüft: 512 APs mit Router, ein zweiter Lauf ändert nichts.
- Schritt 2 und 3: `sammler/patches/unifi-respondd-zuordnung.patch` gegen
  unifi_respondd 6976651, mit sechs eigenen Tests. Alle 33 Tests grün, auch
  auf einem sauberen Checkout; der Haupttest schlägt fehl, wenn man die
  Nachschlagezeile entfernt, prüft also wirklich den Zusatz. Ein falsch
  gesetzter Wert (kein Text) wirkt wie ein fehlender, statt den Dienst
  umzuwerfen; das hatten die vorhandenen Tests aufgedeckt.
- Timer `sammler/systemd/karte-unifi-zuordnung.{service,timer}`, im Repo,
  **nicht aktiviert**.

- Ortscode (25.09.2026): der AP meldet den Code seines Routers zusätzlich als
  `site_code`. unifi_respondd meldete bisher nur `domain_code`, und die
  Ortskarten filtern nach `site_code`; ohne das stünden die APs nur auf der
  Gesamtkarte, wie es die Supernodes tun. Der Wert ist der des Knotens, hinter
  dem der AP hängt (in unserer nodelist unter `domain`, etwa
  `lvrmo-33_lvrmo`), er besteht die Filter dieser Domain also von selbst.
  34 Tests.

**Weg der Antworten zu yanic, entschieden 25.09.2026: eine Instanz, eine
Schnittstelle.** unifi_respondd lauscht mit `SO_BINDTODEVICE` auf genau einer
Schnittstelle und beantwortet dort jede Abfrage mit allen APs. `yanic@neander`
ist ein einziger Sammler über alle 48 `bat`-Schnittstellen und ordnet jeden
Knoten nach seinem gemeldeten `site_code`, nicht nach der Schnittstelle, auf
der die Antwort kam. Die Daten kommen per HTTPS vom Controller, nicht aus dem
Client-Netz. Eine Instanz je Domain würde also nichts gewinnen, sondern jede
würde alle Sites auslesen und alle APs doppelt melden.
Gemessen auf map6: ein Horcher, gebunden wie unifi_respondd an `[::]:1001` auf
`bat-11_lvr`, bekommt die Abfrage, die dort lokal an `ff02::1` geht (die
Maschine hört ihre eigene Multicast-Abfrage). Die Antwort geht an die eigene
Link-Local-Adresse und verlässt die Maschine nicht; im Mesh entsteht dadurch
kein zusätzlicher Verkehr.

Für die Inbetriebnahme fehlt noch: unifi_respondd auf map6 installieren
(auf 6976651 festgenagelt, Patch anwenden), Konfiguration mit
`offloader_by_ap: /var/lib/karte/unifi-zuordnung.json`,
`multicast_enabled: true`, `interface: bat-11_lvr`, dann Timer und Dienst
aktivieren. Danach der
Content-Session Bescheid geben, sie nimmt "noch nicht gebaut" aus beiden
Anleitungen.

Ursprünglicher Plan:

1. **Zuordnung erzeugen:** `werkzeug/unifi-offloader.py` bekommt eine
   Ausgabe `--json <datei>`: ein Objekt `{AP-MAC: Router-MAC}`, beide klein
   mit Doppelpunkten. Router-MAC ist die **primäre** MAC des Knotens aus
   `nodes.json` (`nodeinfo.network.mac`), denn genau so sucht unifi_respondd
   den Offloader in der nodelist (`x["mac"] == offloader_mac`), und daraus
   ohne Doppelpunkte wird `gateway_nexthop`, also die node_id. APs, die
   gerade nicht in der Tabelle stehen, behalten ihren letzten bekannten
   Router (Datei wird zusammengeführt, nicht überschrieben), mit Zeitstempel
   der letzten Messung je AP.
   Auf map6 als `/var/lib/karte/unifi-zuordnung.json`, erzeugt von einem
   Timer alle 5 Minuten (braucht root wegen batctl).
2. **Patch an unifi_respondd** (`sammler/patches/unifi-respondd-zuordnung.patch`,
   gegen freifunkMUC/unifi_respondd 6976651 vom 18.09.2026): neuer optionaler
   Konfigurationsschlüssel `offloader_by_ap` (Pfad zur Datei). Im AP-Durchlauf
   von `unifi_client.py` gilt dann je AP
   `zuordnung.get(ap_mac) or cfg.offloader_mac.get(site["desc"])` statt nur des
   Site-Werts, an allen drei Stellen (neighbour_macs, offloader_id, Suche in
   der nodelist). Fehlt die Datei oder der Eintrag, verhält sich alles wie
   ohne Patch.
3. Test im vorhandenen `tests/`-Verzeichnis von unifi_respondd: ein AP mit
   Eintrag in der Zuordnung bekommt dessen Router, einer ohne den der Site.

Der folgende Abschnitt beschreibt die Lage **ohne** den Patch und bleibt
stehen, weil er erklärt, warum der Patch nötig ist.

### Eine Site je Domain oder je Router?

Ein AP erbt alles Netzbezogene vom **einen** Offloader seiner Site
(`unifi_client.py`): die Domain (`domain_code`), das Gateway
(`gateway`, `gateway6`), den nächsten Sprung (`gateway_nexthop`) und die
Verbindungslinie auf der Karte (`neighbour_macs`).

- **Eine Site je Domain ist das Minimum.** Damit stimmen Domain, Domainkarte,
  Statistik und Gateway. Hängen die APs einer Domain aber hinter mehreren
  Routern, zeichnet die Karte sie alle am selben, eingetragenen Router.
- **Eine Site je Router** braucht es nur, wenn die Karte auch zeigen soll,
  hinter welchem Router jeder AP wirklich hängt.

Beim LVR (615 APs hinter 95 Routern in sieben Domains) wären das 95 Sites,
deshalb die Aufteilung je Domain in der Anleitung für die dortige IT.

**Namen der Sites:** unifi_respondd deutet den Namen nicht, zugeordnet wird
über `offloader_mac` in unserer Konfiguration, Schlüssel ist der
Anzeigename der Site. Er muss also nur eindeutig und stabil sein und exakt so
geschrieben werden. Als Schema nehmen wir den Namen der Domain auf unserer
Karte (Spalte `host` in `tunnel/domains.conf`, z.B. `lvr-hph-nordost`,
`dus-unterkuenfte-west`, `wuelfrath`). Teilen sich mehrere Einrichtungen eine
Domain auf unserem Controller, bekommt jede ihre eigene Site mit angehängter
Einrichtung (`wuelfrath-wir-haus`), damit die Rechte getrennt bleiben.

### Offene Einstellungen für die Inbetriebnahme

- **`ssid_regex`** ist noch nicht festgelegt. Es ist ein Pflichtfeld ohne
  Vorgabe im Code; `.*freifunk.*` steht nur in der Beispielkonfiguration.
  Geprüft wird ohne Beachtung von Groß- und Kleinschreibung. Ein AP, dessen
  SSID nicht passt, erscheint nicht auf der Karte. Beim LVR laufen `Freifunk`
  und `FreifunkStreaming`, beide passen auf `.*freifunk.*`. Ob
  `FreifunkStreaming` überhaupt ins Freifunk-Netz führt, ist noch zu klären;
  sonst zählen seine Clients fälschlich mit.
- **`controller_port`** 443 für `unifi.ffnef.de`, nicht die 8443 aus dem
  Beispiel; beide sind offen, 443 ist der Weg, den auch der Browser nimmt.
- **`version`** passend zur Controller-Software setzen (`v5` im Beispiel,
  `UDMP-unifiOS` bei UniFi OS). Unser Controller ist Version 10.2.105 und
  beantwortet die klassischen Pfade (`/api/login`, `/api/s/<site>/...`), also
  `v5`.
- **`nodelist`** auf unsere Karte:
  `https://neander.map.freifunk.space/data/meshviewer.json`. Daraus erbt jeder
  AP Domain und Gateway seines Offloaders.

### Koordinaten: Zahlen, kein Freitext

Steht im Feld SNMP Location ein Freitext statt eines Koordinatenpaars, schickt
unifi_respondd ihn an Nominatim, den Geocoder von OpenStreetMap. Das ist ein
fremder Dienst, und schlägt die Suche fehl, setzt er 0/0: der AP landet dann
auf "Null Island" im Golf von Guinea. Die Anleitung für die Betreuenden
verlangt deshalb Zahlen (`51.2506, 6.9746`).
