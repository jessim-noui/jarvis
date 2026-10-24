/* Démo en ligne (GitHub Pages) : chargé AVANT app.js. Remplace le serveur de Jarvis (127.0.0.1:4100) par des réponses
   enregistrées sur des données fictives (demo-data/). Aucune requête ne part vers le PC ; toute action est désactivée. */
'use strict';
(function () {
  const SERVEUR = 'http://127.0.0.1:4100';
  const vraiFetch = window.fetch.bind(window);
  const SILENCIEUX = ['/site/ouvert', '/offres/vues', '/alertes/lu', '/jeu/xp', '/dictee/prechauffer', '/sante/vive', '/presence'];
  const DESACTIVE = 'Désactivé dans la démo';
  const json = (d, code) => new Response(JSON.stringify(d), {status: code || 200, headers: {'Content-Type': 'application/json'}});
  const nom = c => c.replace(/^\/+|\/+$/g, '').replace(/\//g, '_').replace('?', '__').replace(/=/g, '-').replace(/&/g, '_') || 'racine';
  const simple = t => (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
  let chat = null;

  async function repondreChat(corps) {
    if (!chat) chat = await vraiFetch('demo-data/chat.json').then(r => r.json()).catch(() => ({}));
    const q = simple(corps.question), cle = Object.keys(chat).find(k => simple(k) === q);
    const PERSONNE = '(createur|creatrice|auteur|programmeur|developpeur|concepteur|proprietaire|utilisateur|personne (qui|derriere)|creator|author|developer|owner)';
    const PERSO = [new RegExp('\\b(qui suis je|que sais tu (de|sur) moi|parle moi de moi|tu me connais)\\b'), new RegExp('\\b' + PERSONNE + '\\b'),
      /\b(memoire|souvenirs?|profil|moi json|donnees perso|nom|prenom|adresse|ville|habite|domicile|bts|diplome|ecole|age)\b.{0,60}\b(toi|ton|ta|tes|lui|son|sa|ses)\b/,
      /\b(montre|affiche|donne|lis|exporte|revele|dis)\b.{0,40}\b(memoire|souvenirs?|profil|moi json|donnees)\b/, /\bqui (t|vous) a (cree|fait|code|ecrit)\b/, /\bwho (made|created|wrote|built|owns)\b/];
    const refus = !cle && PERSO.some(r => r.test(q)) ? chat['Qui a créé Jarvis ?'] : null;
    const fin = cle ? chat[cle] : refus ? refus : {agent: 'jarvis', agent_nom: 'Jarvis', chemin: 'code', reponse:
      'Dans la démo, je réponds seulement à quelques questions enregistrées :\n- ' + Object.keys(chat).join('\n- ')};
    if (!corps.flux) return json(fin);
    const mots = fin.reponse.split(/(?<=\s)/), enc = new TextEncoder();
    const flux = new ReadableStream({async start(c) {
      c.enqueue(enc.encode(JSON.stringify({etat: 'je réfléchis'}) + '\n'));
      for (const m of mots) { await new Promise(r => setTimeout(r, 25)); c.enqueue(enc.encode(JSON.stringify({mot: m}) + '\n')); }
      c.enqueue(enc.encode(JSON.stringify({fin, code: 200}) + '\n')); c.close();
    }});
    return new Response(flux, {status: 200, headers: {'Content-Type': 'application/x-ndjson'}});
  }

  window.fetch = async function (url, opt) {
    const u = String(url && url.url || url);
    if (!u.startsWith(SERVEUR)) return vraiFetch(url, opt);
    const chemin = u.slice(SERVEUR.length) || '/', post = opt && opt.method === 'POST';
    let corps = {};
    try { corps = JSON.parse(opt && opt.body || '{}'); } catch (_) {}
    if (post && chemin === '/demander') return repondreChat(corps);
    if (post) return SILENCIEUX.includes(chemin) ? json({ok: true}) : json({erreur: DESACTIVE}, 403);
    if (chemin === '/ping') return json({ok: true});
    const f = nom(decodeURIComponent(chemin.split('&')[0])) + '.json';
    if (!(await liste()).includes(f)) return json({erreur: 'Pas disponible dans la démo'}, 404);
    const r = await vraiFetch('demo-data/' + f).catch(() => null);
    return r && r.ok ? json(await r.json()) : json({erreur: 'Pas disponible dans la démo'}, 404);
  };
  let fichiers = null;  // demo-data/liste.json : on ne demande jamais un fichier absent (pas d'erreur 404 en console)
  const liste = () => fichiers || (fichiers = vraiFetch('demo-data/liste.json').then(r => r.json()).catch(() => []));

  /* Pas de micro, pas de notifications dans la démo */
  window.EventSource = undefined;

  function bandeau() {
    if (document.getElementById('demo-bandeau')) return;
    const b = document.createElement('div');
    b.id = 'demo-bandeau'; b.setAttribute('role', 'note');
    b.textContent = 'Démo — données fictives. Le vrai Jarvis tourne sur mon PC.';
    b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#7a3e12;color:#fff8ee;font:600 14px/1.2 system-ui,sans-serif;' +
      'text-align:center;padding:7px 12px;box-shadow:0 1px 4px rgba(0,0,0,.25)';
    document.body.prepend(b);
    document.body.style.paddingTop = (parseFloat(getComputedStyle(document.body).paddingTop) + b.offsetHeight) + 'px';
    decaler();
    setTimeout(decaler, 600);
  }
  /* Les barres fixées en haut du site passent sous le bandeau */
  function decaler() {
    const h = document.getElementById('demo-bandeau').offsetHeight;
    for (const e of document.querySelectorAll('body *')) {
      if (e.id === 'demo-bandeau' || e.dataset.demoDecale) continue;
      const s = getComputedStyle(e);
      if ((s.position === 'fixed' || s.position === 'sticky') && parseFloat(s.top) === 0) { e.style.top = h + 'px'; e.dataset.demoDecale = '1'; }
    }
  }
  if (document.body) bandeau(); else document.addEventListener('DOMContentLoaded', bandeau);
})();
