# VM-Konfiguration

Dateien, die auf der Karten-VM ausserhalb des Projekts liegen, aber zu ihm
gehoeren, weil ihr Zustand den Betrieb entscheidet.

| Datei | Ziel |
| --- | --- |
| `interfaces` | `/etc/network/interfaces` |
| `sysctl-neighbours.conf` | `/etc/sysctl.d/90-karte-neighbours.conf`, danach `sysctl --system` |

Die Begruendung steht jeweils im Kopf der Datei. Kurz: die geerbte Fassung
liess ifupdown2 einen DHCPv6-Client starten, der endlos wartete, wodurch die
oeffentliche IPv6-Adresse nach einem Neustart fehlte.

Ausspielen von Hand, das ist kein Automatismus:

```bash
sudo cp -a /etc/network/interfaces /etc/network/interfaces.$(date +%F)
sudo install -m 0644 interfaces /etc/network/interfaces
sudo ifquery --check ens18
```

Wirksam wird es beim naechsten Neustart. Wer es sofort will, braucht einen
Weg in die Maschine, der nicht ueber ens18 laeuft.
