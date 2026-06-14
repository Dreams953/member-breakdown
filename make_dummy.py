#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ランキングBIツール動作確認用のダミーデータ生成。"""
import json
import random

random.seed(42)

FAC_DEPT = {
    "理工学部": ["機械工学科", "電気電子通信工学科", "応用化学科"],
    "情報工学部": ["情報科学科", "知能情報工学科"],
    "建築都市デザイン学部": ["建築学科", "都市工学科"],
}
POSITIONS = ["教授", "准教授", "講師", "助教"]
ITEM_KEYS = [
    "査読付ジャーナル件数 過去３年", "査読付ジャーナル件数 過去５年",
    "研究面での指標 Output", "科研費 金額", "府省庁からの外部資金 金額",
    "受賞など（最大15点） 点数", "特記事項（最大15点） 点数",
    "運営・社会貢献など（①～⑨の合計が最大15点） 点数",
]
SURNAMES = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
            "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "清水", "斎藤"]
GIVEN = ["太郎", "花子", "一郎", "美咲", "健", "由美", "誠", "彩", "大輔", "恵"]

researchers = []
for fac, depts in FAC_DEPT.items():
    for dept in depts:
        for _ in range(random.randint(4, 8)):
            ronbun = round(random.uniform(0, 60), 1)
            gakujutsu = round(random.uniform(0, 50), 1)
            activity = round(random.uniform(0, 40), 1)
            items = {k: round(random.uniform(0, 15), 1) for k in ITEM_KEYS}
            researchers.append({
                "name": random.choice(SURNAMES) + random.choice(GIVEN),
                "faculty": fac,
                "department": dept,
                "position": random.choice(POSITIONS),
                "age": random.randint(30, 64),
                "total": round(ronbun + gakujutsu + activity, 1),
                "divisions": {"論文部門": ronbun, "学術部門": gakujutsu, "アクティビティー部門": activity},
                "items": items,
            })

out = {
    "meta": {"source": "ダミーデータ", "divisions": ["論文部門", "学術部門", "アクティビティー部門"],
             "count": len(researchers)},
    "researchers": researchers,
}
with open("data_award.sample.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"{len(researchers)} 名のダミーデータを data_award.sample.json に出力")
