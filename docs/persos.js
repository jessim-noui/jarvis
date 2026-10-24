'use strict';
/* Mission 10 : les personnages pixel art, partagés par Le jeu et la Table du Conseil. */
/* =========================================================
   Pixel art : un gabarit de personnage, recoloré et accessoirisé
   ========================================================= */
const GABARIT = [
  '......KKKK......','....KKHHHHKK....','...KHHHHHHHHK...','...KHHHHHHHHK...','..KHHSSSSSSHHK..','..KHSSSSSSSSHK..',
  '..KSSESSSSESSK..','..KSSESSSSESSK..','..KSSSSSSSSSSK..','...KSSSMMSSSK...','....KKSSSSKK....','...KTTKSSKTTK...',
  '..KTTTTTTTTTTK..','.KTTTTTTTTTTTTK.','.KTTKTTTTTTKTTK.','.KTTKTTTTTTKTTK.','.KSSKTTTTTTKSSK.','..KKKTTTTTTKKK..',
  '....KPPPPPPK....','....KPPPPPPK....','....KPPKKPPK....','....KPPKKPPK....','....KBBKKBBK....','...KBBBKKBBBK...'];
const PERSOS = {
  perso:     {H:'#4a2e21', S:'#f0c9a0', T:'#3f7d5c', P:'#4f6d93', B:'#3a2a22'},
  facteur:    {H:'#2d2420', S:'#d9a77c', T:'#3c66a8', P:'#2f3e5e', B:'#2a1f1a', extra:[['#2f56a0',3,0,10,4],['#24427d',2,4,6,1],['#8a5a35',1,15,4,4],['#6b4428',4,11,1,5]]},
  recruteuse: {H:'#6b3a22', S:'#f2cfaa', T:'#7c2f3f', P:'#3a2e3a', B:'#2a1f1a', extra:[['#6b3a22',2,5,1,7],['#6b3a22',13,5,1,7],['#efe2c8',12,13,4,6],['#cdbb9c',12,13,4,1]]},
  eclaireur:  {H:'#5a4030', S:'#e4b58c', T:'#7a6a3c', P:'#5b4b33', B:'#3a2a22', extra:[['#c9b07a',3,0,10,4],['#b39a64',1,4,14,1],['#8f8f96',13,12,3,2],['#5d5d66',15,12,1,2]]},
  mentor:     {H:'#b9b6ae', S:'#e9c3a0', T:'#6a5a8a', P:'#3f3a48', B:'#2a1f1a', extra:[['#c9c6be',4,8,8,3],['#c9c6be',5,11,6,1],['#4c3f63',5,12,6,6]]},
  ingenieur:  {H:'#3a2a20', S:'#dcae86', T:'#d1782f', P:'#3d4a5e', B:'#2a1f1a', extra:[['#f2c230',3,0,10,4],['#d9a91f',2,4,12,1],['#9a9aa3',14,15,2,4],['#7c7c86',13,15,1,1]]},
  gardien:    {H:'#3b3f4a', S:'#e2b893', T:'#7c8aa3', P:'#4a5468', B:'#2a2f3a', extra:[['#9aa7bf',3,0,10,4],['#2f5fa6',0,12,5,7],['#f2c46d',2,13,1,5],['#f2c46d',1,15,3,1]]},
};
const SPR = {};
function fabriquer(nom, signe) {
  const p = PERSOS[nom], c = document.createElement('canvas'); c.width = 16; c.height = 24;
  const x = c.getContext('2d'), coul = {K:'#2b2024', E:'#2b2024', M:'#a5584a', ...p};
  GABARIT.forEach((l, j) => [...l].forEach((ch, i) => { if (ch !== '.') { x.fillStyle = coul[ch]; x.fillRect(i, j, 1, 1); } }));
  for (const [col, a, b, w, h] of p.extra || []) { x.fillStyle = col; x.fillRect(a, b, w, h); }
  if (signe) {  // bras droit levé qui fait coucou
    x.clearRect(12, 13, 3, 4); x.fillStyle = '#2b2024'; x.fillRect(12, 13, 1, 4);
    x.fillStyle = p.T; x.fillRect(13, 7, 2, 6); x.fillStyle = p.S; x.fillRect(13, 4, 2, 3);
    x.fillStyle = '#2b2024'; x.fillRect(12, 4, 1, 9); x.fillRect(15, 4, 1, 9); x.fillRect(13, 3, 2, 1);
  }
  return c;
}
for (const n in PERSOS) SPR[n] = fabriquer(n);
SPR.perso_signe = fabriquer('perso', true);
