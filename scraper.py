#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
東京都市大学 研究者情報データベース 業績データ収集スクリプト
==============================================================

公開されている研究者情報データベース
  https://www.risys.gl.tcu.ac.jp/
を巡回し、所属別の研究業績・教育業績・社会貢献業績を JSON (data.json) に書き出します。
出力した data.json を research-bi.html と同じフォルダに置くと、BIツールが読み込みます。

このサイトは自動アクセスをブロックする場合があります。必ずご自身の環境で、
利用規約・robots.txt を確認のうえ、低速・少回数でご利用ください。

使い方
------
  pip install requests beautifulsoup4
  # (A) 研究者IDの一覧ファイル ids.txt（1行1ID, 例: 7000118）を用意して実行
  python scraper.py --ids ids.txt --out data.json
  # (B) 検索結果ページ等から自動収集を試す場合
  python scraper.py --discover --out data.json
  # 動作確認（1人だけ）
  python scraper.py --ids ids.txt --limit 1 --out data.json

注意（要確認ポイント）
----------------------
detail ページの HTML 構造（見出し文言・表組み）が想定と違う場合は parse_detail() の
ヒューリスティックを実ページに合わせて調整してください。サンプル HTML を共有いただければ
こちらで確定版に仕上げます。
"""

import argparse
import json
import re
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://www.risys.gl.tcu.ac.jp/"
DETAIL_URL = BASE + "Main.php?action=01&tchCd={tid}&type=detail"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}

# 業績の大分類。サイト上の見出し文言に合わせて調整可。
CATEGORY_KEYS = {
    "研究業績": ["研究業績", "研究活動", "論文", "著書", "学会発表"],
    "教育業績": ["教育業績", "教育活動", "担当授業", "担当科目"],
    "社会貢献業績": ["社会貢献", "社会活動", "社会貢献業績"],
}

YEAR_RE = re.compile(r"(19[5-9]\d|20\d\d)")  # 1950-2099 の西暦


def fetch(session: requests.Session, url: str, retries: int = 3) -> str:
    """URL を取得して HTML 文字列を返す。失敗時は指数バックオフでリトライ。"""
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            print(f"  ! 取得失敗 ({e}). {wait}s 後に再試行 ...", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"取得に失敗しました: {url}")


def classify(heading_text: str) -> str | None:
    """見出し文言を大分類（研究/教育/社会貢献）に振り分ける。"""
    for cat, keys in CATEGORY_KEYS.items():
        if any(k in heading_text for k in keys):
            return cat
    return None


def parse_detail(tid: str, html: str) -> dict:
    """
    研究者詳細ページから 所属・職名・業績一覧を抽出する。

    ヒューリスティック方針（実ページに合わせて調整可）:
      1. 見出し(h1-h4, th, .title 等)を走査し、研究/教育/社会貢献のセクションを特定。
      2. セクション配下の各行(li, tr, p)から西暦(4桁)と種別・タイトルを拾う。
    """
    soup = BeautifulSoup(html, "html.parser")
    text_of = lambda el: el.get_text(" ", strip=True) if el else ""

    # --- 氏名・所属・職名（要確認: ページ構造に応じて調整） ---
    name = text_of(soup.find("h1")) or text_of(soup.find("title"))
    name = re.sub(r"\s*\|.*$", "", name).strip()

    faculty = department = position = ""
    # 「所属」「職名」というラベルの近傍テキストを拾う一般的なパターン
    for label, setter in (("所属", "faculty"), ("職名", "position"), ("職位", "position")):
        node = soup.find(string=re.compile(label))
        if node:
            val = node.parent.find_next(string=True)
            val = (val or "").strip()
            if setter == "faculty" and val:
                faculty = val
            elif setter == "position" and val:
                position = val

    achievements = []
    current_cat = None
    # ドキュメント順に走査して、直近のカテゴリ見出しに紐づけて行を集める
    for el in soup.find_all(["h2", "h3", "h4", "th", "tr", "li", "p", "dt", "dd"]):
        t = el.get_text(" ", strip=True)
        if not t:
            continue
        cat = classify(t)
        if cat and len(t) < 40:  # 短いものは見出しとみなす
            current_cat = cat
            continue
        if current_cat:
            m = YEAR_RE.search(t)
            if m:
                achievements.append(
                    {
                        "category": current_cat,
                        "type": guess_type(t, current_cat),
                        "year": int(m.group(1)),
                        "title": t[:200],
                    }
                )

    return {
        "id": tid,
        "name": name,
        "faculty": faculty,
        "department": department,
        "position": position,
        "url": DETAIL_URL.format(tid=tid),
        "achievements": achievements,
    }


def guess_type(text: str, category: str) -> str:
    """行テキストから業績の種別を推定。"""
    table = {
        "論文": "論文", "著書": "著書", "学会": "学会発表", "発表": "学会発表",
        "特許": "特許", "授業": "担当授業科目", "科目": "担当授業科目",
        "教科書": "教科書", "委員": "委員会・審議会", "講演": "講演",
        "メディア": "メディア", "受賞": "受賞",
    }
    for k, v in table.items():
        if k in text:
            return v
    return {"研究業績": "その他研究", "教育業績": "その他教育", "社会貢献業績": "その他社会貢献"}[category]


def discover_ids(session: requests.Session) -> list[str]:
    """
    所属一覧/検索結果ページから tchCd を収集する。
    ※ 検索結果ページの URL/フォーム構造はサイト依存のため、実ページに合わせて要調整。
       現状はトップから detail へのリンクを拾う簡易版。
    """
    ids: set[str] = set()
    html = fetch(session, BASE + "Main.php?action=top&type=form")
    for href in re.findall(r"tchCd=(\d+)", html):
        ids.add(href)
    return sorted(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description="TCU 研究者業績スクレイパ")
    ap.add_argument("--ids", help="研究者ID一覧ファイル（1行1ID）")
    ap.add_argument("--discover", action="store_true", help="サイトからIDを自動収集")
    ap.add_argument("--out", default="data.json", help="出力JSONパス")
    ap.add_argument("--limit", type=int, default=0, help="先頭N件のみ処理（動作確認用）")
    ap.add_argument("--sleep", type=float, default=1.5, help="リクエスト間隔(秒)")
    args = ap.parse_args()

    session = requests.Session()

    ids: list[str] = []
    if args.ids:
        with open(args.ids, encoding="utf-8") as f:
            ids = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    elif args.discover:
        print("IDを自動収集中 ...", file=sys.stderr)
        ids = discover_ids(session)
    else:
        ap.error("--ids か --discover のいずれかを指定してください")

    if args.limit:
        ids = ids[: args.limit]
    print(f"対象 {len(ids)} 名", file=sys.stderr)

    researchers = []
    for i, tid in enumerate(ids, 1):
        url = DETAIL_URL.format(tid=tid)
        print(f"[{i}/{len(ids)}] {tid}", file=sys.stderr)
        try:
            html = fetch(session, url)
            rec = parse_detail(tid, html)
            researchers.append(rec)
        except Exception as e:  # noqa: BLE001
            print(f"  ! スキップ: {e}", file=sys.stderr)
        time.sleep(args.sleep)

    out = {
        "meta": {
            "source": "東京都市大学 研究者情報データベース (https://www.risys.gl.tcu.ac.jp/)",
            "generatedAt": time.strftime("%Y-%m-%d"),
            "categories": list(CATEGORY_KEYS.keys()),
            "count": len(researchers),
        },
        "researchers": researchers,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"書き出し完了: {args.out}（{len(researchers)} 名）", file=sys.stderr)


if __name__ == "__main__":
    main()
