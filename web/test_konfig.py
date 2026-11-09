#!/usr/bin/env python3
"""Tests fuer den Startausschnitt in konfig-erzeugen.py:  python3 -m pytest web/"""
import importlib.util
import json
import os

spec = importlib.util.spec_from_file_location('konfig', os.path.join(os.path.dirname(__file__), 'konfig-erzeugen.py'))
konfig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(konfig)


def haufen(la, lo, anzahl, streuung=0.05):
    """anzahl Punkte in einem Raster um la/lo, Abstand weit unter 25 km"""
    return [(la + streuung * (i % 5) / 4, lo + streuung * (i // 5) / 4) for i in range(anzahl)]


def test_einzelne_ausreisser_fallen_raus():
    orte = haufen(51.2, 6.9, 90) + [(39.55, 2.63), (39.55, 2.63), (53.29, 12.8)]
    kern = konfig.kern(orte)
    assert len(kern) == 90
    assert all(la > 51 for la, _ in kern)


def test_grosse_zweite_gruppe_bleibt():
    # wie das Siegerland: weit weg, aber gut ein Zehntel der Knoten
    orte = haufen(51.2, 6.9, 80) + haufen(50.9, 8.0, 15)
    assert len(konfig.kern(orte)) == 95


def test_kette_haelt_zusammen():
    # Punkte je 20 km auseinander bilden eine Gruppe, auch ueber 100 km
    orte = [(51.0 + i * 20 / 111.2, 7.0) for i in range(6)]
    assert len(konfig.kern(orte)) == 6


def test_wenige_punkte_unveraendert():
    orte = [(51.2, 6.9), (39.5, 2.6)]
    assert konfig.kern(orte) == orte


def test_rahmen_ohne_null_island_und_ausreisser(tmp_path):
    knoten = [{'location': {'latitude': la, 'longitude': lo}} for la, lo in haufen(51.2, 6.9, 30)]
    knoten += [{'location': {'latitude': 0.0, 'longitude': 0.0}},
               {'location': {'latitude': 39.55, 'longitude': 2.63}}, {}]
    datei = tmp_path / 'meshviewer.json'
    datei.write_text(json.dumps({'nodes': knoten}))
    (nord, west), (sued, ost) = konfig.rahmen(str(datei))
    assert 51.1 < sued < nord < 51.3
    assert 6.8 < west < ost < 7.0


def test_rahmen_ohne_datei_gibt_vorgabe(tmp_path):
    assert konfig.rahmen(str(tmp_path / 'fehlt.json')) == [[51.52, 7.05], [51.20, 7.55]]


def test_weitere_namen(tmp_path):
    p = tmp_path / 'namen.conf'
    p.write_text('# Kommentar\nneander/alle  a.example b.example  # Rest\n\n'
                 'neander/alle *.c.example\nkaputt\n')
    assert konfig.weitere_namen(str(p)) == ({'neander/alle': ['a.example', 'b.example', '*.c.example']}, {})


def test_weitere_namen_umleiten(tmp_path):
    p = tmp_path / 'namen.conf'
    p.write_text('neander/alle ziel.example\nneander/alle umleiten alt.example *.alt.example\n')
    assert konfig.weitere_namen(str(p)) == ({'neander/alle': ['ziel.example']},
                                             {'neander/alle': ['alt.example', '*.alt.example']})


def test_weitere_namen_ohne_datei(tmp_path):
    assert konfig.weitere_namen(str(tmp_path / 'fehlt.conf')) == ({}, {})


def test_gruppen(tmp_path):
    p = tmp_path / 'gruppen.conf'
    p.write_text('# Kommentar\nneander lvr 11_lvr,31_lvrno Freifunk LVR-HPH\nkaputt zeile\n')
    assert konfig.gruppen(str(p)) == [('neander', 'lvr', ['11_lvr', '31_lvrno'], 'Freifunk LVR-HPH')]


def test_statistik_links_sammelkarte():
    alle = [{'code': '11_lvr', 'host': 'lvr-hph'}, {'code': '31_lvrno', 'host': 'lvr-hph-nordost'}]
    href = konfig.statistik_links('neander/lvr', alle)[0]['href']
    assert 'var-domain=11_lvr&var-domain=31_lvrno' in href
    assert '$__all' in konfig.statistik_links('neander/alle', alle)[0]['href']
    assert 'var-domain=11_lvr' in konfig.statistik_links('neander/lvr-hph', alle)[0]['href']


# Kopf aus dem meshviewer-Build (Stand 13.2.0), gekuerzt
BUILD_KOPF = '''<!doctype html>
<html itemscope itemtype="http://schema.org/WebPage">
  <head>
    <meta charset="utf-8" />
    <meta itemprop="name" content="Meshviewer" />
    <meta
      name="description"
      itemprop="description"
      content="Knotenkarte - Zeigt alle Knoten"
    />
    <meta name="twitter:card" content="summary" />
    <meta name="og:title" content="Meshviewer" />
    <meta
      name="og:description"
      content="Meshviewer Knotenkarte - Zeigt alle Knoten"
    />
    <meta name="og:site_name" content="Meshviewer" />
    <meta name="og:type" content="website" />
    <title>Meshviewer - loading...</title>
    <link rel="manifest" href="./manifest.webmanifest">
  </head>
<body></body></html>'''


def test_kopf_ersetzen_ohne_bild():
    html = konfig.kopf_ersetzen(BUILD_KOPF, 'Neanderfunk-Karte', 'Neanderfunk', 'Text & mehr',
                                'https://karte.neanderfunk.de/')
    assert 'Meshviewer' not in html
    assert html.count('<title>') == 1 and '<title>Neanderfunk-Karte</title>' in html
    assert '<meta property="og:title" content="Neanderfunk-Karte" />' in html
    assert '<meta property="og:url" content="https://karte.neanderfunk.de/" />' in html
    assert 'content="Text &amp; mehr"' in html
    assert html.count('twitter:card') == 1 and 'content="summary"' in html
    assert 'og:image' not in html
    assert '<meta charset="utf-8" />' in html and 'rel="manifest"' in html
    assert html.index('mapserver:vorschau') < html.index('</head>')


def test_kopf_ersetzen_mit_bild():
    html = konfig.kopf_ersetzen(BUILD_KOPF, 'K', 'N', 'T', 'https://k/',
                                ('https://k/vorschau.png', 1200, 630), 'Alt')
    assert '<meta property="og:image" content="https://k/vorschau.png" />' in html
    assert 'og:image:width" content="1200"' in html
    assert 'content="summary_large_image"' in html


def test_png_groesse_und_vorschaubild(tmp_path):
    png = (b'\x89PNG\r\n\x1a\n' + b'\x00\x00\x00\x0dIHDR' + (1200).to_bytes(4, 'big')
           + (630).to_bytes(4, 'big') + b'\x08\x06\x00\x00\x00')
    (tmp_path / 'neander.png').write_bytes(png)
    (tmp_path / 'kaputt.png').write_bytes(b'kein png')
    assert konfig.png_groesse(tmp_path / 'neander.png') == (1200, 630)
    assert konfig.png_groesse(tmp_path / 'kaputt.png') is None
    assert konfig.vorschaubild('neander/lvr', tmp_path).endswith('neander.png')
    (tmp_path / 'neander-lvr.png').write_bytes(png)
    assert konfig.vorschaubild('neander/lvr', tmp_path).endswith('neander-lvr.png')
    assert konfig.vorschaubild('essen/alle', tmp_path) is None


def test_manifest_ersetzen():
    m = json.loads(konfig.manifest_ersetzen('{"name":"Meshviewer","lang":"en","icons":[1]}',
                                            'Neanderfunk-Karte', 'Karte', 'T'))
    assert m['name'] == 'Neanderfunk-Karte' and m['short_name'] == 'Karte'
    assert m['lang'] == 'de' and m['icons'] == [1]


def test_alte_namen_bauen_service_worker_ab():
    # Ohne eigenes /sw.js haelt der alte Service Worker die Karte unter dem
    # alten Namen fest, der 301 kommt nie an (09.11.2026)
    for vorlage in (konfig.NAMENSWECHSEL, konfig.UMLEITUNG):
        conf = vorlage % {'swabbau': konfig.SW_ABBAU, 'titel': 't', 'namen': 'alt.example',
                          'fqdn': 'alt.example', 'ziel': 'neu.example', 'grund': 'g',
                          'community': 'neander'}
        assert 'location = /sw.js' in conf
        assert conf.index('location = /sw.js') < conf.index('location / {')
    assert os.path.exists(os.path.join(os.path.dirname(__file__), 'sw-abbau.js'))
