# Einrichtung

Von einer leeren VM zur laufenden Karte. Drei Schichten, drei Skripte, in
dieser Reihenfolge.

## Voraussetzungen

- Debian 13 (trixie), getestet mit Kernel 6.12. Die Module `l2tp_eth`,
  `l2tp_netlink` und `batman_adv` liegen dort in-tree, es muss nichts gebaut
  werden.
- root per `sudo`.
- Ausgehendes UDP zu den Brokern der Zielgemeinschaft. IPv4 genügt, auch
  hinter NAT: Tunneldigger baut von innen auf und hält die Sitzung per
  Keepalive offen.
- Eine öffentliche Adresse für den Webteil, oder einen Proxy davor.
- Etwa 1 GB RAM und 5 GB Platte. Die laufende Installation braucht spürbar
  weniger, der Spitzenbedarf entsteht beim `npm install` des meshviewer.

## Die drei Schichten

| Schicht | Skript | Was danach läuft |
| --- | --- | --- |
| Tunnel und Mesh | `tunnel/einrichten.sh` | acht `karte-en-tunnel@<code>` |
| Collector | `sammler/einrichten.sh` | `yanic.service` |
| Web | `web/einrichten.sh` | nginx mit neun Vhosts |

Alle drei sind idempotent und können wiederholt laufen.

```bash
sudo ./tunnel/einrichten.sh
sudo ./sammler/einrichten.sh
sudo ./web/einrichten.sh
```

Das Arbeitsverzeichnis muss dabei das Projektverzeichnis sein, die Skripte
finden ihre Dateien über den eigenen Pfad.

## Was die Skripte tun

### tunnel/einrichten.sh

1. Pakete: `batctl`, `cmake`, `build-essential`, `libnl-3-dev`,
   `libnl-genl-3-dev`, `libasyncns-dev`.
2. Baut den C-Client aus `wlanslovenija/tunneldigger` auf einen festen Commit
   (`TD_COMMIT` im Skript) nach `/usr/local/bin/tunneldigger`.
3. Legt `/etc/modules-load.d/karte-en.conf` an und lädt die drei Module.
4. Installiert:
   - `/etc/karte-en/domains.conf` (die Domaintabelle, einzige Quelle)
   - `/usr/local/sbin/karte-en-hook` (aus `tunnel/tunnel-hook.sh`)
   - `/usr/local/sbin/karte-en-tunnel` (aus `tunnel/tunnel-start.sh`)
   - `/etc/systemd/system/karte-en-tunnel@.service`
5. Aktiviert und startet je Domain eine Instanz und zeigt den Stand.

### sammler/einrichten.sh

1. Pakete: `golang-go`, `git`.
2. Baut yanic aus `codeberg.org/FreifunkBremen/yanic` auf den Tag in
   `YANIC_TAG` nach `/usr/local/bin/yanic`.
3. Legt den Systembenutzer `yanic` an und die Ausgabeverzeichnisse unter
   `/var/www/karte-en/sites/<host>/data`.
4. Erzeugt `/etc/yanic.conf` aus der Domaintabelle
   (`/usr/local/sbin/karte-en-yanic-conf`, aus `sammler/yanic-conf.py`).
5. Startet `yanic.service`.

`/etc/yanic.conf` wird erzeugt, nicht gepflegt. Änderungen gehören in
`yanic-conf.py` oder in die Domaintabelle.

### web/einrichten.sh

1. Pakete: `nodejs`, `npm`, `nginx`.
2. Klont und baut `github.com/freifunk/meshviewer` (Zweig `main`) und legt das
   Ergebnis nach `/var/www/karte-en/meshviewer`. Ein Build für alle Vhosts.
3. Holt `github.com/freifunk/device-pictures` und liefert die Bilder lokal aus.
4. Erzeugt je Vhost eine `config.json` und die nginx-Site
   (`/usr/local/sbin/karte-en-konfig`, aus `web/konfig-erzeugen.py`).
5. Aktiviert die Site und prüft mit einer HTTP-Abfrage.

## Die Domaintabelle

`tunnel/domains.conf` ist die einzige Stelle, an der die Domains stehen. Alles
andere wird daraus erzeugt.

```
# code   ordner        port   id host          prefix6                    prefix4       name
ffha     hagen         10161   7 hagen         2a11:6c6:7000:feed::/64    10.61.0.0/16  Freifunk Hagen
```

- `code` ist der `site_code` aus ihrer `site.json` und zugleich der
  Instanzname der Unit sowie der Filter in der yanic-Ausgabe.
- `id` muss eindeutig sein. Sie wird zur lokalen Tunnel-ID und zum letzten
  Byte der beiden MACs.
- `host` ist der Namensteil unter `<community>.map.freifunk.space`.
- `prefix6` und `prefix4` sind reine Dokumentation, wir belegen daraus nichts.

### Eine Domain hinzufügen

1. Zeile in `tunnel/domains.conf` ergänzen, `id` neu vergeben.
2. Datei auf die VM bringen und installieren:
   ```bash
   sudo install -m 0644 domains.conf /etc/karte-en/domains.conf
   sudo systemctl enable --now karte-en-tunnel@<code>
   sudo /usr/local/sbin/karte-en-yanic-conf > /etc/yanic.conf
   sudo systemctl restart yanic
   sudo /usr/local/sbin/karte-en-konfig && sudo nginx -t && sudo systemctl reload nginx
   ```
3. DNS-Name anlegen und ins Zertifikat aufnehmen.

### Eine weitere Community

Der Aufbau ist darauf vorbereitet, aber noch nicht mehrfach belegt. Nötig
wären: eine zweite Domaintabelle, ein zweiter yanic-Abschnitt (oder ein
zweiter Prozess), und in `web/konfig-erzeugen.py` die Konstante

```python
COMMUNITY = 'en'
BASIS = f'{COMMUNITY}.map.freifunk.space'
```

Die Vorgabeseite unter dem VM-Namen listet dann beide auf. Wer das zuerst
anfasst, sollte die Pfade `/etc/karte-en` und `/var/www/karte-en` vorher auf
einen Namen je Community umstellen, sonst vermischt sich das.

## Proxy und Zertifikat

Die VM spricht nur HTTP auf Port 80. TLS und der öffentliche Name liegen auf
dem Proxy davor (bei uns `twin2.ffdus.de`). Dort braucht es:

- einen Vhost je Kartenname, oder einen Wildcard-Vhost für
  `*.en.map.freifunk.space` plus einen für `en.map.freifunk.space` selbst,
- die Namen im Zertifikat. Let's Encrypt kann bis zu 100 Namen in einem
  Zertifikat, das ist für neun Namen der einfachere Weg als ein Wildcard über
  DNS-01. Ein Wildcard deckt außerdem nur eine Ebene ab und nicht den
  Elternnamen.
