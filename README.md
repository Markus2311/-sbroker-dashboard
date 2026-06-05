# 📈 S Broker Depot Dashboard

Streamlit-Dashboard zur Analyse eines S Broker Depots mit historischer Bewertung,
echtem Piotroski F-Score, Wertentwicklung und Live-News.

## Features

- 🏦 **Mehrwährungs-Handling**: Live-FX über yfinance, frei wählbare Basiswährung
- 🧮 **Echter Piotroski F-Score**: 9 Bilanzkriterien (Profitabilität, Leverage, Effizienz)
- 📊 **Historischer KGV-Vergleich**: 5-Jahres-Median aus echten Kursdaten
- 📈 **Wertentwicklung**: Normierter 12-Monats-Chart aller Positionen
- 📰 **Live-News**: Top-Meldungen je Position (Yahoo Finance)
- 🏭 **Sektor-Allokation**: Automatische Klassifikation
- 📂 **Robuster CSV-Import**: Erkennt Separator, Encoding, deutsches Zahlenformat (1.234,56), ISIN → Ticker

## Lokal starten

```bash
pip install -r requirements.txt
streamlit run app.py
```

Browser öffnet sich unter `http://localhost:8501`.

## Auf Streamlit Cloud deployen (kostenlos)

1. **GitHub-Repository** anlegen (privat empfohlen)
2. `app.py` und `requirements.txt` hochladen
3. Auf [share.streamlit.io](https://share.streamlit.io) mit GitHub einloggen
4. **Create app** → Repo, Branch (`main`), Hauptdatei (`app.py`) wählen
5. **Deploy** klicken — nach 1–2 Minuten ist das Dashboard online

## S Broker CSV Export

S Broker → Anmelden → **Depotübersicht** → **Export** → CSV.

Die App erkennt automatisch:
- Separator (`;`, `,`, Tab)
- Encoding (UTF-8, Windows-1252, Latin-1)
- Deutsches Zahlenformat: `1.234,56` → `1234.56`
- Spaltennamen: WKN, ISIN, Bezeichnung, Stück, Einstandskurs, Währung

Wenn der S Broker nur ISIN/WKN ausgibt, mappt die App auf Yahoo-Ticker.
Fehlt eine ISIN im internen Mapping, einfach das Dict `ISIN_TO_TICKER`
in `app.py` ergänzen:

```python
ISIN_TO_TICKER = {
    "DE000XYZ1234": "YHOO.DE",
    ...
}
```

## Bekannte Einschränkungen

- **Yahoo Finance** ist die Datenquelle: nicht jeder S Broker-Titel ist abrufbar
  (manche Fonds, kleine deutsche Werte). Fehler werden in einer Diagnose-Box angezeigt.
- **Piotroski F-Score** funktioniert nur für Aktien mit veröffentlichten Bilanzen.
  ETFs, Krypto und Anleihen geben hier `—` zurück.
- **Historisches KGV** ist vereinfacht: aktuelles EPS × historische Kurse.
  Eine exakte EPS-Historie ist über yfinance nicht zuverlässig verfügbar.
- **Caching**: Daten werden 1 Stunde gecacht. Für tagesaktuelle Werte:
  Streamlit-Menü oben rechts → **Clear cache** → **Rerun**.

## Datenschutz

Bei Deployment auf Streamlit Cloud:
- **Private** Repo wählen, wenn die CSV nicht öffentlich werden soll
- CSV wird nur in der laufenden Session verarbeitet, nicht gespeichert
- Bei sensiblen Daten besser lokal betreiben

## Haftungsausschluss

Keine Anlageberatung. Yahoo-Finance-Daten ohne Gewähr.
Eigene Recherche unerlässlich.
