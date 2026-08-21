# Der Lagerist

Lokales Netzwerk-Tool für Lagerverwaltung per QR-Code.

## Funktionen

- **Host** managt Lagerbestand in SQLite, generiert Session-QR und Objekt-QR-Codes.
- **Clients** (Handys) scannen den Session-QR-Code, loggen sich ein und scannen Objekt-QR-Codes.
- **Echtzeit** via WebSockets: Scans und Änderungen erscheinen sofort beim Host.
- **CSV**-Import/Export für Bestand.
- **Einfache SQLite**-Datenbank.
- **HTTPS-Modus** für Kamera-Zugriff auf Handys.

## Starten

### Windows

1. PowerShell öffnen.
2. In den Projektordner wechseln:
   ```powershell
   cd C:\Users\Schmiddi\Documents\Projekt\der-lagerist
   ```
3. Skript ausführen:
   ```powershell
   .\start.ps1
   ```
4. Die Konsole zeigt die HTTPS-URL an, z.B. `https://192.168.1.10:8000/host`.

Beim ersten Start erzeugt `start.ps1` automatisch ein self-signed HTTPS-Zertifikat in `certs/` für die aktuelle IP.

## Nutzung

1. **Host öffnen** im Browser auf dem Host-PC: `https://<host-ip>:8000/host`
2. **QR-Code für Client-Einlogg** anzeigen lassen.
3. **Client öffnen** auf dem Handy:
   - Entweder die angezeigte URL aufrufen.
   - Oder den QR-Code auf dem Host mit der Handy-Kamera scannen.
4. **Zertifikat akzeptieren** (nur beim ersten Mal):
   - Der Browser warnt wegen des selbstsignierten Zertifikats.
   - In Chrome/Safari: „Fortfahren“ oder „Risiko akzeptieren“.
   - Danach funktioniert die Kamera.
5. **Objekt scannen**: Handy richtet Kamera auf QR-Code am Objekt → Infos werden angezeigt und können bearbeitet werden.

## Hinweise

- Alle Geräte müssen sich im **gleichen Netzwerk** befinden.
- Der Server bindet an `0.0.0.0`, ist also im ganzen lokalen Netzwerk erreichbar.
- Wechselt die IP (anderes Netzwerk), lösche `certs/cert.pem` und `certs/key.pem` und starte neu. Dann wird ein neues Zertifikat erstellt.
- **Ohne mkcert**: Der Browser zeigt eine Warnung wegen des selbstsignierten Zertifikats. Auf dem Handy kannst du entweder „Fortfahren“ wählen oder die `certs/rootCA.pem` installieren.
- **Mit mkcert** (empfohlen): `start.ps1` nutzt automatisch `mkcert`, falls verfügbar. Auf dem Host-PC ist das Zertifikat dann vertrauenswürdig. Für Handys muss die Datei `certs/rootCA.pem` (umbenannt in `rootCA.crt`) in den Android-/iOS-Zertifikatsspeicher importiert werden.
- **Firefox**: Unter Windows wird `mkcert` nicht automatisch in Firefox vertrauenswürdig. Einmalig `setup-firefox.ps1` **als Administrator** ausführen:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\setup-firefox.ps1
  ```
  Danach Firefox neu starten.
- **Client-Session**: Die Verbindungsdaten werden 24 Stunden lokal gespeichert. Der Client verbindet sich automatisch wieder, ohne dass du zum Host musst.
