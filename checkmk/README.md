# checkmk

Local checks fuer die Freifunk-Rechner des Neanderfunk. Hier liegt der Code,
auf den Rechnern liegt nur eine Kopie.

Wir ueberwachen alles ueber Local checks, nicht ueber eigene Agenten-Plugins
oder aktive Checks: ein Skript, das seine Zeilen selbst ausgibt, ist auf dem
Rechner nachvollziehbar und laesst sich von Hand aufrufen.

## Verzeichnis

Das Verzeichnis `local/` bildet die Struktur des Agenten ab:

```
local/<name>              laeuft bei jedem Agentenlauf
local/<sekunden>/<name>   hoechstens in diesem Abstand (asynchron)
```

Teure Pruefungen gehoeren in das verzoegerte Verzeichnis. Die Konvention
stammt aus [Adorfer/check_mk](https://github.com/Adorfer/check_mk), dort
`mapsrv` fuer den Eulenfunk-Kartenserver.

## Was drin ist

| Datei | Rechner | Dienste |
| --- | --- | --- |
| `local/mapserver` | map6.freifunk.space | Tunnel, Collector, Abschottung, Batman, je Domain einer |
| `local/300/mapserver-web` | map6.freifunk.space | Web, alle fuenf Minuten |

Der Kartenserver selbst liegt eine Ebene hoeher in diesem Repository, die
Hintergruende zu den Zusicherungen in `../docs/hintergrund.md`.

## Ausspielen

```bash
sudo ./installieren.sh              # alles
sudo ./installieren.sh 'mapserver*' # nur den Kartenserver
```

Danach laeuft ein Probelauf und zeigt die Ausgabezeilen.

## Format

Eine Zeile je Dienst:

```
<zustand> <dienstname> <metrik>=<wert>;<warn>;<crit>|<metrik2>=… <Klartext>
```

`<zustand>` ist 0, 1, 2 oder 3, oder `P`, wenn Checkmk den Zustand aus den
Schwellwerten ableiten soll. Untere Schwellen werden als Bereich geschrieben,
also `knoten_online=527;50:;1:` fuer "warn unter 50, crit unter 1".

Der Klartext soll ohne Grafik verstaendlich sein: er steht in der
Benachrichtigung, und wer sie nachts liest, hat kein Dashboard offen.
