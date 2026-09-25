# Wenn die Karte einer Community leer bleibt

Gelernt am 20. und 21.09.2026 beim Aufbau des Kartenservers für Freifunk EN
und die Neanderfunk-Domains. Die Fälle sahen alle gleich aus, nämlich "die
Karte ist leer", hatten aber sechs verschiedene Ursachen auf fünf
verschiedenen Schichten. Das hier ist die Reihenfolge, in der man sie
auseinandersortiert, damit das nächste Mal eine Stunde reicht statt einer
Nacht.

Die Werkzeuge dazu liegen in `werkzeug/`.

## Die Grundregel

**Von unten nach oben messen und jede Schicht einzeln bestätigen.** Der
teuerste Fehler des Abends war, aus einem leeren Ergebnis auf die unterste
Schicht zu schließen. Zwischen "der Tunnel steht" und "auf der Karte steht ein
Knoten" liegen fünf Übergänge, und jeder davon kann still verschlucken.

```
Tunnel  →  batman  →  IP  →  respondd  →  Filter  →  Ausgabe
```

## Schicht 1: Tunnel

```bash
systemctl is-active karte-en-tunnel@<code>
ip -br link show td-<code>
```

**Falle: der Dienst läuft, die Schnittstelle ist weg.** Beobachtet am
20.09.: der Client meldete "Tunnel successfully established" und hielt seine
Keepalives, `td-ffen` existierte trotzdem nicht mehr. Aus Sicht von systemd
war alles in Ordnung. Dagegen gibt es den Wächter (`tunnel/waechter.sh`).

Antwortet der Broker gar nicht, klopft man protokollkonform an, ohne einen
Tunnel aufzubauen:

```bash
werkzeug/broker-probe.py --broker broker1.example.net:10161
```

**Falle: zu kurze Brokerliste.** Elf von 48 Neanderfunk-Domains bekamen keinen
Tunnel, weil sie nur auf zwei der sechs Broker liegen. Immer alle Broker aus
der site.conf eintragen und den Client wählen lassen.

## Schicht 2: batman

```bash
batctl meshif bat-<code> originators | grep -c '^ \*'
batctl meshif bat-<code> neighbors
batctl meshif bat-<code> transglobal | wc -l
```

Originatoren sind Knoten, Nachbarn ist bei einem Tunnelteilnehmer genau einer
(der Broker), und die Translation Table sind die Clients im ganzen Mesh.

**Falle: Konvergenz dauert länger als man denkt.** Nach einem Neustart der
Maschine stand zwei Minuten lang alles auf null und war nach drei Minuten
vollständig da. Der Tunneldigger-Client setzt die MTU erst rund zwanzig
Sekunden nach dem Verbindungsaufbau, und danach sortiert batman sich neu. Wer
früher misst, misst Unsinn. Die Checks haben deshalb eine Schonfrist.

## Schicht 3: IP

```bash
ping6 -c3 -I bat-<code> ff02::1        # wer antwortet ausser uns selbst?
ip -6 neigh show dev bat-<code>        # FAILED heisst: Multicast kommt nicht an
batctl meshif bat-<code> ping <originator-mac>
```

**Der wichtigste Einzeltest ist `ff02::1`.** Darauf antwortet jedes
IPv6-Gerät, ohne dass respondd oder sonst etwas laufen müsste. Antworten dort
viele Knoten, ist alles unterhalb in Ordnung. Antwortet nur die eigene
Adresse, während `batctl ping` auf dieselben Knoten funktioniert, dann ist
**Unicast heil und Multicast tot**, und das ist der Befund, der alles Weitere
bestimmt (siehe unten).

## Schicht 4: respondd

```bash
werkzeug/respondd-probe.py bat-<code>
```

**Falle: die Abfragegruppe.** Stock-Gluon bedient `ff05::2:1001` auf
`br-client` und `ff02::2:1001` auf den Mesh-Schnittstellen. Im Neanderfunk
antwortet auf `ff05::2:1001` gemessen **nur der Supernode**, auf `ff02::1`
dagegen alle Knoten, weil unser Patch `fix-respondd-rsk` diese Gruppe
zusätzlich öffnet. Fragt der Collector die falsche Gruppe, kartiert man 48
Supernodes und keinen Knoten.

**Falle: der Messtakt.** yanic sammelt nicht zur vollen Minute, sondern
versetzt (`synchronize`). Zwei Mitschnitte zwischen den Läufen haben eine
halbe Stunde gekostet. Vor dem Mitschneiden immer erst ins Log sehen, wann
die Läufe tatsächlich liegen.

**Falle: der taube Collector.** Das Netz antwortet, von Hand per
`respondd-probe.py` sogar vollzaehlig, aber yanic bekommt nichts. yanic bindet
je Domain einen Socket an die Schnittstelle, genauer an ihren ifindex. Wird
die bat-Instanz geloescht und neu angelegt, traegt sie denselben Namen, aber
einen neuen Index, und der alte Socket hoert ins Leere, ohne Fehlermeldung.
Erkennbar in `ss -uanp`: die Schnittstelle steht dort als blanke Nummer
(`%if100`) statt mit Namen. Am 22.09.2026 um 06:27 schickte ein Broker allen
Tunneln einen Teardown, der Client verband sich binnen Sekunden neu, und
fuenfzehn Domains blieben zwoelf Stunden stumm, waehrend Tunnel, Mesh und die
Pruefung der Originatoren gruen waren. Seitdem loescht der Hook die
bat-Instanz nicht mehr, und der Waechter startet einen Collector neu, der an
einer verschwundenen Schnittstelle haengt.

Merksatz dazu: **erst von Hand fragen, dann dem Collector glauben.** Antwortet
die Probe und yanic nicht, liegt es an unserer Seite.

## Schicht 5: Filter

Hier sind die meisten leeren Karten entstanden, und sie sehen von außen genau
aus wie ein kaputtes Netz.

**Der site_code der Knoten ist nicht der Name der Domain.** Im Neanderfunk
heißt die Domain `10_wlf`, die Knoten melden `nef-10_wlf`, die 4/32-Geräte
zusätzlich `nef-10_wlf_EOL`, und das Präfix ist je Domain verschieden: `nef`,
`dus`, `bgl`, `lvrno` und drei weitere. Die Regel steht in
`sites.nefall.sta`: **META_PREFIX (Spalte 9) + "-" + SITE_CODE (Spalte 4)**.
Mit einem falsch geratenen Präfix blieben 28 von 48 Karten leer, obwohl die
Daten ankamen.

Bei einer fremden Community gibt es keine Buildliste zum Nachschlagen. Dann
erhebt man die Codes im Netz:

```bash
sammler/sitecodes-ermitteln.py > sitecodes.conf
```

**Supernodes melden keinen site_code, nur einen domain_code.** Jeder
site-Filter wirft sie deshalb weg, und ohne sie gibt es keine VPN-Kanten und
keine Uplink-Färbung auf der Karte. Die saubere Lösung ist, gar nicht zu
filtern: je Community ein eigener Collector, dann entsteht die Trennung schon
daraus, welche Schnittstellen er abhört.

**Nicht mit `domain_as_site` lösen.** Der Filter täte genau das Richtige, aber
yanic baut seine Filtermenge aus einer Go-Map, und deren Reihenfolge ist
zufällig. Läuft `sites` vor `domain_as_site`, ist der Supernode schon
verworfen. Ein Verhalten, das bei jedem Start anders ist, will man nicht.

## Schicht 6: Ausgabe

**yanic legt fehlende Verzeichnisse nicht an** und schreibt dann still nichts.
**yanic beendet sich mit einem Panic, wenn eine konfigurierte Schnittstelle
fehlt** ("route ip+net: no such network interface"); bei 56 Domains nimmt ein
einziger stummer Broker die ganze Karte mit. Die Konfiguration deshalb bei
jedem Start neu erzeugen und nur vorhandene Instanzen aufnehmen.

## Der Sonderfall: Multicast tot, Unicast heil

Das war der Fall bei Freifunk EN, über viele Stunden und je Domain wechselnd.
Kennzeichen:

- Originatoren in voller Zahl, `batctl ping` auf Knoten mit 20 bis 40 ms
- Router Advertisements von ihrem Gateway **kommen an**, unsere Adressen aus
  ihrem Präfix werden laufend erneuert
- unsere Rundrufe erreichen ihre Knoten nicht, Nachbarschaftsauflösung
  scheitert (`FAILED`)
- Unicast an eine bekannte Knotenadresse funktioniert sofort

Kaputt ist dann genau eine Richtung: **vom Tunnelteilnehmer ins Mesh hinein**.
Und das ist dieselbe Richtung, die ein Kartenserver braucht, der nicht direkt
auf dem Supernode sitzt. Eine Community mit diesem Problem kann ihre eigene
Karte nicht zum Laufen bringen und weiß oft nicht, warum.

### Der Weg daran vorbei

Die MAC jedes Knotens steht in der Translation Table, die batman **jedem
Mitglied des Mesh zustellt**; wir erheben nichts, wir haben es schon. Die
Link-Local-Adresse ist daraus nach RFC 4291 berechenbar (EUI-64), nicht
geraten. Ein Unicast dorthin erreicht respondd auch dann, wenn kein Rundruf
durchkommt.

```bash
sammler/ziele-ernten.py <community> > ziele.txt
```

Gemessen in einer Domain ohne jeden Multicast: 175 Kandidaten, 73 Antworten,
und die Karte ging von null auf 72 Knoten.

Wichtig: **die Originator-MAC taugt dafür nicht.** Das ist die MAC der
Mesh-Schnittstelle, ihre Link-Local-Adresse lebt dort und ist über bat0 nicht
erreichbar. Nur die Einträge der Translation Table führen auf `br-client`, wo
respondd lauscht. Messwert: über Originatoren 0 Antworten, über die
Translation Table 25 von 40.

Damit yanic diese Adressen mitfragt, braucht es
`sammler/patches/yanic-seeds.patch`, 51 Zeilen: es liest
eine Adressliste und fragt sie in jeder Runde mit. Die Antworten kommen an
yanics eigenem Socket an, es lernt Adresse und Knoten wie sonst auch.

## Wenn die Ursache beim Gegenüber liegt

Kandidaten, die genau dieses Bild erzeugen, geordnet nach Trefferwahr-
scheinlichkeit. Alle sind bei ihnen prüfbar, keiner von außen.

1. **IGMP/MLD-Snooping ohne Querier** auf einem Switch im Pfad. Multicast
   wird dann verworfen statt geflutet, Unicast bleibt unberührt.
2. **Storm Control oder Broadcast-Rate-Limit** je Port. Greift erst ab einer
   bestimmten Netzgröße und trifft die größte Domain zuerst.
3. **MAC-Tabelle oder Port Security.** Freifunk EN führte zum Messzeitpunkt
   3560 Client-MACs über acht Domains, allein Hattingen 1081.
4. **Hyper-V: MAC Address Spoofing** (standardmäßig aus, bricht jede Brücke
   mit fremden Quell-MACs), **Router Guard** (verwirft RAs aus der VM), und
   **VMQ** auf der physischen Karte.

Ein Test, der in zwei Minuten sagt, ob es an batman liegt oder tiefer:
`batctl meshif bat<domain> multicast_mode disable` auf ihrem Supernode. Wird
es besser, war es die Multicast-Optimierung im Zusammenspiel mit dem Snooping
unterwegs.

## Was man zuerst fragt, bevor man vermutet

Bei einer fremden Community ist die Diagnose billiger als das Raten, aber
das Gespräch ist billiger als beides:

- Wo saß euer Kartenserver, auf dem Supernode oder auf einer eigenen Maschine
  mit Tunnel? Das entscheidet, ob sie überhaupt eine Chance hatten.
- Seht ihr denselben Bruch zwischen Unicast und Multicast?
- Liegt zwischen euren Hypervisoren Netztechnik, die ihr nicht selbst
  konfiguriert?

## Kurzform

| Beobachtung | Schicht | Verdacht |
| --- | --- | --- |
| Dienst aktiv, `td-*` fehlt | Tunnel | stiller Abriss, neu starten |
| "No suitable brokers found" | Tunnel | Brokerliste unvollständig |
| alles null, Maschine frisch gestartet | batman | drei Minuten warten |
| `ff02::1` nur die eigene Adresse, `batctl ping` geht | IP | Multicast tot, Unicast heil |
| nur Supernodes antworten | respondd | falsche Abfragegruppe |
| Pakete fließen, Karte leer | Filter | site_code stimmt nicht |
| keine VPN-Kanten, keine Gateways | Filter | Supernodes weggefiltert |
| Collector stirbt beim Start | Ausgabe | Schnittstelle fehlt, Panic |
| Probe antwortet, yanic nicht, `%ifNNN` in `ss` | respondd | tauber Collector nach Neuanlage der bat-Instanz |
| `nginx -t` scheitert, Karten laufen trotzdem | Ausgabe | alte Konfiguration im Speicher, der naechste Neustart nimmt alles |
