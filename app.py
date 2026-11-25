"""API Flask + tableau de bord : triage d'un ticket à la volée et consultation du rapport."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request

from classifier import classify

app = Flask(__name__)
REPORT_PATH = Path(os.getenv("OUTPUT_DIR", "output")) / "report.json"
DEFAULT_BACKEND = os.getenv("DEFAULT_BACKEND", "rules")

PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>SAVLens</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{font-family:system-ui,sans-serif;max-width:1000px;margin:1.5rem auto;padding:0 1rem;color:#222}
 h1{margin-bottom:.2rem} h2{margin-top:2rem;font-size:1.1rem}
 .kpis{display:flex;gap:1rem;flex-wrap:wrap} .kpi{background:#f4f4f6;border-radius:8px;padding:.8rem 1.2rem}
 .kpi b{display:block;font-size:1.6rem}
 table{border-collapse:collapse;width:100%;font-size:.9rem} th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid #e3e3e8}
 .alert{background:#fff3cd;border-left:4px solid #e0a800;padding:.5rem .8rem;margin:.4rem 0;border-radius:4px}
 .danger{background:#fde2e2;border-left-color:#c0392b}
 textarea{width:100%;height:5rem;padding:.5rem;font-size:1rem} pre{background:#f4f4f6;padding:.8rem;border-radius:6px;white-space:pre-wrap}
</style></head><body>
<h1>SAVLens</h1><p>Détection de non-conformités dans les tickets SAV et avis clients.</p>
<div class="kpis" id="kpis"></div>
<h2>Problèmes émergents</h2><div id="emerging"></div>
<h2>Produits les plus concernés</h2><table id="products"></table>
<h2>Escalades sécurité</h2><table id="esc"></table>
<h2>Tester un ticket</h2>
<textarea id="t" placeholder="Ex : Ma bouilloire dégage une odeur de brûlé..."></textarea>
<select id="b"><option value="rules">rules</option><option value="llm">llm</option></select>
<button onclick="triage()">Analyser</button><pre id="res"></pre>
<script>
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function load(){
  const r = await fetch('/api/report');
  if(!r.ok){document.getElementById('kpis').innerHTML='<p>Aucun rapport. Lancez <code>python analyze.py</code>.</p>';return;}
  const d = await r.json();
  document.getElementById('kpis').innerHTML =
    '<div class="kpi"><b>'+d.total+'</b>tickets</div>'+
    '<div class="kpi"><b>'+d.non_conform_count+'</b>non-conformes ('+(d.non_conform_rate*100).toFixed(0)+' %)</div>'+
    '<div class="kpi"><b>'+d.escalation_count+'</b>escalades sécurité</div>'+
    '<div class="kpi"><b>'+esc(d.backend)+'</b>backend</div>';
  document.getElementById('emerging').innerHTML = d.emerging_issues.length
    ? d.emerging_issues.map(a=>'<div class="alert danger"><b>'+esc(a.product)+'</b> — '+esc(a.category)+' : '+a.last_7d+
        ' tickets sur 7 jours (référence '+a.weekly_baseline+'/semaine)</div>').join('')
    : '<p>Aucune anomalie détectée.</p>';
  document.getElementById('products').innerHTML = '<tr><th>Produit</th><th>Famille</th><th>Tickets</th><th>Non-conformes</th><th>Taux</th><th>Cause principale</th></tr>'+
    d.by_product.map(p=>'<tr><td>'+esc(p.product)+'</td><td>'+esc(p.family)+'</td><td>'+p.tickets+'</td><td>'+p.non_conform+
      '</td><td>'+(p.rate*100).toFixed(0)+' %</td><td>'+esc(p.top_category)+'</td></tr>').join('');
  document.getElementById('esc').innerHTML = '<tr><th>Date</th><th>Produit</th><th>Résumé</th></tr>'+
    d.escalations.slice(0,10).map(e=>'<tr><td>'+esc(e.created_at)+'</td><td>'+esc(e.product)+'</td><td>'+esc(e.summary)+'</td></tr>').join('');
}
async function triage(){
  const text = document.getElementById('t').value.trim(); if(!text) return;
  const r = await fetch('/api/triage',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:text, backend:document.getElementById('b').value})});
  document.getElementById('res').textContent = JSON.stringify(await r.json(), null, 2);
}
load();
</script></body></html>"""


@app.get("/")
def home():
    return PAGE


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/report")
def report():
    if not REPORT_PATH.exists():
        return jsonify(error="Rapport introuvable. Lancez d'abord : python analyze.py"), 404
    return jsonify(json.loads(REPORT_PATH.read_text(encoding="utf-8")))


@app.post("/api/triage")
def triage():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="Le champ 'text' est requis."), 400
    if len(text) > 5000:
        return jsonify(error="Texte trop long (5000 caractères max)."), 413
    backend = data.get("backend") or DEFAULT_BACKEND
    if backend not in ("rules", "llm"):
        return jsonify(error="backend invalide (rules ou llm)."), 400
    return jsonify(asdict(classify(text, data.get("product"), backend)))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
