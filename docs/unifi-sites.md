# UniFi-Accesspoints auf der Karte

Öffentliche Anleitung für die Betreuenden eines Controllers (Koordinaten
eintragen):
[freifunk-docs: UniFi-Accesspoints auf die Freifunk-Karte](https://github.com/Neanderfunk/freifunk-docs/blob/main/unifi-accesspoints-freifunk-karte.md).
Ändert sich beim Einrichten etwas, das die Betreuenden betrifft, etwa Port,
Zugang oder SSID-Muster, muss sie nachgezogen werden; die Content-Session
pflegt sie.


## Stand

**In Betrieb seit 25.09.2026, 10:50.** UniFi-Accesspoints stehen als eigene
Knoten auf der Karte, verbunden mit dem Freifunk-Router, hinter dem sie
hängen. Erste Messung: 544 APs online, 1021 Clients an APs. Die Summe aller
Clients blieb bei rund 3050 (vorher 3011 bis 3047); ohne das Abziehen beim
Router wären es rund 4000 gewesen.

Beteiligt sind zwei Forks in der Neanderfunk-Organisation, je Funktion ein
Commit, erklärt in `NEANDERFUNK.md` im jeweiligen Fork:

| Fork | Aufgabe |
| --- | --- |
| [Neanderfunk/unifi_respondd](https://github.com/Neanderfunk/unifi_respondd) | holt die APs aus dem Controller und meldet sie per respondd |
| [Neanderfunk/yanic](https://github.com/Neanderfunk/yanic) | zieht die AP-Clients beim Router ab, zeichnet die Links richtig |

## Wie es zusammenspielt

1. **Zuordnung AP → Router.** `karte-unifi-zuordnung.timer` startet alle fünf
   Minuten `karte-unifi-offloader neander --json
   /var/lib/karte/unifi-zuordnung.json` (aus `werkzeug/unifi-offloader.py`).
   Das liest die batman-Übersetzungstabellen: ein in-band verwalteter AP ist
   für batman ein Client seines Routers. Die Datei wird zusammengeführt, ein
   AP behält seinen letzten bekannten Router. Stand 25.09.2026: 587 APs mit
   Router, darunter praktisch jeder, der online ist.
2. **unifi_respondd** (`unifi-respondd.service`, `/opt/unifi_respondd`)
   holt höchstens einmal je Minute Geräte, Clients und Funkwerte vom
   Controller, liest dazu die Zuordnung und unsere nodelist
   (`meshviewer.json`, für Domain und Gateway des Routers). Er lauscht auf
   Port 1001 auf allen 43 batman-Instanzen der Community und beantwortet
   jede Anfrage nur mit den APs, deren Router in der Domain dieser
   Schnittstelle steht. So bekommt jeder Sammler im Mesh, auch ein fremder,
   genau die APs seiner Domain. **APs ohne gemessenen Router meldet er
   nicht**: ein falscher Router wäre schlimmer als ein fehlender AP.
3. **yanic@neander** fragt wie immer alle 5 Minuten auf jeder batman-Instanz
   (`ff02::1`) und bekommt die APs wie gewöhnliche Knoten. Erkannt werden sie
   an `software.firmware.base = "UniFi"` (Schlüssel
   `nodes.accesspoint_firmware`, Vorgabe `["UniFi"]`).

## Was die Karte von einem AP zeigt

- **Ort**: aus dem Feld SNMP Location im Controller, siehe "Koordinaten".
  Ohne Koordinaten steht der AP in Liste, Graph und Statistik an seinem
  Router, nur nicht auf der Landkarte. Einen Platzhalter wie 0/0 gibt es
  nicht.
- **Ortskarte**: der AP meldet den Ortscode (`site_code`) seines Routers und
  erscheint damit auf derselben Ortskarte wie der Router.
- **Linie zum Router**: als Kabel, mit voller Qualität auf beiden Seiten.
  Den Link meldet nur der AP, der Router kennt ihn nicht als batman-Nachbarn;
  yanic trägt die zweite Seite nach. Linien zwischen zwei APs (UniFi-Mesh
  per Funk) bleiben Funk.
- **Clients**: beim AP. Der Router zeigt nur noch seine eigenen, denn die
  Clients hinter einem AP stehen in der Übersetzungstabelle als Clients des
  Routers (gemessen: 836 von 837). yanic zieht sie beim Router ab, aber nie
  unter dessen eigene WLAN-Clients. Gesamtsummen zählen jeden Client einmal.
- **Airtime**: Kanalauslastung je Band aus dem Controller (`cu_total`,
  `cu_self_rx`, `cu_self_tx`), so frisch wie der Controller, also einige
  Minuten alt. unifi_respondd rechnet die Prozente in fortlaufende Zähler um,
  wie Gluon sie liefert, yanic bildet daraus wieder dieselben Prozente.
  Interferenz ist belegt minus eigene.
- **Systemlast und Speicher**: die des AP selbst (`loadavg_1`, Speicher aus
  dem Controller).
- **Erstsichtung**: einmalig am 25.09.2026 aus dem Controller übernommen, siehe
  `betrieb.md` ("Erstsichtung").
- **Offline**: meldet der Controller den AP nicht mehr als verbunden, meldet
  ihn unifi_respondd nicht mehr. yanic setzt ihn nach 20 Minuten auf offline,
  mit "zuletzt gesehen", und räumt ihn nach 90 Tagen ab. APs, die seit dem
  Einschalten nie online waren, stehen gar nicht auf der Karte.

## Koordinaten

Das Feld SNMP Location wird tolerant gelesen, Linie adorfer 25.09.2026:
"Wir sollten die User nicht unnötig mit Pedanterie schikanieren, wo es hier
nur ein paar Zeilen Code sind." Welche Schreibweisen gehen, steht für die
Nutzer in der öffentlichen Anleitung (oben verlinkt, gepflegt von der
Content-Session) und für Entwickler bei `parse_location()` im Fork samt
Tests. Wer über einen unlesbaren Eintrag stolpert, erweitert den Code, nicht
die Anleitung, und gibt der Content-Session Bescheid.

Bewusste Grenze (mit adorfer abgestimmt): nichts raten, was die Bedeutung
ändert. Keine Adresssuche (früher Nominatim, ein fremder Dienst), keine
Kurzlinks, nichts Widersprüchliches (Minus und Himmelsrichtung zugleich,
zweimal N), keine 0/0.

Die Standortwahl der Karte bietet ein Feld "Breite, Länge", das sich direkt
in den Controller kopieren lässt (Fork Neanderfunk/meshviewer).

Gegenprobe eines Eintrags: mit dem Lesekonto die Geräte lesen,
`parse_location()` darauf anwenden und den Abstand zum Router aus der
nodelist prüfen; bei den ersten Einträgen lag er bei 7 bis 88 m.

## Betrieb

| Was | Wo |
| --- | --- |
| Dienst | `unifi-respondd.service`, Benutzer `unifi-respondd`, Port 1001 |
| Code | `/opt/unifi_respondd` (Fork, Zweig `neanderfunk`), venv darin |
| Konfiguration | bei jedem Start aus `karte-unifi-respondd-conf` (`sammler/unifi-respondd-conf.py`): `sitecodes.conf` + Zugang |
| Zuordnung | `karte-unifi-zuordnung.timer`, Datei `/var/lib/karte/unifi-zuordnung.json` |
| Einrichtung | `sudo ./sammler/unifi-einrichten.sh` (setzt `/etc/unifi_respondd/zugang` voraus) |
| Überwachung | Checkmk `mapserver-unifi`: Dienst läuft, Zuordnung höchstens 30 min alt, APs online; höchstens WARN |

**Aktualisieren:** Fork pflegen und pushen, dann auf map6
`sudo ./sammler/unifi-einrichten.sh` oder von Hand `git -C /opt/unifi_respondd
fetch` plus Checkout von `origin/neanderfunk` und
`systemctl restart unifi-respondd`. yanic: `sudo ./sammler/einrichten.sh`
baut aus dem Fork `Neanderfunk/yanic`.

## Was normal ist und was nicht

- **Nach einem Neustart von yanic** fehlen alle Links für 2 bis 5 Minuten,
  bis zur ersten Sammelrunde: yanic speichert die Nachbarschaften nicht im
  Zustand. War vor den Forks genauso.
- **Nach einem Neustart von unifi_respondd** fehlt den APs für eine Runde
  die Airtime (Zähler beginnen neu), wie bei einem Gluon-Knoten nach dem
  Neustart.
- **Alle APs gleichzeitig offline**: unifi_respondd oder der Controller
  ausgefallen, oder das Lesekonto gesperrt. Checkmk meldet "kein AP online".
  Journal: `journalctl -u unifi-respondd`; der Dienst schreibt nur Warnungen.
- **Ein AP fehlt**: steht er in `/var/lib/karte/unifi-zuordnung.json`? Wenn
  nicht, ist er out-of-band verwaltet oder sein Herstellerpräfix fehlt in
  `werkzeug/unifi-offloader.py` (so fehlten bis 25.09.2026 80 APs mit vier
  Präfixen).
- **Airtime außerhalb 0 bis 100 %** in alten Daten: einmalig am 25.09.2026 um
  11:02 beim Umstieg auf die Airtime-Zähler. Grafana und die Karte klammern
  die Werte deshalb auf 0 bis 100.

## Grenzen

- **6 GHz** fehlt: yanic kennt nur 2,4 (11g) und 5 GHz (11a), ein drittes
  Band überschriebe 5 GHz. Am 25.09.2026 meldet keiner der 545 APs ein
  aktives 6-GHz-Modul.
- **Rauschen** (noise) liefert der Controller nicht.
- **Out-of-band verwaltete Installationen**: ihr Router lässt sich nicht
  aus der Übersetzungstabelle messen, dort bräuchte es `offloader_mac` von
  Hand; zwei solche Sites sind für unser Konto derzeit nicht sichtbar.

## In-band oder out-of-band

Das entscheidet, ob wir den Router eines AP messen können.

**In-band**: die Accesspoints beziehen ihre eigene Adresse aus dem
Freifunk-Netz, ihre MAC steht in der Übersetzungstabelle von batman, und
`werkzeug/unifi-offloader.py` findet sie samt Router.

**Out-of-band**: die Verwaltung liegt in einem eigenen VLAN, nur der Verkehr
der Freifunk-SSID wird ins Client-Netz gebrückt. Im Mesh stehen dann nur die
WLAN-Clients und kein AP; der Router muss von Hand eingetragen werden
(`offloader_mac` je Site), am einfachsten über den Kartenlink des Knotens.

## Standorte, Konto und Zugänge

Welche Sites es gibt, hinter welchen Routern sie hängen, das Konto am
Controller und wo die Zugangsdaten liegen, steht nicht in diesem
öffentlichen Repo, sondern im Betriebs-Repo der Supernode-Session
(übergeben am 25.09.2026). Hier nur: der Dienst braucht ein Konto mit reinen
Leserechten, er liest Sites, Geräte und Clients und schreibt nichts.

## Vorgeschichte bis zur Inbetriebnahme

Die folgenden Abschnitte beschreiben den Weg bis zum 25.09.2026 und bleiben
stehen, weil sie Entscheidungen begründen. Wo sie vom heutigen Stand
abweichen, gilt der Teil oben.

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

Der Blick in den Controller (lesend, eigenes Konto) ergab: keiner der
APs hatte Koordinaten; Einzelheiten im Betriebs-Repo.

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
Verwaltungsnetz (out-of-band) ordnen wir selbst
über `offloader_mac` zu. Die Anleitungen (öffentlich in freifunk-docs, für den
LVR in freifunk-content) passt die Content-Session an.
Die Aufteilungsliste von damals ist damit überholt.

#### Bauplan (Stand 24.09.2026, gebaut, noch nicht in Betrieb)

Gebaut und getestet:

- Schritt 1: `werkzeug/unifi-offloader.py --json` (1436329), auf map6
  geprüft: 512 APs mit Router, ein zweiter Lauf ändert nichts.
- Schritt 2 und 3: Fork [Neanderfunk/unifi_respondd](https://github.com/Neanderfunk/unifi_respondd), Zweig `neanderfunk`, gegen
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

**Weg der Antworten zu yanic (25.09.2026): alle bat-Schnittstellen, je
Domain gefiltert.** Ein Prozess holt die Daten per HTTPS vom Controller und
lauscht auf allen `bat`-Schnittstellen auf respondd-Anfragen. An der
Ankunftsschnittstelle jeder Anfrage (`IPV6_PKTINFO`) erkennt er die Domain und
antwortet nur mit den APs, deren Router dort steht. So verhält er sich wie ein
echter Knoten, und zwar für **jeden** Sammler im Mesh, nicht nur für unseren.

Mein erster Entwurf war "eine Instanz auf einer Schnittstelle, alle APs". Für
unseren eigenen yanic hätte das gereicht, weil der nach `site_code` ordnet.
Übersehen hatte ich die anderen Sammler in denselben Meshes, etwa eulenmap1,
der in allen 48 Domains hängt: der hätte in `lvr-hph` alle 615 APs aus allen
sieben Domains bekommen. adorfer hat das Modell richtiggestellt.

Umgesetzt im Patch (Konfigurationsschlüssel `interfaces`: Schnittstelle →
Liste der site_codes dieser Domain, aus `sitecodes.conf` zu erzeugen), dazu
`cache_seconds` (Vorgabe 60): im Original holt unifi_respondd bei **jeder**
einzelnen Anfrage alle Daten neu vom Controller, bei 48 Schnittstellen also
48-mal je Runde. 44 Tests, darunter ein echter Socket-Test, der die
Ankunftsschnittstelle über Loopback erkennt.

Gemessen vorab auf map6: ein Horcher auf `bat-11_lvr` bekommt die Abfrage,
die yanic dort lokal an `ff02::1` schickt. Unser yanic wird also auf jeder
Schnittstelle bedient, ohne dass Verkehr ins Mesh geht.

Für die Inbetriebnahme fehlt noch: unifi_respondd auf map6 installieren
(auf 6976651 festgenagelt, Patch anwenden), Konfiguration mit
`offloader_by_ap: /var/lib/karte/unifi-zuordnung.json`,
`multicast_enabled: true`, `interfaces` aus `sitecodes.conf` erzeugt (alle
`bat-*` der Community neander), dann Timer und Dienst aktivieren. Den
Erzeuger für `interfaces` gibt es noch nicht. Danach der
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
2. **Änderung an unifi_respondd** (heute im Fork Neanderfunk/unifi_respondd,
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
Einrichtung (`<ort>-<einrichtung>`), damit die Rechte getrennt bleiben.

### Offene Einstellungen für die Inbetriebnahme

- **`ssid_regex`** ist noch nicht festgelegt. Es ist ein Pflichtfeld ohne
  Vorgabe im Code; `.*freifunk.*` steht nur in der Beispielkonfiguration.
  Geprüft wird ohne Beachtung von Groß- und Kleinschreibung. Ein AP, dessen
  SSID nicht passt, erscheint nicht auf der Karte. Beim LVR laufen `Freifunk`
  und `FreifunkStreaming`, beide passen auf `.*freifunk.*`. Ob
  `FreifunkStreaming` überhaupt ins Freifunk-Netz führt, ist noch zu klären;
  sonst zählen seine Clients fälschlich mit. (Geklärt 25.09.2026: 32 von 37
  seiner Clients standen in der Übersetzungstabelle, es führt ins Freifunk-Netz,
  die Clients zählen zu Recht.)
- **`controller_port`** 443 für unseren Controller, nicht die 8443 aus dem
  Beispiel; beide sind offen, 443 ist der Weg, den auch der Browser nimmt.
- **`version`** passend zur Controller-Software setzen (`v5` im Beispiel,
  `UDMP-unifiOS` bei UniFi OS). Unser Controller ist Version 10.2.105 und
  beantwortet die klassischen Pfade (`/api/login`, `/api/s/<site>/...`), also
  `v5`.
- **`nodelist`** auf unsere Karte:
  `https://neander.map.freifunk.space/data/meshviewer.json`. Daraus erbt jeder
  AP Domain und Gateway seines Offloaders.

### Ohne Koordinaten: in Liste und Graph, nicht auf der Karte

Koordinaten braucht nur die geografische Karte. Liste, Graphansicht,
Statistik und Grafana kommen ohne aus, dort hängt der AP an seinem gemessenen
Router (adorfer 25.09.2026: "im Mesh müssten die doch auch so angezeigt
werden können").

Dafür musste unifi_respondd lernen, **keinen** Ort zu melden: im Original
setzt er ohne Koordinaten 0/0, und alle APs stünden auf "Null Island" im Golf
von Guinea. Der Patch lässt den Ort dann ganz weg, ebenso bei einer
eingetragenen 0/0. Zusätzlich übergeht der Generator der Kartenausschnitte
(`rahmen()` in `web/konfig-erzeugen.py`) Punkte bei 0/0, damit auch ein
einzelner Gluon-Knoten mit 0/0 den Ausschnitt nicht aufzieht.

Damit sind die Koordinaten beim LVR kein Hindernis mehr für den Start, nur
noch für die Kartenansicht.

### Koordinaten: Zahlen, kein Freitext (überholt)

Steht im Feld SNMP Location ein Freitext statt eines Koordinatenpaars, schickt
unifi_respondd ihn an Nominatim, den Geocoder von OpenStreetMap. Das ist ein
fremder Dienst, und schlägt die Suche fehl, setzt er 0/0: der AP landet dann
auf "Null Island" im Golf von Guinea. Die Anleitung für die Betreuenden
verlangte deshalb Zahlen (`51.2506, 6.9746`).

Überholt am 25.09.2026: Der Fork fragt Nominatim nicht mehr und liest
gängige Schreibweisen selbst, siehe "Koordinaten" oben.
