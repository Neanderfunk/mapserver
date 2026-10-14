# Skripte

Alle Skripte des Repos auf einen Blick: was sie tun, unter welchem Namen sie
auf der Karten-VM liegen und wer sie aufruft. Wie es zusammenspielt, steht in
[`betrieb.md`](betrieb.md) und [`einrichtung.md`](einrichtung.md); hier nur
der Wegweiser. Jedes Skript erklärt sich zusätzlich in seinem Kopf.

Installiert wird ausschließlich über die `einrichten.sh` der jeweiligen
Schicht. Ein Skript, das nur von Hand auf der VM liegt, geht bei einer
Neuinstallation verloren; deshalb steht hier, wo es installiert wird.

## Einrichtung

Reihenfolge: Tunnel, Sammler, Web, Zeitreihe, dann die Zusätze. Alle als root
auf der Karten-VM, aus einer aktuellen Arbeitskopie (siehe "Aktualisieren"
in `betrieb.md`).

| Skript | richtet ein |
| --- | --- |
| `tunnel/einrichten.sh` | Tunneldigger und fastd je Domain, batman-Instanzen, Hook, Wächter. **Schaltet alle Domains ein**, auch ruhende (EN); neue Domains einzeln einspielen. |
| `sammler/einrichten.sh` | yanic je Community, Adressbuch, Clientzählung, Verlauf, Ziele für EN. |
| `sammler/mesh-announce-einrichten.sh` | mesh-announce: die VM antwortet in jedem Mesh selbst per respondd. |
| `sammler/unifi-einrichten.sh` | unifi_respondd mit Zuordnung AP → Router; setzt `/etc/unifi_respondd/zugang` voraus. |
| `sammler/controller-tunnel.sh` | WireGuard-Peer an `wg-ctl` für einen UniFi-Controller hinter NAT; gibt die Client-Konfiguration aus. |
| `web/einrichten.sh` | meshviewer-Build aus dem Fork, Gerätebilder, Konfigurationen und nginx-Vhosts. |
| `zeitreihe/einrichten.sh` | VictoriaMetrics, Grafana samt Dashboards, nginx-Zugang `/nf/prom/`. |
| `service/einrichten.sh` | Service-Menü hinter Anmeldung. |
| `checkmk/installieren.sh` | Local checks für den Checkmk-Agenten. |

## Im Betrieb

| Skript | auf der VM als | ausgelöst | Zweck |
| --- | --- | --- | --- |
| `tunnel/tunnel-start.sh` | `karte-en-tunnel` | `karte-en-tunnel@<code>.service` | startet Tunneldigger oder fastd einer Domain, Werte aus `domains.conf` |
| `tunnel/tunnel-hook.sh` | `karte-en-hook` | Tunneldigger-Client | hängt die L2TP-Schnittstelle an batman, ohne Bridge, Clients oder Gateway |
| `tunnel/waechter.sh` | `karte-en-waechter` | `karte-en-waechter.timer`, 5 min | startet Tunnel ohne Schnittstelle oder ohne batman-Nachbarn neu, dazu Collector und mesh-announce |
| `sammler/warten.sh` | `karte-en-warten` | `ExecStartPre` von `yanic@` | wartet, bis die batman-Instanzen da sind |
| `sammler/yanic-conf.py` | `karte-en-yanic-conf` | `ExecStartPre` von `yanic@` | erzeugt `/etc/yanic-<community>.conf` |
| `sammler/sitecodes-ermitteln.py` | `karte-en-sitecodes` | von Hand | misst, welche site_codes die Knoten je Domain melden |
| `sammler/adressbuch.py` | `karte-adressbuch` | `karte-adressbuch@neander.timer`, 2 min | `targets.json` (node_id → Adressen) unter `/nf/` |
| `sammler/clients-zaehlen.py` | `karte-clients` | `karte-clients@neander.timer`, 5 min | Clients und dunkle Knoten je Domain aus der batman-Übersetzungstabelle in die Zeitreihen, `dunkel.json` |
| `sammler/verlauf.py` | `karte-verlauf` | `karte-verlauf.timer`, 5 min | eine Zeile je Domain in `/var/lib/karte/verlauf.csv` |
| `sammler/ziele-ernten.py` | `karte-ziele-ernten` | `karte-ziele.timer`, 30 min (nur EN, ruht) | Unicast-Ziele für Domains, in denen Multicast nicht ankommt |
| `sammler/mesh-announce-conf.py` | `karte-mesh-announce-conf` | `ExecStartPre` von `mesh-announce` | Konfiguration für mesh-announce |
| `sammler/unifi-respondd-conf.py` | `karte-unifi-respondd-conf` | `ExecStartPre` von `unifi-respondd` | Konfiguration für unifi_respondd, weitere Controller aus `/etc/unifi_respondd/controller/` |
| `werkzeug/unifi-offloader.py` | `karte-unifi-offloader` | `karte-unifi-zuordnung.timer`, 5 min | Router je UniFi-AP aus der Übersetzungstabelle |
| `web/konfig-erzeugen.py` | `karte-en-konfig` | `web/einrichten.sh` | `config.json` je Vhost und die nginx-Site |
| `service/service.py` | `/usr/local/lib/karte-service/service.py` | `karte-service.service` | Service-Menü, schreibt Aliase, Entfernen-Aufträge und `overrides.json` |
| `checkmk/local/mapserver`, `local/60/mapserver-domains`, `local/300/mapserver-web` | `/usr/lib/check_mk_agent/local/…` | Checkmk-Agent | Tunnel, Daten, Zeitreihen, UniFi, Controller-Tunnel, Webseiten |

## Einmalig oder bei Bedarf

| Skript | auf der VM als | Zweck |
| --- | --- | --- |
| `sammler/erstsichtung-uebernehmen.py` | `karte-erstsichtung` | Erstsichtung aus einer älteren Karte übernehmen; yanic vorher anhalten |
| `zeitreihe/altkarte-uebernehmen.py` | (aus der Arbeitskopie) | Zeitreihen der alten Karte übernehmen, Label `quelle="altkarte"`; gelaufen am 14.10.2026, siehe `betrieb.md` |
| `tunnel/kennung-wechseln.sh` | `karte-en-kennung-wechseln` (von Hand abgelegt) | neue Kennung (MACs, Broker-Name) für alle Domains, als Probe |
| `tunnel/kennungstest.sh` | `karte-en-kennungstest` (von Hand abgelegt) | einmalige Probe, ob Knoten nach einer Pause wieder antworten |

## Werkzeuge ohne Installation

Aus der Arbeitskopie aufrufen. Wo sie in der Diagnose vorkommen, steht in
[`kartenausfall-diagnose.md`](kartenausfall-diagnose.md) und
[`neue-community.md`](neue-community.md).

| Skript | Zweck |
| --- | --- |
| `werkzeug/site-lesen.py` | site.json aus den Firmware-Images einer Community lesen |
| `werkzeug/domains-erzeugen.py` | aus dem Ergebnis eine `domains.conf` |
| `werkzeug/broker-probe.py` | Tunneldigger-Broker per COOKIE anklopfen, ohne Tunnel |
| `werkzeug/respondd-probe.py` | respondd-Rundruf auf einer batman-Instanz, zählt Antworten; auf der VM zusätzlich als `karte-en-respondd-probe` |
| `zeitreihe/grafana/dashboard-erzeugen.py` | Grafana-Dashboards; aufgerufen von `zeitreihe/einrichten.sh` |
