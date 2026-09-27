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
