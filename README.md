# SAVLens – Détection de non-conformités dans les tickets SAV et avis clients

Pipeline IA pour un distributeur (retail) : il lit les **tickets SAV** et les **avis clients**, détecte les **produits non conformes** (défectueux, non conformes à la description, abîmés, mauvais article, pièce manquante), évalue la **gravité**, **escalade les risques sécurité** et **alerte sur les problèmes émergents** (ex. un lot de batteries défectueuses) avant qu'ils ne deviennent des rappels produit.

> Toutes les données du dépôt sont **100 % synthétiques** (générées par `generate_data.py`). Aucune donnée client réelle.

## Pourquoi ce projet

Un SAV reçoit des milliers de messages libres par mois. Les trier à la main est lent, et les signaux faibles (hausse de pannes sur une référence, batterie qui gonfle) se perdent dans le volume. SAVLens montre une approche industrialisable :

- **Extraction structurée par LLM** (catégorie, gravité, résumé, action recommandée) avec sortie JSON validée
- **Baseline par règles** pour mesurer honnêtement l'apport du LLM
- **Repli automatique** sur les règles si l'API LLM est indisponible : le SAV n'est jamais bloqué
- **Détection de problèmes émergents** par comparaison du volume des 7 derniers jours à l'historique
- **Banc d'évaluation** (précision, rappel, F1, rappel sur les escalades sécurité)

## Architecture

```
tickets.csv ──> classifier.py ──> catégorie / gravité / résumé / action
                 ├─ backend "rules"  (baseline, hors-ligne)
                 └─ backend "llm"    (Azure OpenAI / OpenAI, JSON, repli sur "rules")
                          │
        ┌─────────────────┼───────────────────┐
   analyze.py        evaluate.py           app.py (Flask)
 rapport + alertes   métriques vs vérité   API /api/triage + tableau de bord
```

## Démarrage rapide (sans clé API)

```bash
python -m venv .venv && source .venv/bin/activate    # Windows : .venv\Scripts\activate
pip install -r requirements.txt

python generate_data.py      # crée data/tickets.csv (825 tickets synthétiques)
python analyze.py            # triage + rapport dans output/
python evaluate.py           # métriques de la baseline
python app.py                # tableau de bord sur http://localhost:5000
pytest                       # tests unitaires
```

## Utiliser le LLM

```bash
cp .env.example .env          # renseigner PROVIDER et les clés Azure OpenAI ou OpenAI
python analyze.py  --backend llm
python evaluate.py --backend llm --limit 200     # échantillon pour limiter le coût
```

Le LLM reçoit le ticket comme une **donnée** (et non une instruction), répond en JSON, et la réponse est **revalidée** côté code : catégorie inconnue, gravité hors bornes ou incohérence (risque sécurité classé « avis positif ») sont corrigées avant d'être utilisées.

## Résultats de la baseline à règles

Mesurés sur les 825 tickets synthétiques (`seed=42`). Le jeu contient volontairement des formulations indirectes (« rien ne se passe, aucun voyant », « la batterie a gonflé ») que des mots-clés ne captent pas.

| Indicateur | Règles | LLM |
|---|---|
| Accuracy (catégorie) | 67,0 % | 
| Macro-F1 | 0,72 |
| Non-conformité : précision / rappel | 0,92 / 0,63 | 
| Escalade sécurité : précision / rappel | 1,00 / 0,57 |

Lecture : la baseline est précise quand elle se prononce, mais elle **rate près de la moitié des risques sécurité** et classe par défaut en « demande_info » tout ce qu'elle ne reconnaît pas. C'est exactement l'écart que le LLM doit combler. Ajoutez vos propres résultats LLM dans la colonne de droite.

## Détection de problèmes émergents

Pour chaque couple (produit, catégorie), `analyze.py` compare le nombre de tickets non conformes des **7 derniers jours** à la moyenne des **8 semaines précédentes** et lève une alerte si le volume dépasse `moyenne + 2 écarts-types` (avec un minimum de 4 tickets pour éviter le bruit). Sur les données de démo, l'alerte remonte le lot de batteries défectueuses de la perceuse :

```
ALERTE Perceuse ProDrill 18V / produit_defectueux : 10 tickets sur 7 jours (référence 0.8/semaine, seuil 2.8)
```

## API

```bash
curl -X POST http://localhost:5000/api/triage \
  -H "Content-Type: application/json" \
  -d '{"text": "Ma bouilloire dégage une odeur de brûlé", "backend": "rules"}'
```

Réponse :

```json
{
  "category": "produit_defectueux",
  "is_non_conform": true,
  "severity": 3,
  "needs_escalation": true,
  "summary": "Ma bouilloire dégage une odeur de brûlé",
  "suggested_action": "ESCALADE IMMÉDIATE (risque sécurité) : ...",
  "backend": "rules"
}
```

Autres routes : `GET /api/report` (rapport JSON), `GET /health`, `GET /` (tableau de bord).

## Configuration (`.env`)

| Variable | Rôle |
|---|---|
| `PROVIDER` | `azure` ou `openai` |
| `DEFAULT_BACKEND` | backend de l'API (`rules` ou `llm`) |
| `AZURE_OPENAI_*` | endpoint, clé, version, déploiement du modèle de chat |
| `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` | mode OpenAI |

## Docker

```bash
docker build -t savlens .
docker run -p 5000:5000 --env-file .env savlens
```

## Structure

| Fichier | Rôle |
|---|---|
| `classifier.py` | triage : règles, LLM, validation, repli |
| `generate_data.py` | tickets synthétiques avec problème émergent |
| `analyze.py` | rapport agrégé et détection d'anomalies |
| `evaluate.py` | métriques par catégorie, non-conformité et escalade |
| `app.py` | API Flask et tableau de bord |
| `test_classifier.py` | tests unitaires |

## Limites et pistes d'amélioration

- Données synthétiques : les chiffres sont indicatifs et à confirmer sur des tickets réels anonymisés
- Détection d'anomalie simple (moyenne + écart-type) : tester des méthodes saisonnières
- Ajouter le regroupement sémantique des tickets par embeddings pour découvrir de nouveaux motifs
- Brancher les alertes sur Teams/Slack et l'outil de ticketing
- Journaliser les corrections des agents SAV pour réentraîner ou affiner le prompt

## Stack

Python · LLM (Azure OpenAI / OpenAI) · Flask · pytest · Docker
