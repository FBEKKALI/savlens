"""Génère un jeu de tickets SAV / avis clients 100 % synthétique (aucune donnée réelle).

Le jeu contient un "problème émergent" volontaire (lot de batteries défectueuses sur une
perceuse) pour démontrer la détection d'anomalies de analyze.py.
"""
import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

# produit -> (famille, groupe nominal, féminin ?)
PRODUCTS = {
    "Canapé Oslo 3 places": ("Mobilier", "mon canapé", False),
    "Chaise Nova": ("Mobilier", "ma chaise", True),
    "Matelas Confort+ 160x200": ("Literie", "mon matelas", False),
    "Aspirateur TurboClean X2": ("Électroménager", "mon aspirateur", False),
    "Bouilloire Aroma 1.7L": ("Électroménager", "ma bouilloire", True),
    "Perceuse ProDrill 18V": ("Bricolage", "ma perceuse", True),
    "Lampe Lumi LED": ("Décoration", "ma lampe", True),
    "Casque Sonic BT": ("Électronique", "mon casque", False),
}
ELECTRIC = {"Électroménager", "Bricolage", "Électronique", "Décoration"}
CHANNELS = ["email", "chat", "avis_site", "reseaux_sociaux", "telephone"]
SPIKE_PRODUCT = "Perceuse ProDrill 18V"

CATEGORY_WEIGHTS = {
    "produit_defectueux": 0.20,
    "non_conforme_description": 0.12,
    "produit_endommage": 0.10,
    "mauvais_article": 0.06,
    "piece_manquante": 0.06,
    "retard_livraison": 0.14,
    "demande_info": 0.14,
    "avis_positif": 0.18,
}

# (gabarit, gravité). {np} = groupe nominal, {e} = "e" si le produit est féminin.
TEMPLATES = {
    "non_conforme_description": [
        ("{np} ne correspond pas du tout à la description du site, les dimensions sont bien plus petites.", 1),
        ("La couleur reçue est très différente de la photo du site pour {np}.", 1),
        ("Annoncé en matière haut de gamme mais {np} est en plastique fin. Déçu de la qualité.", 1),
        ("Sur la page produit, il était indiqué une garantie de 5 ans, finalement c'est 2 ans pour {np}.", 1),
        ("{np} fait beaucoup moins bien que ce qui était promis sur l'emballage.", 1),
        ("Pas conforme à l'annonce : {np} n'a pas la fonction indiquée sur la fiche.", 1),
        ("J'ai pris {np} pour sa taille indiquée mais la taille réelle est nettement inférieure.", 1),
    ],
    "produit_endommage": [
        ("{np} est arrivé{e} cassé{e}, le carton était complètement écrasé.", 2),
        ("Rayures profondes sur {np} dès la réception, emballage éventré.", 2),
        ("À l'ouverture du colis, un coin de {np} était fissuré.", 2),
        ("{np} est arrivé{e} dans un état lamentable, tout est tordu d'un côté.", 2),
        ("Produit abîmé à la livraison, le transporteur a manifestement jeté le colis de {np}.", 2),
    ],
    "mauvais_article": [
        ("J'ai reçu un autre modèle que celui commandé, ce n'est pas du tout la bonne référence pour {np}.", 2),
        ("Erreur de préparation : colis reçu avec un article gris alors que j'avais pris du noir pour {np}.", 2),
        ("Dans le carton il y avait un produit complètement différent de ma commande de {np}.", 2),
        ("J'avais commandé la version premium mais on m'a envoyé la version de base de {np}.", 2),
        ("Mauvaise couleur reçue pour {np}, j'avais choisi le blanc.", 2),
    ],
    "piece_manquante": [
        ("Il manque une pièce essentielle dans le carton de {np}, impossible de l'assembler.", 1),
        ("{np} est livré{e} incomplet{e}, pas de chargeur ni de notice.", 1),
        ("Montage bloqué : une des pièces de {np} n'est pas dans la boîte.", 1),
        ("Il n'y a que la moitié des accessoires avec {np}.", 1),
        ("Les accessoires annoncés avec {np} ne sont pas dans le colis.", 1),
    ],
    "retard_livraison": [
        ("Toujours rien reçu pour {np} alors que la livraison était annoncée pour lundi.", 0),
        ("La commande de {np} a dix jours de retard, aucune nouvelle du transporteur.", 0),
        ("Colis bloqué depuis une semaine, le suivi n'a pas bougé pour {np}.", 0),
        ("Ça fait trois semaines que j'attends {np}, personne ne me répond.", 0),
        ("Livraison de {np} décalée trois fois sans explication.", 0),
    ],
    "demande_info": [
        ("Comment régler {np} ? La notice n'est pas claire.", 0),
        ("Pouvez-vous m'envoyer la facture de {np} pour ma déclaration d'assurance ?", 0),
        ("Est-il possible d'obtenir des pièces de rechange pour {np} ?", 0),
        ("Quelle est la durée de garantie de {np} ?", 0),
        ("Je voudrais connaître les conditions de reprise de {np}.", 0),
        ("Est-ce normal que {np} fasse un petit clic au démarrage ? Pas de souci sinon, juste pour savoir.", 0),
    ],
    "avis_positif": [
        ("Très satisfait de {np}, rien à redire, je recommande.", 0),
        ("Parfait, conforme à la description et livraison rapide pour {np}.", 0),
        ("Excellent rapport qualité-prix, {np} fonctionne à merveille depuis trois mois.", 0),
        ("Aucune panne depuis l'achat, je recommande {np} sans hésiter.", 0),
        ("Mon voisin a eu le même modèle cassé à la livraison ; {np} est arrivé{e} nickel.", 0),
    ],
}
DEFECT_ELEC = [
    "{np} ne fonctionne plus du tout après deux jours d'utilisation.",
    "{np} est en panne, impossible de l'allumer malgré plusieurs essais.",
    "Je l'ai branché{e} hier soir, rien ne se passe, aucun voyant. À remplacer SVP.",
    "Bruit anormal en continu sur {np}, on dirait un roulement qui lâche.",
    "{np} s'éteint tout seul au bout d'une minute, impossible de l'utiliser normalement.",
]
DEFECT_FURN = [
    "{np} s'affaisse déjà après quelques semaines, il y a clairement un défaut de fabrication.",
    "Une couture de {np} a lâché dès le premier mois, le produit est défectueux.",
    "Après un mois, {np} grince à chaque mouvement, la structure semble mal assemblée.",
]
SAFETY = [
    ("{np} a chauffé anormalement et dégage une odeur de brûlé, j'ai tout débranché.", 3),
    ("Des étincelles sont sorties de {np} quand je l'ai branché{e} ! C'est dangereux.", 3),
    ("{np} est devenu{e} brûlant{e} pendant l'utilisation, un peu de fumée est sortie du boîtier.", 3),
    ("Le câble de {np} a fondu à un endroit, j'ai eu peur d'un départ de feu.", 3),
    ("Le boîtier de {np} est tout déformé après quelques utilisations, la batterie a gonflé.", 3),
    ("Ça sent le plastique chaud dès que je branche {np}, je n'ose plus m'en servir.", 3),
]
SPIKE = [
    ("La batterie de {np} ne charge plus depuis hier.", 2),
    ("{np} s'éteint au bout de deux minutes, la batterie semble morte.", 2),
    ("Batterie de {np} complètement HS après trois utilisations.", 2),
    ("La batterie de {np} a gonflé, le boîtier est déformé, ça m'inquiète.", 3),
    ("{np} ne tient plus la charge, lot de batteries défectueux à mon avis.", 2),
]
PREFIXES = ["Bonjour,", "Bonjour,", "", "", "URGENT :", "Salut,", "Madame, Monsieur,"]
SUFFIXES = ["Merci de votre retour.", "J'attends votre réponse.", "Cordialement.", "", "", "",
            "Ça fait la deuxième fois que ça m'arrive.", "J'ai joint des photos."]


def pick_template(category, family, rng):
    if category == "produit_defectueux":
        if family in ELECTRIC:
            if rng.random() < 0.15:
                return rng.choice(SAFETY)
            return rng.choice(DEFECT_ELEC), 2
        return rng.choice(DEFECT_FURN), 2
    return rng.choice(TEMPLATES[category])


def render(template, product, rng):
    _, np_, feminine = PRODUCTS[product]
    text = template.format(np=np_, e="e" if feminine else "")
    text = text[0].upper() + text[1:]
    return " ".join(p for p in (rng.choice(PREFIXES), text, rng.choice(SUFFIXES)) if p)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=800, help="nombre de tickets de fond")
    ap.add_argument("--days", type=int, default=90, help="période couverte (jours)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--spike", type=int, default=25, help="tickets du problème émergent (0 = désactivé)")
    ap.add_argument("--spike-days", type=int, default=9)
    ap.add_argument("--end-date", help="YYYY-MM-DD (défaut : aujourd'hui)")
    ap.add_argument("--out", default="data/tickets.csv")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    end = (datetime.strptime(args.end_date + " 18:00", "%Y-%m-%d %H:%M") if args.end_date
           else datetime.now().replace(second=0, microsecond=0))
    cats, weights = list(CATEGORY_WEIGHTS), list(CATEGORY_WEIGHTS.values())
    products = list(PRODUCTS)

    rows = []
    for _ in range(args.n):
        product = rng.choice(products)
        category = rng.choices(cats, weights)[0]
        template, severity = pick_template(category, PRODUCTS[product][0], rng)
        ts = end - timedelta(minutes=rng.randint(0, args.days * 24 * 60))
        rows.append((ts, product, category, severity, render(template, product, rng)))
    for _ in range(args.spike):
        template, severity = rng.choice(SPIKE)
        ts = end - timedelta(minutes=rng.randint(0, args.spike_days * 24 * 60))
        rows.append((ts, SPIKE_PRODUCT, "produit_defectueux", severity, render(template, SPIKE_PRODUCT, rng)))
    rows.sort(key=lambda r: r[0])

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticket_id", "created_at", "channel", "product", "product_family", "text",
                    "true_category", "true_severity"])
        for i, (ts, product, category, severity, text) in enumerate(rows, start=1):
            w.writerow([f"T-{i:05d}", ts.strftime("%Y-%m-%d %H:%M"), rng.choice(CHANNELS), product,
                        PRODUCTS[product][0], text, category, severity])
    print(f"{len(rows)} tickets synthétiques écrits dans {out}")


if __name__ == "__main__":
    main()
