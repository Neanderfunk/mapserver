# Einrichtung

Von einer leeren VM zum laufenden Kartenserver. Drei Grundschichten, danach
Zusätze, jeweils mit eigenem Skript.

## Voraussetzungen

- Debian 13 (trixie), getestet mit Kernel 6.12. Die Module `l2tp_eth`,
  `l2tp_netlink`, `batman_adv` und `tun` (für fastd) liegen dort in-tree, es
  muss nichts gebaut werden.
- root per `sudo`.
- Ausgehendes UDP zu den Brokern bzw. fastd-Servern der Communities. IPv4
  genügt, auch hinter NAT: beide Tunnelarten bauen von innen auf und halten
  die Sitzung per Keepalive offen.
- Eine öffentliche Adresse für den Webteil, oder einen Proxy davor.
- Für 48 Domains mit Zeitreihen und Grafana: 2 CPUs, gut 2 GB RAM. Den
  Spitzenbedarf macht der `npm install` des meshviewer.

## Die Schichten

| Schicht | Skript | Was danach läuft |
| --- | --- | --- |
| Tunnel und Mesh | `tunnel/einrichten.sh` | je Domain `karte-en-tunnel@<code>` (Tunneldigger oder fastd), Watchdog |
| Collector | `sammler/einrichten.sh` | je Community `yanic@<community>`, Adressbuch, Clientzählung |
| Web | `web/einrichten.sh` | meshviewer, nginx mit je Community einer Gesamt- und je Domain einer Ortskarte |
| Zeitreihen (optional) | `zeitreihe/einrichten.sh` | VictoriaMetrics, Grafana, `/nf/prom/` |
| UniFi (optional) | `sammler/unifi-einrichten.sh` | `unifi-respondd`, Zuordnung AP → Router |
| Eigene Antwort | `sammler/mesh-announce-einrichten.sh` | `mesh-announce`: map6 als Knoten in jedem Mesh |
| Überwachung | `checkmk/installieren.sh` | Local Checks für den Checkmk-Agenten |
| Maschine | `vm/` | `/etc/network/interfaces`, IPv6-Nachbartabelle; von Hand, siehe `vm/README.md` |

```bash
sudo ./tunnel/einrichten.sh
sudo ./sammler/einrichten.sh
sudo ./web/einrichten.sh
```

Das Arbeitsverzeichnis muss dabei das Projektverzeichnis sein, die Skripte
finden ihre Dateien über den eigenen Pfad.

**Achtung bei laufendem Betrieb:** `tunnel/einrichten.sh` und
`sammler/einrichten.sh` schalten Tunnel bzw. Collector **aller** Einträge in
`domains.conf` ein, auch ruhender Communities (EN, siehe `web/standby.conf`).
Für eine neue Domain oder Community deshalb die Einzelschritte unten nehmen.
`web/einrichten.sh` berücksichtigt `standby.conf` und lädt nginx nur nach
bestandenem `nginx -t` neu. Die neue Site-Datei liegt dann aber schon da:
scheitert der Test, vor dem nächsten Neustart der Maschine beheben, sonst
startet nginx nicht (so am 22.09.2026 knapp vermieden, Hash-Größe).

## Was die Grundskripte tun

### tunnel/einrichten.sh

1. Pakete: `batctl`, Build-Werkzeuge und Bibliotheken für den
   Tunneldigger-Client, `fastd`. Die mitgelieferten fastd-Units bleiben aus.
2. Baut den C-Client aus `wlanslovenija/tunneldigger` auf einen festen Commit
   (`TD_COMMIT` im Skript) nach `/usr/local/bin/tunneldigger`.
3. Legt `/etc/modules-load.d/karte-en.conf` an und lädt die Module.
4. Installiert `/etc/karte-en/domains.conf` und `/etc/karte-en/fastd.conf`,
   Hook, Starter, Unit-Vorlage und Watchdog. Erzeugt je Community mit
   fastd-Domains einmalig einen Schlüssel (`/etc/karte-en/fastd/<community>.secret`,
   öffentlicher Teil in `.pub`).
5. Aktiviert und startet je Domain eine Instanz und zeigt den Stand.

### sammler/einrichten.sh

1. Pakete: `golang-go`, `git`.
2. Baut yanic aus dem Fork `Neanderfunk/yanic` (Zweig `neanderfunk`) nach
   `/usr/local/bin/yanic` und lässt vorher dessen Tests laufen.
3. Legt den Systembenutzer `yanic` und die Ausgabeverzeichnisse an.
4. Je Community: `/etc/yanic-<community>.conf` aus der Domaintabelle
   (`karte-en-yanic-conf`, aus `sammler/yanic-conf.py`) und `yanic@<community>`.
   Die Unit erzeugt die Konfiguration bei jedem Start neu, nur mit den
   batman-Instanzen, die gerade existieren.
5. Adressbuch und Clientzählung für neander.

Die yanic-Konfiguration wird erzeugt, nicht gepflegt. Änderungen gehören in
`yanic-conf.py` (etwa die Abfragegruppe je Community, `ABFRAGE`) oder in die
Domaintabelle.

### web/einrichten.sh

1. Pakete: `nodejs`, `npm`, `git`, `nginx`.
2. Baut den Fork `Neanderfunk/meshviewer` (Zweig `neanderfunk`) nach
   `/var/www/karte-en/meshviewer`. Ein Build für alle Vhosts.
3. Holt `github.com/freifunk/device-pictures` und liefert die Bilder lokal aus.
4. Erzeugt je Vhost eine `config.json` und die nginx-Site
   (`karte-en-konfig`, aus `web/konfig-erzeugen.py`), dazu `conf.d`-Dateien
   (Hash-Größe, Adress-Proxy für die Standortwahl).
5. `nginx -t`, Neuladen, Probe per HTTP.

## Die Domaintabelle

`tunnel/domains.conf` ist die einzige Stelle, an der die Domains stehen. Alles
andere wird daraus erzeugt. Die Spalten erklärt der Kopf der Datei; wichtig:

- `community` ist der Namensraum: `<community>.map.freifunk.space`, eine
  yanic-Instanz je Community.
- `code` ist der Domaincode und zugleich Instanzname der Unit und Suffix der
  Interfaces (`td-<code>`, `bat-<code>`). Über alle Communities eindeutig.
- `id` muss eindeutig sein und bleibt danach unverändert: sie wird zur
  lokalen Tunnel-ID und zum letzten Byte unserer MACs, also zu unserer
  Kennung im fremden Mesh. Vergeben: EN 1-8, Neanderfunk 64 plus
  Domainnummer, Essen 129, Hildesheim 130 (reserviert).
- `host` ist der Namensteil der Ortskarte unter `<community>.map.freifunk.space`.

fastd-Domains stehen zusätzlich in `tunnel/fastd.conf` (Methoden, Peers mit
Schlüsseln), siehe `docs/betrieb.md`, Abschnitt "fastd-Domains".

### Eine Domain oder Community hinzufügen

1. Zeile(n) in `tunnel/domains.conf`, bei fastd auch in `tunnel/fastd.conf`;
   für eine neue Community den Klartextnamen in `NAMEN` in
   `web/konfig-erzeugen.py`. Die Abfragegruppe erst messen
   (`werkzeug/respondd-probe.py`, `ff05::2:1001`, `ff02::2:1001`,
   `ff02::1`) und bei Bedarf in `ABFRAGE` in `sammler/yanic-conf.py`.
2. Auf der VM einzeln einspielen:
   ```bash
   sudo install -m 0644 tunnel/domains.conf tunnel/fastd.conf /etc/karte-en/
   sudo install -m 0755 tunnel/tunnel-start.sh /usr/local/sbin/karte-en-tunnel
   # nur bei einer neuen fastd-Community: Schluessel erzeugen, siehe tunnel/einrichten.sh
   sudo systemctl enable --now karte-en-tunnel@<code>
   sudo install -m 0755 sammler/yanic-conf.py /usr/local/sbin/karte-en-yanic-conf
   sudo systemctl enable --now yanic@<community>      # neue Community
   sudo systemctl restart yanic@<community>           # neue Domain einer bestehenden
   sudo install -m 0755 web/konfig-erzeugen.py /usr/local/sbin/karte-en-konfig
   sudo karte-en-konfig && sudo nginx -t && sudo systemctl reload nginx
   ```
   mesh-announce nimmt die neue batman-Instanz beim nächsten Watchdog-Lauf
   von selbst auf, Checkmk die neue Domain ebenso.
3. Namen auf dem Proxy (twin2) eintragen, adorfer.

## Proxy und Zertifikat

Die VM spricht nur HTTP auf Port 80. TLS und die öffentlichen Namen liegen auf
dem Proxy davor (bei uns `twin2.ffdus.de`, gepflegt von adorfer). Dort braucht
es je Name einen Eintrag und ein Let's-Encrypt-Zertifikat; eingetragen sind
`neander`, `essen`, `einbeck`, `hildesheim` und `en` unter
`map.freifunk.space`. Die Ortskarten `<ort>.neander.map.freifunk.space` kommen
mit dem Umzug von `map.eulenfunk.de`. Ein Name ohne Karte zeigt die
Vorgabeseite der VM mit der Kartenliste.
