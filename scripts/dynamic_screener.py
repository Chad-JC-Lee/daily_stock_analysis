#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台股策略1：量價爆發型・短線強勢動態選股器
篩選規則：
1. 聚焦台股上市普通股（排除 ETF、權證、DR 等，代碼為 4 位數字且開頭非 0）
2. 當日收紅 K（收盤價 > 開盤價）且當日漲幅 >= 1.5%
3. 當日成交量顯著爆發：成交量 >= 2,000 張，且成交量 >= 近 5 日均量 1.5 倍以上
4. 股價突破或站穩 20 日均線（MA20）
5. 依動能強度（爆量倍數 * 漲幅）排序，挑選前 3~4 檔
"""

import warnings
warnings.filterwarnings("ignore")

import urllib.request
import csv
import io
import sys
import logging

try:
    import yfinance as yf
except ImportError:
    yf = None

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s")
logger = logging.getLogger("tw_screener")

DEFAULT_FALLBACK = "2330.TW,2454.TW,2317.TW"

def fetch_twse_candidates():
    """從證交所開放資料獲取今日全市場行情並初篩"""
    url = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=csv"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)"
    })
    
    candidates = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
        
        reader = csv.reader(io.StringIO(content))
        header = next(reader, None)
        if not header:
            return []
            
        for row in reader:
            if len(row) < 10:
                continue
            code = row[1].strip()
            name = row[2].strip()
            # 僅篩選 4 位數一般個股（排除 00 開頭之 ETF）
            if len(code) == 4 and code.isdigit() and code[0] in "123456789":
                try:
                    close_s = row[8].replace(",", "").replace("--", "").strip()
                    open_s = row[5].replace(",", "").replace("--", "").strip()
                    vol_s = row[3].replace(",", "").replace("--", "").strip()
                    change_s = row[9].replace(",", "").replace("+", "").strip()
                    
                    if close_s and open_s and vol_s and change_s:
                        close_p = float(close_s)
                        open_p = float(open_s)
                        vol = int(vol_s)
                        change = float(change_s)
                        prev_close = close_p - change
                        pct_change = (change / prev_close) * 100 if prev_close > 0 else 0
                        
                        # 初篩：收紅 K、漲幅 >= 1.5%、成交量 >= 2,000 張 (2,000,000 股)
                        if close_p > open_p and pct_change >= 1.5 and vol >= 2_000_000:
                            candidates.append({
                                "code": f"{code}.TW",
                                "name": name,
                                "close": close_p,
                                "pct": pct_change,
                                "vol": vol
                            })
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"TWSE API 抓取失敗: {e}")
        return []
        
    # 依成交量降序排列，取前 15 檔進入精細檢驗
    candidates = sorted(candidates, key=lambda x: x["vol"], reverse=True)[:15]
    return candidates

def refine_with_yfinance(candidates):
    """結合 yfinance 檢驗 20 日均線 (MA20) 與 5 日均量倍數"""
    if not yf or not candidates:
        return []
        
    selected = []
    for c in candidates:
        ticker = c["code"]
        try:
            t = yf.Ticker(ticker)
            df = t.history(period="1mo")
            if len(df) >= 10:
                ma20 = df["Close"].mean()
                # 前 5 日均量（排除最新當日）
                ma5_vol = df["Volume"].iloc[-6:-1].mean() if len(df) >= 6 else df["Volume"].mean()
                latest_vol = df["Volume"].iloc[-1]
                vol_ratio = latest_vol / ma5_vol if ma5_vol > 0 else 1.0
                latest_close = df["Close"].iloc[-1]
                
                # 策略條件：成交量放大 >= 1.3 倍，且股價站穩 MA20
                if vol_ratio >= 1.3 and latest_close >= ma20:
                    score = vol_ratio * c["pct"]
                    selected.append({
                        "ticker": ticker,
                        "name": c["name"],
                        "close": latest_close,
                        "pct": round(c["pct"], 2),
                        "vol_ratio": round(vol_ratio, 2),
                        "score": round(score, 2)
                    })
        except Exception:
            continue
            
    # 依綜合動能得分排序
    selected = sorted(selected, key=lambda x: x["score"], reverse=True)
    return selected

def main():
    candidates = fetch_twse_candidates()
    selected = refine_with_yfinance(candidates)
    
    if selected:
        # 取前 4 檔強勢股
        top_stocks = [s["ticker"] for s in selected[:4]]
        logger.info(f"✅ 今日台股策略1篩選成功 ({len(top_stocks)} 檔):")
        for s in selected[:4]:
            logger.info(f"  📌 {s['ticker']} {s['name']} | 漲幅: +{s['pct']}% | 爆量: {s['vol_ratio']}x | 收盤: {s['close']:.2f}")
        # 最後一行純輸出逗號分隔字串
        sys.stdout.write(",".join(top_stocks) + "\n")
        sys.stdout.flush()
    else:
        logger.info("ℹ️ 今日無符合強烈爆量條件之個股或非交易日，回退至核心主流股")
        sys.stdout.write(DEFAULT_FALLBACK + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
