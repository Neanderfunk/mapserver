# Hintergrund und Besonderheiten

Die Dinge, die man aus dem Code nicht ablesen kann, und die Entscheidungen,
die jemand sonst versehentlich rueckgaengig macht.

Wer eine leere Karte vor sich hat und nicht weiss, woran es liegt, faengt
besser bei `docs/kartenausfall-diagnose.md` in der Router-Werkstatt an: dort
steht die Reihenfolge, in der man die Schichten auseinandersortiert, und die
Fallen, die uns beim Aufbau dieses Servers eine Nacht gekostet haben.

## Warum wir das ueberhaupt duerfen

Respondd ist so gebaut, dass jeder Knoten einer Domain fragen darf: Anfrage
per Multicast in die Domain, Antwort per Unicast an den Fragesteller. Der
Knoten muss nicht wissen, wer fragt, und nicht, ob es der erste oder der
dritte ist. Mehrere Karten nebeneinander sind im Freifunk der Normalfall, kein
Uebergriff. Deshalb liegen die Multicast-Gruppen auf `br-client` und den
Mesh-Schnittstellen und nicht auf einer konfigurierten Sammleradresse.

Tunneldigger kennt keine Peer-Autorisierung, ein Beitritt ist also technisch
einseitig moeglich. Das ist kein Freibrief fuer beliebiges Verhalten, siehe
den naechsten Abschnitt.

## Was wir in fremden Netzen nicht tun

Diese Liste ist der Kern des Projekts, nicht Beiwerk:

- **`gw_mode off`.** Ein Sammler, der sich als Gateway anmeldet, zieht Verkehr
  auf sich, den er nicht bedienen will. Das waere aus dem Mitlesen ein
  Eingriff.
- **Keine Clients, keine Bridge, kein DHCP, kein Forwarding.**
- **Keine Adresse aus ihrem Praefix von Hand.** Wir nehmen nur, was ihr
  Router Advertisement anbietet, und respondd braucht ohnehin nur Link-Local.
- **Keine Router aus ihren RAs.** Siehe unten, das ist der heikelste Punkt.
- **Erkennbar bleiben.** Feste, lokal verwaltete MACs und ein sprechender
  Name am Broker (`map-neanderfunk-<code>`). Wer bei ihnen in `batctl o` oder
  ins Brokerlog sieht, soll uns zuordnen koennen.

## Praefixe ja, Router nein

Der gefaehrlichste Fehler waere, aus ihren Router Advertisements einen
Standardweg zu uebernehmen. Dann liefe eigener Verkehr der VM in ihr Netz
hinaus, im schlimmsten Fall die acht Tunnel selbst, und man haette eine
Schleife, die schwer zu finden ist.

Der Hook setzt deshalb je bat-Instanz:

```
accept_ra                     1    Praefix nehmen
accept_ra_pinfo               1
autoconf                      1
accept_ra_defrtr              0    kein Standardweg
accept_ra_rt_info_max_plen    0    keine Route-Information-Optionen
accept_ra_rtr_pref            0    keine Router-Praeferenz
accept_ra_mtu                 0
use_tempaddr                  0    stabile Adresse statt Privacy-Wechsel
forwarding                    0
```

**Die Reihenfolge ist Teil der Sicherheit.** Erst die Verbote setzen, dann
`accept_ra` einschalten, und all das, solange die Schnittstelle noch `down`
ist. Sonst verarbeitet der Kernel das erste RA noch mit den Vorgabewerten, und
fuer ein paar Sekunden steht ein fremder Standardweg im System.

Gegenprobe im Betrieb: `ip -6 route show proto ra` muss leer bleiben, und
`ip -6 route show default` darf nur die eigene Uplink-Schnittstelle nennen.

Nicht global loesen: `net.ipv6.conf.default.accept_ra_defrtr = 0` wuerde beim
naechsten Start auch die Uplink-Schnittstelle treffen koennen, je nach
Reihenfolge, und die VM waere ohne Standardweg. Per Schnittstelle im Hook ist
umstaendlicher und richtig.

## MAC-Schema

```
02:45:4e:00:00:<id>   L2TP-Schnittstelle, unsere Originator-Adresse im Mesh
02:45:4e:00:01:<id>   batman-Instanz
```

`02` heisst lokal verwaltet, `45:4e` ist "EN" in ASCII, `<id>` kommt aus der
Domaintabelle. Die Adressen sind stabil ueber Neustarts, die daraus gebildete
SLAAC-Adresse also auch. Wer die IDs in der Tabelle vertauscht, wechselt
unsere Identitaet in ihrem Netz.

## Der ff02::1-Patch, und warum er hier nichts nuetzt

Unsere eigene Flotte faehrt einen Patch, der respondd zusaetzlich auf
`ff02::1` lauschen laesst, eine Rueckkehr zum Verhalten von Gluon 2016. Ein
Sammler, der darauf ausgelegt ist, sieht in fremden Netzen nichts: Stock-Gluon
bedient nur `ff05::2:1001` auf `br-client` und `ff02::2:1001` auf den
Mesh-Schnittstellen. yanic fragt von sich aus `ff05::2:1001`, deshalb
funktioniert es hier ohne jede Aenderung an ihrer Firmware.

Merksatz: die fehlende Antwort liegt fast nie an ihrem Netz, sondern an der
Adresse, auf der wir fragen.

## Keine blauen Uplink-Knoten

meshviewer faerbt Knoten mit VPN-Verbindung anders ein, im Graphen
`forceGraph.nodeUplinkColor` (#4285F4), auf der Karte `icon["online.uplink"]`
als heller Punkt mit dickem Ring. Beides ist in den Vorgaben aktiv, es gibt
nichts einzuschalten.

Ausgeloest wird es von `helper.hasUplink()`, und das verlangt eine Verbindung
vom Typ `vpn`. Eine solche Verbindung entsteht nur, wenn beide Enden bekannt
sind, also auch das Gateway als Knoten in den Daten steht. Dafuer laeuft bei
anderen ein `ext-respondd` auf den Supernodes.

Bei Freifunk EN antwortet kein Gateway. Die Knoten nennen ihre Gateway-MAC
(`0a:be:ef:20:XX:02`, eine je Domain), aber es gibt kein Gegenstueck, also
keine `vpn`-Verbindung und keine Faerbung. Zum Vergleich, beide oeffentlich
abrufbar:

| | Aachen | unsere EN-Karte |
| --- | --- | --- |
| Knoten | 1608 | 528 |
| `is_gateway` | 40 | 0 |
| Verbindungen `vpn` | 1036 | 0 |

Das ist kein Konfigurationsfehler, sondern fehlende Software auf ihren
Servern. Man koennte die acht Gateways als Pseudoknoten erfinden und die
Verbindungen aus dem `gateway`-Feld erzeugen; dann stuenden aber Objekte auf
der Karte, die nie geantwortet haben, waehrend alles andere gemessen ist.
Bisher bewusst nicht gemacht.

## no_owner

Im eigenen Netz zeigen wir die Kontaktangabe, in fremden nicht.

Das Pico Peering Agreement, auf dem Freifunk fusst, sieht die
Veroeffentlichung ausdruecklich vor: wer sein Netz oeffnet, macht sich
ansprechbar (picopeer.net, Abschnitt 2.2). Eingetragen wird sie freiwillig im
Knoten, und die alte Karte der Community zeigt sie ebenfalls. Seit dem
24.09.2026 steht sie deshalb auch bei uns im Knotenfenster, als Zeile
"Kontakt"; von 1110 Knoten haben 911 eine. Geschaltet wird das ueber KONTAKT
in sammler/yanic-conf.py, je Community.

Fuer fremde Netze bleibt der Filter an. Wer bei Freifunk EN einen Kontakt
eingetragen hat, hat das fuer deren Karte getan und nicht damit gerechnet,
dass ausgerechnet wir seine Adresse veroeffentlichen.

## Neun Karten aus einem Build

Der meshviewer-Build liegt einmal unter `/var/www/karte-en/meshviewer` und
wird von allen Vhosts als `root` benutzt. Je Vhost sind nur zwei Pfade
anders, per `alias`:

```
location = /config.json  ->  sites/<host>/config.json
location /data/          ->  sites/<host>/data/
```

Damit kostet eine weitere Ortskarte eine Konfigurationsdatei und ein
Datenverzeichnis, nicht eine weitere Kopie des Javascript.

Die Kartenausschnitte (`fixedCenter`) rechnet der Generator aus den
tatsaechlichen Knotenkoordinaten. Bei jedem Lauf von `karte-en-konfig`
aktualisiert sich das.

## Keine fremden Ressourcen im Browser

Kacheln kommen ueber den Cache in Duesseldorf (`tiles.ffdus.de`), nicht direkt
von OSM oder CARTO. Die Geraetebilder liefern wir selbst aus, statt sie wie
die Beispielkonfiguration von `github.io` zu holen. Sonst erfuehre ein
fremder Server, wer unsere Karten ansieht.

## Vorgabe-Vhost

Der blanke Name der VM und alles ohne eigenen Vhost landen auf einer
Uebersichtsseite, die nur auflistet, welche Karten es gibt. Die Karte einer
Community soll nicht zufaellig unter dem Namen der Maschine erscheinen, und
`map.freifunk.space` bleibt fuer weitere Communities frei.

## Verhaeltnis zum Community-Finder

Die Knoten dieser Karte fliessen in die Gebietsberechnung von mitfunken ein,
die Karte wird dort aber **nicht verlinkt und nicht genannt**. Intern
unterscheidet die Auswertung drei Faelle statt zwei:

| Quelle | Bedeutung |
| --- | --- |
| eigene Karte | die Community betreibt sie selbst |
| Aggregator | fremde Gesamtkarte, Aussage Dritter |
| unsere Karte (…) | wir messen ihr Netz, sie haben keine Karte |

Ohne diese Unterscheidung wuerde der Finder behaupten, Freifunk EN betreibe
eine Karte, und damit eine Betriebsfaehigkeit anzeigen, die dort nicht
besteht. Umgesetzt ist das in `finder.py` als Liste `EIGENBETRIEB` und in
`initiativen.yaml` dadurch, dass die Quelle unter `daten:` steht statt unter
`quellen.karte`.

## Bekannte Eigenheiten

- **broker2.ff-en.de** antwortet auf keinem der acht Ports, die Maschine pingt
  aber. Beide Broker stehen in der Startzeile, `-g` nimmt den ersten
  erreichbaren; sobald dort wieder ein Dienst laeuft, wird er von selbst
  genutzt.
- **Ein Knoten in Wetter** antwortet mit leerer node_id, yanic verwirft ihn mit
  einer Warnung. Fehler auf seiner Seite.
- **61 der 528 Knoten** haben keine Koordinaten und erscheinen nur in der
  Liste, nicht auf der Karte.
- **`other`-Verbindungen** (133 Stueck) sind Mesh ueber Kabel, nicht Tunnel.
