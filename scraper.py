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

サイト構造（実ページに基づく）
------------------------------
- 業績はタブ（別ページ）に分かれる:
    研究業績   action=01   （論文 / MISC / 講演・口頭発表等 / 研究課題 / 産業財産権 ...）
    教育業績   action=02
    社会貢献   action=04
  URL: Main.php?action=01&type=detail&tchCd=（研究者ID）
- 各ページ内に <table class="TBL-glist02" id="gskXX"> が複数:
    1行目 = 種別見出し(<th colspan>) 例「論文」
    2行目 = 列ヘッダ
    3行目以降 = データ行。年は「出版年月/発表年月日/研究期間/出願日」等の列に「YYYY年」
- 所属一覧: action=position&type=form
    学部に Facultyk コード（理工=001000, 情報工=003000, ...）。
    POST(action=position, type=list, Facultyk=コード, cntno=100, offset=...) で
    研究者一覧（tchCd リンク）を取得。

使い方
------
  pip install requests beautifulsoup4
  # (A) 所属一覧から全学を自動収集（推奨）
  python scraper.py --discover --out data.json
  # (B) 研究者IDの一覧ファイル ids.txt（1行1ID）から
  python scraper.py --ids ids.txt --out data.json
  # 動作確認（1人だけ）
  python scraper.py --ids ids.txt --limit 1 --out data.json
"""

import argparse
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.risys.gl.tcu.ac.jp/"
MAIN = BASE + "Main.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}

# 業績タブ（action）→ カテゴリ名
ACTION_CATEGORY = {"01": "研究業績", "02": "教育業績", "04": "社会貢献業績"}

# 列ヘッダから「年の列」を見つけるためのキーワード
DATE_HEAD = ["出版年", "発表年", "年月", "年度", "研究期間", "出願日", "登録日",
             "発行日", "取得", "受賞", "期間", "日付", "実施", "時期", "年"]
# 列ヘッダから「タイトルの列」を見つけるためのキーワード
TITLE_HEAD = ["タイトル", "名称", "課題名", "題名", "科目", "事項", "件名",
              "活動", "内容", "テーマ", "役割", "賞"]

YEAR_RE = re.compile(r"((?:19|20)\d{2})\s*年")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


def fetch(session: requests.Session, url: str, *, method="get", data=None, retries=4) -> str:
    """URL を取得。失敗時は指数バックオフでリトライ。"""
    for attempt in range(retries):
        try:
            if method == "post":
                resp = session.post(url, data=data, headers=HEADERS, timeout=30)
            else:
                resp = session.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return resp.text
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            print(f"  ! 取得失敗 ({e}). {wait}s 後に再試行 ...", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"取得に失敗しました: {url}")


# ----------------------------------------------------------------------
# 所属一覧（discover）
# ----------------------------------------------------------------------
def get_faculty_codes(session: requests.Session) -> list[tuple[str, str]]:
    """所属別検索フォームから (Facultykコード, 学部名) を取得。"""
    html = fetch(session, MAIN + "?action=position&type=form")
    pairs = []
    # <a ... onclick="hidval('Facultyk','001000');...">理工学部</a>
    for m in re.finditer(r"hidval\('Facultyk','(\d{6})'\)[^>]*>\s*([^<]+?)\s*</a>", html):
        code, name = m.group(1), clean(m.group(2))
        if code != "000000" and name:
            pairs.append((code, name))
    # 学部（学部・研究科）を優先順に（学部=00X000 を先頭へ）
    pairs.sort(key=lambda p: (0 if p[0][1:3] != "00" else 0, p[0]))
    return pairs


def list_researchers(session: requests.Session, facultyk: str, cntno=100, sleep=1.2) -> list[str]:
    """1つの所属(Facultyk)に属する研究者の tchCd 一覧を取得（ページング対応）。"""
    ids: list[str] = []
    seen: set[str] = set()
    offset = 0
    while True:
        data = {"action": "position", "type": "list", "Facultyk": facultyk,
                "cntno": str(cntno), "offset": str(offset), "opid": "", "andor": ""}
        html = fetch(session, MAIN, method="post", data=data)
        page_ids = [t for t in re.findall(r"tchCd=(\d{6,})", html) if t != "0000000000"]
        new = [t for t in page_ids if t not in seen]
        for t in new:
            seen.add(t)
            ids.append(t)
        # 次ページが無ければ終了
        if len(set(page_ids)) < cntno or not new:
            break
        offset += cntno
        time.sleep(sleep)
    return ids


def discover(session: requests.Session, sleep=1.2) -> dict[str, str]:
    """全所属を巡回し {tchCd: 学部名} を返す（最初に見つかった所属を採用）。"""
    faculties = get_faculty_codes(session)
    print(f"所属 {len(faculties)} 件: " + ", ".join(n for _, n in faculties), file=sys.stderr)
    id_faculty: dict[str, str] = {}
    for code, name in faculties:
        ids = list_researchers(session, code, sleep=sleep)
        print(f"  {name} ({code}): {len(ids)}名", file=sys.stderr)
        for t in ids:
            id_faculty.setdefault(t, name)
        time.sleep(sleep)
    return id_faculty


# ----------------------------------------------------------------------
# 業績ページの解析
# ----------------------------------------------------------------------
def find_col(headers: list[str], keywords: list[str], default=None):
    for i, h in enumerate(headers):
        if any(k in h for k in keywords):
            return i
    return default


def parse_category_page(html: str, category: str) -> list[dict]:
    """1カテゴリ(研究/教育/社会貢献)ページ内の全 TBL-glist02 テーブルを解析。"""
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for table in soup.select("table.TBL-glist02"):
        section = None       # 種別（論文 等）
        headers: list[str] | None = None
        title_col = 1
        date_col = None
        for tr in table.find_all("tr"):
            ths = tr.find_all("th", recursive=False)
            tds = tr.find_all("td", recursive=False)
            if ths and not tds:
                if section is None and len(ths) == 1:
                    section = clean(ths[0].get_text())
                elif headers is None and len(ths) > 1:
                    headers = [clean(th.get_text()) for th in ths]
                    title_col = find_col(headers, TITLE_HEAD, default=1)
                    date_col = find_col(headers, DATE_HEAD, default=None)
                continue
            if not tds:
                continue
            # データ行
            cells = [clean(td.get_text()) for td in tds]
            year = None
            if date_col is not None and date_col < len(cells):
                m = YEAR_RE.search(cells[date_col])
                if m:
                    year = int(m.group(1))
            if year is None:  # フォールバック: 行内で最後に出てくる「YYYY年」
                yrs = [int(x) for c in cells for x in YEAR_RE.findall(c)]
                if yrs:
                    year = yrs[-1]
            if year is None:
                continue
            title = cells[title_col] if title_col < len(cells) else (cells[1] if len(cells) > 1 else "")
            out.append({
                "category": category,
                "type": section or category,
                "year": year,
                "title": title[:200],
            })
    return out


def scrape_researcher(session: requests.Session, tid: str, faculty="", sleep=1.0) -> dict:
    """1人の研究者の 研究/教育/社会貢献 業績をまとめて取得。"""
    name = ""
    achievements: list[dict] = []
    for action, category in ACTION_CATEGORY.items():
        url = f"{MAIN}?action={action}&type=detail&tchCd={tid}"
        html = fetch(session, url)
        if not name:
            soup = BeautifulSoup(html, "html.parser")
            ttl = soup.find("p", class_="TTL-gform")
            name = clean(ttl.get_text()).split("(")[0].strip() if ttl else ""
        achievements.extend(parse_category_page(html, category))
        time.sleep(sleep)
    return {
        "id": tid,
        "name": name,
        "faculty": faculty,
        "department": "",   # 学科は所属一覧の詳細展開で取得可能（必要なら拡張）
        "position": "",     # 職名は基本情報(action=profile)で取得可能（必要なら拡張）
        "url": f"{MAIN}?action=01&type=detail&tchCd={tid}",
        "achievements": achievements,
    }


# ----------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="TCU 研究者業績スクレイパ")
    ap.add_argument("--ids", help="研究者ID一覧ファイル（1行1ID）")
    ap.add_argument("--discover", action="store_true", help="所属一覧から全学を自動収集")
    ap.add_argument("--out", default="data.json", help="出力JSONパス")
    ap.add_argument("--limit", type=int, default=0, help="先頭N件のみ処理（動作確認用）")
    ap.add_argument("--sleep", type=float, default=1.0, help="リクエスト間隔(秒)")
    args = ap.parse_args()

    session = requests.Session()

    id_faculty: dict[str, str] = {}
    if args.discover:
        print("所属一覧からIDを収集中 ...", file=sys.stderr)
        id_faculty = discover(session, sleep=args.sleep)
    elif args.ids:
        with open(args.ids, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    id_faculty[ln] = ""
    else:
        ap.error("--discover か --ids のいずれかを指定してください")

    ids = list(id_faculty)
    if args.limit:
        ids = ids[: args.limit]
    print(f"対象 {len(ids)} 名", file=sys.stderr)

    researchers = []
    for i, tid in enumerate(ids, 1):
        print(f"[{i}/{len(ids)}] {tid} {id_faculty.get(tid, '')}", file=sys.stderr)
        try:
            rec = scrape_researcher(session, tid, faculty=id_faculty.get(tid, ""), sleep=args.sleep)
            researchers.append(rec)
            print(f"    業績 {len(rec['achievements'])} 件", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            print(f"  ! スキップ: {e}", file=sys.stderr)

    out = {
        "meta": {
            "source": "東京都市大学 研究者情報データベース (https://www.risys.gl.tcu.ac.jp/)",
            "generatedAt": time.strftime("%Y-%m-%d"),
            "categories": list(ACTION_CATEGORY.values()),
            "count": len(researchers),
        },
        "researchers": researchers,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"書き出し完了: {args.out}（{len(researchers)} 名）", file=sys.stderr)


if __name__ == "__main__":
    main()
