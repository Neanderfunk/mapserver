# Eigene Gerätebilder

Fotos oder Zeichnungen für Modelle, die
[freifunk/device-pictures](https://github.com/freifunk/device-pictures) nicht
hat. `web/einrichten.sh` kopiert `*.svg` und `*.jpg` von hier nach
`pictures-eigen/` auf der Karten-VM; nginx liefert sie unter
`/pictures-svg/<modell>.svg` aus, wenn device-pictures kein Bild hat.

- **Dateiname**: Modellname, wie ihn der Knoten meldet, klein, alles außer
  `a-z`, `0-9`, `.` und `-` wird zu `-`, ohne Bindestrich am Anfang und Ende
  (meshviewer `{MODEL_NORMALIZED}`). "Cudy WR3000E v1" wird
  `cudy-wr3000e-v1.jpg`.
- **Format**: JPG, freigestellt auf weißem Grund, etwa 400 × 400 Pixel,
  unter 50 KB. SVG geht auch, dann **mit `viewBox`**: Das Knotenfenster
  zeigt Bilder 150 px hoch, ohne `viewBox` schneidet der Browser ein SVG ab,
  statt es zu verkleinern (TOTOLINK X5000R, 21.10.2026: rechte Antenne und
  unterer Rand fehlten).
- **Lizenz**: eigene Fotos CC BY-SA 4.0, Urheber in die Metadaten der Datei.
  Fremde Bilder nur mit geklärter Lizenz.

Welche Modelle fehlen: Tabelle in der Router-Werkstatt,
`docs/geraetefotos.md`.
