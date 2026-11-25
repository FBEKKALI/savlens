"""Pipeline : triage de tous les tickets, agrégats par produit, détection de problèmes émergents."""
import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from classifier import classify_many

HISTORY_WEEKS = 8  # semaines servant de référence pour la détection d'anomalie
MIN_RECENT = 4  # volume minimal sur 7 jours pour lever une alerte (évite le bruit sur petits volumes)


def load_tickets(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def triage_all(tickets, backend="rules", workers=8):
    results = classify_many([(t["text"], t.get("product")) for t in tickets], backend, workers)
    return [{**t, **{f"pred_{k}": v for k, v in asdict(r).items()}} for t, r in zip(tickets, results)]


def _week_index(dt, ref):
    """0 = les 7 derniers jours, 1 = les 7 jours d'avant, etc."""
    return int((ref - dt).total_seconds() // (7 * 86400))


def detect_emerging(rows, ref):
    """Signale (produit, catégorie) dont le volume des 7 derniers jours dépasse moyenne + 2 écarts-types."""
    counts = defaultdict(lambda: [0] * (HISTORY_WEEKS + 1))
    for r in rows:
        if r["pred_is_non_conform"]:
            idx = _week_index(r["_dt"], ref)
            if idx <= HISTORY_WEEKS:
                counts[(r["product"], r["pred_category"])][idx] += 1
    alerts = []
    for (product, category), weekly in counts.items():
        recent, history = weekly[0], weekly[1:]
        mean = statistics.mean(history)
        threshold = mean + 2 * max(statistics.pstdev(history), 1.0)
        if recent >= MIN_RECENT and recent > threshold:
            alerts.append({"product": product, "category": category, "last_7d": recent,
                           "weekly_baseline": round(mean, 1), "threshold": round(threshold, 1)})
    return sorted(alerts, key=lambda a: a["last_7d"], reverse=True)


def build_report(rows, backend):
    for r in rows:
        r["_dt"] = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M")
    ref = max(r["_dt"] for r in rows)
    nc_rows = [r for r in rows if r["pred_is_non_conform"]]

    per_product = defaultdict(list)
    for r in rows:
        per_product[r["product"]].append(r)
    products = []
    for name, items in per_product.items():
        nc = [i for i in items if i["pred_is_non_conform"]]
        top = Counter(i["pred_category"] for i in nc).most_common(1)
        products.append({
            "product": name, "family": items[0]["product_family"], "tickets": len(items),
            "non_conform": len(nc), "rate": round(len(nc) / len(items), 3),
            "top_category": top[0][0] if top else None,
        })
    products.sort(key=lambda p: p["non_conform"], reverse=True)

    trend = []
    for idx in range(11, -1, -1):
        week = [r for r in rows if _week_index(r["_dt"], ref) == idx]
        trend.append({"week_ending": (ref - timedelta(days=7 * idx)).strftime("%Y-%m-%d"),
                      "tickets": len(week), "non_conform": sum(1 for r in week if r["pred_is_non_conform"])})

    escalations = sorted((r for r in rows if r["pred_needs_escalation"]), key=lambda r: r["_dt"], reverse=True)
    return {
        "backend": backend,
        "reference_date": ref.strftime("%Y-%m-%d"),
        "total": len(rows),
        "non_conform_count": len(nc_rows),
        "non_conform_rate": round(len(nc_rows) / len(rows), 3),
        "escalation_count": len(escalations),
        "by_category": dict(Counter(r["pred_category"] for r in rows).most_common()),
        "by_product": products,
        "weekly_trend": trend,
        "emerging_issues": detect_emerging(rows, ref),
        "escalations": [
            {"ticket_id": r["ticket_id"], "created_at": r["created_at"], "product": r["product"],
             "summary": r["pred_summary"], "text": r["text"][:240]}
            for r in escalations[:30]
        ],
    }


def print_summary(report):
    print(f"\n=== SAVLens | backend={report['backend']} | données jusqu'au {report['reference_date']} ===")
    print(f"Tickets : {report['total']} | non-conformes : {report['non_conform_count']} "
          f"({report['non_conform_rate']:.0%}) | escalades sécurité : {report['escalation_count']}")
    print("\nRépartition par catégorie :")
    for cat, n in report["by_category"].items():
        print(f"  {cat:26} {n}")
    print("\nTop produits non conformes :")
    for p in report["by_product"][:5]:
        print(f"  {p['product']:28} {p['non_conform']:3} / {p['tickets']:3}  ({p['rate']:.0%})  -> {p['top_category']}")
    print("\nProblèmes émergents :")
    if not report["emerging_issues"]:
        print("  aucun")
    for a in report["emerging_issues"]:
        print(f"  ALERTE {a['product']} / {a['category']} : {a['last_7d']} tickets sur 7 jours "
              f"(référence {a['weekly_baseline']}/semaine, seuil {a['threshold']})")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/tickets.csv")
    ap.add_argument("--backend", choices=["rules", "llm"], default="rules")
    ap.add_argument("--workers", type=int, default=8, help="appels LLM en parallèle")
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    rows = triage_all(load_tickets(args.input), args.backend, args.workers)
    report = build_report(rows, args.backend)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [k for k in rows[0] if not k.startswith("_")]
    with (out / "triaged.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print_summary(report)
    print(f"\nFichiers écrits : {out / 'report.json'}, {out / 'triaged.csv'}")


if __name__ == "__main__":
    main()
