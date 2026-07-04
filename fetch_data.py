#!/usr/bin/env python3
"""
fetch_data.py  —  Refresh Chart Master game data from TwelveData API

Usage:
  TWELVE_DATA_KEY=yourkey python fetch_data.py
  python fetch_data.py --resume      (skip tickers already fetched today)
  python fetch_data.py --ticker AAPL (single ticker)

Output:
  data/<TICKER>.json   compact OHLCV per ticker
  data/manifest.json   index of available tickers with candle counts

TwelveData free tier: 800 credits/day · 8 requests/minute
Runtime for full universe (~120 tickers): ~18 minutes
"""

import os, sys, json, time, datetime, argparse, urllib.request, urllib.parse

API_KEY = os.environ.get('TWELVE_DATA_KEY', '')
BASE_URL = 'https://api.twelvedata.com/time_series'
OUT_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DELAY_S  = 8.0   # 7.5 req/min to stay safely under the 8/min limit

# Game symbol → TwelveData API symbol mapping
# The key is used for the filename; slashes are forbidden on filesystems
TICKERS = {
    # Mega-cap Tech
    'AAPL':'AAPL', 'MSFT':'MSFT', 'GOOGL':'GOOGL', 'AMZN':'AMZN',
    'NVDA':'NVDA', 'META':'META', 'TSLA':'TSLA',
    # Semiconductors
    'AMD':'AMD', 'INTC':'INTC', 'AVGO':'AVGO', 'QCOM':'QCOM',
    'MU':'MU', 'AMAT':'AMAT', 'KLAC':'KLAC', 'LRCX':'LRCX', 'TXN':'TXN', 'ADI':'ADI',
    # Software / Cloud
    'CRM':'CRM', 'ADBE':'ADBE', 'ORCL':'ORCL', 'NOW':'NOW',
    'INTU':'INTU', 'WDAY':'WDAY', 'PLTR':'PLTR', 'SNOW':'SNOW',
    # Cybersecurity / Infrastructure
    'NET':'NET', 'CRWD':'CRWD', 'ZS':'ZS', 'DDOG':'DDOG', 'PANW':'PANW', 'FTNT':'FTNT',
    # Fintech / Crypto-adjacent
    'SQ':'SQ', 'PYPL':'PYPL', 'COIN':'COIN', 'MSTR':'MSTR', 'SHOP':'SHOP', 'MELI':'MELI',
    # Consumer / Retail
    'TGT':'TGT', 'WMT':'WMT', 'COST':'COST', 'SBUX':'SBUX', 'MCD':'MCD', 'NKE':'NKE',
    # Healthcare / Pharma / Biotech
    'UNH':'UNH', 'LLY':'LLY', 'JNJ':'JNJ', 'ABBV':'ABBV',
    'MRK':'MRK', 'PFE':'PFE', 'AMGN':'AMGN', 'MRNA':'MRNA',
    'VRTX':'VRTX', 'REGN':'REGN', 'ISRG':'ISRG', 'DXCM':'DXCM', 'BIIB':'BIIB',
    # Finance / Banks
    'JPM':'JPM', 'BRK-B':'BRK/B', 'V':'V', 'MA':'MA',
    'GS':'GS', 'MS':'MS', 'BAC':'BAC', 'AXP':'AXP', 'BLK':'BLK',
    # Energy
    'XOM':'XOM', 'CVX':'CVX', 'COP':'COP', 'SLB':'SLB', 'MPC':'MPC',
    # Industrials / Aerospace & Defense
    'CAT':'CAT', 'DE':'DE', 'BA':'BA', 'LMT':'LMT', 'RTX':'RTX', 'HON':'HON',
    # Autos / Mobility
    'F':'F', 'GM':'GM', 'UBER':'UBER', 'RIVN':'RIVN',
    # Chinese ADRs
    'BABA':'BABA', 'JD':'JD', 'BIDU':'BIDU', 'PDD':'PDD', 'NIO':'NIO',
    # High-vol / Growth
    'ROKU':'ROKU', 'SNAP':'SNAP', 'RBLX':'RBLX', 'U':'U',
    # Broad Market ETFs
    'SPY':'SPY', 'QQQ':'QQQ', 'IWM':'IWM', 'DIA':'DIA',
    # Sector ETFs
    'SMH':'SMH', 'XLK':'XLK', 'XLE':'XLE', 'XLF':'XLF',
    'XLV':'XLV', 'XLI':'XLI', 'XLY':'XLY', 'XLRE':'XLRE',
    # Alt / Commodity ETFs
    'GLD':'GLD', 'SLV':'SLV', 'USO':'USO', 'TLT':'TLT',
    'HYG':'HYG', 'EEM':'EEM', 'EWJ':'EWJ', 'VNQ':'VNQ',
    # Leveraged / Thematic ETFs
    'SOXL':'SOXL', 'TQQQ':'TQQQ', 'ARKK':'ARKK', 'LABU':'LABU',
    # Crypto (via TwelveData)
    'BTC-USD':'BTC/USD', 'ETH-USD':'ETH/USD',
    # REITs
    'O':'O', 'AMT':'AMT', 'EQIX':'EQIX', 'PLD':'PLD',
}

MIN_CANDLES = 504  # CTX(252) + PLAY(252) — absolute minimum to be playable


def fetch_ticker(api_sym: str) -> list | None:
    """Fetch full daily history from TwelveData. Returns sorted list of candle dicts or None."""
    params = {
        'symbol':     api_sym,
        'interval':   '1day',
        'outputsize': 5000,
        'apikey':     API_KEY,
    }
    url = BASE_URL + '?' + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'chart-master-game/2.0'})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.loads(r.read())
    except Exception as e:
        return None, f'network error: {e}'

    if j.get('status') == 'error':
        return None, j.get('message', 'API error')

    values = j.get('values', [])
    if len(values) < MIN_CANDLES:
        return None, f'only {len(values)} candles (need {MIN_CANDLES})'

    candles = []
    for v in reversed(values):  # TwelveData returns newest-first
        try:
            candles.append([
                v['datetime'][:10],
                round(float(v['open']),  2),
                round(float(v['high']),  2),
                round(float(v['low']),   2),
                round(float(v['close']), 2),
                int(v.get('volume') or 0),
            ])
        except (ValueError, KeyError):
            continue

    if len(candles) < MIN_CANDLES:
        return None, f'after parse: only {len(candles)} valid candles'

    return candles, None


def load_existing_manifest() -> dict:
    path = os.path.join(OUT_DIR, 'manifest.json')
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def write_manifest(results: dict, updated: str):
    """Write manifest.json listing all tickers with their candle counts."""
    manifest = {
        'updated': updated,
        'count':   len(results),
        'tickers': results,  # {game_sym: candle_count}
    }
    path = os.path.join(OUT_DIR, 'manifest.json')
    with open(path, 'w') as f:
        json.dump(manifest, f, separators=(',', ':'))
    print(f'\nManifest written: {path}  ({len(results)} tickers)')


def main():
    parser = argparse.ArgumentParser(description='Fetch Chart Master ticker data')
    parser.add_argument('--resume',  action='store_true', help='Skip tickers with today\'s data')
    parser.add_argument('--ticker',  metavar='SYM',       help='Fetch only this ticker')
    args = parser.parse_args()

    if not API_KEY:
        print('ERROR: TWELVE_DATA_KEY environment variable not set.')
        print('  Set it with: set TWELVE_DATA_KEY=yourkey  (Windows)')
        print('          or:  export TWELVE_DATA_KEY=yourkey  (Linux/Mac)')
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    today     = datetime.date.today().isoformat()
    tickers   = [(args.ticker, TICKERS.get(args.ticker, args.ticker))] if args.ticker else list(TICKERS.items())
    existing  = load_existing_manifest()
    manifest  = {}    # game_sym → candle count (for all successful tickers, including pre-existing)

    # Carry over existing counts (we'll update if we re-fetch)
    for sym, count in existing.get('tickers', {}).items():
        manifest[sym] = count

    total = len(tickers)
    ok = fail = skipped = 0

    print(f'Chart Master data fetch  |  {total} tickers  |  output -> {OUT_DIR}')
    print(f'Today: {today}  |  resume={args.resume}')
    print('-' * 56)

    for i, (game_sym, api_sym) in enumerate(tickers, 1):
        out_path = os.path.join(OUT_DIR, f'{game_sym}.json')
        prefix = f'[{i:3d}/{total}] {game_sym:<10}'

        # Resume mode: skip if file was updated today
        if args.resume and os.path.exists(out_path):
            try:
                with open(out_path) as f:
                    meta = json.load(f)
                if meta.get('u') == today:
                    print(f'{prefix} skip (today)')
                    manifest[game_sym] = len(meta.get('d', []))
                    skipped += 1
                    continue
            except Exception:
                pass

        print(f'{prefix}', end=' ', flush=True)
        candles, err = fetch_ticker(api_sym)

        if candles:
            payload = {'s': game_sym, 'u': today, 'd': candles}
            with open(out_path, 'w') as f:
                json.dump(payload, f, separators=(',', ':'))
            manifest[game_sym] = len(candles)
            print(f'OK  ({len(candles)} candles)')
            ok += 1
        else:
            print(f'FAIL - {err}')
            fail += 1

        if i < total:
            time.sleep(DELAY_S)

    print('-' * 56)
    print(f'Done: {ok} OK / {fail} failed / {skipped} skipped')

    write_manifest(manifest, today)


if __name__ == '__main__':
    main()
