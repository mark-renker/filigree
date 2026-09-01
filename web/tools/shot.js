// Dev-only capture helper (NOT part of the shipped app; tests skip web/tools/).
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2] || '/tmp/shot.png';
  const w = +(process.argv[3] || 1440), h = +(process.argv[4] || 900);
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  const errs = [];
  pg.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') errs.push(m.type() + ': ' + m.text()); });
  pg.on('pageerror', e => errs.push('pageerror: ' + e.message));
  await pg.goto('http://localhost:8123/', { waitUntil: 'networkidle' });
  await pg.waitForTimeout(1400);
  // pin a note so the inspector is populated in the capture
  await pg.evaluate(() => window.scrollTo(0, 0));
  // pin the long expressive lead note in bar 4 (F5, 2.5 beats, `wide` gesture)
  const hit = await pg.evaluate(() => {
    const el = document.getElementById('cRoll').getBoundingClientRect();
    return { x: el.left, y: el.top };
  });
  const geo = await pg.evaluate(() => {
    const g = window.__geo(); return { x: g.b2x(12.6), y: g.p2y(77) + g.rowH / 2 };
  });
  await pg.mouse.click(hit.x + geo.x, hit.y + geo.y);
  await pg.waitForTimeout(300);
  // roll the transport so the playhead and position readout are alive
  if (process.argv[5] !== 'still') {
    await pg.evaluate(() => { document.getElementById('btnPlay').click(); });
    await pg.waitForTimeout(3200);
  }
  await pg.waitForTimeout(700);
  const diag = await pg.evaluate(() => ({
    voices: window.__dbgVoices ? window.__dbgVoices() : null
  }));
  await pg.screenshot({ path: out });
  console.log('diag', JSON.stringify(diag));
  console.log(JSON.stringify({ out, errs }, null, 1));
  await b.close();
})();
