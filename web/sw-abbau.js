// SPDX-License-Identifier: BSD-3-Clause
// Wird unter alten Namen der Karte als /sw.js ausgeliefert (konfig-erzeugen.py,
// SW_ABBAU). Ein Browser, der die Karte dort frueher geoeffnet hat, liefert
// sie sonst aus dem Cache des Service Workers weiter, der 301 kommt nie an,
// und die Daten scheitern als fremde Origin: "No connection available"
// (adorfer, 09.11.2026). Der Browser prueft /sw.js bei jedem Aufruf, findet
// dieses Skript, das den alten Worker ersetzt, dessen Cache leert, sich
// abmeldet und die offenen Fenster neu laedt. Dann greift der 301.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) await caches.delete(k);
    await self.registration.unregister();
    for (const c of await self.clients.matchAll({ type: 'window' })) c.navigate(c.url);
  })());
});
