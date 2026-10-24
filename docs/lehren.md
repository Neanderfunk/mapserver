# Lehren aus dem Betrieb

Was der Betrieb des Kartenservers seit September 2026 gelehrt hat, kurz und an
einer Stelle. Je Eintrag: was passiert ist, die Regel daraus und wo sie
umgesetzt oder ausführlich beschrieben ist. Die Einzelheiten stehen in
[betrieb.md](betrieb.md), [kartenausfall-diagnose.md](kartenausfall-diagnose.md),
[einrichtung.md](einrichtung.md) und [neuaufbau.md](neuaufbau.md); diese Datei
ersetzt sie nicht, sie ist der Überblick.

Stand 24.10.2026.

## Stumme Domains: "läuft" heißt nicht "liefert"

Die häufigste Störung sieht immer gleich aus: Eine Domain steht auf der Karte
komplett offline, obwohl jeder Dienst `active` meldet. Bisher fünf Ursachen,
jede inzwischen vom Wächter (`tunnel/waechter.sh`, alle fünf Minuten) erkannt
und selbst geheilt:

| Seit | Ursache | Erkennung | Heilung |
| --- | --- | --- | --- |
| 20.09.2026 | Tunnel-Client läuft, L2TP-Schnittstelle ist weg | `td-<code>` fehlt, zweimal hintereinander | Tunnel neu starten |
| 22.09.2026 | bat-Instanz neu angelegt, yanic hängt am alten Schnittstellenindex | Socket mit `%if<nummer>` statt Namen | yanic neu starten; seither bleibt die bat-Instanz beim Tunnelabbau stehen |
| 30.09.2026 | Broker nimmt den Tunnel an, hängt seine Seite aber nicht an batman | kein batman-Nachbar, zweimal hintereinander | Tunnel neu starten, höchstens einmal je halbe Stunde |
| 23.10.2026 | yanic lauscht auf einer Link-Local-Adresse, die es nicht mehr gibt (die der zufälligen Start-MAC der bat-Instanz) | gebundene Adresse fehlt auf der Schnittstelle | yanic neu starten; dazu entfernen Hook und Startwarten fremde Link-Local-Adressen |
| (mesh-announce) | Multicast-Gruppe fehlt nach Neuanlage einer bat-Instanz | Gruppe fehlt in `/proc/net/igmp6` | mesh-announce neu starten |

Regel: **Jede neue Spielart bekommt eine Prüfung im Wächter, nicht nur einen
Absatz in der Doku.** Erkennbar wird so ein Fall von außen fast immer daran,
dass alle Knoten einer Domain gleichzeitig offline gehen und die alte Karte sie
weiter sieht. Diagnose von unten nach oben, Schicht für Schicht:
[kartenausfall-diagnose.md](kartenausfall-diagnose.md).

## Neustart der VM

- Nach einem Neustart können yanic-Sockets auf vergänglichen Adressen landen
  (siehe oben, 22.10.2026). Seither dreifach abgesichert: Hook, Startwarten
  (`sammler/warten.sh`), Wächter.
- Ob ein Kernel-Neustart aussteht, zeigt `/var/run/reboot-required` auf
  Debian ohne needrestart nicht. `uname -r` mit dem neuesten installierten
  `linux-image-*` vergleichen.
- yanic wartet beim Start auf alle bat-Instanzen; ein Neustart von yanic
  kostet daher etwa zwei Minuten ohne frische Daten.

## Einspielen

- **Arbeitskopie zuerst.** Die Einrichtungsskripte installieren aus ihrem
  eigenen Verzeichnis. Eine veraltete Kopie auf der VM holt alte Fassungen
  zurück (28.09.2026, Startausschnitt). Vor jedem Lauf per `git archive`
  auf den Repo-Stand bringen.
- **Nur Konfiguration geändert:** `konfig-erzeugen.py` als
  `karte-en-konfig` installieren und ausführen genügt, kein Neubau. Die
  meisten Darstellungsschalter des meshviewer-Forks stehen deshalb in der
  Konfiguration, nicht im Code.
- **Neubau des meshviewer:** Besucher sehen ihn erst nach hartem Neuladen
  (Service Worker). Nach reinen Konfigurationsänderungen genügt normales
  Neuladen.
- **Immer von außen nachprüfen.** Am 21.10.2026 lieferte nginx eine neue
  Ersatzregel nach dem Einrichtungsskript noch nicht aus; erst ein zweites
  `systemctl reload nginx` half. Die Ursache ist offen, die Regel bleibt:
  nach dem Einspielen die betroffene URL abrufen.
- **dpkg-Sperre.** Läuft gleichzeitig ein apt (etwa ein Ansible-Lauf), bricht
  ein Einrichtungsskript gleich bei "Pakete" ab und richtet nichts ein.
  Abwarten, nicht abbrechen; wer apt gestartet hat, steht in
  `/var/log/apt/history.log` (`Requested-By`).
- **Ruhende Communities.** `tunnel/einrichten.sh` und `sammler/einrichten.sh`
  schalten alle Communities aus `domains.conf` ein, auch die im Standby.
  Danach wieder anhalten, samt `karte-ziele.timer` bei EN (der wurde am
  23.09.2026 übersehen), und `systemctl reset-failed`.

## Paketquellen und Versionen

- **Grafana** kommt aus apt.grafana.com, das unter "stable" auch die nächste
  Hauptversion liefert. Seit 24.10.2026 per apt-Pin auf Hauptversion 13
  festgelegt; neue Hauptversion nur von Hand mit Prüfung der Dashboards.
- **Forks und Pins** (yanic, meshviewer, unifi_respondd, tunneldigger,
  mesh-announce) werden bewusst von Hand mit den Einrichtungsskripten
  nachgezogen, nicht automatisch. Upstream nachziehen per Merge, nie per
  Rebase: auf Fork-Commits verweisen veröffentlichte Links.

## Neuaufbau

Am 24.10.2026 einmal vollständig auf einer frischen VM durchgespielt
(Ansible-Rolle von Betrieb und Operations). Was dabei auffiel und behoben ist:

- Der Kernel der Debian-Cloud-Images hat kein batman-adv; Standard-Kernel
  nehmen. `tunnel/einrichten.sh` prüft das jetzt vorab.
- Die Vorgabe-Site von nginx kollidiert mit unserer `default_server`;
  `web/einrichten.sh` entfernt sie jetzt.
- `gnupg` und `wireguard-tools` fehlten auf einem frischen Debian; die
  Skripte holen sie jetzt selbst.
- **Kennung und fastd-Schlüssel vor `tunnel/einrichten.sh` zurückspielen.**
  Sonst entstehen neue, und die Freischaltung bei der Gegenstelle ist weg.

Reihenfolge, zu erhaltende Dateien und Abhängigkeiten: [neuaufbau.md](neuaufbau.md).

## Sicherheit und Hygiene

- **Lokal lauschen reicht nicht.** Grafanas Datenquellen-Proxy reichte bis
  24.09.2026 anonyme Anfragen an VictoriaMetrics durch, auch `delete_series`.
  Seither haben die Verwaltungsfunktionen einen Schlüssel. Bei jedem Dienst
  hinter einem Proxy fragen, wer durch den Proxy hindurch was darf.
- **Keine Firewall auf der VM**, gefiltert wird davor. Von außen erreichbar
  sind nur nginx (80) und ssh; der Checkmk-Agent lauscht zwar auf allen
  Adressen, ist aber davor gesperrt, respondd beantwortet keine Unicast-Frage
  von außen. Bei jedem Rundgang von außen nachmessen, nicht aus `ss`
  schließen.
- **journald** ist auf 1 GB begrenzt, mit dem Dateinamen, den alle
  Neanderfunk-Hosts nutzen (`90-groesse.conf`), damit später nicht zwei
  Drop-ins nebeneinander liegen.
- **Zugangsdaten** nie ausgeben, auch nicht zum Prüfen; Länge oder Größe
  genügt. Wenn ein Skript per `sudo -S` sein Passwort über die
  Standardeingabe bekommt, darf das Skript selbst nicht ebenfalls über die
  Standardeingabe kommen (sonst liest sudo das Skript als Passwort und
  protokolliert Fehlversuche): Passwort als erste Zeile, dann das Skript.
- **Ändernde Befehle mit Hostnamen-Prüfung**
  (`[ "$(hostname)" = map.freifunk.space ] || exit 1`), weil mehrere
  Maschinen mit ähnlichen Zugängen nebeneinander verwaltet werden.

## Gerätebilder

- Eigene Bilder (`web/geraetebilder/`) haben seit 23.10.2026 Vorrang vor
  freifunk/device-pictures; so ersetzen sie auch ein unpassendes Bild von
  dort.
- Der Dateiname muss genau der normalisierte Modellname sein, den die Karte
  abfragt (meshviewer `{MODEL_NORMALIZED}`), oft mit Revision (`-v1`, `-a1`).
  Vor der Übernahme in den Daten der Karte nachsehen, welche Schreibweisen
  vorkommen. Gleiches Gehäuse unter mehreren Namen: Kopien, keine Symlinks.
- SVG nur mit `viewBox`; ohne sie schneidet der Browser im Knotenfenster
  (150 px hoch) ab, statt zu verkleinern. Vor der Übernahme prüfen: nur
  Zeichenelemente, keine Skripte, keine externen Verweise, Urheber und
  Lizenz im Kopf, und einmal in 150 px Höhe ansehen.
- Gerätebilder liefert nginx mit 30 Tagen Cache-Dauer aus; ein ersetztes Bild
  sehen Besucher erst nach hartem Neuladen.

## Darstellung

- **Graphansicht:** Kräfte einzeln und am echten Bild einstellen, je Schritt
  ein Wert. Gewollt ist, dass jede Domain eine eigene, nicht überschneidende
  "Galaxie" bildet; das beim Nachjustieren erhalten. Werte und Gründe:
  betrieb.md, "Graphansicht".
- **Firefox im Hintergrund-Tab** behält freigegebenen Speicher
  (Bugzilla 2070900); die Karte pausiert dort nach 10 Minuten, nur in
  Gecko-Browsern. Ausbauen, sobald der Fehler behoben ist.

## Arbeitsweise

- Eine Änderung, ein Commit, sofort gepusht; Doku im selben Zug.
- Erst messen, dann ändern: Ursachen wie die verschwundene Link-Local-Adresse
  waren nur per Mitschnitt (`tcpdump` auf der bat-Instanz) und Vergleich der
  Socket-Adresse mit der Schnittstelle zu finden.
- Ein Nachstellen an einer Test-Instanz (Dummy-Schnittstelle mit eigener
  bat-Instanz) ist auf der laufenden VM möglich, ohne fremde Netze zu
  berühren.
