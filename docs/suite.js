/* Petits outils partagés par les pages de la suite (Décisions, Santé, Découvertes, Labo, Pilote).
   S'appuie sur app.js (api, el, bouton, toast, fenetre). Tout texte venu du serveur passe par textContent : jamais innerHTML. */
'use strict';
function ilya(sec) {
  if (sec == null) return 'jamais';
  if (sec < 60) return 'à l’instant';
  if (sec < 3600) return `il y a ${Math.round(sec / 60)} min`;
  if (sec < 86400) return `il y a ${Math.round(sec / 3600)} h`;
  return `il y a ${Math.round(sec / 86400)} j`;
}
function depuis(iso) { const t = Date.parse(iso || ''); return isNaN(t) ? null : (Date.now() - t) / 1000; }
function heure(iso) { const t = Date.parse(iso || ''); return isNaN(t) ? '' : new Date(t).toLocaleString('fr-FR', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}); }
function vide(zone, texte) { zone.replaceChildren(el('p', 'mut vide', texte)); }
function eteint(zone) { vide(zone, 'Jarvis est éteint : double-clique sur JARVIS.bat.'); }
function pastille(etat) {
  const noms = {ok: 'OK', panne: 'En panne', instable: 'Instable', disponible: 'Disponible', en_cours: 'Au travail', termine: 'Vient de finir',
    erreur: 'Erreur', pending: 'À faire', running: 'En cours', blocked: 'En pause', done: 'Fait', failed: 'Raté', skipped: 'Sauté'};
  const p = el('span', 'etat etat-' + etat, noms[etat] || etat); return p;
}
function details(titre, ...enfants) { const d = el('details'); d.append(el('summary', '', titre), ...enfants); return d; }
function ligneCle(cle, val) { const p = el('p', 'kv'); p.append(el('b', '', cle + ' : '), document.createTextNode(val || '—')); return p; }
async function charger(zone, chemin, rendu) {
  try { rendu(await api(chemin)); } catch (e) { e.message.startsWith('Erreur') ? vide(zone, e.message) : eteint(zone); }
}
