"""
S Broker Portfolio Dashboard – konkret auf das Live-Depot zugeschnitten
=======================================================================

Konkretisierungen gegenüber der generischen Version:
- Erkennt das S Broker Export-Format automatisch (4 Metadaten-Zeilen vor Header,
  ISO-8859-1, Semikolon-Separator, 11× duplizierte 'Währung'-Spalte).
- Verwendet die vom S Broker bereits in EUR umgerechneten Werte
  ('Aktuelle Summe', 'Kaufwert') als Primärquelle für Portfolio-Metriken.
  yfinance dient nur noch der Fundamental-Anreicherung (KGV, Piotroski, News).
- ISIN→Yahoo-Ticker-Mapping für alle 73 Positionen des konkreten Depots
  (US-, DE-, CH-, GB-, FR-, NL-, CA-, AU-, HK-, SE-, ZA-, BR-Listings).
- Gattung-Filter (Aktien / Fonds / Zertifikat) für getrennte Analysen.
- Defensives Error-Handling pro Position, Diagnose-Panel für fehlende Tickerdaten.

Hinweis: Keine Anlageberatung. Yahoo-Daten ohne Gewähr.
"""

import io
import re

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf


def _fmt_num(val, decimals=1, fallback="—"):
    """Robustes Zahlenformat: toleriert None, NaN, Strings, Inf, alles."""
    if val is None:
        return fallback
    try:
        f = float(val)
    except (TypeError, ValueError):
        return fallback
    if not np.isfinite(f):  # fängt NaN und ±Inf
        return fallback
    return round(f, decimals)


def _fmt_pct(val, decimals=2, fallback="—", multiplier=1.0):
    """Wie _fmt_num, aber mit Multiplikator (z.B. 100 für Dividenden­rendite)."""
    if val is None:
        return fallback
    try:
        f = float(val) * multiplier
    except (TypeError, ValueError):
        return fallback
    if not np.isfinite(f) or f == 0:
        return fallback
    return round(f, decimals)


# ============================================================
# SEITENKONFIGURATION
# ============================================================
st.set_page_config(
    page_title="S Broker Depot Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📈 S Broker Portfolio- & Zukunfts-Dashboard")
st.caption(
    "S-Broker-Format-Autoerkennung · Native EUR-Werte · "
    "Echter Piotroski F-Score · Historischer KGV-Vergleich · Live-News"
)

# ============================================================
# ISIN → YAHOO TICKER MAPPING
# (Für das konkrete Depot vorbefüllt; bei Bedarf erweitern.)
# ============================================================
ISIN_TO_TICKER = {
    # Krypto-ETP
    "CH0454664001": "BTCE.DE",        # 21Shares Bitcoin ETP (Xetra)
    # US-Listings
    "US00287Y1091": "ABBV",           # AbbVie
    "US01609W1027": "BABA",           # Alibaba ADR
    "US02079K1079": "GOOG",           # Alphabet Class C
    "US0231351067": "AMZN",           # Amazon
    "US03027X1000": "AMT",            # American Tower
    "US04010L1035": "ARCC",           # Ares Capital
    "US1101221083": "BMY",            # Bristol-Myers Squibb
    "US1405011073": "CSWC",           # Capital Southwest
    "US12503M1080": "CBOE",           # Cboe Global Markets
    "US18452B2097": "CLSK",           # CleanSpark
    "US22266T1097": "CPNG",           # Coupang
    "US20459V1052": "GPGI",           # GPGI Inc. (ggf. Fallback nötig)
    "US4270965084": "HTGC",           # Hercules Capital
    "US42824C1099": "HPE",            # Hewlett Packard Enterprise
    "US4385161066": "HON",            # Honeywell
    "US44812J1043": "HUT",            # Hut 8
    "US46284V1017": "IRM",            # Iron Mountain
    "US5024311095": "LHX",            # L3Harris
    "US56035L1044": "MAIN",           # Main Street Capital
    "US5801351017": "MCD",            # McDonald's
    "US6819361006": "OHI",            # Omega Healthcare
    "US70450Y1038": "PYPL",           # PayPal
    "US7134481081": "PEP",            # PepsiCo
    "US7427181091": "PG",             # Procter & Gamble
    "US74460D1090": "PSA",            # Public Storage
    "US7561091049": "O",              # Realty Income
    "US7574683014": "RDHL",           # Redhill Biopharma ADR
    "US81141R1005": "SE",             # Sea Ltd ADR
    "US84265V1052": "SCCO",           # Southern Copper
    "US88160R1014": "TSLA",           # Tesla
    "US91324P1021": "UNH",            # UnitedHealth
    "US9286612067": "VNRX",           # VolitionRx
    "US63253R2013": "KAP.IL",         # Kazatomprom GDR (LSE)
    # Deutsche Listings (Xetra)
    "DE0008404005": "ALV.DE",         # Allianz
    "DE000BAY0017": "BAYN.DE",        # Bayer
    "DE0005557508": "DTE.DE",         # Deutsche Telekom
    "DE0008402215": "HNR1.DE",        # Hannover Rück
    "DE0008430026": "MUV2.DE",        # Münchener Rück
    # Schweizer Listings
    "CH0038863350": "NESN.SW",        # Nestlé
    "CH0012005267": "NOVN.SW",        # Novartis
    "CH0012032113": "ROG.SW",         # Roche
    "CH0011075394": "ZURN.SW",        # Zurich Insurance
    # UK Listings (LSE)
    "GB0002875804": "BATS.L",         # British American Tobacco
    "GB00BN7SWP63": "GSK.L",          # GSK
    "GB00BDR05C01": "NG.L",           # National Grid
    "GB0007188757": "RIO.L",          # Rio Tinto
    # Französische Listings (Euronext Paris)
    "FR0000121014": "MC.PA",          # LVMH
    "FR0000120693": "RI.PA",          # Pernod Ricard
    # Niederlande (Euronext Amsterdam)
    "NL0015000IY2": "UMG.AS",         # Universal Music Group
    "NL0011683594": "TDIV.AS",        # VanEck Morningstar DM Dividend
    # Kanada (Toronto / NYSE)
    "CA11271J1075": "BN",             # Brookfield Corp (NYSE)
    "CA29250N1050": "ENB",            # Enbridge (NYSE)
    "CA3039011026": "FFH.TO",         # Fairfax Financial
    "CA3495531079": "FTS.TO",         # Fortis
    "CA4339211035": "HIVE",           # HIVE Digital (NASDAQ)
    "CA8787422044": "TECK",           # Teck Resources Cl.B (NYSE)
    "CA9628791027": "WPM",            # Wheaton Precious Metals (NYSE)
    # Australien (ASX)
    "AU000000CUV3": "CUV.AX",         # Clinuvel
    "AU000000PLS0": "PLS.AX",         # Pilbara Minerals
    # Hong Kong / China
    "KYG217651051": "0001.HK",        # CK Hutchison
    "KYG4124C1096": "GRAB",           # Grab Holdings (NASDAQ ADR)
    "KYG875721634": "0700.HK",        # Tencent
    "HK0882007260": "0882.HK",        # Tianjin Development
    "CNE1000003X6": "2318.HK",        # Ping An H-shares
    "BMG507361001": "J36.SI",         # Jardine Matheson (SGX)
    # Brasilien (NYSE ADR Variante)
    "BRPETRACNPR6": "PBR-A",          # Petrobras Preferred ADR
    "BRVALEACNOR0": "VALE",           # Vale ADR
    # Südafrika
    "ZAE000259701": "SBSW",           # Sibanye-Stillwater ADR
    # Schweden
    "SE0018538068": "VER.ST",         # Verve Group
    # Irland / ETFs
    "IE00075IVKF9": "URNJ.L",         # Sprott Junior Uranium Miners (LSE)
    "IE00BD45KH83": "EIMI.L",         # iShares Core MSCI EM IMI (LSE)
    "IE00B14X4T88": "IAPD.L",         # iShares Asia Pac Div (LSE)
}


# ============================================================
# CSV-PARSING
# ============================================================

def parse_german_number(val):
    """Wandelt deutsche Zahlenformate (1.234,56) in float."""
    if pd.isna(val) or val == "":
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lstrip("+")  # S Broker prefixt "+"-Zeichen bei Performance
    s = re.sub(r"[€$£\s]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return np.nan


def decode_bytes(file_bytes):
    """Versucht mehrere Encodings (S Broker exportiert in ISO-8859-1)."""
    for encoding in ["iso-8859-1", "cp1252", "utf-8", "latin-1"]:
        try:
            return file_bytes.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, None


def find_header_row(text, sep=";"):
    """Findet die Header-Zeile (S Broker hat 4 Metadaten-Zeilen davor)."""
    for i, line in enumerate(text.split("\n")[:15]):
        # Header enthält typischerweise 'ISIN' UND 'WKN' (S Broker)
        # oder mind. 'Name'/'Bezeichnung' UND 'Anzahl'/'Stück'
        line_lower = line.lower()
        if "isin" in line_lower and "wkn" in line_lower:
            return i
        if ("name" in line_lower or "bezeichnung" in line_lower) and (
            "stück" in line_lower or "stueck" in line_lower or "anzahl" in line_lower
        ):
            return i
    return 0  # Fallback: erste Zeile


def is_sbroker_format(text):
    """Erkennt S Broker Exporte am charakteristischen Header."""
    first_line = text.split("\n", 1)[0].lower()
    return "depotübersicht" in first_line or "depotuebersicht" in first_line


def load_sbroker_csv(file_bytes):
    """S Broker spezifischer Loader: 4 Meta-Zeilen, ; getrennt, ISO-8859-1, EUR-Werte."""
    text, encoding = decode_bytes(file_bytes)
    if text is None:
        return None, "Datei konnte nicht dekodiert werden."

    header_row = find_header_row(text)
    try:
        df = pd.read_csv(
            io.StringIO(text), sep=";", skiprows=header_row,
            dtype=str, on_bad_lines="skip",
        )
    except Exception as e:
        return None, f"CSV-Parser-Fehler: {e}"

    # Mapping auf einheitliche Spalten
    out = pd.DataFrame()
    out["Name"] = df["Name"].astype(str).str.strip()
    out["ISIN"] = df["ISIN"].astype(str).str.strip()
    out["WKN"] = df.get("WKN", pd.Series([""] * len(df))).astype(str).str.strip()
    out["Gattung"] = df.get("Gattung", pd.Series(["Aktie"] * len(df))).fillna("Aktie")
    out["Anzahl"] = df["Nominal / Stück"].map(parse_german_number)
    out["Kaufkurs"] = df["Kaufkurs"].map(parse_german_number)
    out["Aktueller Kurs"] = df["Aktueller Kurs"].map(parse_german_number)
    # S Broker liefert die Summen schon EUR-konvertiert
    out["Marktwert (EUR)"] = df["Aktuelle Summe"].map(parse_german_number)
    out["Kaufwert (EUR)"] = df["Kaufwert"].map(parse_german_number)
    out["G/V abs (EUR)"] = df["Gesamterfolg abs."].map(parse_german_number)
    out["Performance %"] = df["Gesamterfolg rel. [%]"].map(parse_german_number)
    # Yahoo-Ticker aus ISIN ableiten
    out["Ticker"] = out["ISIN"].map(lambda x: ISIN_TO_TICKER.get(x, x))
    return out, encoding


def load_generic_csv(file_bytes):
    """Fallback für Nicht-S-Broker-CSVs (alte Logik)."""
    text, encoding = decode_bytes(file_bytes)
    if text is None:
        return None, "Datei konnte nicht dekodiert werden."

    sample = "\n".join(text.split("\n")[:5])
    sep_counts = {s: sample.count(s) for s in [";", ",", "\t", "|"]}
    sep = max(sep_counts, key=sep_counts.get) if max(sep_counts.values()) > 0 else ","

    try:
        df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, on_bad_lines="skip")
    except Exception as e:
        return None, f"CSV-Parser-Fehler: {e}"

    # Heuristik-Mapping (generisch)
    out = pd.DataFrame()
    out["Name"] = df.iloc[:, 0]
    out["ISIN"] = ""
    out["WKN"] = ""
    out["Gattung"] = "Aktie"
    out["Anzahl"] = pd.to_numeric(df.iloc[:, 1] if df.shape[1] > 1 else 1, errors="coerce")
    out["Kaufkurs"] = pd.to_numeric(df.iloc[:, 2] if df.shape[1] > 2 else 0, errors="coerce")
    out["Aktueller Kurs"] = np.nan
    out["Marktwert (EUR)"] = np.nan
    out["Kaufwert (EUR)"] = out["Anzahl"] * out["Kaufkurs"]
    out["G/V abs (EUR)"] = np.nan
    out["Performance %"] = np.nan
    out["Ticker"] = out["Name"]
    return out, encoding


# ============================================================
# MARKTDATEN (yfinance)
# ============================================================

def _safe_get(df, key, year, default=0.0):
    try:
        matches = [k for k in df.index if key.lower() in str(k).lower()]
        if matches:
            val = df.loc[matches[0], year]
            return float(val) if pd.notna(val) else default
    except Exception:
        pass
    return default


def calculate_piotroski(ticker_obj):
    """Echter Piotroski F-Score (0–9)."""
    try:
        fin = ticker_obj.financials
        bs = ticker_obj.balance_sheet
        cf = ticker_obj.cashflow
        if fin.empty or bs.empty or cf.empty or len(fin.columns) < 2:
            return None
        y0, y1 = fin.columns[0], fin.columns[1]
        score = 0
        ni_0 = _safe_get(fin, "net income", y0)
        ni_1 = _safe_get(fin, "net income", y1)
        ta_0 = _safe_get(bs, "total assets", y0)
        ta_1 = _safe_get(bs, "total assets", y1)
        cfo_0 = _safe_get(cf, "operating cash flow", y0) or _safe_get(
            cf, "cash flow from continuing operating", y0
        )
        if ni_0 > 0: score += 1
        if ta_0 > 0 and (ni_0 / ta_0) > 0: score += 1
        if cfo_0 > 0: score += 1
        if cfo_0 > ni_0: score += 1
        ltd_0 = _safe_get(bs, "long term debt", y0)
        ltd_1 = _safe_get(bs, "long term debt", y1)
        if ta_0 > 0 and ta_1 > 0 and (ltd_0 / ta_0) < (ltd_1 / ta_1): score += 1
        ca_0 = _safe_get(bs, "current assets", y0)
        ca_1 = _safe_get(bs, "current assets", y1)
        cl_0 = _safe_get(bs, "current liabilities", y0)
        cl_1 = _safe_get(bs, "current liabilities", y1)
        if cl_0 > 0 and cl_1 > 0 and (ca_0 / cl_0) > (ca_1 / cl_1): score += 1
        sh_0 = _safe_get(bs, "share issued", y0) or _safe_get(bs, "ordinary shares", y0)
        sh_1 = _safe_get(bs, "share issued", y1) or _safe_get(bs, "ordinary shares", y1)
        if sh_1 > 0 and sh_0 <= sh_1 * 1.01: score += 1
        rev_0 = _safe_get(fin, "total revenue", y0)
        rev_1 = _safe_get(fin, "total revenue", y1)
        gp_0 = _safe_get(fin, "gross profit", y0)
        gp_1 = _safe_get(fin, "gross profit", y1)
        if rev_0 > 0 and rev_1 > 0 and (gp_0 / rev_0) > (gp_1 / rev_1): score += 1
        if ta_0 > 0 and ta_1 > 0 and rev_0 > 0 and rev_1 > 0:
            if (rev_0 / ta_0) > (rev_1 / ta_1): score += 1
        return score
    except Exception:
        return None


def calculate_risk_reward(hist_price, risk_free_rate=0.02):
    """Sharpe-ähnliches Chancen-Risiko-Verhältnis aus 1-Jahres-Kurshistorie.
    Returns: (sharpe, annual_return, annual_vol, max_drawdown) — alle als float oder None."""
    try:
        if hist_price is None or hist_price.empty:
            return None, None, None, None
        closes = hist_price["Close"].tail(252)  # letzte ~252 Handelstage = 1 Jahr
        if len(closes) < 30:
            return None, None, None, None
        returns = closes.pct_change().dropna()
        if len(returns) < 30:
            return None, None, None, None

        # Annualisierte Rendite (geometrisch)
        n = len(closes)
        annual_return = ((closes.iloc[-1] / closes.iloc[0]) ** (252.0 / n)) - 1
        # Annualisierte Volatilität
        annual_vol = float(returns.std() * (252 ** 0.5))
        if annual_vol == 0:
            return None, float(annual_return), 0.0, None
        sharpe = (float(annual_return) - risk_free_rate) / annual_vol

        # Max Drawdown (zusätzlich, für Diagnose)
        rolling_max = closes.cummax()
        drawdown = (closes / rolling_max - 1)
        max_dd = float(drawdown.min())

        return float(sharpe), float(annual_return), annual_vol, max_dd
    except Exception:
        return None, None, None, None


def calculate_dividend_growth(ticker_obj):
    """Dividendenwachstums-Analyse: CAGR der letzten 5 Jahre, Streak konsekutiver Steigerungen.
    Returns: dict mit 'cagr_5y' (in %), 'streak' (Jahre), 'score' (0–4), 'max_score'."""
    result = {"cagr_5y": None, "streak": 0, "score": None, "max_score": 0}
    try:
        divs = ticker_obj.dividends
        if divs is None or divs.empty:
            return result

        # Auf Jahressummen aggregieren (manche Firmen zahlen quartalsweise)
        annual = divs.groupby(divs.index.year).sum().sort_index()
        # Letztes Jahr ggf. noch unvollständig → ausschließen, wenn aktuelle Jahresummen
        # unter dem Median der Vorjahre liegen (Heuristik)
        if len(annual) >= 2 and annual.index[-1] >= pd.Timestamp.now().year:
            if annual.iloc[-1] < annual.iloc[:-1].median() * 0.5:
                annual = annual.iloc[:-1]

        if len(annual) < 2:
            return result

        # CAGR über die letzten 5 vollen Jahre (oder so viel wie verfügbar, min 3)
        window = min(5, len(annual))
        if window >= 3:
            recent = annual.tail(window)
            start, end = float(recent.iloc[0]), float(recent.iloc[-1])
            years = window - 1
            if start > 0 and years > 0:
                cagr = ((end / start) ** (1.0 / years) - 1) * 100
                result["cagr_5y"] = float(cagr)

        # Streak: konsekutive Jahre mit Steigerung (vom aktuellsten rückwärts)
        streak = 0
        for i in range(len(annual) - 1, 0, -1):
            if annual.iloc[i] > annual.iloc[i - 1]:
                streak += 1
            else:
                break
        result["streak"] = int(streak)

        # Score 0–4
        score = 0
        max_score = 4
        if result["cagr_5y"] is not None:
            if result["cagr_5y"] >= 10: score += 2
            elif result["cagr_5y"] >= 5: score += 1
            elif result["cagr_5y"] >= 0: score += 0  # Stagnation: 0 Punkte
            # Schrumpfung: negativer Wert, keine Punkte
        if streak >= 5: score += 2
        elif streak >= 3: score += 1

        result["score"] = score
        result["max_score"] = max_score
        return result
    except Exception:
        return result


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ticker_data(ticker):
    """Holt alle relevanten Fundamentaldaten."""
    result = {
        "ticker": ticker, "pe": None, "forward_pe": None, "peg": None,
        "pb": None, "dividend_yield": None, "sector": None, "industry": None,
        "market_cap": None, "beta": None, "rd_ratio": None,
        "piotroski": None, "hist_pe_median": None, "hist_price": None,
        "news": [], "error": None,
        # Neue Felder
        "sharpe": None, "annual_return": None, "annual_vol": None, "max_drawdown": None,
        "div_cagr_5y": None, "div_streak": 0, "div_growth_score": None, "div_growth_max": 0,
    }
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            # Fallback-Test: history
            hist_test = t.history(period="5d")
            if hist_test.empty:
                result["error"] = "Kein Yahoo-Treffer"
                return result

        result["pe"] = info.get("trailingPE")
        result["forward_pe"] = info.get("forwardPE")
        result["peg"] = info.get("pegRatio") or info.get("trailingPegRatio")
        result["pb"] = info.get("priceToBook")
        result["dividend_yield"] = info.get("dividendYield")
        result["sector"] = info.get("sector")
        result["industry"] = info.get("industry")
        result["market_cap"] = info.get("marketCap")
        result["beta"] = info.get("beta")
        result["hist_price"] = t.history(period="5y")

        # F&E-Quote
        try:
            fin = t.financials
            if not fin.empty:
                rd_keys = [k for k in fin.index if "research" in str(k).lower() and "development" in str(k).lower()]
                rev_keys = [k for k in fin.index if str(k).lower() in ("total revenue", "revenue", "totalrevenue")]
                if rd_keys and rev_keys:
                    rd_val = fin.loc[rd_keys[0]].iloc[0]
                    rev_val = fin.loc[rev_keys[0]].iloc[0]
                    if pd.notna(rd_val) and pd.notna(rev_val) and rev_val > 0:
                        result["rd_ratio"] = (rd_val / rev_val) * 100
        except Exception:
            pass

        result["piotroski"] = calculate_piotroski(t)

        # Chancen-Risiko-Verhältnis
        sharpe, ann_ret, ann_vol, max_dd = calculate_risk_reward(result["hist_price"])
        result["sharpe"] = sharpe
        result["annual_return"] = ann_ret
        result["annual_vol"] = ann_vol
        result["max_drawdown"] = max_dd

        # Dividendenwachstum
        div_info = calculate_dividend_growth(t)
        result["div_cagr_5y"] = div_info["cagr_5y"]
        result["div_streak"] = div_info["streak"]
        result["div_growth_score"] = div_info["score"]
        result["div_growth_max"] = div_info["max_score"]

        # Historisches KGV (vereinfacht)
        try:
            eps_ttm = info.get("trailingEps")
            if eps_ttm and eps_ttm > 0 and result["hist_price"] is not None and not result["hist_price"].empty:
                closes = result["hist_price"]["Close"]
                if len(closes) > 0:
                    result["hist_pe_median"] = float((closes / eps_ttm).median())
        except Exception:
            pass

        # News (neues + altes Format)
        try:
            for item in (t.news or [])[:5]:
                content = item.get("content", item)
                title = content.get("title")
                link = (content.get("canonicalUrl") or {}).get("url") or content.get("link") or "#"
                publisher = (content.get("provider") or {}).get("displayName") or content.get("publisher") or ""
                if title:
                    result["news"].append({"title": title, "link": link, "publisher": publisher})
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)
    return result


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.header("⚙️ Konfiguration")
st.sidebar.markdown("---")
st.sidebar.subheader("📂 Depot laden")
uploaded_file = st.sidebar.file_uploader(
    "S Broker CSV-Export",
    type=["csv", "txt"],
    help="S Broker → Depotübersicht → CSV-Export. Format wird automatisch erkannt.",
)

fetch_fundamentals = st.sidebar.checkbox(
    "Fundamentaldaten (Yahoo) laden",
    value=True,
    help="Bei 73 Positionen dauert der erste Lauf ~2–3 Min. Wird 1h gecacht.",
)

# ============================================================
# DEPOT EINLESEN
# ============================================================
if uploaded_file is None:
    st.info(
        "👈 Bitte S Broker CSV in der Sidebar hochladen.\n\n"
        "Erwartet wird das Standard-Format aus *Depotübersicht → Export*."
    )
    st.stop()

raw = uploaded_file.read()

# Format-Detektion
text, enc = decode_bytes(raw)
if text is None:
    st.error("❌ Datei konnte nicht dekodiert werden.")
    st.stop()

if is_sbroker_format(text):
    df_depot, info_msg = load_sbroker_csv(raw)
    format_label = "✅ S Broker Export erkannt"
else:
    df_depot, info_msg = load_generic_csv(raw)
    format_label = "⚠️ Generisches CSV-Format"

if df_depot is None:
    st.error(f"❌ {info_msg}")
    st.stop()

# Bereinigen
df_depot = df_depot.dropna(subset=["Anzahl"])
df_depot = df_depot[df_depot["Anzahl"] > 0].reset_index(drop=True)

st.sidebar.success(f"{format_label} · {len(df_depot)} Positionen · Encoding: {info_msg}")

# Ticker-Mapping-Diagnose
unmapped = df_depot[~df_depot["ISIN"].isin(ISIN_TO_TICKER.keys())]
if len(unmapped) > 0:
    with st.sidebar.expander(f"⚠️ {len(unmapped)} ISIN(s) ohne festes Mapping"):
        for _, r in unmapped.iterrows():
            st.caption(f"`{r['ISIN']}` · {r['Name'][:50]}")

# ============================================================
# KENNZAHLEN OBEN
# ============================================================
total_buy = df_depot["Kaufwert (EUR)"].sum()
total_now = df_depot["Marktwert (EUR)"].sum()
total_pl = total_now - total_buy
total_pl_pct = (total_pl / total_buy * 100) if total_buy > 0 else 0

n_aktien = (df_depot["Gattung"] == "Aktie").sum()
n_fonds = (df_depot["Gattung"] == "Fonds").sum()
n_zerti = (df_depot["Gattung"] == "Zertifikat").sum()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("💼 Depotwert", f"{total_now:,.0f} €".replace(",", "."))
c2.metric("📊 G/V", f"{total_pl:+,.0f} €".replace(",", "."), f"{total_pl_pct:+.2f} %")
c3.metric("💰 Einsatz", f"{total_buy:,.0f} €".replace(",", "."))
c4.metric("🔢 Positionen", f"{len(df_depot)}")
c5.metric(
    "📊 Struktur",
    f"{n_aktien} A",
    f"{n_fonds} F · {n_zerti} Z",
    delta_color="off",
)

st.markdown("---")

# ============================================================
# TOP-WINNER / LOSER
# ============================================================
col_w, col_l = st.columns(2)

with col_w:
    st.subheader("🏆 Top 5 Gewinner (%)")
    top = df_depot.nlargest(5, "Performance %")[["Name", "Marktwert (EUR)", "G/V abs (EUR)", "Performance %"]]
    top = top.rename(columns={"Marktwert (EUR)": "Wert €", "G/V abs (EUR)": "G/V €", "Performance %": "%"})
    st.dataframe(top.round(2), use_container_width=True, hide_index=True)

with col_l:
    st.subheader("📉 Top 5 Verlierer (%)")
    bot = df_depot.nsmallest(5, "Performance %")[["Name", "Marktwert (EUR)", "G/V abs (EUR)", "Performance %"]]
    bot = bot.rename(columns={"Marktwert (EUR)": "Wert €", "G/V abs (EUR)": "G/V €", "Performance %": "%"})
    st.dataframe(bot.round(2), use_container_width=True, hide_index=True)

st.markdown("---")

# ============================================================
# ALLOKATION
# ============================================================
st.subheader("🥧 Asset-Allokation")
col_a, col_b = st.columns(2)

with col_a:
    by_gattung = df_depot.groupby("Gattung")["Marktwert (EUR)"].sum().reset_index()
    fig_g = px.pie(
        by_gattung, values="Marktwert (EUR)", names="Gattung", hole=0.45,
        title="Nach Gattung", color_discrete_sequence=px.colors.qualitative.Set2,
    )
    st.plotly_chart(fig_g, use_container_width=True)

with col_b:
    # Top 15 + Rest
    df_sorted = df_depot.sort_values("Marktwert (EUR)", ascending=False)
    top15 = df_sorted.head(15).copy()
    if len(df_sorted) > 15:
        rest_sum = df_sorted.iloc[15:]["Marktwert (EUR)"].sum()
        top15 = pd.concat([top15, pd.DataFrame([{
            "Name": f"… {len(df_sorted) - 15} weitere",
            "Marktwert (EUR)": rest_sum,
        }])], ignore_index=True)
    fig_t = px.pie(
        top15, values="Marktwert (EUR)", names="Name", hole=0.45,
        title="Top 15 Positionen", color_discrete_sequence=px.colors.qualitative.Set3,
    )
    fig_t.update_traces(textposition="inside", textinfo="percent")
    st.plotly_chart(fig_t, use_container_width=True)

# Performance-Balken
st.subheader("📈 Performance je Position")
df_perf = df_depot.sort_values("Performance %").copy()
fig_bar = px.bar(
    df_perf, x="Performance %", y="Name", orientation="h",
    color="Performance %", color_continuous_scale="RdYlGn",
    color_continuous_midpoint=0, height=max(400, 18 * len(df_perf)),
)
fig_bar.update_layout(yaxis_title="", showlegend=False, coloraxis_showscale=False)
st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# ============================================================
# FUNDAMENTAL-ANREICHERUNG (yfinance)
# ============================================================
market_data = {}
if fetch_fundamentals:
    # Nur gemappte ISINs abrufen (sonst nur Fehler)
    tickers_to_fetch = [
        t for t in df_depot["Ticker"].unique()
        if t in ISIN_TO_TICKER.values()
    ]
    prog = st.progress(0, text=f"Lade Yahoo-Daten für {len(tickers_to_fetch)} Positionen…")
    for i, ticker in enumerate(tickers_to_fetch):
        market_data[ticker] = fetch_ticker_data(ticker)
        prog.progress((i + 1) / max(1, len(tickers_to_fetch)),
                      text=f"Lade {ticker} ({i+1}/{len(tickers_to_fetch)})")
    prog.empty()

    # Fehler-Report
    errors = [(t, d["error"]) for t, d in market_data.items() if d.get("error")]
    if errors:
        with st.expander(f"⚠️ {len(errors)} Yahoo-Fehler"):
            for t, e in errors:
                st.caption(f"`{t}`: {e}")

    # Sektor-Allokation
    df_depot["Sektor"] = df_depot["Ticker"].map(
        lambda x: market_data.get(x, {}).get("sector") or "Unbekannt"
    )
    sector_agg = df_depot.groupby("Sektor")["Marktwert (EUR)"].sum().reset_index().sort_values("Marktwert (EUR)")
    if len(sector_agg) > 1:
        st.subheader("🏭 Sektor-Allokation")
        fig_sec = px.bar(
            sector_agg, x="Marktwert (EUR)", y="Sektor", orientation="h",
            color="Marktwert (EUR)", color_continuous_scale="Blues",
        )
        fig_sec.update_layout(showlegend=False, height=max(300, 30 * len(sector_agg)),
                              coloraxis_showscale=False)
        st.plotly_chart(fig_sec, use_container_width=True)

    # Strategische Tabelle
    st.subheader("🧠 Strategische Analyse (Fundamentaldaten)")
    rows = []
    for _, r in df_depot.iterrows():
        md = market_data.get(r["Ticker"], {})
        pe, hist_pe = md.get("pe"), md.get("hist_pe_median")
        peg, rd, piot = md.get("peg"), md.get("rd_ratio"), md.get("piotroski")

        if pe and hist_pe and hist_pe > 0:
            ratio = pe / hist_pe
            hist_val = "🔴 Über" if ratio > 1.15 else ("🟢 Unter" if ratio < 0.85 else "🟡 Fair")
        else:
            hist_val = "—"

        pts, max_pts = 0, 0
        if peg is not None:
            max_pts += 1
            if 0 < peg < 1.5: pts += 1
        if rd is not None:
            max_pts += 1
            if rd > 7: pts += 1
        if piot is not None:
            max_pts += 1
            if piot >= 6: pts += 1
        if max_pts == 0:
            future = "—"
        elif pts / max_pts >= 0.66:
            future = "🚀 Stark"
        elif pts / max_pts >= 0.33:
            future = "📈 Stabil"
        else:
            future = "⚠️ Schwach"

        # Chancen-Risiko-Verhältnis (Sharpe-Ratio, 1J)
        sharpe = md.get("sharpe")
        if sharpe is not None:
            if sharpe > 1.0: crv_label = f"🟢 {sharpe:+.2f}"
            elif sharpe > 0.5: crv_label = f"🟡 {sharpe:+.2f}"
            elif sharpe > 0: crv_label = f"🟠 {sharpe:+.2f}"
            else: crv_label = f"🔴 {sharpe:+.2f}"
        else:
            crv_label = "—"

        # Dividendenwachstums-Score
        dg_score = md.get("div_growth_score")
        dg_max = md.get("div_growth_max", 0)
        dg_cagr = md.get("div_cagr_5y")
        dg_streak = md.get("div_streak", 0)
        if dg_score is None or dg_max == 0:
            dg_label = "—"
        else:
            # Score 0–4 zu Sternen
            stars = "★" * dg_score + "☆" * (dg_max - dg_score)
            dg_label = f"{stars} ({dg_cagr:+.1f}%, {dg_streak}J)" if dg_cagr is not None else stars

        # KBV (Kurs-Buchwert-Verhältnis) — sektorabhängig, keine fixe Farbe
        pb_label = _fmt_num(md.get("pb"), 2)

        rows.append({
            "Name": r["Name"][:40],
            "Gattung": r["Gattung"],
            "Sektor": md.get("sector") or "—",
            "Wert €": float(r["Marktwert (EUR)"]) if pd.notna(r["Marktwert (EUR)"]) else 0.0,
            "Perf %": _fmt_num(r["Performance %"], 1),
            "KGV": _fmt_num(pe, 1),
            "KGV 5J-Med": _fmt_num(hist_pe, 1),
            "KBV": pb_label,
            "Bewertung": hist_val,
            "PEG": _fmt_num(peg, 2),
            "F&E %": _fmt_num(rd, 1),
            "Piotroski": f"{piot}/9" if piot is not None else "—",
            "Zukunft": future,
            "CRV (Sharpe)": crv_label,
            "Div %": _fmt_pct(md.get("dividend_yield"), 2, multiplier=100),
            "Div-Wachstum": dg_label,
        })
    df_analysis = pd.DataFrame(rows).sort_values("Wert €", ascending=False)
    st.dataframe(df_analysis, use_container_width=True, hide_index=True)

    with st.expander("ℹ️ Interpretation der Kennzahlen"):
        st.markdown("""
**Bewertungs- und Fundamentaldaten:**
- **KGV vs. 5J-Median**: ≥ 15 % darüber = historisch teuer.
- **KBV (Kurs-Buchwert-Verhältnis)**: Marktkapitalisierung / Eigenkapital. **Stark sektorabhängig** — bei Banken/Versicherern (Allianz, Hannover Rück, Münchener Rück) ist KBV 0,8–1,5 normal, KBV < 1 = Aktie unter Substanzwert. Bei Tech-Werten (Microsoft, Apple) ist KBV 10+ normal, weil Bilanz wenig immaterielle Vermögen abbildet. Niemals zwischen Branchen vergleichen.
- **PEG < 1,5**: Klassisch günstig im Verhältnis zum erwarteten Gewinnwachstum.
- **F&E-Quote**: F&E am Umsatz. Tech > 10 %, Konsumgüter < 3 %.
- **Piotroski F-Score (0–9)**: 9 Bilanzkriterien (Profitabilität, Leverage, Effizienz). ≥ 7 stark.

**Chancen-Risiko-Verhältnis (Sharpe-Ratio, 1-Jahres-Basis):**
Annualisierte Rendite minus Risikolos-Zins (2 %) geteilt durch annualisierte Volatilität.
Misst, wie viel zusätzliche Rendite pro Einheit eingegangenes Schwankungsrisiko erzielt wurde.
- 🟢 **> 1,0**: Sehr gut — Rendite schlägt Risiko deutlich
- 🟡 **0,5 – 1,0**: Solide
- 🟠 **0 – 0,5**: Mager
- 🔴 **< 0**: Negative risikobereinigte Rendite (Verlust oder Underperformance Risikolos-Zins)

**Dividendenwachstums-Score (0–4 Sterne):**
Kombination aus zwei Faktoren — je 0–2 Punkte für:
- **CAGR der Dividende (5J)**: ≥ 10 % p. a. → 2 Punkte, ≥ 5 % → 1 Punkt
- **Streak**: konsekutive Jahre mit Dividendenanhebung. ≥ 5 J → 2 Punkte, ≥ 3 J → 1 Punkt

Beispiel `★★★☆ (+8,2%, 4J)`: 3 von 4 Sternen, Dividende wuchs 8,2 % p. a., 4 Jahre konsekutive Steigerungen.

**Ein Gedankenstrich (—)** bedeutet: Yahoo liefert keine verwertbaren Daten (häufig bei ETFs, Zertifikaten, Microcaps, oder weil das Unternehmen gar keine Dividende zahlt).
        """)

    st.markdown("---")

    # News
    st.subheader("📰 News (Top 5 Positionen nach Wert)")
    top_positions = df_depot.nlargest(5, "Marktwert (EUR)")
    for _, r in top_positions.iterrows():
        with st.expander(f"📌 {r['Name']} · {r['Marktwert (EUR)']:,.0f} €".replace(",", ".")):
            news = market_data.get(r["Ticker"], {}).get("news", [])
            if news:
                for n in news:
                    st.markdown(f"**[{n['title']}]({n['link']})**")
                    if n.get("publisher"):
                        st.caption(f"Quelle: {n['publisher']}")
                    st.markdown("")
            else:
                st.write("Keine aktuellen Nachrichten verfügbar.")

# ============================================================
# DETAIL-TABELLE
# ============================================================
with st.expander("📋 Vollständige Depot-Detailansicht"):
    show = df_depot[[
        "Name", "ISIN", "WKN", "Ticker", "Gattung", "Anzahl",
        "Kaufkurs", "Aktueller Kurs", "Kaufwert (EUR)", "Marktwert (EUR)",
        "G/V abs (EUR)", "Performance %",
    ]].copy()
    st.dataframe(show.round(2), use_container_width=True, hide_index=True)

st.markdown("---")
st.caption(
    "⚠️ Keine Anlageberatung. Portfolio-Zahlen aus S Broker CSV (vom Broker EUR-konvertiert). "
    "Fundamentaldaten via Yahoo Finance, ohne Gewähr."
)
