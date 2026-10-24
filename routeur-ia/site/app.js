/* Socle commun du site (mission 4) : barre du haut, menu « Plus », réglages, et les fenêtres partagées
   (offre, brouillon de mail) pour que l'accueil, l'équipe, l'emploi et le jeu montrent la même chose.
   Usage dans une page : <body data-ecran="accueil"> … <script src="app.js"></script> */
'use strict';
const API = (location.protocol.startsWith('http') && location.port === '4100') ? '' : 'http://127.0.0.1:4100';
const CALME = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = id => document.getElementById(id);
const el = (tag, cls, txt) => { const e = document.createElement(tag); if (cls) e.className = cls; if (txt != null) e.textContent = txt; return e; };
const httpSur = u => /^https?:\/\//i.test(u || '') ? u : null;
const ARRONDI = s => (s >= 80 ? 'score' : 'score moyen');

/* Ouverte en double-clic : si Jarvis tourne, on recharge la page depuis lui (même origine que l'API = plus sûr). */
if (location.protocol === 'file:') fetch('http://127.0.0.1:4100/ping', {mode: 'no-cors'}).then(() =>
  location.replace('http://127.0.0.1:4100/' + location.pathname.split('/').pop() + location.search + location.hash)).catch(() => {});

async function api(chemin, corps, signal) {
  const r = await fetch(API + chemin, corps === undefined ? {cache: 'no-store', signal}
    : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(corps), signal});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.erreur || 'Erreur ' + r.status); e.trace = d.trace; e.code = r.status; throw e; }
  return d;
}
function toast(t) { let e = $('toast'); if (!e) { e = el('div', 'toast'); e.id = 'toast'; e.setAttribute('role', 'status'); document.body.append(e); }
  e.textContent = t; e.classList.add('vu'); clearTimeout(toast.m); toast.m = setTimeout(() => e.classList.remove('vu'), 2600); }
function lien(txt, url, cls) { const a = el('a', cls ?? 'btn', txt); a.href = url; if (/^https?:/.test(url)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; } return a; }
function bouton(txt, cls, fn) { const b = el('button', 'btn ' + (cls || ''), txt); b.type = 'button'; b.onclick = fn; return b; }
if (/discret/.test(location.hash)) document.body.classList.add('discret');  // voir .prive dans app.css
const memo = {lire: k => { try { return localStorage.getItem(k); } catch (_) { return null; } },
              ecrire: (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} }};
/* Mission 15 : thème Auto (sombre de 22 h à 7 h, heure du PC) · Clair · Sombre, gardé dans le navigateur. ?heure=22 simule l'heure (tests). */
const THEMES = {auto: '☾ Nuit auto', clair: '☀ Clair', sombre: '☾ Sombre'};
function appliquerTheme() {
  const t = THEMES[memo.lire('theme')] ? memo.lire('theme') : 'auto', hs = new URLSearchParams(location.search).get('heure');
  const h = hs !== null && /^\d{1,2}$/.test(hs) ? +hs : new Date().getHours();
  document.documentElement.dataset.theme = t === 'sombre' || (t === 'auto' && (h >= 22 || h < 7)) ? 'sombre' : 'clair';
  const b = $('theme'); if (b) { b.textContent = THEMES[t]; b.title = 'Thème : ' + t + ' (clic pour changer)'; }
  return t;
}
function choisirTheme(t) { memo.ecrire('theme', t); appliquerTheme(); document.dispatchEvent(new Event('theme')); }
appliquerTheme(); setInterval(appliquerTheme, 60000);

/* ---------- Mission 15 : barre du haut en 4 espaces (maquettes15, images 01, 10, 11, 19, 20) ----------
   Jarvis · Accueil · Ma recherche · L'atelier Jarvis · La bibliothèque · Le jeu ; à droite la pastille d'activité (le fil),
   Décisions · N (discret) et Ctrl K. Sous-onglets sous la barre. Plus de menu « Plus ». Un sous-onglet sans page = « bientôt ». */
const ESPACES = [
  ['accueil', 'Accueil', 'accueil.html', []],
  ['recherche', 'Ma recherche', '', [['Offres', 'emploi.html'], ['Mes candidatures', 'emploi.html#candidatures'], ['Moi', 'moi.html'],
    ['Lettres', 'emploi.html#lettres'], ['Entretien', 'entretien.html']]],
  ['atelier', 'L’atelier Jarvis', '', [['Pilote', 'pilote.html'], ['Mes IA', 'mes-ia.html'], ['Santé et alertes', 'sante.html', 'alertes.html'],
    ['Panneau de contrôle', 'controle.html'], ['Réglages', 'reglages.html']]],
  ['bibliotheque', 'La bibliothèque', '', [['Rapports', 'rapports.html'], ['Journal', 'journal.html'], ['Découvertes', 'decouvertes.html', 'decouvertes-chercher.html'],
    ['Idées', 'idees.html'], ['Mémoire', 'memoire.html'], ['Skills', 'skills.html']]],
  ['jeu', 'Le jeu', 'jeu.html', []],
];
const PAGE = (location.pathname.split('/').pop() || 'accueil.html');
function ici() {  // [espace, sous-onglet] de la page ouverte (le hash départage deux onglets d'une même page)
  let trouve = null;
  for (const e of ESPACES) {
    if (e[2] === PAGE) return [e, null];
    for (const o of e[3]) { const [f, h] = (o[1] || '#').split('#');
      if (f === PAGE || o[2] === PAGE) { if (h && location.hash.startsWith('#' + h)) return [e, o]; if (!h && !trouve) trouve = [e, o]; } }
  }
  return trouve || [null, null];
}
(function nav() {
  const [esp, sous] = ici(), n = el('nav', 'nav'); n.setAttribute('aria-label', 'Navigation');
  const haut = el('div', 'nav-haut'), m = el('a', 'marque', 'Jarvis'); m.href = 'accueil.html';
  const l = el('div', 'liens'); l.setAttribute('aria-label', 'Espaces');
  for (const e of ESPACES) { const a = el('a', '', e[1]); a.href = e[2] || e[3][0][1]; a.id = 'nav-' + e[0];
    if (e === esp) a.setAttribute('aria-current', 'page'); l.append(a); }
  const act = el('div', 'activite'), pa = el('button', 'presence', 'Jarvis attend · rien ne tourne'); pa.type = 'button'; pa.id = 'presence';
  pa.setAttribute('aria-expanded', 'false'); pa.title = 'Ce que fait Jarvis : clique pour voir le fil';
  const boite = el('div', 'fil-jarvis'); boite.id = 'filJarvis'; boite.setAttribute('role', 'dialog'); boite.setAttribute('aria-label', 'Le fil de Jarvis'); boite.hidden = true;
  pa.onclick = e => { e.stopPropagation(); montrerFil(boite.hidden); };
  act.append(pa, boite);
  const dc = el('a', 'decisions-nav', 'Décisions'); dc.href = 'decisions.html'; dc.id = 'nav-decisions'; if (PAGE === 'decisions.html') dc.setAttribute('aria-current', 'page');
  const ck = el('button', 'ctrlk', 'Ctrl K'); ck.type = 'button'; ck.id = 'ctrlk'; ck.title = 'Chercher partout'; ck.onclick = () => window.ouvrirRecherche && ouvrirRecherche();
  const th = el('button', 'theme-nav'); th.type = 'button'; th.id = 'theme';
  th.onclick = () => { const o = Object.keys(THEMES), t = memo.lire('theme') || 'auto'; choisirTheme(o[(o.indexOf(t) + 1) % o.length]); };
  haut.append(m, l, act, dc, th, ck); n.append(haut);
  if (esp && esp[3].length) {
    const so = el('div', 'sous'); so.setAttribute('aria-label', esp[1]);
    for (const o of esp[3]) {
      if (!o[1]) { const b = el('span', 'bientot', o[0]); b.title = 'Bientôt (Mission 15)'; so.append(b); continue; }
      const a = el('a', '', o[0]); a.href = o[1]; if (o === sous) a.setAttribute('aria-current', 'page'); so.append(a); }
    n.append(so); document.body.classList.add('a-sous');
  }
  document.body.prepend(n); appliquerTheme();
  document.addEventListener('click', e => { if (!act.contains(e.target)) montrerFil(false); });
  addEventListener('hashchange', majSous);
  if (location.hash === '#fil') setTimeout(() => montrerFil(true));  // accueil.html#fil : le fil ouvert (Ctrl K, captures)
  addEventListener('keydown', e => { if (e.key === 'Escape') montrerFil(false); });
})();

function majSous() {  // une page qui change d'onglet (emploi, journal) remet le bon sous-onglet en valeur
  const s = ici()[1];
  for (const a of document.querySelectorAll('.nav .sous a')) if (s && a.getAttribute('href') === s[1]) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
}
/* Le fil de Jarvis : la tâche en cours + les 3 dernières actions (phrases écrites par le serveur, jamais de contenu).
   Lu toutes les 5 s, seulement page visible et Jarvis présent (pas en jeu, pas en pause, pas d'arrêt d'urgence). */
let FIL = null;
const duree = s => s < 60 ? s + ' s' : Math.round(s / 60) + ' min';
async function lireFil() {
  if (document.visibilityState !== 'visible' || !PRESENT || !PRESENT.present) return;
  try { FIL = await api('/fil'); } catch (_) { FIL = null; }
  voyant(); if (!$('filJarvis').hidden) dessinerFil();
}
setInterval(lireFil, 5000);
function montrerFil(o) {
  const b = $('filJarvis'); if (!b) return; b.hidden = !o; $('presence').setAttribute('aria-expanded', !!o);
  if (o) { dessinerFil(); lireFil(); }
}
function dessinerFil() {
  const b = $('filJarvis'), t = el('div', 'fil-tete'); t.append(el('b', '', 'Le fil de Jarvis'), el('span', '', FIL && FIL.actif ? 'en direct' : 'à l’arrêt'));
  b.replaceChildren(t);
  const c = FIL && FIL.en_cours;
  if (c) { const x = el('div', 'fil-cours'), p = el('span'); p.append(el('b', '', c.qui), ` ${c.quoi} · depuis ${duree(c.depuis)}`);
    const barre = el('span', 'barre'); barre.append(el('i')); x.append(p, barre); b.append(x); }
  else b.append(el('p', 'fil-rien', PRESENT && !PRESENT.present ? 'En pause : ' + (PRESENT.raison || 'tu n’es pas sur le site') + '.' : 'Rien ne tourne en ce moment.'));
  for (const f of (FIL && FIL.lignes) || []) {
    const r = el('div', 'fil-ligne'), d = el('span'); d.append(el('b', '', f.qui), ' · ' + f.quoi + (f.ia ? ' · ' + f.ia : ''));
    if (f.pourquoi) d.append(el('small', '', f.pourquoi));
    r.append(el('span', 'h', f.h), d); b.append(r); }
  b.append(lien('Tout l’historique → La bibliothèque › Journal', 'journal.html', 'fil-lien'));
}

/* ---------- Mission 15 : Ctrl K, chercher partout (maquette R_ChercherPartout, image 03) ----------
   Pages et actions connues ici ; IA, rapports, offres, candidatures, skills, notes et idées : /recherche/index (titres seulement).
   Sans accents, avec des mots-clés et synonymes. ↑ ↓ choisir, Entrée ouvrir ; rien trouvé → Entrée pose la question à Jarvis. */
const K_PAGES = [  // [type, titre, sous-titre, mots-clés, adresse]
  ['Page', 'Accueil', 'Parler à Jarvis, les 3 choses du jour', 'accueil parler jarvis question bonjour journee', 'accueil.html'],
  ['Page', 'Le fil de Jarvis', 'Ce que Jarvis fait en ce moment', 'fil activite en cours direct travaille', 'accueil.html#fil'],
  ['Page', 'Offres', 'Ma recherche · les offres lues par Jarvis', 'offres offre emploi travail job annonces poste', 'emploi.html'],
  ['Page', 'Mes candidatures', 'Ma recherche · tes candidatures et les réponses', 'candidatures candidature postule reponses recruteurs', 'emploi.html#candidatures'],
  ['Page', 'Moi', 'Ma recherche · ton portrait, ta frise, tes projets', 'moi profil cv parcours projets competences portrait', 'moi.html'],
  ['Page', 'Lettres', 'Ma recherche · les lettres de motivation', 'lettre lettres motivation postuler', 'emploi.html#lettres'],
  ['Page', 'Pilote', 'L’atelier · ce que fait chaque agent', 'pilote graphe agents equipe constellation arbre', 'pilote.html'],
  ['Page', 'Mes IA', 'L’atelier · où sont tes IA, celle par défaut', 'ia ias ollama modele modeles intelligence artificielle ordinateur pc local routeur choisir defaut', 'mes-ia.html'],
  ['Page', 'Santé et alertes', 'L’atelier · services, pannes, alertes, quotas', 'sante alertes pannes panne probleme erreur services tests quotas', 'sante.html'],
  ['Page', 'Panneau de contrôle', 'L’atelier · démarrer, arrêter, lancer un script', 'controle panneau demarrer script lancer', 'controle.html'],
  ['Page', 'Réglages', 'L’atelier · Telegram, jeux, thème, partager', 'reglages parametres telegram theme nuit sombre jeux exporter partager', 'reglages.html'],
  ['Page', 'Rapports', 'La bibliothèque · les rapports de mission', 'rapport rapports mission', 'rapports.html'],
  ['Page', 'Journal', 'La bibliothèque · tout ce qui s’est passé, jour par jour', 'journal historique conversations passe fait seul annuler remettre', 'journal.html'],
  ['Page', 'Découvertes', 'La bibliothèque · versions, outils, failles à suivre', 'decouvertes veille nouveautes outils', 'decouvertes.html'],
  ['Page', 'Mémoire', 'La bibliothèque · ce que Jarvis sait de toi : corriger, oublier', 'memoire obsidian notes souvenirs oublier corriger', 'memoire.html'],
  ['Page', 'Idées', 'La bibliothèque · la boîte à idées', 'idees idee boite propositions ameliorations', 'idees.html'],
  ['Page', 'Entretien', 'Ma recherche · s’entraîner à l’oral avec Jarvis', 'entretien oral entrainement micro questions recruteur', 'entretien.html'],
  ['Page', 'Skills', 'La bibliothèque · les consignes que Claude suit', 'skills skill consignes', 'skills.html'],
  ['Page', 'Décisions', 'Les questions que Jarvis te pose', 'decisions decision questions choix repondre', 'decisions.html'],
  ['Page', 'Le jeu', 'Ta chambre en pixel art', 'jeu chambre pixel quetes xp', 'jeu.html'],
  ['Question', 'Pourquoi c’est lent ?', 'Jarvis regarde la santé des IA et te répond en une phrase', 'lent lente lenteur rame pourquoi bug marche pas repond probleme', '#lent'],
  ['Action', 'Tester mes IA', 'Résultat en moins d’une minute', 'tester test ia lent lente marche pas probleme', '#tester'],
  ['Action', 'Regarder une vidéo', 'Un lien ou un fichier : résumé, idées, montage', 'video videos regarder youtube montage', 'video.html'],
  ['Action', 'Conseil des IA', 'Recherche approfondie à cinq points de vue', 'conseil recherche approfondie avis', 'conseil.html'],
  ['Action', 'Chercher des offres', 'Jarvis lance une recherche maintenant', 'chercher offres recherche nouvelles', '#offres'],
  ['Action', 'Tout arrêter', 'Directeur, veille, Ollama, routeur, Jarvis', 'arreter tout stop urgence couper eteindre', '#arreter'],
];
/* « Où est passé quoi ? » : [espace, couleur, [[page, avant, adresse]]] */
const K_PLAN = [
  ['Accueil', '#1b2318', [['Parler à Jarvis', 'Accueil', 'accueil.html'], ['Le fil de Jarvis', 'nouveau', 'accueil.html#fil']]],
  ['Ma recherche', '#2f6b3d', [['Offres', 'Emploi', 'emploi.html'], ['Mes candidatures', 'Emploi → onglet', 'emploi.html#candidatures'], ['Moi', 'Moi', 'moi.html'],
    ['Lettres', 'nouveau (était dans Emploi)', 'emploi.html#lettres']]],
  ['L’atelier Jarvis', '#1b2350', [['Pilote', 'Plus → Pilote', 'pilote.html'], ['Mes IA', 'Plus → Choisir une IA + Santé', 'mes-ia.html'],
    ['Santé et alertes', 'Plus → Santé + Alertes', 'sante.html'], ['Panneau de contrôle', 'Plus → Panneau de contrôle', 'controle.html'], ['Réglages', 'Plus → ⚙ Réglages', 'reglages.html']]],
  ['La bibliothèque', '#b5561f', [['Rapports', 'Plus → Journal → Rapports', 'rapports.html'], ['Journal', 'Plus → Journal', 'journal.html'],
    ['Découvertes', 'Plus → Découvertes 2.0', 'decouvertes.html'], ['Mémoire', 'Plus → Mémoire (Obsidian)', 'memoire.html'], ['Skills', 'Plus → Mes skills', 'skills.html']]],
  ['Partout (barre du haut, accueil, Ctrl K)', '#7a3410', [['Décisions', 'onglet Décisions', 'decisions.html'], ['Regarder une vidéo', 'Plus → Regarder une vidéo', 'video.html'],
    ['Conseil des IA', 'Plus → Conseil des IA', 'conseil.html'], ['Tout arrêter', 'Plus → Tout arrêter', '#arreter'], ['Le jeu', 'Le jeu', 'jeu.html']]],
];
const K_PLACE = {'#lent': 'sante.html', '#tester': 'sante.html', '#offres': 'emploi.html'};  // une action « habite » une page du plan
const K_COUL = {Question: '#7a3410', Page: '#1b2318', IA: '#5b5f97', Action: '#b5561f', Rapport: '#2f8a49', Offre: '#2f6b3d', Candidature: '#2f6b3d', Skill: '#8a6a16', Note: '#6c7393', Idée: '#b5561f'};
const K_PLAN_JUSQUA = new Date('2026-11-04');  // 2 semaines après la Mission 15, puis seulement dans Réglages
const sansAccent = t => String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’'?!.,:;]/g, ' ');
const K_VIDES = new Set(['ou', 'sont', 'mes', 'ma', 'mon', 'le', 'la', 'les', 'de', 'du', 'des', 'est', 'un', 'une', 'c', 'je', 'j', 'il', 'quoi', 'et', 'a']);
let K_INDEX = null;
function chercherK(q, liste) {
  const mots = sansAccent(q).split(/\s+/).filter(m => m.length > 1 && !K_VIDES.has(m));
  if (!mots.length) return liste.filter(x => x[0] !== 'Offre' && x[0] !== 'Candidature').slice(0, 8);
  const score = x => { const titre = ' ' + sansAccent(x[1]), tout = titre + ' ' + sansAccent(x[2] + ' ' + x[3]);  // un mot qui commence pareil
    return mots.reduce((s, m) => s + (titre.includes(' ' + m) ? 3 : tout.includes(' ' + m) ? 1 : 0), 0) + (x[0] === 'Page' ? .5 : 0); };
  return liste.map(x => [score(x), x]).filter(a => a[0] >= 1).sort((a, b) => b[0] - a[0]).slice(0, 8).map(a => a[1]);
}
function planK(boite, vise) {  // le plan du site, une case allumée = là où mène le résultat choisi
  const g = el('div', 'ck-plan');
  for (const [nom, c, pages] of K_PLAN) {
    const e = el('div', 'ck-esp'), t = el('div', 't', nom); t.style.background = c; e.append(t);
    const l = el('div', 'l');
    for (const [n, avant, u] of pages) { const a = el('a', u === vise ? 'allume' : ''); a.href = u; a.append(el('b', '', n), el('span', '', 'avant : ' + avant)); l.append(a); }
    e.append(l); g.append(e);
  }
  const r = el('div', 'ck-raccourcis'); r.append(el('b', '', 'Raccourcis clavier'));
  for (const [k, t] of [['Ctrl K', 'chercher partout'], ['D', 'décisions · Échap fermer'], ['G A', 'accueil · G R recherche'], ['G J', 'atelier Jarvis · G B bibliothèque']]) {
    const s = el('span'); s.append(el('kbd', '', k), ' ' + t); r.append(s); }
  g.append(r); boite.append(g);
}
async function actionK(u, rep) {  // les actions qui répondent dans la fenêtre même
  const dire = t => { rep.hidden = false; rep.replaceChildren(el('b', '', 'Jarvis · '), t); };
  if (u === '#lent') {
    try { const v = await api('/sante/vive'); if (v.incident) return dire(v.incident.description);
      const m = ((await api('/sante')).ias || {}).modeles || [], lentes = m.filter(x => x.appels && x.duree_moy > 8).sort((a, b) => b.duree_moy - a.duree_moy);
      dire(lentes.length ? `${lentes[0].nom} est lente (${String(lentes[0].duree_moy).replace('.', ',')} s en moyenne) ; Jarvis passe à la suivante si besoin.` : 'Rien de lent en ce moment : tes IA répondent normalement.');
    } catch (x) { dire(x.message); }
  } else if (u === '#tester') {
    dire('Je teste tes IA…');
    try { const avant = ((await api('/sante/test')).resultat || {}).t; await api('/sante/tester', {});
      for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 2000)); const t = await api('/sante/test');
        if (!t.en_cours && t.resultat && t.resultat.t !== avant) return dire(t.resultat.phrase); }
    } catch (x) { dire(x.message); }
  } else if (u === '#offres') { try { await api('/offres/chercher', {}); dire('C’est lancé : les nouvelles offres arrivent dans Offres d’ici quelques minutes.'); } catch (x) { dire(x.message); } }
  else if (u === '#arreter') { fermerRecherche(); toutArreter(fenetre('Tout arrêter')); }
}
function fermerRecherche() { const c = $('ck'); if (c) { c.remove(); $('ctrlk').textContent = 'Ctrl K'; } }
function ouvrirRecherche() {
  if ($('ck')) return $('ckq').focus();
  const c = el('div', 'ck'); c.id = 'ck'; c.setAttribute('role', 'dialog'); c.setAttribute('aria-label', 'Chercher partout'); $('ctrlk').textContent = 'Ctrl K · ouvert';
  const p = el('section', 'ck-boite'), haut = el('div', 'ck-haut'), q = el('input'); q.id = 'ckq'; q.setAttribute('aria-label', 'Chercher partout');
  q.placeholder = 'Une page, une IA, un rapport, une offre… ou une question'; q.autocomplete = 'off';
  const x = el('button', 'ck-echap', 'Échap'); x.type = 'button'; x.onclick = fermerRecherche;
  haut.append(el('span', 'loupe', '⌕'), q, x);
  const essais = el('div', 'ck-essais'); essais.append(el('span', '', 'Essaie :'));
  for (const t of ['où sont mes IA ?', 'rapport 14', 'vidéo', 'c’est lent', 'offre support']) { const b = el('button', '', t); b.type = 'button'; b.onclick = () => { q.value = t; maj(); q.focus(); }; essais.append(b); }
  const res = el('div', 'ck-res'); res.setAttribute('role', 'listbox'); const rep = el('p', 'ck-rep'); rep.hidden = true;
  const pied = el('div', 'ck-pied'); pied.append(el('span', '', '↑ ↓ choisir'), el('span', '', 'Entrée ouvrir'), el('span', '', 'Une question ? Jarvis répond'));
  p.append(haut, essais, res, rep, pied);
  const droite = el('section', 'ck-droite'); droite.setAttribute('aria-label', 'Le plan du site');
  c.append(p, droite); document.body.append(c);
  let liste = [], choix = 0;
  const aller = it => { const u = it[4]; if (u.startsWith('#')) return actionK(u, rep); fermerRecherche(); if (u === 'accueil.html#fil' && $('filJarvis')) return montrerFil(true); location.href = u; };
  function maj() {
    liste = chercherK(q.value, K_PAGES.concat(K_INDEX || [])); choix = 0; rep.hidden = true; dessiner(); }
  function dessiner() {
    res.replaceChildren(...liste.map((it, k) => { const b = el('button', 'ck-l' + (k === choix ? ' choisi' : '')); b.type = 'button'; b.setAttribute('role', 'option'); b.setAttribute('aria-selected', k === choix);
      const t = el('span', 'type', it[0]); t.style.background = K_COUL[it[0]] || '#1b2318';
      const m = el('span', 'm'); m.append(el('b', '', it[1]), el('span', '', it[2]));
      b.append(t, m, el('span', 'fl', k === choix ? 'Entrée ↵' : '')); b.onclick = () => aller(it); b.onmouseenter = () => { choix = k; dessinerPlan(); }; return b; }));
    if (!liste.length) res.append(el('p', 'vide', 'Rien trouvé. Appuie sur Entrée : Jarvis répond à ta question.'));
    dessinerPlan();
  }
  function dessinerPlan() {
    droite.replaceChildren(); const montrer = Date.now() < K_PLAN_JUSQUA; c.classList.toggle('seule', !montrer); if (!montrer) return;
    const it = liste[choix], u = it && (K_PLACE[it[4]] || it[4].replace(/#offre=.*/, '')), page = K_PLAN.flatMap(e => e[2].map(p => [e[0], p])).find(([, p]) => p[2] === u);
    const h = el('div', 'ck-titre'); h.append(el('h2', '', 'Où est passé quoi ?'), el('span', '', '18 pages rangées en 4 espaces. Plus de menu « Plus ».')); droite.append(h);
    if (page && q.value.trim()) { const d = el('div', 'ck-dest'); d.append('Tu irais à : ', el('b', '', `${page[0]} → ${page[1][0]}`), ' (la case s’allume ci-dessous)'); droite.append(d); }
    planK(droite, page && q.value.trim() ? u : null);
  }
  q.oninput = maj;
  q.onkeydown = e => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (liste.length) { choix = (choix + (e.key === 'ArrowDown' ? 1 : liste.length - 1)) % liste.length; dessiner(); } }
    else if (e.key === 'Enter') { e.preventDefault(); if (liste[choix]) aller(liste[choix]); else if (q.value.trim()) { fermerRecherche(); location.href = 'accueil.html?q=' + encodeURIComponent(q.value.trim().slice(0, 3000)); } }
  };
  c.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); fermerRecherche(); } });
  c.addEventListener('mousedown', e => { if (e.target === c) fermerRecherche(); });
  const q0 = /[#&]k=([^&]*)/.exec(location.hash); if (q0) q.value = decodeURIComponent(q0[1]);  // page.html#k=… : recherche pré-remplie (tests, captures)
  maj(); q.focus();
  if (!K_INDEX) api('/recherche/index').then(d => { K_INDEX = (d.index || []).map(i => [i.type, i.titre, i.sous, i.mots, i.url]); maj(); }).catch(() => {});
}
/* Raccourcis : Ctrl K · D (décisions) · G A / G R / G J / G B (les 4 espaces). Jamais pendant qu'on tape dans un champ. */
let K_G = 0;
addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'k') { e.preventDefault(); ouvrirRecherche(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey || (e.target.closest && e.target.closest('input,textarea,select,[contenteditable],dialog')) || $('ck')) return;
  const k = e.key.toLowerCase();
  if (K_G && Date.now() - K_G < 1500) { K_G = 0; const u = {a: 'accueil.html', r: 'emploi.html', j: 'pilote.html', b: 'rapports.html'}[k]; if (u) { e.preventDefault(); location.href = u; } return; }
  if (k === 'g') K_G = Date.now();
  else if (k === 'd') location.href = 'decisions.html';
});
if (/[#&]k=/.test(location.hash)) setTimeout(ouvrirRecherche);

/* ---------- Fenêtre (dialog natif : Échap ferme, le focus reste dedans) ---------- */
function fenetre(titre) {
  let d = $('fen');
  if (!d) { d = el('dialog', 'fen'); d.id = 'fen'; d.addEventListener('click', e => { if (e.target === d) d.close(); }); document.body.append(d); }
  const boite = el('div', 'boite'), tete = el('div', 'tete'), x = el('button', 'x', '×');
  x.type = 'button'; x.setAttribute('aria-label', 'Fermer'); x.onclick = () => d.close();
  tete.append(el('h2', '', titre), x); boite.append(tete); d.replaceChildren(boite);
  if (!d.open) d.showModal();
  return boite;
}

/* ---------- Réglages : services, Telegram (code d'appairage), lien vers les quotas, arrêts (l'IA par défaut : mes-ia.html) ---------- */
async function ouvrirReglages() {
  const ici = $('reglages'), p = ici || fenetre('Réglages');  // mission 15 : Réglages est une page (reglages.html), la fenêtre reste pour les anciens liens
  if (ici) p.replaceChildren();
  let e;
  try { e = await api('/etat'); } catch (err) { p.append(el('p', 'mut', 'Jarvis est éteint : double-clique sur JARVIS.bat.')); return; }
  const s = e.services || {}, sv = el('div', 'services');
  for (const [ok, nom] of [[s.ollama, s.ollama ? 'IA locale' : 'IA locale (éteinte tant qu’elle ne sert pas)'], [s.routeur, 'Routeur'], [true, 'Jarvis'], [s.telegram_lie, 'Telegram']]) {
    const x = el('span', ok ? 'ok' : ''); x.append(el('i'), document.createTextNode(nom)); sv.append(x); }
  p.append(el('h3', '', 'Services'), sv);
  const tg = e.telegram || {};
  p.append(el('h3', '', 'Telegram'));
  if (tg.lie) p.append(el('p', 'mut', 'Lié à ton compte. C’est bon.'));
  else if (tg.code) { const c = el('p', 'mut'); c.append(`Envoie à @${tg.bot || 'ton bot'} :  `, el('span', 'code-tg', '/lier ' + tg.code)); p.append(c, el('p', 'dim', 'Une seule fois. Ce code change après 5 essais faux.')); }
  else p.append(el('p', 'mut', 'Bot : ' + (tg.etat || 'arrêté') + (tg.erreur ? ' · ' + tg.erreur : '')));
  const qs = el('p', 'mut'); qs.append('Tokens, vitesse et quota de chaque IA : ', lien('page Santé', 'sante.html', ''), ' (mêmes chiffres que le Pilote).');
  p.append(el('h3', '', 'Quotas'), qs);
  const l2 = el('div', 'actions');
  l2.append(bouton(e.arret ? 'Relancer les agents' : 'Arrêt d’urgence', e.arret ? 'pri' : 'danger', async () => {
      if (!e.arret && !confirm('Couper tous les appels aux IA (Jarvis, Découvertes, Telegram) ?')) return;
      await api('/arret', {actif: !e.arret}).catch(() => {}); ouvrirReglages(); }),
    bouton('Tout arrêter', 'danger', () => toutArreter(p)));
  p.append(el('h3', '', 'Partager le projet'), el('p', 'dim', 'L’export automatique est désactivé dans la version publique : le code est sur GitHub, sans clé ni donnée perso.'));
  p.append(el('h3', '', 'Arrêts'), l2, el('p', 'dim', 'Obsidian, la première fois : « Ouvrir un dossier comme coffre » → jarvis\\memoire.'));
  /* Mission 15 : le thème (aussi dans la barre du haut) */
  const tz = el('div', 'actions');
  const dessinerTh = () => { const t = memo.lire('theme') || 'auto'; tz.replaceChildren(...[['auto', 'Auto (sombre de 22 h à 7 h)'], ['clair', 'Clair'], ['sombre', 'Sombre']].map(([k, n]) => {
    const b = bouton(n, t === k ? 'sombre' : '', () => { choisirTheme(k); dessinerTh(); }); b.setAttribute('aria-pressed', t === k); return b; })); };
  dessinerTh(); p.append(el('h3', '', 'Thème'), tz);
  /* Mission 16 : l'initiative de Jarvis (seulement ce qui s'annule, seulement si tu es là) et la dictée */
  const iz = el('div', 'actions'), im = el('p', 'dim');
  const NIV = {prudent: ['Prudent', 'Il te propose, il ne fait rien seul.'], normal: ['Normal', 'Il prépare les brouillons de lettre, réessaie une question ratée, range une offre expirée. Tout s’annule depuis le Journal.'],
               audacieux: ['Audacieux', 'Comme Normal, plus souvent (budget du Directeur doublé). Toujours rien d’irréversible.']};
  const dessinerIni = n => { iz.replaceChildren(...Object.entries(NIV).map(([k, [nom]]) => { const b = bouton(nom, n === k ? 'sombre' : '', async () => {
      try { dessinerIni((await api('/reglages/initiative', {niveau: k})).niveau); } catch (x) { toast(x.message); } }); b.setAttribute('aria-pressed', n === k); return b; }));
    im.textContent = NIV[n][1]; };
  api('/reglages/initiative').then(d => dessinerIni(d.niveau)).catch(() => dessinerIni('normal'));
  p.append(el('h3', '', 'Initiative de Jarvis'), iz, im);
  const de = el('label', 'mut'), cb = el('input'); cb.type = 'checkbox'; cb.checked = memo.lire('jarvis-dictee-edge') === 'oui';
  cb.onchange = () => memo.ecrire('jarvis-dictee-edge', cb.checked ? 'oui' : 'non');
  de.append(cb, ' Dictée instantanée d’Edge');
  p.append(el('h3', '', 'Dictée'), de, el('p', 'dim', 'Éteinte par défaut. Allumée, ta voix part chez Microsoft pour être reconnue. Éteinte, elle reste sur ton PC (Whisper, carte graphique).'));
  /* Mission 13 : mes jeux (nom du programme) — pendant un jeu, Jarvis se met en pause et éteint l'IA locale */
  const j = el('input'); j.setAttribute('aria-label', 'Mes jeux'); j.placeholder = 'ex. league of legends.exe, rocketleague.exe';
  api('/gardien').then(d => { j.value = (d.jeux || []).join(', '); }).catch(() => {});
  const jm = el('p', 'dim', 'Les jeux connus (LoL, Valorant, CS2, Fortnite, Rocket League…) sont déjà reconnus, ainsi que le plein écran.');
  p.append(el('h3', '', 'Mes jeux'), j, bouton('Enregistrer mes jeux', '', async () => {
    try { const r = await api('/reglages/jeux', {jeux: j.value.split(',').map(x => x.trim()).filter(Boolean)}); jm.textContent = 'Enregistré : ' + (r.jeux.join(', ') || 'aucun jeu ajouté') + '.'; }
    catch (x) { jm.textContent = x.message; } }), jm);
}

/* Pastille sur « Le jeu » = mails qui valent une réponse ; « Décisions · N » (mission 15 : discret, petit point orange). */
async function surveiller() {
  try {
    const e = await api('/etat'), s = e.services || {};
    const n = e.a_repondre || 0, j = $('nav-jeu'); let b = j.querySelector('.pastille');
    if (n && !b) { b = el('span', 'pastille'); j.append(b); }
    if (b) { if (n) { b.textContent = n; b.title = n + ' mail(s) qui valent une réponse'; } else b.remove(); }
    const d = (await api('/decisions')).decisions.length, pb = $('nav-decisions');
    pb.textContent = d ? 'Décisions · ' + d : 'Décisions'; pb.classList.toggle('a-faire', d > 0); pb.title = d ? d + ' décision(s) pour toi' : 'Rien à décider';
  } catch (_) {}
}
surveiller(); setInterval(surveiller, 30000);
/* Mission 11 : « je suis là » toutes les 30 s et à chaque changement d'onglet. Onglet caché ou PC inutilisé 10 min = Jarvis en pause ;
   plus aucun onglet pendant 2 min = Jarvis s'arrête tout seul. Le serveur décide aussi du cycle du Directeur (au plus toutes les 3 h). */
const ONGLET = Math.random().toString(36).slice(2, 10);
let PRESENT = null;
const DELAIS = {prevu: 75, max: 255};  // mission 14 : remplacés par ceux de reglages.json (/sante/vive)
const siteOuvert = () => api('/site/ouvert', {onglet: ONGLET, visible: document.visibilityState === 'visible'}).then(r => {
  if (r.present === undefined) return; PRESENT = r; if (!r.present) FIL = null; voyant(); if (r.present && !FIL) lireFil(); if ($('filJarvis') && !$('filJarvis').hidden) dessinerFil();
}).catch(() => {});
/* Mission 14 : le voyant à 5 états, jamais de faux « prêt » : Site prêt · Routeur en démarrage · IA disponible · En pause · Erreur. */
function voyant() {
  const p = $('presence'); if (!p) return;
  const v = window.SANTE, r = v && (v.composants || {}).routeur, cl = p.classList;
  let t = 'Jarvis attend · rien ne tourne', etat = '';
  if (PRESENT && !PRESENT.present) { t = 'En pause : ' + (PRESENT.raison || 'tu n’es pas sur le site'); etat = 'pause'; }
  else if (v && !v.routeur_vivant && Date.now() / 1000 - v.demarrage < 120) { t = 'Routeur en démarrage'; etat = 'pause'; }
  else if (v && (!v.routeur_vivant || (r && r.etat === 'muet'))) { t = 'Erreur : le routeur ne répond pas'; etat = 'erreur'; }
  const c = FIL && FIL.actif && FIL.en_cours;  // mission 15 : ce qui tourne vraiment passe avant « Jarvis attend »
  if (c && !etat) t = `${c.qui} ${c.quoi.split(' ')[0]} · ${duree(c.depuis)}`;
  p.replaceChildren(el('span', 't', t), el('span', 'v', ' ▾')); p.setAttribute('aria-label', t + ' : voir le fil'); cl.toggle('travaille', !!(c && !etat)); cl.toggle('pause', etat === 'pause'); cl.toggle('erreur', etat === 'erreur');
  p.title = v && v.incident ? v.incident.description : '';
}
/* Mission 14 : le navigateur surveille le serveur (toutes les 30 s, seulement page visible, délai court). Muet 2 fois → bandeau
   « Jarvis ne répond plus » + « Relancer Jarvis » (lance JARVIS.bat, qui reconnaît l'instance gelée). Rien sans ce clic. */
let MUET = 0;
async function veilleServeur() {
  if (document.visibilityState !== 'visible') return;
  const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), 5000);
  try { window.SANTE = await api('/sante/vive', undefined, ctl.signal); MUET = 0;
    if (SANTE.delais) Object.assign(DELAIS, SANTE.delais);
    bandeau(SANTE.perime && PRESENT && PRESENT.present ? 'Surveillance indisponible : Jarvis ne vérifie plus ses pannes pour le moment.' : '');
    document.dispatchEvent(new Event('sante'));
  } catch (e) { if (!e.code && ++MUET >= 2) bandeau('Jarvis ne répond plus.', true); }  // une réponse d'erreur = il répond
  finally { clearTimeout(t); voyant(); }
}
function bandeau(texte, relancer) {
  let b = $('bandeauPanne');
  if (!texte) { if (b) b.remove(); return; }
  if (!b) { b = el('div', 'bandeau-panne'); b.id = 'bandeauPanne'; b.setAttribute('role', 'alert'); document.body.prepend(b); }
  b.replaceChildren(el('span', '', texte));
  if (relancer) { const a = lien('Relancer Jarvis', 'jarvis-relance:', 'btn pri'); a.removeAttribute('target');
    a.title = 'Lance JARVIS.bat (Windows te demande de confirmer)'; b.append(a); }
}
if (location.protocol !== 'file:') { veilleServeur(); setInterval(veilleServeur, 30000); document.addEventListener('visibilitychange', veilleServeur); }
siteOuvert(); setInterval(siteOuvert, 30000); document.addEventListener('visibilitychange', siteOuvert);
/* Mission 13 : la page se ferme (ou l'onglet part en arrière-plan) → un dernier « caché », envoyé même si la page disparaît.
   Un onglet caché ou un navigateur réduit (visibilityState = hidden) ne compte jamais comme « la personne est présente ». */
addEventListener('pagehide', () => { try { fetch(API + '/site/ouvert', {method: 'POST', keepalive: true, headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({onglet: ONGLET, visible: false})}); } catch (_) {} });

/* ---------- Les offres : une seule page, utilisée par Emploi et par le Panneau des offres du jeu ---------- */
const PUCES_OFFRE = o => [o.contrat, o.experience && (o.experience === 'débutant accepté' ? 'débutant accepté' : 'exp. ' + o.experience), o.salaire].filter(Boolean);

/* Le texte complet, avec la phrase-preuve surlignée (texte inerte : jamais interprété comme du HTML). */
function texteSurligne(texte, phrase) {
  const p = el('div', 'texte-offre');
  if (!phrase) { p.textContent = texte; return p; }
  const motif = new RegExp(phrase.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+').replace(/['’]/g, "['’]"), 'i');
  const m = motif.exec(texte);
  if (!m) { p.textContent = texte; return p; }
  p.append(texte.slice(0, m.index), el('mark', '', m[0]), texte.slice(m.index + m[0].length));
  return p;
}

async function voirCorbeille(apres) {
  const b = fenetre('Corbeille des offres'); let d;
  try { d = await api('/offres/corbeille'); } catch (e) { b.append(el('p', '', e.message)); return; }
  if (!d.offres.length) { b.append(el('p', 'mut', 'La corbeille est vide.')); return; }
  for (const o of d.offres) { const p = el('p'); p.append(el('b', '', o.titre), ` · ${o.entreprise || ''} · enlevée le ${(o.quand || '').slice(0, 10)} `,
    bouton('Remettre', '', async ev => { ev.target.disabled = true; try { await api('/offres/choisir', {id: o.id, quoi: 'remettre'}); p.remove(); toast('Remise dans tes offres.'); if (apres) apres(); } catch (e) { toast(e.message); } })); b.append(p); }
}
async function pasPourMoi(o, apres) {
  try { await api('/offres/pas-pour-moi', {id: o.id}); toast('Dans la Corbeille. Jarvis ne te la reproposera pas.'); if (apres) apres(); }
  catch (e) { toast(e.message); return; }
  /* Mission 12 : pourquoi ? (facultatif) — les raisons aident Jarvis à te proposer une règle dans Décisions */
  const b = fenetre('Pourquoi ? (facultatif)'), choix = el('div', 'actions');
  b.append(el('p', 'dim', 'Ta réponse aide Jarvis à mieux trier. Tu peux fermer sans répondre.'), choix);
  const envoyer = async (raison, texte) => { try { const r = await api('/offres/pas-pour-moi/raison', {id: o.id, raison, texte});
    $('fen').close(); toast(r.regle_proposee ? 'Merci. Jarvis te propose une règle dans Décisions.' : 'Merci, c’est noté.'); } catch (e) { toast(e.message); } };
  for (const r of ['trop loin', 'trop d\'expérience demandée', 'pas mon domaine', 'contrat', 'salaire', 'entreprise']) choix.append(bouton(r, '', () => envoyer(r)));
  const autre = el('input'); autre.placeholder = 'Autre raison…'; autre.maxLength = 200; autre.setAttribute('aria-label', 'Autre raison');
  choix.append(autre, bouton('Envoyer', '', () => autre.value.trim() && envoyer('autre', autre.value.trim())));
}

async function ouvrirOffre(o, apres) {
  const id = typeof o === 'string' ? o : o.id;
  const b = fenetre(typeof o === 'string' ? 'Offre' : o.titre); b.parentElement.classList.add('large');
  const attente = el('p', 'dim', 'Chargement de l’offre…'); b.append(attente);
  try { o = await api('/offres/detail?id=' + encodeURIComponent(id)); } catch (e) { attente.textContent = 'Offre introuvable.'; return; }
  attente.remove(); b.querySelector('h2').textContent = o.titre;
  const sous = el('p', 'mut', [o.entreprise, o.ville, o.region].filter(Boolean).join(' · ')); b.append(sous);
  const puces = el('div', 'puces-offre'); PUCES_OFFRE(o).forEach(t => puces.append(el('span', '', t))); b.append(puces);
  if (o.etat === 'pour_toi' && o.pourquoi) b.append(el('p', 'pourquoi', 'Pourquoi elle te va : ' + o.pourquoi));
  if (o.etat === 'a_verifier') b.append(el('p', 'alerte-lien', 'À vérifier : ' + o.raison + '. À toi de juger en lisant l’offre.'));
  if (o.etat === 'ecartee') b.append(el('p', 'alerte-lien', 'Écartée : ' + o.raison + '.'));
  if (o.experience_phrase) { const q = el('p', 'dim'); q.append('Ce que dit l’offre sur l’expérience : ', el('mark', '', o.experience_phrase)); b.append(q); }
  const act = el('div', 'actions');
  if (o.postule) b.append(el('p', 'pourquoi', 'Déjà postulé le ' + o.postule.slice(8, 10) + '/' + o.postule.slice(5, 7) + ' : rien à refaire.'));  // mission 12 : le bouton Postuler est remplacé
  else if (o.lien_etat === 'casse') b.append(el('p', 'alerte-lien', 'Cette offre n’est plus en ligne : le site l’a retirée.'));
  else if (!httpSur(o.lien)) b.append(el('p', 'alerte-lien', 'Le lien de cette offre manque. Cherche son titre sur France Travail ou Indeed.'));
  else { const a = lien('Postuler sur le site de l’offre', o.lien, 'btn pri gros'); a.onclick = () => api('/jeu/xp', {raison: 'offre_ouverte', ref: o.id}).catch(() => {}); act.append(a); }
  if (typeof boutonsCandidature === 'function') boutonsCandidature(o, act, apres);
  if (o.etat !== 'pas_pour_moi') act.append(bouton('Pas pour moi', 'danger', () => { $('fen').close(); pasPourMoi(o, apres); }));
  b.append(act);
  if (o.texte) b.append(el('h3', '', 'L’offre en entier'), texteSurligne(o.texte, o.experience_phrase));
  else b.append(el('p', 'dim', 'Le texte complet n’a pas pu être lu : ouvre le site de l’offre.'));
  b.append(el('p', 'dim', 'C’est toi qui postules : Jarvis ne contacte jamais une entreprise à ta place.'));
}

/* Les offres (page Emploi et Panneau des offres du jeu) : la liste à gauche, l'offre lue à droite (maquette EmploiB, mission 7).
   Onglets Pour toi · À lire · À vérifier · Postulé (mission 8 : « À lire » = pas encore analysée), filtre zone locale / Sud / VIE / Tout, tri par score. */
async function afficherOffres(box, etat) {
  etat = etat || (afficherOffres.etat = afficherOffres.etat || {onglet: 'pour_toi', region: memo.lire('emploi_region') || 'Tout', voirEcartees: false, choisie: ''});
  box.replaceChildren(el('p', 'dim', 'Chargement…'));
  let d; try { d = await api('/offres'); } catch (e) { box.replaceChildren(el('p', 'alerte-lien', 'Jarvis est éteint : lance JARVIS.bat.')); return; }
  const recharger = () => afficherOffres(box, etat), c = d.compte || {};
  const groupes = {pour_toi: o => o.etat === 'pour_toi' && !o.postule, a_lire: o => o.etat === 'a_lire' && !o.postule,
    a_verifier: o => ['a_verifier', 'erreur'].includes(o.etat) && !o.postule, postule: o => !!o.postule};
  const zone = o => etat.region === 'Tout' || o.region === etat.region;
  const visibles = d.offres.filter(zone);  // mission 10 : plus rien n'est caché tout seul (lien mort, +30 jours = étiquettes)
  const liste = visibles.filter(groupes[etat.onglet]);
  if (etat.voirEcartees) liste.push(...d.offres.filter(o => o.etat === 'ecartee' && zone(o)));

  const lecteur = el('div', 'lecteur'), gauche = el('aside', 'lecteur-liste'), tete = el('div', 'lecteur-tete');
  const ongl = el('div', 'lecteur-onglets'); ongl.setAttribute('role', 'tablist');
  for (const [v, n] of [['pour_toi', 'Pour toi'], ['a_lire', 'À lire'], ['a_verifier', 'À vérifier'], ['postule', 'Postulé']]) {
    const b = el('button', '', `${n} ${visibles.filter(groupes[v]).length}`); b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', etat.onglet === v);
    b.onclick = () => { etat.onglet = v; etat.choisie = ''; etat.voirEcartees = false; recharger(); }; ongl.append(b); }
  const filtres = el('div', 'lecteur-zones');
  for (const r of ['Zone locale', 'Sud', 'VIE', 'Tout']) { const b = el('button', '', r); b.type = 'button'; b.setAttribute('aria-pressed', r === etat.region);
    b.title = r === 'Sud' ? 'Autres villes de la zone Sud' : ''; b.onclick = () => { etat.region = r; etat.choisie = ''; memo.ecrire('emploi_region', r); recharger(); }; filtres.append(b); }
  tete.append(el('h2', '', 'Mes offres'), ongl, filtres); gauche.append(tete);
  if (etat.onglet === 'postule') gauche.append(lien('Les chiffres et les réponses des recruteurs →', 'emploi.html#candidatures', 'lecteur-pied'));
  const droite = el('section', 'lecteur-offre'); droite.setAttribute('aria-live', 'polite');
  let active = null;
  const choisir = (o, ligne) => { if (active) active.removeAttribute('aria-current'); active = ligne; ligne.setAttribute('aria-current', 'true'); etat.choisie = o.id; lireOffre(o, droite, recharger);
    if (o.nouvelle) { o.nouvelle = false; const n = ligne.querySelector('.nouv'); if (n) n.remove(); api('/offres/vues', {ids: [o.id]}).catch(() => {}); } };  // vue = ouverte, pas seulement listée
  const ul = el('div', 'lecteur-lignes'); let premiere = null;
  for (const o of liste) {
    const l = el('button', 'lecteur-ligne'); l.type = 'button';
    const t = el('span', 't'); t.append(el('b', '', o.titre), el('span', '', [(o.ville || o.lieu || '').replace(/^\d+ -? ?/, ''), o.contrat, o.date].filter(Boolean).join(' · ')));
    l.append(el('span', 'score', o.etat === 'a_lire' ? 'en lecture' : o.score ? String(o.score) : '–'), t);  // m12 : jamais « 0 » pour une offre pas lue
    if (o.nouvelle) l.append(el('span', 'nouv', 'nouvelle'));
    if (o.gardee) l.append(el('span', 'nouv', 'gardée'));
    for (const e of o.etiquettes || []) l.append(el('span', 'etiq', e));
    l.onclick = () => choisir(o, l); ul.append(l);
    if (!premiere || o.id === etat.choisie) premiere = [o, l];
  }
  gauche.append(liste.length ? ul : el('p', 'lecteur-vide', etat.onglet === 'postule' ? 'Tu n’as encore postulé à aucune offre d’ici.' : etat.onglet === 'pour_toi' ? 'Aucune offre vérifiée pour cette zone.' : etat.onglet === 'a_lire' ? 'Tout est lu.' : 'Rien à vérifier ici.'));
  if (c.a_lire && etat.onglet !== 'a_lire') gauche.append(el('p', 'lecteur-pied', `${c.a_lire} offre${c.a_lire > 1 ? 's' : ''} à lire : Jarvis lit les nouvelles offres une fois par heure.`));
  const nb = Object.values(d.ecartees || {}).reduce((a, b) => a + b, 0);
  if (nb && etat.onglet !== 'postule') {
    const p = el('p', 'lecteur-pied'), raisons = Object.entries(d.ecartees).sort((a, b) => b[1] - a[1]).map(([r, n]) => `${r} (${n})`).join(', ');
    p.append(`${nb} écartée${nb > 1 ? 's' : ''} : ${raisons}. `);
    const v = el('button', 'lien-bouton', etat.voirEcartees ? 'cacher' : 'voir'); v.type = 'button'; v.onclick = () => { etat.voirEcartees = !etat.voirEcartees; recharger(); };
    p.append(v); gauche.append(p);
  }
  const autres = [c.pas_pour_moi && `${c.pas_pour_moi} « pas pour moi »`].filter(Boolean);
  if (autres.length) gauche.append(el('p', 'lecteur-pied', autres.join(' · ') + '.'));
  if (d.corbeille) { const p = el('p', 'lecteur-pied', `${d.corbeille} dans la corbeille (enlevées par toi). `);
    const v = el('button', 'lien-bouton', 'voir'); v.type = 'button'; v.onclick = () => voirCorbeille(recharger); p.append(v); gauche.append(p); }
  lecteur.append(gauche, droite); box.replaceChildren(lecteur);
  if (premiere) choisir(...premiere); else droite.append(el('p', 'mut', 'Choisis une offre à gauche.'));
}
/* L'offre lue : mini-résumé, toutes les infos, la phrase qui prouve, Postuler sur le site de l'offre. */
async function lireOffre(o, zone, recharger) {
  const statut = o.postule ? 'Postulé le ' + o.postule.slice(0, 10) : ({a_verifier: 'À vérifier', a_lire: 'En lecture', erreur: 'À vérifier', ecartee: 'Lue · écartée', pas_pour_moi: 'Pas pour moi'})[o.etat] || 'Lue · pour toi';
  const haut = el('div', 'lo-haut'), titre = el('div', 'lo-titre');
  titre.append(el('span', 'lo-statut', o.score ? `${statut} · ${o.score} / 100` : statut), el('h2', '', o.titre), el('p', 'mut', [o.entreprise, (o.ville || o.lieu || '').replace(/^\d+ -? ?/, ''), o.contrat].filter(Boolean).join(' · ')));
  haut.append(titre);
  if (o.postule) haut.append(el('span', 'lo-postuler', 'Déjà postulé le ' + o.postule.slice(8, 10) + '/' + o.postule.slice(5, 7)));
  else if (o.lien_etat !== 'casse' && httpSur(o.lien)) { const a = lien('Postuler sur le site de l’offre', o.lien, 'btn lo-postuler'); a.onclick = () => api('/jeu/xp', {raison: 'offre_ouverte', ref: o.id}).catch(() => {}); haut.append(a); }
  const infos = el('div', 'lo-infos');
  for (const [k, v, bon] of [['Contrat', o.contrat], ['Expérience', o.experience, /débutant|0 an|sans exp/i.test(o.experience || '')], ['Diplôme', o.diplome],
                             ['Salaire', o.salaire || 'non précisé'], ['Lieu', (o.lieu || o.ville || '').replace(/^\d+ -? ?/, '')], ['Télétravail', o.teletravail]]) {
    if (!v) continue; const i = el('div', bon ? 'bon' : ''); i.append(el('b', '', k), document.createTextNode(v)); infos.append(i); }
  const pourquoi = el('div', 'lo-pourquoi');
  pourquoi.append(el('h3', '', o.etat === 'pour_toi' ? 'Pourquoi Jarvis la garde' : o.etat === 'ecartee' ? 'Pourquoi elle est écartée' : 'Ce qu’il faut vérifier'));
  const resume = o.resume || o.verdict; if (resume) pourquoi.append(el('p', '', resume + '.'));
  if (o.pourquoi && o.etat === 'pour_toi') pourquoi.append(el('p', '', o.pourquoi));
  if (o.raison && o.etat !== 'pour_toi') pourquoi.append(el('p', '', o.raison + '.'));
  if (o.etat === 'a_lire') pourquoi.append(el('p', '', 'Jarvis ne l’a pas encore lue en entier.'));
  if (o.detail) pourquoi.append(el('p', 'dim', 'Détail technique : ' + o.detail));
  if (o.experience_phrase) { const p = el('p'); p.append('L’offre dit : ', el('mark', '', '« ' + o.experience_phrase + ' »')); pourquoi.append(p); }
  const act = el('div', 'actions lo-actions');
  if (o.lien_etat === 'casse') act.append(el('p', 'alerte-lien', 'Cette offre n’est plus en ligne : le site l’a retirée.'));
  else if (!httpSur(o.lien)) act.append(el('p', 'alerte-lien', 'Le lien de cette offre manque. Cherche son titre sur France Travail ou Indeed.'));
  zone.replaceChildren(haut, infos, pourquoi, act);
  boutonsCandidature(o, act, recharger);
  if (o.etat !== 'pas_pour_moi' && o.etat !== 'ecartee') act.append(bouton('Pas pour moi', '', () => pasPourMoi(o, recharger)));
  act.insertBefore(bouton(o.gardee ? 'Gardée ✓' : 'Garder', o.gardee ? 'vert' : '', async () => {
    try { await api('/offres/choisir', {id: o.id, quoi: o.gardee ? 'ne_plus_garder' : 'garder'}); recharger(); } catch (e) { toast(e.message); } }), act.children[2] || null);
  const enl = bouton('Enlever', '', () => {  // confirmation dans la page : l'offre va dans la corbeille, d'où on peut la remettre
    const oui = bouton('Oui, l’enlever', 'danger', async () => { try { await api('/offres/choisir', {id: o.id, quoi: 'enlever'}); toast('Dans la corbeille : tu peux la remettre.'); recharger(); } catch (e) { toast(e.message); } });
    const non = bouton('Non', '', () => conf.replaceWith(enl)); const conf = el('span', 'confirm'); conf.append('Sûr ? ', oui, ' ', non); enl.replaceWith(conf); });
  act.append(enl);
  if ((o.etiquettes || []).length) act.prepend(el('p', 'dim', 'Étiquettes : ' + o.etiquettes.join(', ') + ' (c’est toi qui décides).'));
  const tout = el('details', 'lo-texte'); tout.append(el('summary', '', 'Lire l’offre en entier')); zone.append(tout,
    el('p', 'dim', 'C’est toi qui postules : Jarvis ne contacte jamais une entreprise à ta place.'));
  tout.ontoggle = async () => { if (!tout.open || tout.dataset.lu) return; tout.dataset.lu = 1; tout.append(el('p', 'dim', 'Chargement…'));
    try { const x = await api('/offres/detail?id=' + encodeURIComponent(o.id)); tout.lastChild.replaceWith(x.texte ? texteSurligne(x.texte, x.experience_phrase) : el('p', 'dim', 'Le texte complet n’a pas pu être lu : ouvre le site de l’offre.')); }
    catch (e) { tout.lastChild.textContent = 'Offre introuvable.'; } };
}

/* ---------- Postuler, c'est toi : la lettre (à copier ou en .docx) et « J'ai postulé » ---------- */
function boutonsCandidature(o, act, apres) {
  const zone = el('div', 'lettre'); act.after(zone);
  const preparer = async (ev, info) => {
    ev.target.disabled = true; zone.replaceChildren(el('p', 'dim', 'Jarvis écrit une lettre courte, d’après ta page « Moi »…'));
    try {
      const r = await api('/offres/lettre', {id: o.id, info});
      if (r.question) {  // mission 12 : il manque de quoi parler de l'entreprise → une question plutôt qu'une invention
        const rep = el('textarea'); rep.setAttribute('aria-label', 'Ta réponse'); rep.style.minHeight = '70px';
        zone.replaceChildren(el('h3', '', 'Une question avant d’écrire'), el('p', '', r.question), rep,
          bouton('Écrire la lettre', 'pri', e => rep.value.trim() && preparer(e, rep.value.trim())));
        ev.target.disabled = false; return;
      }
      const t = el('textarea'); t.value = r.texte; t.setAttribute('aria-label', 'Ta lettre (modifie-la)');
      const a = el('div', 'actions');
      a.append(bouton('Copier', '', async () => { try { await navigator.clipboard.writeText(t.value); toast('Copiée'); } catch (_) { t.select(); toast('Sélectionnée : Ctrl+C'); } }),
        bouton('Télécharger en .docx', '', async () => { try { const g = await api('/offres/lettre/garder', {id: o.id, texte: t.value}); location.href = API + g.url; } catch (e) { toast(e.message); } }));
      zone.replaceChildren(el('h3', '', 'Ta lettre (relis-la et modifie-la)'), t, a, el('p', 'dim', 'Écrite par ' + (r.ia || 'Rédaction') + '. Rien n’est envoyé : tu la colles toi-même sur le site de l’offre.'));
      for (const x of (r.alertes || [])) zone.append(el('p', 'alerte-lien', x));
      if ((r.retire || []).length) { const d = el('details'); d.append(el('summary', '', `Le vérificateur a retiré ${r.retire.length} phrase${r.retire.length > 1 ? 's' : ''}`));
        r.retire.forEach(x => d.append(el('p', 'dim', x))); zone.append(d); }
    } catch (e) { zone.replaceChildren(el('p', 'alerte-lien', e.message)); }
    ev.target.disabled = false;
  };
  act.append(bouton('Préparer ma lettre', '', ev => preparer(ev)));
  act.append(bouton(o.postule ? 'Postulé le ' + o.postule.slice(0, 10) : 'J’ai postulé', o.postule ? 'vert' : '', async ev => {
    if (o.postule) return;
    try { const r = await api('/offres/postule', {id: o.id}); o.postule = r.t; ev.target.textContent = 'Postulé le ' + r.t.slice(0, 10); ev.target.className = 'btn vert';
          toast('Ajoutée à Mes candidatures. Bonne chance !'); if (apres) apres(); } catch (e) { toast(e.message); }
  }));
}

/* ---------- Un mail reçu, en entier, et les échanges d'avant (lus sur ton PC uniquement) ---------- */
function blocMail(m, ouvert) {
  const d = el('details', 'mail-complet prive'); d.open = !!ouvert;
  d.append(el('summary', '', `${(m.date || '').slice(0, 16).replace('T', ' ')} · ${m.de}`), el('p', 'dim', 'Objet : ' + (m.sujet || '')), el('div', 'texte-offre', m.texte || '(vide)'));
  return d;
}
async function chargerFil(m, zone) {
  zone.replaceChildren(el('p', 'dim', 'Lecture du mail sur ton PC…'));
  try {
    const f = await api('/mails/fil?id=' + encodeURIComponent(m.id));
    zone.replaceChildren(el('h3', '', 'Le mail reçu'), f.recu ? blocMail(f.recu, true) : el('p', 'dim', 'Mail introuvable dans Gmail.'));
    const avant = f.fil.filter(x => !f.recu || x.id !== f.recu.id);
    if (avant.length) { const d = el('details'); d.append(el('summary', '', `Les échanges d’avant avec eux (${avant.length}), du plus ancien au plus récent`)); avant.forEach(x => d.append(blocMail(x, false))); zone.append(d); }
    return f;
  } catch (e) { zone.replaceChildren(el('p', 'alerte-lien', 'Lecture impossible : ' + e.message)); return null; }
}
async function ouvrirFil(m) {
  const b = fenetre(m.entreprise || 'Un recruteur'); b.parentElement.classList.add('large');
  const zone = el('div'); b.append(zone, el('p', 'dim', 'Lu sur ton PC : rien ne part sur Telegram ni dans une IA en ligne.'));
  await chargerFil(m, zone);
  if (m.action_requise) b.append(el('div', 'actions'), bouton('Préparer une réponse', 'pri', () => ouvrirBrouillon(m)));
}

/* ---------- Brouillon de réponse à un mail (écrit sur ton PC, envoyé seulement après ton clic) ---------- */
async function ouvrirBrouillon(m, apres) {
  const b = fenetre('Répondre à ' + (m.entreprise || 'un recruteur')); b.classList.add('prive'); b.parentElement.classList.add('large');
  const filZone = el('div'); b.append(filZone);
  const [, rep] = await Promise.all([chargerFil(m, filZone), api('/mails/brouillon', {id: m.id}).catch(e => ({erreur: e.message}))]);
  if (rep.erreur) { b.append(el('p', 'alerte-lien', 'Brouillon impossible : ' + rep.erreur)); return; }
  const d = rep;
  b.append(el('h3', '', 'Ta réponse : destinataire, objet et texte complet'));
  const champ = (lab, val, tag) => { const l = el('label', '', lab), i = el(tag || 'input'); i.id = 'br-' + lab.slice(0, 3); l.htmlFor = i.id; i.value = val || ''; b.append(l, i); return i; };
  const a = champ('À', d.a), o = champ('Objet', d.objet), c = champ('Message (relis et modifie)', d.corps, 'textarea');
  if (!d.a) b.insertBefore(el('p', 'alerte-lien', 'Adresse introuvable dans le mail : écris-la dans « À ».'), a.previousSibling);
  const act = el('div', 'actions');
  act.append(bouton('Envoyer', 'pri', async ev => {
    if (!confirm(`Envoyer vraiment ce mail à ${a.value} ?`)) return;
    ev.target.disabled = true; ev.target.textContent = 'Envoi…';
    try { await api('/mails/envoyer', {a: a.value, objet: o.value, corps: c.value, ref: m.id}); $('fen').close(); toast('Mail envoyé · +20 XP'); if (apres) apres(); }
    catch (e) { ev.target.disabled = false; ev.target.textContent = 'Envoyer'; b.append(el('p', 'alerte-lien', 'Rien n’est parti : ' + e.message)); }
  }), bouton('Annuler', '', () => $('fen').close()));
  b.append(act, el('p', 'dim', 'Rien ne part sans ton clic sur « Envoyer ».'));
  c.focus();
}

/* Mission 10 : « Tout arrêter », confirmé DANS la page (pas de fenêtre du navigateur), puis le compte rendu de chaque étape. */
function toutArreter(zone) {
  const oui = bouton('Oui, tout arrêter', 'danger', async () => {
    oui.disabled = non.disabled = true; zone.replaceChildren(el('p', 'mut', 'J’arrête tout, dans l’ordre…'));
    try { const r = await api('/tout-arreter', {}); const l = el('ul'); r.etapes.forEach(x => l.append(el('li', '', x))); zone.replaceChildren(l, el('p', '', el('b', '', r.message))); }
    catch (_) { zone.replaceChildren(el('p', '', el('b', '', 'Tout est arrêté. Pour relancer : JARVIS.bat'))); }
  });
  const non = bouton('Non, annuler', '', () => { const f = zone.closest('dialog'); if (f) f.close(); else ouvrirReglages(); });
  const act = el('div', 'actions'); act.append(oui, non);
  zone.replaceChildren(el('p', '', 'J’arrête dans l’ordre : le Directeur, les Découvertes, les recherches, le bot Telegram, les modèles d’IA locale (carte graphique libérée), Ollama, le routeur, puis Jarvis. Rien n’est supprimé.'),
                       el('p', 'dim', 'Pour relancer ensuite : double-clique sur JARVIS.bat.'), act);
}

/* ---------- Le chat : une bulle, et sous chaque réponse, qui a répondu ---------- */
const brut = t => (t || '').replace(/\*\*|__|^#+\s*/gm, '');  // les IA mettent parfois du Markdown : on l'enlève
function message(fil, cls, txt) { const m = el('div', 'msg ' + cls, txt); fil.append(m); fil.scrollTop = 1e9; return m; }
function signer(m, r) {
  const q = el('span', 'qui', 'Réponse de ' + (r.agent_nom || 'Jarvis') + ' · ' + (r.chemin === 'code' ? 'le code, sans IA' : r.ia || 'sans IA'));
  q.append(' · ', lien('voir l’équipe', 'pilote.html', ''));
  m.append(q);
}
/* ---------- Mission 16 : la réponse mot par mot, ses sources, ses boutons, 👍/👎 et la voix ---------- */
async function demanderFlux(corps, signal, sur) {  // une ligne JSON par événement : {etat}, {mot}, puis {fin}
  const r = await fetch(API + '/demander', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...corps, flux: true}), signal});
  if (!r.ok || !r.body) { const d = await r.json().catch(() => ({})); const e = new Error(d.erreur || 'Erreur ' + r.status); e.trace = d.trace; throw e; }
  const lec = r.body.getReader(), dec = new TextDecoder(); let reste = '', fin = null;
  for (;;) {
    const {value, done} = await lec.read(); if (done) break; reste += dec.decode(value, {stream: true});
    let i; while ((i = reste.indexOf('\n')) >= 0) { const l = reste.slice(0, i); reste = reste.slice(i + 1);
      if (!l.trim()) continue; const ev = JSON.parse(l); if (ev.fin) fin = ev; else sur(ev); }
  }
  if (!fin) throw new Error('la réponse a été coupée');
  if (fin.code >= 400) { const e = new Error(fin.fin.erreur || 'Erreur ' + fin.code); e.trace = fin.trace; throw e; }
  return {...fin.fin, trace: fin.trace};
}
const VOIX = {on: () => false};  // 22/10 : l'utilisateur ne veut plus la réponse à voix haute
function dire(texte) {  // 🔊 : seulement la phrase-réponse, avec une voix française INSTALLÉE sur le PC (pas « Online »)
  if (!VOIX.on() || !window.speechSynthesis) return;
  const phrase = brut(texte).split(/(?<=[.!?])\s|\n/)[0].slice(0, 300); if (!phrase) return;
  const v = speechSynthesis.getVoices().find(x => /^fr/i.test(x.lang) && x.localService && !/online/i.test(x.name));
  if (!v) return; speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(phrase); u.voice = v; u.lang = v.lang; speechSynthesis.speak(u);
}
/* La dictée : le son part toutes les 2 s à Whisper SUR LE PC (/dictee), le texte s'écrit pendant que la personne parle ;
   seulement le re-clic (ou Alt+M) arrête (22/10 : plus d'arrêt sur un silence), et la question part. Option (Réglages, éteinte par défaut) : la reconnaissance d'Edge. */
const DICTEE = {actif: false, stop: () => {}};
function pcm16(morceaux, taux) {  // Float32 au taux du micro → PCM 16 bits mono 16 kHz, en base64
  const total = morceaux.reduce((s, c) => s + c.length, 0), k = taux / 16000, n = Math.floor(total / k), out = new Int16Array(n);
  const plat = new Float32Array(total); let o = 0; for (const c of morceaux) { plat.set(c, o); o += c.length; }
  for (let i = 0; i < n; i++) { const a = Math.floor(i * k), b = Math.max(a + 1, Math.floor((i + 1) * k)); let s = 0; for (let j = a; j < b; j++) s += plat[j]; out[i] = Math.max(-1, Math.min(1, s / (b - a))) * 32767; }
  let bin = ''; const u = new Uint8Array(out.buffer); for (let i = 0; i < u.length; i += 0x8000) bin += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000));
  return {b64: btoa(bin), sec: n / 16000};
}
async function dicter(champ, bouton_, envoyer) {
  if (DICTEE.actif) return DICTEE.stop();
  if (window.speechSynthesis) speechSynthesis.cancel();  // la voix se tait dès que la personne reparle
  const fini = () => { DICTEE.actif = false; bouton_.classList.remove('rec'); bouton_.setAttribute('aria-pressed', 'false'); };
  if (memo.lire('jarvis-dictee-edge') === 'oui' && (window.SpeechRecognition || window.webkitSpeechRecognition)) {  // option : la voix part chez Microsoft
    const R = new (window.SpeechRecognition || window.webkitSpeechRecognition)(); R.lang = 'fr-FR'; R.interimResults = true; R.continuous = true;
    R.onresult = e => { champ.value = [...e.results].map(x => x[0].transcript).join(' '); champ.dispatchEvent(new Event('input')); };
    R.onend = () => { fini(); if (champ.value.trim()) envoyer(champ.value); };
    DICTEE.actif = true; DICTEE.stop = () => R.stop(); bouton_.classList.add('rec'); bouton_.setAttribute('aria-pressed', 'true'); R.start(); return;
  }
  let flux; try { flux = await navigator.mediaDevices.getUserMedia({audio: true}); } catch (e) { toast('Micro refusé ou absent : autorise-le dans Edge (icône à gauche de l’adresse).'); return; }
  const ctx = new AudioContext(), src = ctx.createMediaStreamSource(flux), proc = ctx.createScriptProcessor(4096, 1, 1), morceaux = [];
  let parle = false, silence = 0, duree = 0, envoi = null;
  const morceau = async () => { const {b64, sec} = pcm16(morceaux, ctx.sampleRate); if (sec < .3) return null;
    const r = await api('/dictee', {pcm: b64}); if (r.texte) { champ.value = r.texte; champ.dispatchEvent(new Event('input')); } return r; };
  proc.onaudioprocess = e => { const d = e.inputBuffer.getChannelData(0); morceaux.push(new Float32Array(d)); duree += d.length / ctx.sampleRate;
    let s = 0; for (let i = 0; i < d.length; i++) s += d[i] * d[i];
    if (Math.sqrt(s / d.length) > .02) { parle = true; silence = 0; } else if (parle) silence += d.length / ctx.sampleRate;
    if (duree > 180) DICTEE.stop(); };  // 3 min au plus ; sinon c'est la personne qui arrête
  src.connect(proc); proc.connect(ctx.destination);
  const tic = setInterval(() => { if (parle && !envoi) envoi = morceau().catch(() => null).finally(() => { envoi = null; }); }, 2000);
  DICTEE.actif = true; bouton_.classList.add('rec'); bouton_.setAttribute('aria-pressed', 'true'); champ.placeholder = 'Je t’écoute… (re-clic pour finir)';
  DICTEE.stop = async () => {
    if (!DICTEE.actif) return; fini(); clearInterval(tic); proc.disconnect(); src.disconnect(); flux.getTracks().forEach(t => t.stop()); ctx.close();
    champ.placeholder = 'Je finis d’écrire…';
    try { if (envoi) await envoi; const r = parle ? await morceau() : null; if (r && r.texte) envoyer(r.texte); else if (!parle) toast('Je n’ai rien entendu.'); }
    catch (e) { toast('Dictée impossible : ' + e.message); }
    champ.placeholder = 'Écris ou dicte à Jarvis…';
  };
}
function finReponse(fil, m, r, q, corps, quand) {
  if (r.tu_voulais) { const p = el('p', 'dim', `Tu voulais peut-être dire « ${r.tu_voulais} » ? `);
    p.append(bouton('Oui, c’est ça', '', () => poser(fil, r.tu_voulais, {}, quand))); m.append(p); }
  if (r.source) m.append(el('span', 'qui', 'D’après ' + r.source));
  const bs = (r.boutons || []).slice(0, 2);
  if (bs.length) { const l = el('div', 'actions');
    for (const b of bs) l.append(b.page ? lien(b.texte, b.page, 'btn') : b.lien ? lien(b.texte, b.lien, 'btn')
      : bouton(b.texte, '', () => poser(fil, q, {en_ligne: !!b.en_ligne}, quand)));
    m.append(l); }
  signer(m, r);
  if (r.trace) {  // 👍 / 👎 : 👎 → pourquoi, puis Jarvis réessaie tout de suite autrement
    const av = el('div', 'avis-rep'), oui = bouton('👍', '', () => noter('bien')), non = bouton('👎', '', () => {
      av.replaceChildren(el('span', 'dim', 'Qu’est-ce qui ne va pas ? '));
      for (const x of ['pas compris', 'faux', 'trop long', 'pas utile']) av.append(bouton(x, '', () => noter('mal', x)));
    });
    oui.title = 'Bonne réponse'; non.title = 'Pas bonne : je réessaie autrement';
    const noter = async (note, raison) => {
      av.replaceChildren(el('span', 'dim', note === 'bien' ? 'Merci, c’est noté.' : 'Noté. Je réessaie autrement…'));
      api('/avis', {trace: r.trace, note, raison: raison || '', question: q, reponse: (r.reponse || '').slice(0, 1500), corrige: !!corps.autrement, chemin: r.chemin || ''}).catch(() => {});
      if (note === 'mal') poser(fil, q, {autrement: raison}, quand);
    };
    av.append(oui, non); m.append(av);
  }
  dire(r.reponse);
}
/* Mission 8 : « Modifie la page … » dans le chat = une vraie modification. On montre l'état RÉEL lu sur le serveur. */
const ETATS_MODIF = {preparation: 'En préparation…', test: 'En test…', redemarrage: 'Redémarrage du serveur…', termine: 'Terminé', attente: 'En attente de ton accord', refuse: 'Refusé', bloque: 'Bloqué', annule: 'Annulé'};
function suivreModif(x, m) {
  const c = el('div', 'modif-suivi'); m.append(c);
  const maj = async () => {
    let d = x; try { d = await api('/modifs?id=' + encodeURIComponent(x.id)); } catch (e) {}
    c.replaceChildren(el('b', '', ETATS_MODIF[d.etat] || d.etat), el('p', '', d.resume || ''));
    if (d.plan) c.append(el('p', 'dim', 'Plan : ' + d.plan));
    if (d.tests || d.controles) c.append(el('p', 'dim', [d.tests && 'Tests : ' + d.tests, ...(d.controles || [])].filter(Boolean).join(' · ')));
    if (d.diff) { const det = el('details'); det.append(el('summary', '', 'Voir le changement (diff)'), el('pre', '', d.diff)); c.append(det); }
    if (d.etat === 'termine' && d.commit) c.append(bouton('Annuler ce changement', '', async ev => { ev.target.disabled = true;
      try { const r = await api('/modifs/annuler', {id: d.id}); toast(r.ok ? 'Annulé : la page est revenue comme avant.' : 'Impossible : ' + (r.detail || r.erreur)); } catch (e) { toast(e.message); } maj(); }));
    if (d.etat === 'attente') c.append(lien('Répondre dans Décisions', 'decisions.html', 'btn'));
    if (['preparation', 'test', 'redemarrage'].includes(d.etat)) setTimeout(maj, 3000);
  };
  maj();
}
/* Mission 10 : Jarvis pose 1 à 3 questions à choix avant une tâche floue (aussi dans Décisions tant qu'il n'y a pas de réponse). */
function cartesQuestions(fil, r, m, quand) {
  const rep = {};
  for (const x of r.questions) {
    const c = el('div', 'modif-suivi'); c.append(el('b', '', x.question));
    if (x.recommande) c.append(el('p', 'dim', 'Mon conseil : ' + x.recommande + (x.pourquoi ? ' — ' + x.pourquoi : '')));
    const ligne = el('div'); c.append(ligne); m.append(c);
    x.choix.forEach((ch, i) => ligne.append(bouton(ch, ch === x.recommande ? 'pri' : '', async () => {
      ligne.querySelectorAll('button').forEach(b => b.disabled = true);
      rep[x.question] = ch; ligne.append(el('span', 'dim', ' ✓ ' + ch));
      api('/decisions/repondre', {id: x.decision, choix: 'c' + i, depuis_chat: true}).catch(() => {});
      if (Object.keys(rep).length === r.questions.length)
        poser(fil, r.demande + '\nMes réponses : ' + Object.entries(rep).map(([q, a]) => q + ' → ' + a).join(' ; '), {}, quand);
    })));
  }
}
/* Mission 10 : Jarvis regarde une vidéo ; on montre l'étape RÉELLE (Téléchargement…, Écoute…, Images…, Résumé…). */
function suivreVideo(id, m) {
  const c = el('div', 'modif-suivi'); m.append(c);
  const maj = async () => {
    let d = {etape: 'En cours…', en_cours: true}; try { d = await api('/video?id=' + encodeURIComponent(id)); } catch (e) {}
    c.replaceChildren(el('b', '', d.etape || ''));
    if (d.erreur) c.append(el('p', '', 'Erreur : ' + d.erreur));
    if (d.resultat) { c.append(el('p', '', brut(d.resultat.analyse))); c.append(lien('Voir sur la page Vidéo', 'video.html', '')); }
    if (d.en_cours) setTimeout(maj, 2000);
  };
  maj();
}
/* Mission 14 : plus jamais « Jarvis réfléchit… » sans fin. Compteur de secondes, puis « plus de temps que prévu », puis une erreur
   claire au délai max, avec l'identifiant de la trace (créé ici, repris par le serveur). Délais lus dans /sante (reglages.json). */
async function poser(fil, q, corps, quand) {
  message(fil, 'moi', q);
  const base = corps.equipe ? 'Toute l’équipe réfléchit…' : 'Jarvis réfléchit…';
  const m = message(fil, 'lui attente', base);
  const trace = Math.random().toString(16).slice(2, 10).padEnd(8, '0'), ctl = new AbortController(), t0 = Date.now();
  let etat = '', texte = '', t1 = t0;  // mission 16 : la ligne d'état dit l'étape (« je lis tes offres… (1 s) »), puis les mots arrivent
  if (window.speechSynthesis) speechSynthesis.cancel();
  const tic = setInterval(() => { if (texte) return; const s = Math.round((Date.now() - t0) / 1000), e = Math.round((Date.now() - t1) / 1000);
    m.textContent = s >= DELAIS.prevu ? 'Jarvis met plus de temps que prévu… ' + s + ' s' : etat ? `${etat}… (${e} s)` : base + ' ' + s + ' s'; }, 1000);
  const coupe = setTimeout(() => ctl.abort(), DELAIS.max * 1000);
  try {
    if (corps.equipe) {
      const r = await api('/equipe', {question: q, trace}, ctl.signal);
      m.classList.remove('attente'); m.textContent = brut(r.synthese) || 'Pas de synthèse : regarde les avis ci-dessous.';
      if (r.synthese) m.append(el('span', 'qui', 'Synthèse de Jarvis · ' + (r.ia || 'sans IA')));
      const av = el('div', 'avis');
      for (const a of r.avis) { const d = el('div'); d.append(el('b', '', a.agent_nom + ' · ' + (a.ia || '—')), document.createTextNode(brut(a.texte) || (a.erreur ? 'N’a pas pu répondre cette fois.' : '—'))); av.append(d); }
      m.append(av);
      if (r.prives && r.prives.length) m.append(el('span', 'qui', 'Mails et Sécurité restent sur ton PC : leur avis n’est pas envoyé à la synthèse.'));
    } else {
      const r = await demanderFlux({question: q, ...corps, trace}, ctl.signal, ev => {
        if (ev.etat) { etat = ev.etat.charAt(0).toUpperCase() + ev.etat.slice(1); t1 = Date.now(); texte = ''; m.classList.add('attente'); m.textContent = etat + '…'; }
        else if (ev.mot) { if (!texte) m.classList.remove('attente'); texte += ev.mot; m.textContent = brut(texte); fil.scrollTop = 1e9; }
      });
      m.classList.remove('attente'); m.textContent = brut(r.reponse) || '(réponse vide)'; finReponse(fil, m, r, q, corps, quand);
      if (r.modif) suivreModif(r.modif, m);
      if (r.questions) cartesQuestions(fil, r, m, quand);
      if (r.video) suivreVideo(r.video.id, m);
      if (r.lien) m.append(lien('Ouvrir la page', r.lien, 'btn'));
      if (r.confirmer) { const b = bouton('Confirmer : ' + r.confirmer.texte, 'pri', async () => { b.disabled = true;  // action du panneau de contrôle préparée par Jarvis
        try { const x = await api('/confirmer', {id: r.confirmer.id}); toast((x.resultat && x.resultat.message) || 'C’est fait.'); b.textContent = 'Fait'; } catch (e) { toast(e.message); b.disabled = false; } }); m.append(b); }
    }
  } catch (e) { m.classList.remove('attente');
    m.textContent = e.name === 'AbortError' ? `Jarvis n’a pas répondu en ${DELAIS.max} s : j’ai arrêté d’attendre. Regarde la page Alertes (trace ${trace}).`
      : 'Petit souci : ' + e.message + (e.trace ? ` (trace ${e.trace})` : ''); }
  finally { clearInterval(tic); clearTimeout(coupe); }
  fil.scrollTop = 1e9; if (quand) quand();
}

/* La ligne des refus : une seule phrase, positive, et un lien « voir ». Rien à faire pour un refus. */
function ligneRefus(n) {
  if (!n) return null;
  const p = el('p', 'dim', `${n} réponse${n > 1 ? 's' : ''} négative${n > 1 ? 's' : ''} cette semaine, c’est normal. On continue. `);
  p.append(lien('voir', 'emploi.html#refus', '')); return p;
}
