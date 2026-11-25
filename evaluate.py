"""Évalue un backend de triage sur le jeu de tickets étiqueté (colonnes true_*)."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from analyze import load_tickets
from classifier import CATEGORIES, NON_CONFORM, classify_many


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def binary_metrics(truth, pred):
    tp = sum(1 for t, p in zip(truth, pred) if t and p)
    fp = sum(1 for t, p in zip(truth, pred) if not t and p)
    fn = sum(1 for t, p in zip(truth, pred) if t and not p)
    p, r, f = prf(tp, fp, fn)
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "support": tp + fn}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="data/tickets.csv")
    ap.add_argument("--backend", choices=["rules", "llm"], default="rules")
    ap.add_argument("--limit", type=int, default=0, help="échantillon aléatoire (utile pour limiter le coût LLM)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    rows = load_tickets(args.input)
    if args.limit and args.limit < len(rows):
        rows = random.Random(args.seed).sample(rows, args.limit)
    preds = classify_many([(r["text"], r["product"]) for r in rows], args.backend, args.workers)

    y_true = [r["true_category"] for r in rows]
    y_pred = [p.category for p in preds]
    n = len(rows)
    accuracy = sum(t == p for t, p in zip(y_true, y_pred)) / n

    per_class = {}
    for c in CATEGORIES:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        pr, rc, f1 = prf(tp, fp, fn)
        per_class[c] = {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(f1, 3), "support": tp + fn}
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)

    non_conform = binary_metrics([t in NON_CONFORM for t in y_true], [p.is_non_conform for p in preds])
    escalation = binary_metrics([int(r["true_severity"]) == 3 for r in rows], [p.needs_escalation for p in preds])

    print(f"\n=== Évaluation | backend={args.backend} | {n} tickets ===")
    print(f"Accuracy catégorie : {accuracy:.1%} | macro-F1 : {macro_f1:.3f}\n")
    print(f"{'catégorie':26} {'préc.':>6} {'rappel':>7} {'F1':>6} {'n':>5}")
    for c, v in per_class.items():
        print(f"{c:26} {v['precision']:6.2f} {v['recall']:7.2f} {v['f1']:6.2f} {v['support']:5d}")
    print(f"\nDétection non-conformité : précision {non_conform['precision']:.2f} | rappel {non_conform['recall']:.2f}")
    print(f"Détection escalade sécurité : précision {escalation['precision']:.2f} | rappel {escalation['recall']:.2f} "
          f"(sur {escalation['support']} cas)")

    errors = [(r, p) for r, p in zip(rows, preds) if r["true_category"] != p.category]
    print("\nConfusions les plus fréquentes (vrai -> prédit) :")
    for (t, p), k in Counter((r["true_category"], p.category) for r, p in errors).most_common(5):
        print(f"  {t} -> {p} : {k}")
    print("\nExemples d'erreurs :")
    for r, p in errors[:5]:
        print(f"  [{r['true_category']} -> {p.category}] {r['text'][:110]}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"eval_{args.backend}.json").write_text(json.dumps({
        "backend": args.backend, "n": n, "accuracy": round(accuracy, 3), "macro_f1": round(macro_f1, 3),
        "non_conformity": non_conform, "escalation": escalation, "per_class": per_class,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
