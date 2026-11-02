/* ShowWise Backend console: nav toggle, live instance checks, confirm prompts, copy buttons. */
(function () {
  'use strict';
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  // Mobile menu
  var menu = $('[data-menu-toggle]');
  var rail = $('.rail');
  if (menu && rail) {
    menu.addEventListener('click', function () {
      var open = rail.classList.toggle('open');
      menu.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Confirm before a destructive form submit: <form data-confirm="Delete Acme?">
  document.addEventListener('submit', function (e) {
    var msg = e.target && e.target.getAttribute && e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Copy buttons: <button data-copy="#some-id">
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-copy]');
    if (!btn) return;
    var src = $(btn.getAttribute('data-copy'));
    if (!src || !navigator.clipboard) return;
    var clone = src.cloneNode(true);
    $$('button', clone).forEach(function (b) { b.remove(); });  // copy the text, not the Copy button's label
    navigator.clipboard.writeText(clone.textContent.trim()).then(function () {
      var old = btn.textContent;
      btn.textContent = 'Copied';
      setTimeout(function () { btn.textContent = old; }, 1400);
    });
  });

  function getJSON(url) {
    return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  }

  // Run async jobs a few at a time so a long list of instances never trips the rate limit.
  function pool(items, worker, size) {
    var i = 0;
    function next() {
      if (i >= items.length) return Promise.resolve();
      var item = items[i++];
      return worker(item).then(next, next);
    }
    var runners = [];
    for (var n = 0; n < Math.min(size, items.length); n++) runners.push(next());
    return Promise.all(runners);
  }

  var LAMP = { up: 'up', degraded: 'warn', down: 'down', blocked: 'down', unknown: 'off' };
  var LABEL = { up: 'Up', degraded: 'Degraded', down: 'Down', blocked: 'Blocked', unknown: 'No URL' };

  // Instance health: any element with data-health="<slug>"
  function checkHealth(row) {
    var slug = row.getAttribute('data-health');
    var lamp = $('[data-lamp]', row), lat = $('[data-latency]', row), label = $('[data-status-label]', row);
    if (lamp) { lamp.setAttribute('data-state', 'checking'); lamp.title = 'Checking'; }
    if (label) label.textContent = 'Checking';
    return getJSON('/api/admin/instances/' + encodeURIComponent(slug) + '/health').then(function (d) {
      var state = LAMP[d.status] || 'off';
      row.setAttribute('data-result', d.status);
      if (lamp) { lamp.setAttribute('data-state', state); lamp.title = d.detail || ''; }
      if (lat) lat.textContent = d.latency_ms != null ? d.latency_ms + ' ms' : '—';
      if (label) { label.textContent = LABEL[d.status] || d.status; label.title = d.detail || ''; }
      var detail = $('[data-detail]', row); if (detail) detail.textContent = d.detail || '';
    }).catch(function () {
      row.setAttribute('data-result', 'unknown');
      if (lamp) { lamp.setAttribute('data-state', 'off'); lamp.title = 'Check failed'; }
      if (label) label.textContent = 'Check failed';
    });
  }

  function tally() {
    var rows = $$('[data-health]');
    var count = function (s) { return rows.filter(function (r) { return r.getAttribute('data-result') === s; }).length; };
    var map = { up: count('up'), down: count('down') + count('blocked'), warn: count('degraded') };
    Object.keys(map).forEach(function (k) {
      $$('[data-tally="' + k + '"]').forEach(function (el) { el.textContent = map[k]; });
    });
  }

  function runHealth() {
    var rows = $$('[data-health]');
    if (!rows.length) return Promise.resolve();
    return pool(rows, checkHealth, 4).then(tally);
  }

  // Support receiver status: any element with data-receiver="<slug>"
  var RECEIVER = { ready: ['up', 'Receiver on'], not_configured: ['warn', 'Not set up'], down: ['down', 'Unreachable'], blocked: ['down', 'Blocked'], unknown: ['', 'No URL'], error: ['down', 'Error'] };
  function checkReceiver(el) {
    var slug = el.getAttribute('data-receiver');
    var chip = $('[data-receiver-chip]', el) || el;
    chip.className = 'chip'; chip.textContent = 'Checking';
    return getJSON('/support/org/' + encodeURIComponent(slug) + '/receiver').then(function (d) {
      var m = RECEIVER[d.status] || ['', d.status];
      chip.className = 'chip ' + m[0]; chip.textContent = m[1]; chip.title = d.detail || '';
      var detail = $('[data-receiver-detail]'); if (detail) detail.textContent = d.detail || '';
    }).catch(function () { chip.className = 'chip'; chip.textContent = 'Check failed'; });
  }
  function runReceivers() {
    var els = $$('[data-receiver]');
    return pool(els, checkReceiver, 3);
  }

  $$('[data-recheck]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      btn.disabled = true;
      Promise.all([runHealth(), runReceivers()]).then(function () { btn.disabled = false; });
    });
  });

  runHealth();
  runReceivers();
})();
