/* =========================================================
   Mes IA · les 6 façons de choisir son IA
   Chaque concept : mount(stage) -> renvoie une fonction de nettoyage
   ========================================================= */
(function(){
'use strict';
const { AIS, AI_BY, icon, UI, setAIVars, openChat, LS, esc } = window.APP;
const RM = matchMedia('(prefers-reduced-motion: reduce)').matches;
const $ = id => document.getElementById(id);

/* ---------------- petits outils ---------------- */
function on(t, ev, fn, opt){ t.addEventListener(ev, fn, opt); return () => t.removeEventListener(ev, fn, opt); }
function vars(a){ return '--c1:'+a.c1+';--c2:'+a.c2+';--a:'+a.a; }
function lines(a, np, nm, anim, d0){
  np = np == null ? 3 : np; nm = nm == null ? 2 : nm; let d = d0 || 0;
  const c = anim === false ? '' : ' ln';
  return a.plus.slice(0, np).map(t => '<li class="p'+c+'" style="--d:'+(d++)+'">'+esc(t)+'</li>').join('') +
         a.moins.slice(0, nm).map(t => '<li class="m'+c+'" style="--d:'+(d++)+'">'+esc(t)+'</li>').join('');
}
const CH = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
function scramble(node, text){
  if(!node) return;
  if(node._scr) cancelAnimationFrame(node._scr);
  if(RM){ node.textContent = text; return; }
  let f = 0; const total = text.length * 2 + 8;
  const tick = () => {
    let s = '';
    for(let i = 0; i < text.length; i++){
      const ch = text[i];
      if(ch === ' ' || f >= i * 2 + 8) s += ch;
      else s += CH[(Math.random() * CH.length) | 0];
    }
    node.textContent = s;
    if(++f <= total) node._scr = requestAnimationFrame(tick); else { node.textContent = text; node._scr = 0; }
  };
  tick();
}
function loop(fn){
  let id = 0, last = performance.now(), alive = true;
  const step = now => {
    if(!alive) return;
    const dt = Math.min(.05, (now - last) / 1000); last = now;
    if(!window.__chatOpen && !document.hidden) fn(dt, now / 1000);
    id = requestAnimationFrame(step);
  };
  id = requestAnimationFrame(step);
  return () => { alive = false; cancelAnimationFrame(id); };
}
function throttle(ms){ let t = 0; return () => { const n = performance.now(); if(n - t < ms) return false; t = n; return true; }; }
const mod = (n, m) => ((n % m) + m) % m;

/* =========================================================
   2 · DÉFILEMENT 3D — une IA à la fois
   ========================================================= */
function scroll3d(st){
  const offs = [];
  st.innerHTML = '<div class="s3-glow"></div><div class="s3-host"></div>' +
    '<section class="s3-sec s3-one"><div class="s3-txt"></div></section>' +
    '<nav class="s3-dots" aria-label="Aller à une IA">' + AIS.map((a, i) => '<button data-i="'+i+'" aria-label="'+a.nom+'"><span>'+a.nom+'</span></button>').join('') + '</nav>';
  const glow = st.querySelector('.s3-glow'), host = st.querySelector('.s3-host'), sec = st.querySelector('.s3-one'), txt = st.querySelector('.s3-txt');
  const dots = [...st.querySelectorAll('.s3-dots button')];
  const beam = document.createElement('div'); beam.className = 's3-beam'; sec.appendChild(beam);
  // la roue tourne en boucle : pos ne s'arrête jamais, l'IA de devant = pos modulo 4
  let target = 0, curI = -1, burst = 0;
  const setCur = i => {
    if(i === curI) return; curI = i;
    const a = AIS[i];
    setAIVars(sec, a);
    glow.style.setProperty('--g', a.c1);
    dots.forEach((d, k) => d.classList.toggle('on', k === i));
    sec.classList.remove('in');
    // la carte de l'IA : qui elle est, ce qu'elle fait bien, ce qu'il faut savoir, et de quoi commencer
    txt.innerHTML =
      '<div class="s3-top rv"><span class="s3-chip">'+a.roman+' · '+esc(a.tag)+'</span><span class="s3-mod">'+esc(a.modele)+'</span></div>' +
      '<h2 class="rv">'+[...a.nom].map((ch, k) => '<span class="s3-l" style="animation-delay:'+(.35 + k * .05).toFixed(2)+'s">'+ch+'</span>').join('')+'</h2>' +
      '<p class="s3-best rv">'+esc(a.best)+'.</p>' +
      '<p class="s3-desc rv">'+esc(a.desc)+'</p>' +
      '<div class="s3-cols rv"><div><h4>Points forts</h4><ul>'+a.plus.map(x => '<li>'+esc(x)+'</li>').join('')+'</ul></div>' +
        '<div><h4>À savoir</h4><ul class="m">'+a.moins.map(x => '<li>'+esc(x)+'</li>').join('')+'</ul></div></div>' +
      '<div class="s3-try rv"><h4>Essaie par exemple</h4>'+a.sugs.slice(0, 2).map(x => '<button class="s3-sug">'+esc(x)+'</button>').join('')+'</div>' +
      '<button class="s3-go rv">Parler à '+a.nom+' '+UI.arrow+'</button>';
    burst = 1;
    txt.querySelector('.s3-go').onclick = e => openChat(a.id, e.currentTarget);
    txt.querySelectorAll('.s3-sug').forEach(b => b.onclick = e => {
      openChat(a.id, e.currentTarget);
      setTimeout(() => { const ta = document.getElementById('cvIn'); if(ta){ ta.value = b.textContent; ta.focus(); ta.dispatchEvent(new Event('input', { bubbles:true })); } }, 700);
    });
    void sec.offsetWidth; sec.classList.add('in');
    // l'apparition : un rayon part de la forme 3D, la carte se déplie depuis ce côté, puis le nom s'écrit
    txt.classList.remove('swap'); void txt.offsetWidth; txt.classList.add('swap');
    const r = txt.getBoundingClientRect();
    if(innerWidth > 900 && r.width){ beam.style.left = r.right + 'px'; beam.style.top = (r.top + r.height / 2) + 'px'; beam.style.width = Math.max(0, innerWidth * .6 - r.right) + 'px';
      beam.classList.remove('go'); void beam.offsetWidth; beam.classList.add('go'); }
  };
  const go = d => { target += d; setCur(mod(target, 4)); };
  dots.forEach(d => d.onclick = () => { let k = mod(+d.dataset.i - mod(target, 4), 4); if(k === 3) k = -1; go(k); });
  let acc = 0, accT = 0;
  offs.push(on(st, 'wheel', e => {
    acc += e.deltaY; clearTimeout(accT); accT = setTimeout(() => { acc = 0; }, 260);
    if(Math.abs(acc) >= 110){ go(acc > 0 ? 1 : -1); acc = 0; }
  }, { passive:true }));
  let ty = null;
  offs.push(on(st, 'touchstart', e => { ty = e.touches[0].clientY; }, { passive:true }));
  offs.push(on(st, 'touchend', e => { if(ty == null) return; const d = ty - e.changedTouches[0].clientY; if(Math.abs(d) > 50) go(d > 0 ? 1 : -1); ty = null; }));
  offs.push(on(document, 'keydown', e => {
    if(window.__chatOpen || e.target.closest('input,textarea')) return;
    if(e.key === 'ArrowDown' || e.key === 'ArrowRight'){ e.preventDefault(); go(1); }
    if(e.key === 'ArrowUp' || e.key === 'ArrowLeft'){ e.preventDefault(); go(-1); }
  }));
  setCur(0);

  /* ---- Three.js : un seul moteur, réutilisé ---- */
  let R = window.__r3;
  if(!R && window.THREE){
    try{ R = new THREE.WebGLRenderer({ antialias:true, alpha:true, powerPreference:'high-performance' }); window.__r3 = R; }
    catch(e){ R = null; }
  }
  if(!R) return () => offs.forEach(f => f());
  R.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  R.setSize(innerWidth, innerHeight);
  R.setClearColor(0x000000, 0);
  host.appendChild(R.domElement);

  const scene = new THREE.Scene();
  const cam = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, .1, 200);
  cam.position.set(0, 0, 11);
  scene.add(new THREE.AmbientLight(0xffffff, .55));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(5, 6, 8); scene.add(sun);
  const p1 = new THREE.PointLight(0xffffff, 70, 40); p1.position.set(-5, 3, 6); scene.add(p1);
  const p2 = new THREE.PointLight(0xffffff, 60, 40); p2.position.set(5, -4, 4); scene.add(p2);

  const disp = [];
  const track = o => { disp.push(o); return o; };

  // étoiles : deux couches qui tournent en sens opposés
  const starLayer = (n, r, size, op) => {
    const g = track(new THREE.BufferGeometry()); const pos = new Float32Array(n * 3);
    for(let i = 0; i < n; i++){
      const u = Math.random() * 2 - 1, t = Math.random() * Math.PI * 2, rr = r * (.55 + Math.random() * .45), s = Math.sqrt(1 - u * u);
      pos[i * 3] = rr * s * Math.cos(t); pos[i * 3 + 1] = rr * u; pos[i * 3 + 2] = rr * s * Math.sin(t) - 10;
    }
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    const m = track(new THREE.PointsMaterial({ size, color:0xffffff, transparent:true, opacity:op, depthWrite:false }));
    const p = new THREE.Points(g, m); scene.add(p); return p;
  };
  const starsA = starLayer(1600, 60, .09, .85), starsB = starLayer(900, 40, .14, .55);

  /* la roue : elle tourne vers toi, une forme vivante par IA sur son bord */
  const RW = 5.4, wheel = new THREE.Group(), tilt = new THREE.Group(); tilt.add(wheel); scene.add(tilt);   // tilt : la roue vue de trois quarts
  const rimG = track(new THREE.BufferGeometry()), rimN = 1400, rp = new Float32Array(rimN * 3);
  for(let k = 0; k < rimN; k++){ const a = k / rimN * Math.PI * 2, j = (Math.random() - .5) * .12; rp[k*3] = (Math.random() - .5) * .5; rp[k*3+1] = Math.sin(a) * (RW + j); rp[k*3+2] = Math.cos(a) * (RW + j); }
  rimG.setAttribute('position', new THREE.BufferAttribute(rp, 3));
  const rimM = track(new THREE.PointsMaterial({ size:.045, color:0xffffff, transparent:true, opacity:.35, depthWrite:false }));
  wheel.add(new THREE.Points(rimG, rimM));
  // un anneau de lumière à la couleur de l'IA devant toi
  // la structure de la roue : jante fine, graduations, rayons et moyeu
  const rimLine = new THREE.Mesh(track(new THREE.TorusGeometry(RW, .012, 6, 240)), track(new THREE.MeshBasicMaterial({ color:0xffffff, transparent:true, opacity:.22 })));
  rimLine.rotation.y = Math.PI / 2; wheel.add(rimLine);
  const rimIn = new THREE.Mesh(track(new THREE.TorusGeometry(RW * .62, .008, 6, 200)), track(new THREE.MeshBasicMaterial({ color:0xffffff, transparent:true, opacity:.12 })));
  rimIn.rotation.y = Math.PI / 2; wheel.add(rimIn);
  const tk = [];
  for(let k = 0; k < 72; k++){ const a = k / 72 * Math.PI * 2, l = k % 18 === 0 ? .5 : k % 6 === 0 ? .26 : .12;
    tk.push(0, Math.sin(a) * (RW + .08), Math.cos(a) * (RW + .08), 0, Math.sin(a) * (RW + .08 + l), Math.cos(a) * (RW + .08 + l)); }
  const tkG = track(new THREE.BufferGeometry()); tkG.setAttribute('position', new THREE.Float32BufferAttribute(tk, 3));
  wheel.add(new THREE.LineSegments(tkG, track(new THREE.LineBasicMaterial({ color:0xffffff, transparent:true, opacity:.3 }))));
  const spokes = AIS.map((a, i) => {
    const ang = -i * Math.PI / 2, g = track(new THREE.BufferGeometry());
    g.setAttribute('position', new THREE.Float32BufferAttribute([0, Math.sin(ang) * .5, Math.cos(ang) * .5, 0, Math.sin(ang) * (RW - 1.9), Math.cos(ang) * (RW - 1.9)], 3));
    const m = track(new THREE.LineBasicMaterial({ color:new THREE.Color(a.a), transparent:true, opacity:.25 })); wheel.add(new THREE.Line(g, m)); return m;
  });
  const hub = new THREE.Mesh(track(new THREE.SphereGeometry(.38, 32, 32)), track(new THREE.MeshStandardMaterial({ color:0x111520, metalness:.9, roughness:.25, emissive:0xffffff, emissiveIntensity:.06 })));
  wheel.add(hub);
  const halo = new THREE.Mesh(track(new THREE.TorusGeometry(2.6, .025, 8, 160)), track(new THREE.MeshBasicMaterial({ color:0xffffff, transparent:true, opacity:.5, blending:THREE.AdditiveBlending })));
  scene.add(halo);
  const blobs = AIS.map((a, i) => {
    const m = APP.LIVE.make(THREE, a, i, 1.35); track(m.geometry); track(m.material);
    const ang = -i * Math.PI / 2;
    const holder = new THREE.Group(); holder.position.set(0, Math.sin(ang) * RW, Math.cos(ang) * RW);
    holder.add(m); wheel.add(holder);
    // un petit essaim de particules autour de chaque forme
    const n = 260, g = track(new THREE.BufferGeometry()), p = new Float32Array(n * 3);
    for(let k = 0; k < n; k++){ const u = Math.random() * 2 - 1, t = Math.random() * 6.283, r = 2 + Math.random() * .9, s = Math.sqrt(1 - u * u); p[k*3] = r * s * Math.cos(t); p[k*3+1] = r * u; p[k*3+2] = r * s * Math.sin(t); }
    g.setAttribute('position', new THREE.BufferAttribute(p, 3));
    const pm = track(new THREE.PointsMaterial({ size:.05, color:new THREE.Color(a.a), transparent:true, opacity:.8, depthWrite:false, blending:THREE.AdditiveBlending }));
    const sw = new THREE.Points(g, pm); holder.add(sw);
    return { m, holder, sw, pm, c1:new THREE.Color(a.c1), c2:new THREE.Color(a.c2) };
  });

  let wide = innerWidth > 900, mx = 0, my = 0, svS = 0;
  const resize = () => { R.setSize(innerWidth, innerHeight); cam.aspect = innerWidth / innerHeight; cam.updateProjectionMatrix(); wide = innerWidth > 900; };
  offs.push(on(window, 'resize', resize));
  offs.push(on(window, 'pointermove', e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; }));

  offs.push(loop((dt, t) => {
    svS += (target - svS) * Math.min(1, dt * 4);
    starsA.rotation.y += dt * .012; starsB.rotation.y -= dt * .018; starsB.rotation.z += dt * .006;
    starsA.rotation.x = svS * .12; starsB.rotation.x = -svS * .2;
    const th = wide ? -.42 : 0, fx = wide ? 2.6 : 0, fy = wide ? 0 : -1.2;
    tilt.rotation.y = th; tilt.position.set(fx - RW * Math.sin(th), fy, -RW * Math.cos(th));
    wheel.rotation.x = -svS * Math.PI / 2;
    const k = mod(Math.round(svS), 4);
    burst = Math.max(0, burst - dt * 1.4);
    halo.position.set(fx, fy, 0);
    halo.material.color.lerp(blobs[k].c1, .06); halo.scale.setScalar(1 + burst * .35); halo.material.opacity = .25 + .35 * (1 - burst);
    halo.rotation.z = t * .2;
    p1.color.lerp(blobs[k].c1, .05); p2.color.lerp(blobs[k].c2, .05);
    hub.material.emissive.lerp(blobs[k].c1, .05); hub.rotation.x = -wheel.rotation.x;
    spokes.forEach((m, i) => { m.opacity += ((i === k ? .7 : .14) - m.opacity) * .08; });
    blobs.forEach((b, i) => {
      let dd = mod(svS - i + 2, 4) - 2; const w = Math.max(0, 1 - Math.abs(dd));
      const e = w * w * (3 - 2 * w);
      b.holder.rotation.x = -wheel.rotation.x;          // la forme reste droite pendant que la roue tourne
      b.holder.scale.setScalar(.45 + .55 * e);
      b.m.material.opacity = .35 + .65 * e;
      b.pm.opacity = .8 * e;
      b.sw.rotation.y += dt * (.3 + burst * 3); b.sw.rotation.z += dt * .1; b.sw.scale.setScalar(1 + burst * .5 * e);
      b.m.rotation.y += dt * .25;
      if(w > .02) APP.LIVE.update(b.m, t + i * 3);
    });
    cam.position.x += (mx * .8 - cam.position.x) * .04;
    cam.position.y += (-my * .5 - cam.position.y) * .04;
    cam.lookAt(wide ? 1.2 : 0, 0, 0);
    R.render(scene, cam);
  }));

  return () => {
    offs.forEach(f => f());
    scene.remove(tilt);
    disp.forEach(o => { try{ o.dispose(); }catch(e){} });
    R.domElement.remove();
  };
}

/* =========================================================
   4 · SPHÈRE — une forme vivante qui change d'IA (clair)
   ========================================================= */
function sphere(st){
  const offs = [];
  st.innerHTML = '<div class="sph-wrap"><div class="sph-blob" tabindex="0" role="button" aria-label="Ouvrir la discussion">' +
      '<div class="ring"></div><div class="b"></div><div class="b b2 hide"></div><div class="shine"></div><div class="ic"></div></div>' +
    '<div class="sph-txt"><div class="idx"></div><div class="nm"></div><div class="best"></div><div class="pcs"></div>' +
      '<button class="sph-cta"></button></div></div>' +
    '<nav class="sph-dots">' + AIS.map(a => '<button data-id="'+a.id+'" style="'+vars(a)+'"><i></i>'+a.nom+'</button>').join('') + '</nav>';
  const blob = st.querySelector('.sph-blob'), bs = [...st.querySelectorAll('.sph-blob .b')], ic = st.querySelector('.sph-blob .ic');
  const idx = st.querySelector('.idx'), nm = st.querySelector('.sph-txt .nm'), best = st.querySelector('.sph-txt .best'),
        pcs = st.querySelector('.pcs'), cta = st.querySelector('.sph-cta'), dots = [...st.querySelectorAll('.sph-dots button')];
  let i = -1, front = 0, swapT = 0;
  const set = (n, first) => {
    n = mod(n, 4); if(n === i) return; const prev = i; i = n;
    const a = AIS[n];
    if(first){ setAIVars(bs[0], a); }
    else {
      const back = 1 - front, nb = bs[back], dir = n === mod(prev + 1, 4) ? 1 : -1;
      setAIVars(nb, a);
      nb.className = 'b' + (back ? ' b2' : '') + (dir > 0 ? ' up' : ' down');   // départ hors champ, sans transition
      void nb.offsetWidth;
      nb.className = 'b' + (back ? ' b2' : '');
      bs[front].className = 'b' + (front ? ' b2' : '') + (dir > 0 ? ' down' : ' up');
      front = back;
    }
    clearTimeout(swapT);
    if(first){ ic.innerHTML = icon(a.id, 132); }
    else { ic.classList.add('swap'); swapT = setTimeout(() => { ic.innerHTML = icon(a.id, 132); ic.classList.remove('swap'); }, 320); }
    idx.textContent = a.num + ' / 04 · ' + a.tag;
    scramble(nm, a.nom);
    best.textContent = a.best;
    pcs.innerHTML = a.plus.map((t, k) => '<span class="pc ln" style="--d:'+k+'">+ '+esc(t)+'</span>').join('') +
                    a.moins.slice(0, 1).map(t => '<span class="pc ln" style="--d:3;color:#77726a">– '+esc(t)+'</span>').join('');
    cta.innerHTML = 'Discuter avec ' + a.nom + ' ' + UI.arrow;
    dots.forEach(d => d.classList.toggle('on', d.dataset.id === a.id));
  };
  set(0, true);
  dots.forEach(d => d.onclick = () => set(AIS.indexOf(AI_BY[d.dataset.id])));
  const go = () => openChat(AIS[i].id, blob);
  blob.onclick = go; cta.onclick = () => openChat(AIS[i].id, cta);
  blob.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); go(); } });
  let acc = 0, accT = 0;
  offs.push(on(st, 'wheel', e => {
    acc += e.deltaY; clearTimeout(accT); accT = setTimeout(() => { acc = 0; }, 260);
    if(Math.abs(acc) >= 110){ set(i + (acc > 0 ? 1 : -1)); acc = 0; }
  }, { passive:true }));
  offs.push(on(document, 'keydown', e => {
    if(window.__chatOpen || e.target.closest('input,textarea')) return;
    if(e.key === 'ArrowRight' || e.key === 'ArrowDown'){ e.preventDefault(); set(i + 1); }
    if(e.key === 'ArrowLeft' || e.key === 'ArrowUp'){ e.preventDefault(); set(i - 1); }
  }));
  // la forme suit un peu la souris
  let mx = 0, my = 0, px = 0, py = 0;
  offs.push(on(window, 'pointermove', e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; }));
  offs.push(loop(() => { px += (mx - px) * .05; py += (my - py) * .05; blob.style.transform = 'translate(' + (px * 24).toFixed(1) + 'px,' + (py * 18).toFixed(1) + 'px)'; }));
  return () => { clearTimeout(swapT); offs.forEach(f => f()); };
}

/* =========================================================
   6 · CARTES — à retourner
   ========================================================= */
function cartes(st){
  const fan = [[-9, 26], [-3, 0], [3, 0], [9, 26]];
  st.innerHTML = '<header class="cd-head"><div class="k ln">Tire ta carte</div><h1 class="ln" style="--d:1">Quatre IA, <em>une seule</em> te ressemble.</h1></header>' +
    '<div class="cd-row">' + AIS.map((a, i) =>
      '<div class="cd-slot" style="--r:'+fan[i][0]+'deg;--y:'+fan[i][1]+'px"><div class="cd" tabindex="0" role="button" aria-label="Parler à '+a.nom+'" data-id="'+a.id+'" style="'+vars(a)+'">' +
        '<div class="f"><span class="k1">'+a.roman+'</span><span class="k2">'+a.roman+'</span>'+icon(a.id, 76)+'<div class="nm">'+a.nom+'</div><div class="tg">'+a.tag+'</div><div class="bst">'+esc(a.best)+'</div></div>' +
      '</div></div>').join('') + '</div>' +
    '<p class="cd-hint">Choisis une carte : elle t\'emmène directement dans la discussion</p>';
  let zoom = null, t1 = 0, t2 = 0;
  const go = c => {
    if(zoom) return;
    const a = AI_BY[c.dataset.id], r = c.getBoundingClientRect();
    zoom = document.createElement('div'); zoom.className = 'cd-zoom'; setAIVars(zoom, a);
    Object.assign(zoom.style, { left:r.left + 'px', top:r.top + 'px', width:r.width + 'px', height:r.height + 'px' });
    zoom.innerHTML = icon(a.id, 76);
    document.body.appendChild(zoom);
    c.style.visibility = 'hidden';
    requestAnimationFrame(() => requestAnimationFrame(() => zoom.classList.add('full')));
    t1 = setTimeout(() => openChat(a.id, { x:innerWidth / 2, y:innerHeight / 2 }), 560);
    t2 = setTimeout(() => { if(zoom){ zoom.remove(); zoom = null; } c.style.visibility = ''; }, 1400);
  };
  st.querySelectorAll('.cd').forEach(c => {
    c.addEventListener('click', () => go(c));
    c.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); go(c); } });
  });
  return () => { clearTimeout(t1); clearTimeout(t2); if(zoom) zoom.remove(); };
}

/* =========================================================
   7 · CONSTELLATION — chaque IA est une étoile
   ========================================================= */
function constel(st){
  const offs = [];
  const POS = innerWidth > 900 ? [[.56, .30], [.80, .24], [.70, .55], [.88, .66]] : [[.25, .34], [.72, .30], [.32, .56], [.76, .60]];
  st.innerHTML = '<canvas class="cs-cv"></canvas>' +
    '<div class="cs-title"><div class="k ln">Constellation</div><h1 class="ln" style="--d:1">Quatre étoiles,<br><em>une</em> pour chaque besoin.</h1></div>' +
    AIS.map((a, i) => '<button class="cs-star" data-id="'+a.id+'" style="left:'+(POS[i][0] * 100)+'%;top:'+(POS[i][1] * 100)+'%;'+vars(a)+'" aria-label="'+a.nom+'"><span class="dot"></span><span class="lb">'+a.nom+'</span></button>').join('') +
    '<div class="cs-panel" id="csP"></div>';
  const cv = st.querySelector('canvas'), cx = cv.getContext('2d'), panel = st.querySelector('#csP');
  const stars = [...st.querySelectorAll('.cs-star')];
  let W, H, dpr = Math.min(devicePixelRatio || 1, 2);
  const size = () => { W = innerWidth; H = innerHeight; cv.width = W * dpr; cv.height = H * dpr; cx.setTransform(dpr, 0, 0, dpr, 0, 0); };
  size(); offs.push(on(window, 'resize', size));
  // poussière d'étoiles qui dérive dans tous les sens
  const dust = Array.from({ length: 1100 }, () => {
    const a = Math.random() * Math.PI * 2, sp = .8 + Math.random() * 5;
    return { x:Math.random(), y:Math.random(), z:Math.random(), vx:Math.cos(a) * sp, vy:Math.sin(a) * sp, r:Math.random() < .08 ? 1.5 : .8, tw:Math.random() * 6 };
  });
  // petites étoiles satellites autour de chaque IA
  const sats = AIS.map(() => Array.from({ length: 4 }, (_, k) => ({ a:k * 1.57 + Math.random() * .9, d:50 + Math.random() * 70 })));
  let hov = -1, sel = -1, mx = 0, my = 0, pmx = 0, pmy = 0, shoot = null, nextShoot = 3;
  const idle = () => {
    panel.innerHTML = '<div class="tag ln" style="color:#9fb7ff">4 étoiles</div><h2 class="ln" style="--d:1">Choisis ton étoile</h2>' +
      '<p class="sb ln" style="--d:2">Chaque étoile est une IA. Survole pour lire ses forces, clique pour lui parler.</p>';
  };
  const show = i => {
    const a = AIS[i];
    panel.innerHTML = '<div class="tag ln" style="color:'+a.a+'">'+a.num+' · '+a.tag+'</div><h2 class="ln" style="--d:1">'+a.nom+'</h2>' +
      '<p class="sb ln" style="--d:2">'+esc(a.best)+' · '+a.modele+'</p><ul>'+lines(a, 2, 1, true, 3)+'</ul>' +
      '<p class="cl ln" style="--d:6">Clique l\'étoile pour ouvrir la discussion →</p>';
  };
  idle();
  stars.forEach((s, i) => {
    s.addEventListener('mouseenter', () => { hov = i; if(sel !== i){ sel = i; show(i); } });
    s.addEventListener('focus', () => { hov = i; if(sel !== i){ sel = i; show(i); } });
    s.addEventListener('mouseleave', () => { hov = -1; });
    s.addEventListener('click', () => openChat(AIS[i].id, s.querySelector('.dot')));
  });
  offs.push(on(window, 'pointermove', e => { mx = e.clientX / innerWidth - .5; my = e.clientY / innerHeight - .5; }));
  const pt = i => {
    const z = .6;
    return [POS[i][0] * W + pmx * -24 * z, POS[i][1] * H + pmy * -18 * z];
  };
  offs.push(loop((dt, t) => {
    pmx += (mx - pmx) * .05; pmy += (my - pmy) * .05;
    cx.clearRect(0, 0, W, H);
    // poussière
    for(const d of dust){
      if(!RM){ d.x += d.vx * dt / W * (.4 + d.z); d.y += d.vy * dt / H * (.4 + d.z); }
      if(d.x < 0) d.x += 1; if(d.x > 1) d.x -= 1; if(d.y < 0) d.y += 1; if(d.y > 1) d.y -= 1;
      const x = d.x * W + pmx * -40 * d.z, y = d.y * H + pmy * -30 * d.z;
      const al = (.25 + .55 * d.z) * (.6 + .4 * Math.sin(t * 1.3 + d.tw));
      cx.fillStyle = 'rgba(220,230,255,' + al.toFixed(3) + ')';
      cx.fillRect(x, y, d.r, d.r);
    }
    // liens entre les IA
    const P = AIS.map((_, i) => pt(i));
    stars.forEach((s, i) => { s.style.left = P[i][0] + 'px'; s.style.top = P[i][1] + 'px'; });
    const order = [[0, 1], [1, 3], [3, 2], [2, 0], [0, 3]];
    order.forEach(([a, b], k) => {
      const lit = hov === a || hov === b;
      const g = cx.createLinearGradient(P[a][0], P[a][1], P[b][0], P[b][1]);
      g.addColorStop(0, AIS[a].c1); g.addColorStop(1, AIS[b].c1);
      cx.globalAlpha = lit ? .75 : .22; cx.strokeStyle = g; cx.lineWidth = lit ? 1.4 : 1;
      cx.setLineDash(k === 4 ? [3, 7] : []);
      cx.beginPath(); cx.moveTo(P[a][0], P[a][1]); cx.lineTo(P[b][0], P[b][1]); cx.stroke();
      // une lumière qui voyage sur le lien
      const f = ((t * .12 + k * .23) % 1);
      const lx = P[a][0] + (P[b][0] - P[a][0]) * f, ly = P[a][1] + (P[b][1] - P[a][1]) * f;
      cx.globalAlpha = lit ? .95 : .45; cx.fillStyle = '#fff';
      cx.beginPath(); cx.arc(lx, ly, lit ? 2 : 1.3, 0, 7); cx.fill();
    });
    cx.setLineDash([]);
    // satellites
    sats.forEach((ss, i) => {
      const lit = hov === i;
      ss.forEach((s, k) => {
        const ang = s.a + t * .03 * (k % 2 ? 1 : -1);
        const x = P[i][0] + Math.cos(ang) * s.d, y = P[i][1] + Math.sin(ang) * s.d * .8;
        cx.globalAlpha = lit ? .7 : .25; cx.strokeStyle = AIS[i].c1; cx.lineWidth = 1;
        cx.beginPath(); cx.moveTo(P[i][0], P[i][1]); cx.lineTo(x, y); cx.stroke();
        cx.globalAlpha = lit ? 1 : .7; cx.fillStyle = '#fff';
        cx.beginPath(); cx.arc(x, y, lit ? 2 : 1.4, 0, 7); cx.fill();
      });
      if(lit){
        const pr = (t * .6) % 1;
        cx.globalAlpha = (1 - pr) * .6; cx.strokeStyle = AIS[i].c1; cx.lineWidth = 1.2;
        cx.beginPath(); cx.arc(P[i][0], P[i][1], 14 + pr * 60, 0, 7); cx.stroke();
      }
    });
    // étoile filante, lente
    nextShoot -= dt;
    if(!shoot && nextShoot <= 0 && !RM){ shoot = { x:Math.random() * W * .7, y:Math.random() * H * .35, p:0 }; nextShoot = 6 + Math.random() * 6; }
    if(shoot){
      shoot.p += dt / 1.6;
      const x = shoot.x + shoot.p * 360, y = shoot.y + shoot.p * 160;
      const g = cx.createLinearGradient(x - 120, y - 53, x, y);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(1, 'rgba(255,255,255,.9)');
      cx.globalAlpha = Math.sin(Math.min(1, shoot.p) * Math.PI); cx.strokeStyle = g; cx.lineWidth = 1.4;
      cx.beginPath(); cx.moveTo(x - 120, y - 53); cx.lineTo(x, y); cx.stroke();
      if(shoot.p >= 1) shoot = null;
    }
    cx.globalAlpha = 1;
  }));
  return () => offs.forEach(f => f());
}

/* =========================================================
   8 · CADRAN — un sélecteur à tourner
   ========================================================= */
function cadran(st){
  const offs = [];
  let ticks = '';
  for(let k = 0; k < 60; k++){
    const a = k * 6 * Math.PI / 180, big = k % 15 === 0, mid = k % 5 === 0;
    const r1 = 47.5, r2 = big ? 42.5 : mid ? 44.5 : 45.8;
    ticks += '<line x1="'+(50 + Math.sin(a) * r1).toFixed(2)+'" y1="'+(50 - Math.cos(a) * r1).toFixed(2)+'" x2="'+(50 + Math.sin(a) * r2).toFixed(2)+'" y2="'+(50 - Math.cos(a) * r2).toFixed(2)+'" stroke="rgba(255,255,255,'+(big ? .55 : mid ? .3 : .14)+')" stroke-width="'+(big ? .6 : .35)+'"/>';
  }
  st.innerHTML = '<div class="cdr-tint"></div><div class="cdr-wrap">' +
    '<div class="dial"><div class="bezel"></div><div class="rot"><svg class="ticks" viewBox="0 0 100 100" aria-hidden="true">'+ticks+'</svg>' +
      AIS.map((a, i) => '<div class="arm" style="--ang:'+(i * 90)+'deg"><button class="slot" data-i="'+i+'" style="'+vars(a)+'" aria-label="'+a.nom+'"><span class="b">'+icon(a.id, 34)+'</span></button></div>').join('') +
      '</div><div class="face"><div class="center"></div></div><div class="pointer"></div></div>' +
    '<div class="cdr-info"><div class="k"></div><div class="nm"></div><div class="best"></div><ul></ul>' +
      '<div class="acts"><button class="go"></button></div>' +
      '<p class="hint2">Tourne la molette, fais glisser le cadran ou clique une pastille.</p></div></div>';
  const rot = st.querySelector('.rot'), slots = [...st.querySelectorAll('.slot')], center = st.querySelector('.center'), tint = st.querySelector('.cdr-tint');
  const k = st.querySelector('.cdr-info .k'), nm = st.querySelector('.cdr-info .nm'), best = st.querySelector('.cdr-info .best'),
        ul = st.querySelector('.cdr-info ul'), go = st.querySelector('.cdr-info .go');
  let pos = 0, i = -1;
  const apply = first => {
    const n = mod(pos, 4);
    rot.style.transform = 'rotate(' + (-pos * 90) + 'deg)';
    slots.forEach((s, j) => {
      s.classList.toggle('on', j === n);
      s.querySelector('.b').style.transform = 'rotate(' + (-(j * 90) + pos * 90) + 'deg)';
    });
    if(n === i) return; i = n;
    const a = AIS[n];
    setAIVars(st, a);
    tint.style.opacity = 0;
    setTimeout(() => { tint.style.background = 'radial-gradient(900px 640px at 30% 50%,' + a.c1 + '33,transparent 65%)'; tint.style.opacity = 1; }, first ? 0 : 250);
    center.innerHTML = '<div class="ci ln">'+icon(a.id, 34)+'</div><div class="cn ln" style="--d:1">'+a.nom+'</div><div class="cx ln" style="--d:2">'+esc(a.modele.toUpperCase())+'</div>';
    k.textContent = a.num + ' · ' + a.tag;
    scramble(nm, a.nom);
    best.textContent = a.best;
    ul.innerHTML = lines(a, 3, 2, true);
    go.innerHTML = 'Parler à ' + a.nom + ' ' + UI.arrow;
  };
  apply(true);
  const step = d => { pos += d; apply(); };
  slots.forEach((s, j) => s.onclick = () => {
    if(j === i){ openChat(AIS[j].id, s); return; }
    let d = mod(j - i, 4); if(d === 3) d = -1;
    step(d);
  });
  const dial = st.querySelector('.dial'); let dg = null;
  offs.push(on(dial, 'pointerdown', e => { const r = dial.getBoundingClientRect(); dg = { cx:r.left + r.width / 2, cy:r.top + r.height / 2, a:Math.atan2(e.clientY - r.top - r.height / 2, e.clientX - r.left - r.width / 2) }; }));
  offs.push(on(window, 'pointermove', e => {
    if(!dg) return;
    const a = Math.atan2(e.clientY - dg.cy, e.clientX - dg.cx); let d = a - dg.a;
    if(d > Math.PI) d -= 2 * Math.PI; if(d < -Math.PI) d += 2 * Math.PI;
    if(Math.abs(d) > .55){ step(d > 0 ? -1 : 1); dg.a = a; }
  }));
  offs.push(on(window, 'pointerup', () => { dg = null; }));
  go.onclick = () => openChat(AIS[i].id, go);
  const can = throttle(650);
  offs.push(on(st.querySelector('.dial'), 'wheel', e => { e.preventDefault(); if(Math.abs(e.deltaY) > 6 && can()) step(e.deltaY > 0 ? 1 : -1); }, { passive:false }));
  offs.push(on(document, 'keydown', e => {
    if(window.__chatOpen || e.target.closest('input,textarea')) return;
    if(e.key === 'ArrowRight' || e.key === 'ArrowDown'){ e.preventDefault(); step(1); }
    if(e.key === 'ArrowLeft' || e.key === 'ArrowUp'){ e.preventDefault(); step(-1); }
    if(e.key === 'Enter' && !e.target.closest('button')){ openChat(AIS[i].id, slots[i]); }
  }));
  return () => offs.forEach(f => f());
}

/* =========================================================
   SÉLECTEUR DE CONCEPTS
   ========================================================= */
const CONCEPTS = [
  { id:'sphere',    nom:'Sphère',        mount:sphere,   sw:'linear-gradient(90deg,#f2efe9,#ffd000,#fa1e0e)', desc:'L\'accueil : une forme par IA. Molette ou flèches : elle descend et la suivante arrive.', light:true, arrows:true },
  { id:'scroll3d',  nom:'La roue 3D',    mount:scroll3d, sw:'linear-gradient(90deg,#ff6a3d,#4285f4,#ffd000,#3fe0b5)', desc:'Molette ou flèches, en boucle : la roue tourne et t\'amène chaque IA.', arrows:true },
  { id:'cadran',    nom:'Cadran',        mount:cadran,   sw:'linear-gradient(90deg,#17181d,#40434d,#ffb340)', desc:'Un sélecteur façon montre : tourne la molette ou fais glisser le cadran.', arrows:true }
];
const NC = CONCEPTS.length;
const stage = $('stage'), wipe = $('wipe');
let ci = -1, clean = null, busy = false;

function mountNow(i){
  if(clean){ try{ clean(); }catch(e){ console.error(e); } clean = null; }
  const c = CONCEPTS[i];
  stage.innerHTML = '';
  stage.removeAttribute('style');
  stage.className = 'stage c-' + c.id + ' enter';
  document.body.classList.toggle('light', !!c.light);
  try{ clean = c.mount(stage) || null; }catch(e){ console.error(e); }
  $('clbl').innerHTML = '<b>' + String(i + 1).padStart(2, '0') + ' / ' + NC + '</b>' + c.nom;
  $('cdesc').textContent = c.desc;
  document.querySelectorAll('.ov-t').forEach((t, k) => t.classList.toggle('cur', k === i));
  ci = i;
  LS.set('concept', i);
  setTimeout(() => stage.classList.remove('enter'), 800);
}

function show(i, instant){
  i = mod(i, NC);
  if(window.__chatOpen) APP.closeChat();
  if(i === ci || busy) return;
  if(instant || RM){ mountNow(i); return; }
  busy = true;
  wipe.style.background = CONCEPTS[i].light ? '#f2efe9' : '#07080d';
  wipe.classList.add('on');
  setTimeout(() => {
    mountNow(i);
    requestAnimationFrame(() => { wipe.classList.remove('on'); busy = false; });
  }, 330);
}

function initOverview(){
  const ov = $('ov');
  ov.innerHTML = '<div class="ov-in"><div class="ov-h"><div><h2>Choisis ton écran</h2><p class="s">Même routeur, même conversation : seule la porte d\'entrée change.</p></div>' +
    '<button class="ov-x" aria-label="Fermer">×</button></div><div class="ov-grid">' +
    CONCEPTS.map((c, i) => '<button class="ov-t" data-i="'+i+'" style="--i:'+i+';--sw:'+c.sw+'"><div class="n">'+String(i + 1).padStart(2, '0')+(c.light ? ' · CLAIR' : '')+'</div><div class="t">'+c.nom+'</div><div class="d">'+esc(c.desc)+'</div><div class="sw"></div></button>').join('') +
    '</div><p class="ov-keys"><kbd>1</kbd>…<kbd>3</kbd> concept direct · <kbd>PgPréc</kbd> <kbd>PgSuiv</kbd> ou <kbd>←</kbd> <kbd>→</kbd> pour changer · <kbd>G</kbd> cet aperçu · <kbd>Ctrl</kbd>+<kbd>K</kbd> ouvrir une IA</p></div>';
  ov.querySelector('.ov-x').onclick = () => ov.classList.remove('on');
  ov.addEventListener('click', e => { if(e.target === ov) ov.classList.remove('on'); });
  ov.querySelectorAll('.ov-t').forEach(t => t.onclick = () => { ov.classList.remove('on'); show(+t.dataset.i); });
}
const ovToggle = f => $('ov').classList.toggle('on', f);

function init(){
  $('prev').innerHTML = UI.chevL; $('next').innerHTML = UI.chevR; $('gridbtn').innerHTML = UI.grid;
  $('prev').onclick = () => show(ci - 1);
  $('next').onclick = () => show(ci + 1);
  $('gridbtn').onclick = () => ovToggle(!$('ov').classList.contains('on'));
  initOverview();

  document.addEventListener('keydown', e => {
    if(window.__chatOpen || e.ctrlKey || e.metaKey || e.altKey) return;
    if(document.querySelector('.pal.on')) return;
    if(e.target.closest && e.target.closest('input,textarea')) return;
    const ovOn = $('ov').classList.contains('on');
    if(e.key === 'Escape' && ovOn){ ovToggle(false); return; }
    if(e.key === 'g' || e.key === 'G'){ ovToggle(!ovOn); return; }
    if(/^[1-9]$/.test(e.key) && +e.key <= NC){ ovToggle(false); show(+e.key - 1); return; }
    if(e.key === 'PageDown'){ e.preventDefault(); show(ci + 1); return; }
    if(e.key === 'PageUp'){ e.preventDefault(); show(ci - 1); return; }
    const c = CONCEPTS[ci];
    if(c && !c.arrows && !ovOn){
      if(e.key === 'ArrowRight'){ show(ci + 1); }
      if(e.key === 'ArrowLeft'){ show(ci - 1); }
    }
  });

  const q = new URLSearchParams(location.search);
  let start = LS.get('concept', 0);
  if(q.has('c')){ const n = parseInt(q.get('c'), 10); if(n >= 1 && n <= NC) start = n - 1; }
  if(!(start >= 0 && start < NC)) start = 0;
  mountNow(start);
  const ai = q.get('ai');
  if(ai && AI_BY[ai]) openChat(ai, null, true);
}

window.showConcept = i => show(i, true);
window.CONCEPTS = CONCEPTS;
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
