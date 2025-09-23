# 📦 Release Notes – Version 1.0

**Datum:** 23.09.2025  

## 🚀 Hauptfunktionen
- **Rechnungsanalyse aus PDF-Dateien**  
  - Automatisches Auslesen von Rechnungsdaten (Rechnungsnummer, Datum, Beträge, Positionen, Adressen, USt-Infos).  
  - Unterstützung für unterschiedliche Layouts (z. B. Amazon, Handwerker, Behörden, Bauunternehmen).  
  - Vereinheitlichung der Inhalte in einer klaren JSON-Struktur.  

- **Datenexport in verschiedene Formate**  
  - **JSON**: Vollständige strukturierte Daten.  
  - **CSV**: Stammdaten und Positionen getrennt für einfache Tabellen-Weiterverarbeitung.  
  - **XLSX (Excel)**: Export mit mehreren Sheets.  
  - **XML**: Systemintegration durch hierarchische Daten.  
  - **YAML**: Menschlich lesbare Struktur, praktisch für Konfigurationen.  

- **Benutzeroberfläche**  
  - Intuitives Pulldown-Menü zur Auswahl des Ausgabeformats.  
  - Export auf Knopfdruck mit automatischem Download.  
  - Tailwind-basiertes UI: clean, responsiv und erweiterbar.  

- **Beispieldatensatz integriert**  
  - Sammlung echter Rechnungsbeispiele (Amazon, CT-Bauprofi, Schornsteinfeger, Landratsamt Heilbronn, Baupark24, ZAPF).  
  - Einheitliche Testdaten als JSON verfügbar.  

## 🛠️ Verbesserungen & Architektur
- **Konsolidierte Typdefinitionen** (`invoice.d.ts`) für robuste Datenmodelle.  
- **Helper-Funktionen** für CSV- und XML-Generierung.  
- **Lazy Imports** für externe Libraries (`xlsx`, `js-yaml`) → bessere Performance.  
- **Erweiterbare Struktur**: Neue Exportformate oder zusätzliche Rechnungsfelder können leicht ergänzt werden.  

## ⚠️ Bekannte Einschränkungen
- Keine automatische Erkennung neuer/unbekannter Rechnungsformate (manuelle Zuordnung nötig).  
- Komplexe Layouts mit Tabellenverschachtelungen müssen noch angepasst werden.  
- CSV nutzt standardmäßig **Semikolon (;)** als Trennzeichen.  

## 📌 Roadmap für 1.x
- Automatisierte Rechnungsparser (OCR + regelbasierte Extraktion).  
- Direkte API-Schnittstelle für den Export in Drittsysteme (ERP, DATEV, etc.).  
- Möglichkeit, mehrere Rechnungen gebündelt hochzuladen und zu exportieren.  
- PDF-Generierung aus den strukturierten Daten.  
- Erweiterte Validierung (z. B. USt-ID-Prüfung, Plausibilitätschecks).  
