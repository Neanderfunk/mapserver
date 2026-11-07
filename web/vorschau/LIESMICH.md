# Vorschaubilder

Bild für die Linkvorschau (Mastodon, Messenger) je Karte, eingebunden als
`og:image` von `konfig-erzeugen.py`:

- `<community>-<ort>.png`, etwa `neander-lvr.png`, sonst
- `<community>.png`, etwa `neander.png` (gilt dann für alle Karten der
  Community), sonst keins.

Alt-Text (`og:image:alt`) in einer Textdatei gleichen Namens daneben, etwa
`neander.txt`; ohne sie ein allgemeiner.

`neander.png`: Content-Session, freigegeben von adorfer 07.11.2026. Quelle
mit Bauskript und SVG in router-werkstatt,
`werbematerial/2026_vorschaubild_karte/` (Commit e03f93d, mit optipng verkleinert). Gilt mangels
eigenem Bild auch für die LVR-Karte, obwohl darauf karte.neanderfunk.de
steht.

Nur PNG, Querformat, am besten 1200 x 630. Kein SVG, Mastodon nimmt es
nicht. Keine Knotennamen oder MACs im Bild.
