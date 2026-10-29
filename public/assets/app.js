'use strict';
const form = document.querySelector('#vote-form');
if (form) {
  const sliders = Array.from(form.querySelectorAll('input[type=range]'));
  const submit = document.querySelector('#submit-vote');
  const update = () => {
    const sum = sliders.reduce((total, slider) => total + Number(slider.value), 0);
    sliders.forEach((slider, i) => {
      document.querySelector('#value-' + i).textContent = slider.value + ' mil. EUR';
      slider.setAttribute('aria-valuetext', slider.value + ' milionů EUR');
    });
    document.querySelector('#allocated').textContent = sum + ' mil. EUR';
    document.querySelector('#remaining').textContent = (4 - sum) + ' mil. EUR';
    document.querySelector('#budget-fill').style.width = Math.min(100, sum * 25) + '%';
    document.querySelector('#budget-status').textContent = sum === 4 ? 'Hotovo! Můžete odeslat svůj hlas.' : sum < 4 ? 'Rozdělte ještě ' + (4 - sum) + ' mil. EUR.' : 'Překročeno o ' + (sum - 4) + ' mil. EUR. Snižte některou částku.';
    document.querySelector('.budget').classList.toggle('over-budget', sum > 4);
    submit.disabled = sum !== 4;
  };
  sliders.forEach(slider => slider.addEventListener('input', update));
  update();
  form.addEventListener('submit', async event => {
    event.preventDefault();
    submit.disabled = true;
    document.querySelector('#vote-error').textContent = '';
    try {
      const response = await fetch(form.action, {method: 'POST', body: new URLSearchParams(new FormData(form))});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Hlas se nepodařilo odeslat.');
      location.reload();
    } catch (error) {
      document.querySelector('#vote-error').textContent = error.message + ' Při potížích s připojením obnovte stránku a ověřte přijetí hlasu.';
      update();
    }
  });
}
const results = document.querySelector('#results');
if (results) {
  const number = new Intl.NumberFormat('cs-CZ');
  const refresh = async () => {
    try {
      const response = await fetch('api.cgi', {cache: 'no-store'});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      document.querySelector('#vote-count').textContent = number.format(data.count);
      document.querySelector('#total-money').textContent = number.format(data.count * 4) + ' mil. EUR';
      results.replaceChildren();
      if (!data.items.length) {
        const empty = document.createElement('p');
        empty.className = 'panel';
        empty.textContent = 'Projekty se připravují.';
        results.append(empty);
      }
      data.items.map((name, i) => ({name, total: data.totals[i], index: i})).sort((a, b) => b.total - a.total || a.index - b.index).forEach((item, rank) => {
        const share = data.count ? item.total / (data.count * 4) * 100 : 0;
        const row = document.createElement('article');
        row.className = 'result-row panel';
        const top = document.createElement('div');
        top.className = 'result-top';
        const title = document.createElement('h2');
        title.textContent = String(rank + 1).padStart(2, '0') + '  ' + item.name;
        const amount = document.createElement('strong');
        amount.textContent = number.format(item.total) + ' mil. EUR';
        const percent = document.createElement('span');
        percent.textContent = number.format(Math.round(share * 10) / 10) + ' %';
        top.append(title, amount, percent);
        const track = document.createElement('div');
        track.className = 'result-track';
        const bar = document.createElement('div');
        bar.style.width = share + '%';
        track.append(bar);
        row.append(top, track);
        results.append(row);
      });
      document.querySelector('#live-status').textContent = 'Živě · aktualizováno ' + new Date().toLocaleTimeString('cs-CZ');
    } catch (_) {
      document.querySelector('#live-status').textContent = 'Spojení přerušeno. Zkouším znovu…';
    } finally { setTimeout(refresh, 5000); }
  };
  refresh();
}
const fullscreen = document.querySelector('#fullscreen');
if (fullscreen) fullscreen.addEventListener('click', async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch (_) { fullscreen.textContent = 'Použijte režim celé obrazovky prohlížeče'; }
});
const reset = document.querySelector('#reset-round');
if (reset) reset.addEventListener('click', event => {
  if (!confirm('Opravdu vymazat všechny dosavadní hlasy a zahájit nové kolo? Tuto akci nelze vrátit.')) event.preventDefault();
});
