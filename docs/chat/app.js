/* =========================================================
   Mes IA · cœur commun
   Données des IA · icônes animées · conversation en streaming
   ========================================================= */
(function(){
'use strict';

const API = ''; // même origine que Jarvis : la clé du routeur reste côté serveur (proxy /chat/completions)
const SYS = "Tu es un assistant IA de démonstration. N’invente ni n’expose de données personnelles. " +
            "Réponds en français, de façon claire, concrète et concise. Utilise des listes courtes quand ça aide. N'invente rien : si tu ne sais pas, dis-le.";

/* ---------------- les 4 IA ---------------- */
const AIS = [
  { id:'groq', nom:'Groq', tag:'Vitesse', num:'01', roman:'I',
    c1:'#ff6a3d', c2:'#a81f0e', a:'#ff7a50',
    modele:'Llama 3.3 70B', best:'Ultra-rapide, parfait pour discuter',
    desc:"Des réponses quasi instantanées grâce à des puces faites pour l'IA.",
    plus:['Réponses quasi instantanées','Idéal pour les échanges rapides','Correct en code simple'],
    moins:['Quota gratuit limité par minute','Moins fin sur les longs raisonnements'],
    role:' Sois vif et direct.',
    sugs:['Explique-moi le modèle OSI en 5 lignes','Donne-moi 3 idées de projets pour mon BTS','Une commande PowerShell utile au quotidien','Différence entre un switch et un routeur ?'] },
  { id:'gemini', nom:'Gemini', tag:'Analyse', num:'02', roman:'II',
    c1:'#4285f4', c2:'#9b3bd9', a:'#7aa2ff',
    modele:'Gemini 2.5 Flash', best:'Analyse et longs textes',
    desc:"Lit vite, résume bien et tient la route sur les sujets complexes.",
    plus:['Très bon pour analyser et résumer','Gère de longs documents','Raisonnement solide'],
    moins:['Parfois un peu bavard','Quota gratuit journalier'],
    role:" Développe si c'est complexe, sinon reste court.",
    sugs:["Résume les points clés d'une offre d'emploi","Compare TCP et UDP dans un tableau",'Aide-moi à préparer un entretien technique','Explique Active Directory simplement'] },
  { id:'mistral', nom:'Mistral', tag:'Français', num:'03', roman:'III',
    c1:'#ffd000', c2:'#fa1e0e', a:'#ffb340',
    modele:'Mistral Large', best:'Le français et la rédaction',
    desc:"L'IA française : un style naturel pour tes mails, lettres et textes.",
    plus:['Excellent en français','Style naturel pour lettres et mails','IA européenne'],
    moins:['Un peu moins rapide','Quota gratuit limité'],
    role:' Soigne le style et la langue.',
    sugs:['Rédige un mail de relance pour une candidature','Reformule ce texte de façon plus pro',"Écris une accroche de CV en 2 phrases",'Trouve un nom pour mon projet de routeur IA'] },
  { id:'local', nom:'Local', tag:'Privé', num:'04', roman:'IV',
    c1:'#5be0c0', c2:'#0f5a49', a:'#3fe0b5',
    modele:'Llama 3.1 8B · carte graphique locale', best:'Privé, gratuit, illimité',
    desc:'Tourne sur ta carte graphique : rien ne sort de ton PC.',
    plus:['Rien ne sort de ton PC','Gratuit et sans limite','Marche sans internet'],
    moins:['Plus lent que le cloud','Moins fort sur les questions pointues'],
    role:' Reste bref.',
    sugs:["C'est quoi un VLAN, en clair ?",'Fais-moi un plan de révision pour la semaine','Comment créer un bon mot de passe ?',"Raconte une blague d'informaticien"] }
];
const AI_BY = Object.fromEntries(AIS.map(a => [a.id, a]));

/* ---------------- pictogrammes animés ---------------- */
const PATHS = {
  groq:   '<path class="bolt" d="M13 2.5 4.5 13.5h6.2l-1.2 8 8.9-11.6h-6.3z"/>',
  gemini: '<path class="spark" d="M12 2.5C12.6 8.4 15.6 11.4 21.5 12 15.6 12.6 12.6 15.6 12 21.5 11.4 15.6 8.4 12.6 2.5 12 8.4 11.4 11.4 8.4 12 2.5z"/>' +
          '<circle class="tw" cx="19.6" cy="4.6" r="1.25"/><circle class="tw tw2" cx="4.6" cy="19.2" r="1"/>',
  mistral:'<path class="fl" d="M12 2.6c2.3 3.1 1.4 5.4.3 6.8 3-1.1 6.2 1.3 6.2 5.3a6.5 6.5 0 0 1-13 0c0-3.2 2-4.7 3.1-6.6-.8 3.9 3.2 4.1 3.2 1 0-2.3-1-4.3.2-6.5z"/>' +
          '<path class="fl fl2" d="M12 20.4c-1.7 0-2.9-1.2-2.9-2.9 0-1.5 1-2.5 1.9-3.5.2 1.3.9 1.9 1.6 1.9.7 0 1.1-.6 1.1-1.5 1 .8 1.2 1.7 1.2 2.6 0 2-1.2 3.4-2.9 3.4z"/>',
  local:  '<rect x="4.5" y="10.5" width="15" height="10.5" rx="2.6"/><path class="sh" d="M8 10.5V7.6a4 4 0 0 1 8 0v2.9"/><circle class="kh" cx="12" cy="15.6" r="1.45"/>'
};
function icon(id, size){
  size = size || 24;
  return '<svg class="aico" viewBox="0 0 24 24" width="'+size+'" height="'+size+'" aria-hidden="true">'+(PATHS[id]||'')+'</svg>';
}
const S = p => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+p+'</svg>';
const UI = {
  back:   S('<path d="M19 12H5M11 18l-6-6 6-6"/>'),
  send:   S('<path d="M12 19V5M5 12l7-7 7 7"/>'),
  stop:   '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2.5" fill="currentColor"/></svg>',
  trash:  S('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  copy:   S('<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>'),
  check:  S('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
  retry:  S('<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>'),
  arrow:  S('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  arrowUR:S('<path d="M7 17 17 7M8 7h9v9"/>'),
  chevL:  S('<path d="M15 18l-6-6 6-6"/>'),
  chevR:  S('<path d="M9 18l6-6-6-6"/>'),
  grid:   S('<rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/>'),
  search: S('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>'),
  hist:   S('<path d="M3.5 12a8.5 8.5 0 1 0 2.5-6M3.5 4.5V9H8"/><path d="M12 7.5V12l3 2"/>'),
  close:  S('<path d="M6 6l12 12M18 6 6 18"/>')
};

function setAIVars(el, ai){
  el.style.setProperty('--c1', ai.c1);
  el.style.setProperty('--c2', ai.c2);
  el.style.setProperty('--a', ai.a);
}

/* ---------------- stockage local (protégé) ---------------- */
const LS = {
  get(k, d){ try{ const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); }catch(e){ return d; } },
  set(k, v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
};

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = n => Math.round(n).toLocaleString('fr-FR');

/* ---------------- état du routeur ---------------- */
let routerOK = null, wakeTried = false;
async function health(){
  let ok = false;
  try{
    const c = new AbortController(); const t = setTimeout(() => c.abort(), 2500);
    const r = await fetch(API + '/health/liveliness', { signal:c.signal });
    clearTimeout(t); ok = r.ok;
  }catch(e){ ok = false; }
  routerOK = ok;
  // routeur éteint : on demande à Windows de l'allumer (lien espaceia://, installé par ACTIVER_DEMARRAGE_AUTO.bat, désormais rangé dans archivesnciens-lanceurs)
  if(!ok && !wakeTried){
    wakeTried = true;
    const f = document.createElement('iframe'); f.style.display = 'none'; f.src = 'espaceia://demarrer';
    document.body.appendChild(f); setTimeout(() => f.remove(), 3000);
    [4, 8, 12, 18, 25].forEach(sec => setTimeout(health, sec * 1000));
  }
  document.querySelectorAll('.st').forEach(el => {
    el.classList.toggle('ok', ok); el.classList.toggle('ko', !ok);
    const l = el.querySelector('.l'); if(l) l.textContent = ok ? 'Routeur en ligne' : 'Routeur éteint';
    el.title = ok ? 'Le routeur répond sur localhost:4000' : 'Lance JARVIS.bat pour allumer le routeur';
  });
}

/* ---------------- petit rendu markdown sûr ---------------- */
function md(src){
  const blocks = [];
  src = String(src).replace(/```[^\n`]*\n?([\s\S]*?)(```|$)/g, (m, code) => {
    blocks.push('<pre><code>' + esc(code.replace(/\n$/, '')) + '</code></pre>');
    return '\n\u0000' + (blocks.length - 1) + '\u0000\n';
  });
  const inl = s => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>');
  let out = '', list = null, para = [];
  const fP = () => { if(para.length){ out += '<p>' + para.map(inl).join('<br>') + '</p>'; para = []; } };
  const fL = () => { if(list){ out += '</' + list + '>'; list = null; } };
  for(const raw of src.split('\n')){
    const l = raw.replace(/\s+$/, ''); let m;
    const t = l.trim();
    if(/^\u0000\d+\u0000$/.test(t)){ fP(); fL(); out += blocks[+t.slice(1, -1)]; continue; }
    if(!t){ fP(); fL(); continue; }
    if((m = l.match(/^\s*#{1,6}\s+(.*)/))){ fP(); fL(); out += '<h4>' + inl(m[1]) + '</h4>'; continue; }
    if((m = l.match(/^\s*[-*•]\s+(.*)/))){ fP(); if(list !== 'ul'){ fL(); out += '<ul>'; list = 'ul'; } out += '<li>' + inl(m[1]) + '</li>'; continue; }
    if((m = l.match(/^\s*\d+[.)]\s+(.*)/))){ fP(); if(list !== 'ol'){ fL(); out += '<ol>'; list = 'ol'; } out += '<li>' + inl(m[1]) + '</li>'; continue; }
    fL(); para.push(l);
  }
  fP(); fL();
  return out;
}

function prettyModel(m, ai){
  m = String(m || '').toLowerCase();
  if(!m) return ai.modele;
  if(m.includes('llama3.1') || m.includes('ollama')) return 'Llama 3.1 8B (local)';
  if(m.includes('llama-3.3')) return 'Llama 3.3 70B';
  if(m.includes('gemini')) return 'Gemini 2.5 Flash';
  if(m.includes('mistral')) return 'Mistral Large';
  return m;
}
const isLocal = m => /llama3\.1|ollama/i.test(String(m || ''));

/* =========================================================
   VUE CONVERSATION
   ========================================================= */
let cv, cur = AIS[0], hist = [], busy = false, ctrl = null, built = false;

function build(){
  if(built) return; built = true;
  cv = document.createElement('div');
  cv.className = 'chatv'; cv.id = 'chatv';
  cv.setAttribute('role', 'dialog'); cv.setAttribute('aria-modal', 'true'); cv.setAttribute('aria-label', 'Conversation');
  cv.innerHTML =
    '<div class="cv-bg"></div><div class="cv-flash"></div>' +
    '<aside class="cv-hist" id="cvHist" aria-label="Historique des tokens"></aside>' +
    '<aside class="cv-side">' +
      AIS.map(a => '<button class="sw" data-id="'+a.id+'" style="--c1:'+a.c1+';--c2:'+a.c2+';--a:'+a.a+'" aria-label="'+a.nom+'">'+icon(a.id, 22)+'<span class="tip">'+a.nom+' · '+a.tag+'</span></button>').join('') +
      '<div class="sep"></div>' +
      '<button class="ibtn" id="cvNew" title="Effacer la conversation" aria-label="Effacer la conversation">'+UI.trash+'</button>' +
      '<button class="ibtn bk" id="cvBack" title="Retour (Échap)" aria-label="Retour">'+UI.back+'</button>' +
    '</aside>' +
    '<section class="cv-main">' +
      '<header class="cv-head">' +
        '<button class="ibtn bk2" id="cvBack2" aria-label="Retour">'+UI.back+'</button>' +
        '<div class="ico" id="cvIco"></div>' +
        '<div><div class="nm" id="cvNm"></div><div class="sub" id="cvSub"></div></div>' +
        '<div class="meta"><button class="chip tk" id="cvTk" title="Voir l\'historique des tokens"></button><button class="ibtn" id="cvHistB" title="Historique des tokens" aria-label="Historique des tokens">'+UI.hist+'</button><span class="chip st"><i class="dot"></i><span class="l">Routeur…</span></span></div>' +
      '</header>' +
      '<div class="cv-scroll" id="cvScroll">' +
        '<div class="cv-empty" id="cvEmpty"></div>' +
        '<div class="cv-log" id="cvLog" aria-live="polite"></div>' +
      '</div>' +
      '<form class="cv-form" id="cvForm" autocomplete="off">' +
        '<div class="inbox"><textarea id="cvIn" rows="1" placeholder="Écris ton message…" aria-label="Message"></textarea>' +
        '<button class="send" id="cvSend" type="submit" aria-label="Envoyer" disabled>'+UI.send+'</button></div>' +
        '<div class="hint">Entrée pour envoyer · Maj + Entrée pour aller à la ligne · Échap pour revenir</div>' +
      '</form>' +
    '</section>';
  document.body.appendChild(cv);

  cv.querySelectorAll('.cv-side .sw').forEach(b => b.addEventListener('click', () => setAI(b.dataset.id)));
  $('cvBack').onclick = closeChat; $('cvBack2').onclick = closeChat;
  $('cvTk').onclick = histToggle; $('cvHistB').onclick = histToggle;
  $('cvNew').onclick = () => {
    if(busy) stop();
    hist = []; LS.set('h_' + cur.id, hist); renderAll();
    $('cvIn').focus();
  };
  const ta = $('cvIn');
  const fit = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 190) + 'px'; $('cvSend').disabled = !busy && !ta.value.trim(); };
  ta.addEventListener('input', fit);
  ta.addEventListener('keydown', e => {
    if(e.key === 'Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); $('cvForm').requestSubmit(); }
  });
  $('cvForm').addEventListener('submit', e => {
    e.preventDefault();
    if(busy){ stop(); return; }
    const t = ta.value.trim(); if(!t) return;
    ta.value = ''; fit(); send(t);
  });
}

function setAI(id){
  const ai = AI_BY[id] || AIS[0];
  if(busy) stop();
  cur = ai;
  setAIVars(cv, ai);
  cv.querySelectorAll('.cv-side .sw').forEach(b => b.classList.toggle('on', b.dataset.id === id));
  $('cvIco').innerHTML = icon(ai.id, 24);
  $('cvNm').textContent = ai.nom;
  $('cvSub').textContent = ai.modele;
  hist = LS.get('h_' + ai.id, []);
  if(!Array.isArray(hist)) hist = [];
  tokens();
  renderAll();
  LS.set('lastAI', ai.id);
}

function tokens(){
  $('cvTk').textContent = fmt(LS.get('t_' + cur.id, 0)) + ' tokens';
}

function renderEmpty(){
  const e = $('cvEmpty');
  e.innerHTML =
    '<div class="halo">'+icon(cur.id, 62)+'</div>' +
    '<h2 class="ln" style="--d:1">Bonjour ! On parle de quoi ?</h2>' +

    '<div class="sugs">' + cur.sugs.map((s, i) => '<button class="sug ln" style="--d:'+(3+i)+'">'+esc(s)+'</button>').join('') + '</div>';
  e.querySelectorAll('.sug').forEach(b => b.onclick = () => send(b.textContent));
}

function renderAll(){
  const log = $('cvLog'); log.innerHTML = '';
  const empty = !hist.length;
  $('cvEmpty').classList.toggle('on', empty);
  if(empty) renderEmpty();
  hist.forEach((m, i) => {
    if(m.role === 'user') addUser(m.content, true);
    else { const w = addBot(true); w.bub.innerHTML = md(m.content); finishBot(w, m.meta, i === hist.length - 1); }
  });
  markLast();
  scrollDown(true);
}

function addUser(text, quiet){
  const d = document.createElement('div');
  d.className = 'm u'; if(quiet) d.style.animation = 'none';
  d.innerHTML = '<div class="bub"></div>';
  d.firstChild.textContent = text;
  $('cvLog').appendChild(d);
  return d;
}

function addBot(quiet){
  const d = document.createElement('div');
  d.className = 'm b'; if(quiet) d.style.animation = 'none';
  d.innerHTML = '<div class="av">'+icon(cur.id, 18)+'</div><div class="col"><div class="bub"></div><div class="tools"></div></div>';
  $('cvLog').appendChild(d);
  return { el:d, bub:d.querySelector('.bub'), tools:d.querySelector('.tools') };
}

function finishBot(w, meta, isLast){
  const t = w.tools; t.innerHTML = '';
  const cp = document.createElement('button');
  cp.className = 'tool'; cp.type = 'button'; cp.innerHTML = UI.copy + '<span>Copier</span>';
  cp.onclick = async () => {
    const txt = w.bub.innerText;
    try{ await navigator.clipboard.writeText(txt); }catch(e){
      const ta = document.createElement('textarea'); ta.value = txt; document.body.appendChild(ta); ta.select();
      try{ document.execCommand('copy'); }catch(_){} ta.remove();
    }
    cp.innerHTML = UI.check + '<span>Copié</span>';
    setTimeout(() => { cp.innerHTML = UI.copy + '<span>Copier</span>'; }, 1400);
  };
  t.appendChild(cp);
  if(isLast){
    const rg = document.createElement('button');
    rg.className = 'tool rg'; rg.type = 'button'; rg.innerHTML = UI.retry + '<span>Régénérer</span>';
    rg.onclick = regen;
    t.appendChild(rg);
  }
  if(meta){
    const s = document.createElement('span');
    s.className = 'tool mt'; s.style.border = '0'; s.style.cursor = 'default';
    s.textContent = meta;
    t.appendChild(s);
  }
}

function markLast(){
  const bots = $('cvLog').querySelectorAll('.m.b');
  bots.forEach((b, i) => {
    const last = i === bots.length - 1;
    b.classList.toggle('last', last);
    if(!last){ const r = b.querySelector('.tool.rg'); if(r) r.remove(); }
  });
}

function nearBottom(){ const s = $('cvScroll'); return s.scrollHeight - s.scrollTop - s.clientHeight < 140; }
function scrollDown(force){
  const s = $('cvScroll');
  if(force || nearBottom()) s.scrollTop = s.scrollHeight;
}

function setBusy(b){
  busy = b;
  const s = $('cvSend');
  s.classList.toggle('stop', b);
  s.innerHTML = b ? UI.stop : UI.send;
  s.setAttribute('aria-label', b ? 'Arrêter' : 'Envoyer');
  s.disabled = !b && !$('cvIn').value.trim();
}

function stop(){ if(ctrl) ctrl.abort(); }

function send(text){
  text = String(text).trim();
  if(!text || busy) return;
  $('cvEmpty').classList.remove('on');
  hist.push({ role:'user', content:text });
  LS.set('h_' + cur.id, hist);
  addUser(text);
  scrollDown(true);
  ask();
}

function regen(){
  if(busy) return;
  if(hist.length && hist[hist.length - 1].role === 'assistant'){
    hist.pop(); LS.set('h_' + cur.id, hist);
    const bots = $('cvLog').querySelectorAll('.m.b');
    if(bots.length) bots[bots.length - 1].remove();
  }
  if(hist.length && hist[hist.length - 1].role === 'user') ask();
}

async function ask(){
  const ai = cur;
  const w = addBot();
  w.bub.innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  scrollDown(true);
  setBusy(true);
  ctrl = new AbortController();
  const t0 = performance.now();
  let acc = '', model = '', usage = null, raf = 0, failed = null;

  const paint = done => {
    raf = 0;
    if(cur !== ai) return;
    const stick = nearBottom();
    w.bub.innerHTML = acc ? md(acc) + (done ? '' : '<span class="caret"></span>')
                          : (done ? '' : '<span class="typing"><i></i><i></i><i></i></span>');
    if(stick) scrollDown(true);
  };
  const later = () => { if(!raf) raf = requestAnimationFrame(() => paint(false)); };

  try{
    const msgs = [{ role:'system', content:SYS + ai.role }]
      .concat(hist.slice(-24).map(m => ({ role:m.role, content:m.content })));
    const r = await fetch(API + '/chat/completions', {
      method:'POST', signal:ctrl.signal,
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ model:ai.id, messages:msgs, stream:true, stream_options:{ include_usage:true } })
    });
    if(!r.ok){
      let tx = ''; try{ tx = await r.text(); }catch(e){}
      let msg = tx; try{ const j = JSON.parse(tx); msg = (j.error && (j.error.message || j.error)) || tx; }catch(e){}
      throw Object.assign(new Error(String(msg).slice(0, 240)), { http:r.status });
    }
    const ct = r.headers.get('content-type') || '';
    if(!r.body || !/event-stream/.test(ct)){
      const j = await r.json();
      acc = (j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content) || '';
      model = j.model || ''; usage = j.usage || null;
    } else {
      const rd = r.body.getReader(); const dec = new TextDecoder(); let buf = '';
      outer: while(true){
        const { value, done } = await rd.read();
        if(done) break;
        buf += dec.decode(value, { stream:true });
        let i;
        while((i = buf.indexOf('\n')) >= 0){
          const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
          if(!line.startsWith('data:')) continue;
          const p = line.slice(5).trim();
          if(p === '[DONE]') break outer;
          try{
            const j = JSON.parse(p);
            if(j.model) model = j.model;
            if(j.usage) usage = j.usage;
            const d = j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
            if(d){ acc += d; later(); }
          }catch(e){}
        }
      }
    }
  }catch(e){
    if(e.name !== 'AbortError') failed = e;
  }
  if(raf){ cancelAnimationFrame(raf); raf = 0; }
  ctrl = null;

  if(failed && !acc){
    w.el.remove();
    if(cur === ai) showErr(failed);
    setBusy(false);
    return;
  }
  if(!acc) acc = '_(réponse interrompue)_';

  const secs = (performance.now() - t0) / 1000;
  const tk = usage && usage.total_tokens ? usage.total_tokens : Math.round(acc.length / 4);
  LS.set('t_' + ai.id, LS.get('t_' + ai.id, 0) + tk);
  let meta = prettyModel(model, ai) + ' · ' + secs.toFixed(1).replace('.', ',') + ' s · ' + fmt(tk) + ' tokens';
  if(ai.id !== 'local' && isLocal(model)) meta += ' · secours local';

  const lastQ = (hist.filter(m => m.role === 'user').pop() || {}).content || '';
  const lg = LS.get('log', []);
  lg.push({ id:ai.id, t:Date.now(), q:lastQ.slice(0, 90), tk, m:prettyModel(model, ai), s:+secs.toFixed(1), fb:ai.id !== 'local' && isLocal(model) });
  LS.set('log', lg.slice(-300));
  if(histOpen) histRender();
  const h = LS.get('h_' + ai.id, []);
  h.push({ role:'assistant', content:acc, meta });
  LS.set('h_' + ai.id, h);
  if(cur === ai){
    hist = h;
    paint(true);
    finishBot(w, meta, true);
    markLast();
    tokens();
  }
  setBusy(false);
}

function showErr(e){
  const d = document.createElement('div');
  d.className = 'm b';
  const down = !e.http;
  d.innerHTML = '<div class="av">'+icon(cur.id, 18)+'</div><div class="col"><div class="err">' +
    (down ? '<b>Le routeur ne répond pas.</b><br>Lance <code>JARVIS.bat</code> (ou <code>run.bat</code>) puis réessaie.'
          : '<b>Le routeur a renvoyé une erreur ' + e.http + '.</b><br>' + esc(e.message)) +
    '<br><button class="tool" type="button">' + UI.retry + '<span>Réessayer</span></button></div></div>';
  d.querySelector('button').onclick = () => { d.remove(); ask(); };
  $('cvLog').appendChild(d);
  scrollDown(true);
  health();
}

/* ---------------- historique des tokens ---------------- */
let histOpen = false;
function ago(t){
  const d = (Date.now() - t) / 1000;
  if(d < 60) return "à l'instant";
  if(d < 3600) return 'il y a ' + Math.floor(d / 60) + ' min';
  if(d < 86400) return 'il y a ' + Math.floor(d / 3600) + ' h';
  return new Date(t).toLocaleDateString('fr-FR', { day:'numeric', month:'short' }) + ' · ' + new Date(t).toLocaleTimeString('fr-FR', { hour:'2-digit', minute:'2-digit' });
}
function histRender(){
  const lg = LS.get('log', []);
  const tot = AIS.map(a => ({ a, n:LS.get('t_' + a.id, 0), c:lg.filter(x => x.id === a.id).length }));
  const max = Math.max(1, ...tot.map(x => x.n));
  const all = tot.reduce((s, x) => s + x.n, 0);
  $('cvHist').innerHTML =
    '<div class="hh"><div><div class="ht">Historique des tokens</div><div class="hs">'+fmt(all)+' tokens au total · '+lg.length+' réponses</div></div>' +
    '<button class="ibtn" id="cvHistX" aria-label="Fermer">'+UI.close+'</button></div>' +
    '<div class="hbars">' + tot.map(x => '<div class="hb" style="--c1:'+x.a.c1+';--c2:'+x.a.c2+'"><span class="hi">'+icon(x.a.id, 16)+'</span><span class="hn">'+x.a.nom+'</span>' +
      '<span class="hr"><i style="width:'+(x.n / max * 100).toFixed(1)+'%"></i></span><span class="hv">'+fmt(x.n)+'</span></div>').join('') + '</div>' +
    '<div class="hl-t">Dernières utilisations</div>' +
    '<div class="hl">' + (lg.length ? lg.slice().reverse().slice(0, 60).map(x => { const a = AI_BY[x.id] || AIS[0];
      return '<div class="he" style="--c1:'+a.c1+';--c2:'+a.c2+'"><span class="hi">'+icon(a.id, 15)+'</span><div class="hx"><div class="hq">'+esc(x.q || '(sans texte)')+'</div>' +
        '<div class="hm">'+a.nom+' · '+esc(x.m || '')+(x.fb ? ' · secours local' : '')+' · '+ago(x.t)+'</div></div><span class="hk">'+fmt(x.tk)+'</span></div>'; }).join('')
      : '<p class="h0">Pas encore d\'utilisation. Pose une question et elle apparaîtra ici.</p>') + '</div>' +
    (lg.length ? '<button class="hclr" id="cvHistC">Vider l\'historique</button>' : '');
  $('cvHistX').onclick = histToggle;
  const c = $('cvHistC'); if(c) c.onclick = () => { LS.set('log', []); AIS.forEach(a => LS.set('t_' + a.id, 0)); tokens(); histRender(); };
}
function histToggle(){
  histOpen = !histOpen;
  if(histOpen) histRender();
  $('cvHist').classList.toggle('on', histOpen);
}

/* ---------------- ouverture / fermeture ---------------- */
function openChat(id, origin, instant){
  build();
  let x = innerWidth / 2, y = innerHeight / 2;
  if(origin && origin.getBoundingClientRect){
    const r = origin.getBoundingClientRect();
    if(r.width || r.height){ x = r.left + r.width / 2; y = r.top + r.height / 2; }
  } else if(origin && typeof origin.x === 'number'){ x = origin.x; y = origin.y; }
  cv.style.setProperty('--ox', x + 'px');
  cv.style.setProperty('--oy', y + 'px');
  setAI(id);
  cv.classList.toggle('instant', !!instant);
  void cv.offsetWidth;
  cv.classList.add('on');
  document.body.classList.add('chat-open');
  window.__chatOpen = true;
  window.dispatchEvent(new CustomEvent('chatopen', { detail:{ id } }));
  setTimeout(() => { const t = $('cvIn'); if(t && window.__chatOpen) t.focus({ preventScroll:true }); }, 520);
  health();
}

function closeChat(){
  if(!cv || !cv.classList.contains('on')) return;
  if(busy) stop();
  if(histOpen) histToggle();
  cv.classList.remove('on', 'instant');
  document.body.classList.remove('chat-open');
  window.__chatOpen = false;
  window.dispatchEvent(new CustomEvent('chatclose'));
}

/* ---------------- palette rapide Ctrl+K ---------------- */
let palSel = 0, palItems = [];
function palRender(q){
  q = (q || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  palItems = AIS.filter(a => (a.nom + ' ' + a.tag + ' ' + a.best + ' ' + a.modele).toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').includes(q));
  palSel = Math.min(palSel, Math.max(0, palItems.length - 1));
  const l = $('palL');
  l.innerHTML = palItems.length ? palItems.map((a, i) =>
    '<button data-id="'+a.id+'" class="'+(i === palSel ? 'on' : '')+'" style="--c1:'+a.c1+';--c2:'+a.c2+'">' +
    '<span class="ic">'+icon(a.id, 20)+'</span><span><span class="t">'+a.nom+'</span><br><span class="d">'+esc(a.best)+' · '+esc(a.modele)+'</span></span><kbd>'+(AIS.indexOf(a) + 1)+'</kbd></button>').join('')
    : '<div style="padding:16px;color:var(--mut);font-size:14px">Aucune IA ne correspond.</div>';
  l.querySelectorAll('button').forEach(b => {
    b.onclick = () => { palClose(); openChat(b.dataset.id, b); };
    b.onmousemove = () => { const i = palItems.findIndex(a => a.id === b.dataset.id); if(i !== palSel){ palSel = i; palMark(); } };
  });
}
function palMark(){ $('palL').querySelectorAll('button').forEach((b, i) => b.classList.toggle('on', i === palSel)); }
function palOpen(){
  const p = $('pal'); if(!p) return;
  p.classList.add('on'); palSel = 0; $('palQ').value = ''; palRender('');
  setTimeout(() => $('palQ').focus(), 30);
}
function palClose(){ const p = $('pal'); if(p) p.classList.remove('on'); }
function palIsOpen(){ const p = $('pal'); return !!(p && p.classList.contains('on')); }

function initPalette(){
  const p = $('pal'); if(!p) return;
  p.innerHTML = '<div class="pal-in" role="dialog" aria-label="Choisir une IA">' +
    '<input id="palQ" placeholder="Quelle IA ? (vitesse, français, privé…)" aria-label="Rechercher une IA">' +
    '<div class="pal-l" id="palL"></div>' +
    '<div class="pal-f"><span><kbd>↑</kbd> <kbd>↓</kbd> choisir</span><span><kbd>↵</kbd> ouvrir</span><span><kbd>Échap</kbd> fermer</span></div></div>';
  p.addEventListener('click', e => { if(e.target === p) palClose(); });
  $('palQ').addEventListener('input', e => { palSel = 0; palRender(e.target.value); });
  $('palQ').addEventListener('keydown', e => {
    if(e.key === 'ArrowDown'){ e.preventDefault(); palSel = (palSel + 1) % Math.max(1, palItems.length); palMark(); }
    else if(e.key === 'ArrowUp'){ e.preventDefault(); palSel = (palSel - 1 + palItems.length) % Math.max(1, palItems.length); palMark(); }
    else if(e.key === 'Enter'){ e.preventDefault(); const a = palItems[palSel]; if(a){ const b = $('palL').querySelectorAll('button')[palSel]; palClose(); openChat(a.id, b); } }
  });
  const kb = $('kbtn'); if(kb) kb.onclick = palOpen;
}

/* ---------------- clavier global ---------------- */
document.addEventListener('keydown', e => {
  if((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')){
    e.preventDefault(); palIsOpen() ? palClose() : palOpen(); return;
  }
  if(e.key === 'Escape'){
    if(palIsOpen()){ palClose(); e.stopImmediatePropagation(); return; }
    if(window.__chatOpen && histOpen){ histToggle(); e.stopImmediatePropagation(); return; }
    if(window.__chatOpen){ closeChat(); e.stopImmediatePropagation(); return; }
  }
  if(window.__chatOpen && e.altKey && /^[1-4]$/.test(e.key)){
    e.preventDefault(); setAI(AIS[+e.key - 1].id);
  }
}, true);

/* ---------------- démarrage ---------------- */
function init(){
  initPalette();
  health();
  setInterval(health, 15000);
  window.addEventListener('focus', health);
}
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

/* ---------------- formes vivantes (Three.js) ---------------- */
const LIVE = {
  make(T, ai, idx, rad){
    const g = new T.SphereGeometry(rad, 128, 88);
    const pos = g.attributes.position, n = pos.count, base = new Float32Array(pos.array);
    const col = new Float32Array(n * 3), c1 = new T.Color(ai.c1), c2 = new T.Color(ai.c2), c3 = new T.Color(ai.a), tmp = new T.Color();
    for(let k = 0; k < n; k++){
      const y = base[k * 3 + 1] / rad * .5 + .5, x = base[k * 3] / rad * .5 + .5;
      tmp.copy(c2).lerp(c1, y).lerp(c3, x * .4); col[k * 3] = tmp.r; col[k * 3 + 1] = tmp.g; col[k * 3 + 2] = tmp.b;
    }
    g.setAttribute('color', new T.BufferAttribute(col, 3));
    const m = new T.MeshPhysicalMaterial({ vertexColors:true, roughness:.18, metalness:.15, clearcoat:1, clearcoatRoughness:.12,
      iridescence:.8, iridescenceIOR:1.5, emissive:new T.Color(ai.c2), emissiveIntensity:.22, transparent:true });
    const mesh = new T.Mesh(g, m);
    mesh.userData.live = { base, rad, kind:idx % 4 };
    return mesh;
  },
  update(mesh, t){
    const L = mesh.userData.live, p = mesh.geometry.attributes.position.array, b = L.base, r = L.rad, n = b.length / 3;
    for(let k = 0; k < n; k++){
      const x = b[k*3] / r, y = b[k*3+1] / r, z = b[k*3+2] / r;
      let d, sx = 1, sy = 1;
      if(L.kind === 0){        // Groq : une boule électrique qui vibre
        d = .16 * Math.sin(7 * x + 3.2 * t) * Math.sin(7 * y + 2.6 * t) * Math.sin(7 * z + 2.1 * t) + .05 * Math.sin(14 * y + 5 * t);
      } else if(L.kind === 1){ // Gemini : une bulle qui respire
        d = .12 * Math.sin(2.4 * x + 1.1 * t) * Math.cos(2.2 * y + .8 * t) + .07 * Math.sin(3 * z + 1.4 * t) + .04 * Math.sin(t * 1.3);
      } else if(L.kind === 2){ // Mistral : une flamme qui ondule
        const up = Math.max(0, y);
        d = .08 * Math.sin(5 * y - 3.4 * t + 2 * x) + .06 * Math.sin(6 * x + 2.4 * t);
        sy = 1 + up * (.55 + .12 * Math.sin(t * 2.6 + x * 3));
        sx = 1 - up * up * .45;
      } else {                 // Local : une goutte liquide, calme
        d = .1 * Math.sin(3 * y + 1.6 * t) + .06 * Math.cos(3 * x + 1.2 * t) * Math.sin(2 * z + t);
      }
      const f = 1 + d;
      p[k*3] = b[k*3] * f * sx; p[k*3+1] = b[k*3+1] * f * sy; p[k*3+2] = b[k*3+2] * f * sx;
    }
    mesh.geometry.attributes.position.needsUpdate = true;
    mesh.geometry.computeVertexNormals();
  }
};

window.APP = { AIS, AI_BY, icon, UI, setAIVars, openChat, closeChat, LS, esc, md, health, palOpen, LIVE,
  isRouterOK: () => routerOK };
})();
