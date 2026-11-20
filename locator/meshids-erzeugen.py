#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Erzeugt meshids.conf: welche Mesh-ID (802.11s) zu welcher Domain gehoert.

  meshids-erzeugen.py <FirmwareConfigs-Klon> [<ref>] > meshids.conf

Liest die Domain-Dateien des Multidomain-Templates
(templates/multidomain/domains/<code>.conf) am Stand <ref>, Vorgabe
origin/v2025.1.x-next. Die Mesh-IDs folgen meist dem Muster <kuerzel>-mesh,
aber nicht immer (43_bggl hat mesh-bgl), deshalb aus den Dateien statt
geraten.
"""
import re
import subprocess
import sys

repo = sys.argv[1]
ref = sys.argv[2] if len(sys.argv) > 2 else 'origin/v2025.1.x-next'
PFAD = 'templates/multidomain/domains/'


def git(*a):
    return subprocess.run(['git', '-C', repo, *a], check=True, capture_output=True, text=True).stdout


stand = git('log', '-1', '--format=%h %ad', '--date=short', ref).strip()
zeilen = []
for datei in git('ls-tree', '--name-only', ref, PFAD).split():
    code = datei[len(PFAD):-len('.conf')]
    text = git('show', ref + ':' + datei)
    # nur ids in einem mesh = { ... }-Block, nicht etwa die SSID
    ids = sorted(set(re.findall(r"mesh\s*=\s*\{[^}]*?\bid\s*=\s*'([^']+)'", text)))
    for i in ids:
        zeilen.append((i, code))

print('# Mesh-ID -> Domain, erzeugt von meshids-erzeugen.py aus FirmwareConfigs')
print('# %s %s, templates/multidomain/domains/. Nicht von Hand aendern.' % (ref, stand))
print('#')
print('# mesh_id     domain')
for i, code in sorted(zeilen, key=lambda z: z[1]):
    print('%-12s %s' % (i, code))
