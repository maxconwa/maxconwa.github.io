/* Interaction for the prerequisite graph.
   The SVG itself is rendered at build time; this only adds selection,
   panning and the side panel. With JS off the graph is still a set of
   links and the lesson list below it still works. */
(function () {
  'use strict';

  var dataEl = document.getElementById('graph-data');
  var canvas = document.getElementById('graph-canvas');
  var panel = document.getElementById('graph-panel');
  if (!dataEl || !canvas || !panel) { return; }

  var data = JSON.parse(dataEl.textContent);
  var svg = canvas.querySelector('svg');
  if (!svg) { return; }

  var nodes = Array.prototype.slice.call(svg.querySelectorAll('.node'));
  var edges = Array.prototype.slice.call(svg.querySelectorAll('.edge-group'));
  var rows = Array.prototype.slice.call(document.querySelectorAll('#lesson-list li[data-slug]'));
  var selected = null;

  /* ---- traversal ---- */

  function reachable(start, adjacency) {
    var seen = Object.create(null);
    var stack = (adjacency[start] || []).slice();
    while (stack.length) {
      var slug = stack.pop();
      if (seen[slug]) { continue; }
      seen[slug] = true;
      var next = adjacency[slug] || [];
      for (var i = 0; i < next.length; i++) {
        if (!seen[next[i]]) { stack.push(next[i]); }
      }
    }
    return seen;
  }

  /* ---- selection ---- */

  function select(slug, updateHash) {
    if (!data.nodes[slug]) { return; }
    selected = slug;
    var ancestors = reachable(slug, data.prereqs);
    var descendants = reachable(slug, data.unlocks);

    canvas.classList.add('has-selection');
    nodes.forEach(function (node) {
      var s = node.dataset.slug;
      node.classList.toggle('is-selected', s === slug);
      node.classList.toggle('is-ancestor', !!ancestors[s]);
      node.classList.toggle('is-descendant', !!descendants[s]);
    });

    edges.forEach(function (edge) {
      var tail = edge.dataset.tail, head = edge.dataset.head;
      var upstream = (ancestors[tail] || tail === slug) && (ancestors[head] || head === slug);
      var downstream = (descendants[tail] || tail === slug) && (descendants[head] || head === slug);
      edge.classList.toggle('is-lit', !!(upstream || downstream));
    });

    rows.forEach(function (row) {
      if (row.dataset.slug === slug) { row.setAttribute('aria-current', 'true'); }
      else { row.removeAttribute('aria-current'); }
    });

    renderPanel(slug, ancestors, descendants);
    if (updateHash !== false && history.replaceState) {
      history.replaceState(null, '', '#' + slug);
    }
  }

  function clear() {
    selected = null;
    canvas.classList.remove('has-selection');
    nodes.forEach(function (n) {
      n.classList.remove('is-selected', 'is-ancestor', 'is-descendant');
    });
    edges.forEach(function (e) { e.classList.remove('is-lit'); });
    rows.forEach(function (r) { r.removeAttribute('aria-current'); });
    panel.innerHTML = '<p class="panel-empty">Select a lesson to see what it needs '
      + 'and what it leads to.</p>';
    if (history.replaceState) { history.replaceState(null, '', location.pathname); }
  }

  function linkList(slugs) {
    if (!slugs.length) { return '<p class="panel-empty">None.</p>'; }
    return '<ul>' + slugs.map(function (s) {
      var n = data.nodes[s];
      return '<li><a href="' + n.url + '">' + escapeHtml(n.title) + '</a></li>';
    }).join('') + '</ul>';
  }

  function renderPanel(slug, ancestors, descendants) {
    var node = data.nodes[slug];
    // Order by the build's topological order so the chain reads sensibly.
    var before = data.order.filter(function (s) { return ancestors[s]; });
    var after = data.order.filter(function (s) { return descendants[s]; });

    panel.innerHTML =
      (node.track ? '<p class="kicker" data-track="' + node.slot + '">'
        + escapeHtml(node.track) + '</p>' : '')
      + '<h2>' + escapeHtml(node.title) + '</h2>'
      + '<p class="panel-summary">' + escapeHtml(node.summary) + '</p>'
      + '<h3>Needs first</h3>' + linkList(before)
      + '<h3>Unlocks</h3>' + linkList(after)
      + '<a class="btn" href="' + node.url + '">Open lesson</a>';
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /* ---- events ---- */

  nodes.forEach(function (node) {
    var slug = node.dataset.slug;
    node.addEventListener('click', function (event) {
      // Let modified clicks and middle-clicks open the lesson as usual.
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) { return; }
      event.preventDefault();
      if (selected === slug) { clear(); } else { select(slug); }
    });
    // Keyboard focus previews without stealing Enter, which still navigates.
    // Only on keyboard focus: a mouse click also focuses the link, and
    // selecting here would make the click handler above see an existing
    // selection and toggle it straight back off.
    node.addEventListener('focusin', function (event) {
      var link = event.target.closest('a') || event.target;
      try {
        if (!link.matches(':focus-visible')) { return; }
      } catch (unsupported) {
        return;
      }
      select(slug);
    });
  });

  canvas.addEventListener('click', function (event) {
    if (!event.target.closest('.node')) { clear(); }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && selected) { clear(); }
  });

  /* ---- pan and zoom ---- */

  var box = svg.getAttribute('viewBox').split(/\s+/).map(Number);

  function applyBox() { svg.setAttribute('viewBox', box.join(' ')); }

  function unitsPerPixel() { return box[2] / canvas.clientWidth; }

  var dragging = false, lastX = 0, lastY = 0;

  canvas.addEventListener('pointerdown', function (event) {
    if (event.target.closest('.node')) { return; }
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.classList.add('is-panning');
    canvas.setPointerCapture(event.pointerId);
  });

  canvas.addEventListener('pointermove', function (event) {
    if (!dragging) { return; }
    var scale = unitsPerPixel();
    box[0] -= (event.clientX - lastX) * scale;
    box[1] -= (event.clientY - lastY) * scale;
    lastX = event.clientX;
    lastY = event.clientY;
    applyBox();
  });

  ['pointerup', 'pointercancel'].forEach(function (name) {
    canvas.addEventListener(name, function () {
      dragging = false;
      canvas.classList.remove('is-panning');
    });
  });

  canvas.addEventListener('wheel', function (event) {
    event.preventDefault();
    var rect = canvas.getBoundingClientRect();
    var scale = unitsPerPixel();
    var pointerX = box[0] + (event.clientX - rect.left) * scale;
    var pointerY = box[1] + (event.clientY - rect.top) * scale;
    var factor = event.deltaY > 0 ? 1.12 : 1 / 1.12;
    var width = Math.min(Math.max(box[2] * factor, 200), 12000);
    var ratio = width / box[2];
    box[0] = pointerX - (pointerX - box[0]) * ratio;
    box[1] = pointerY - (pointerY - box[1]) * ratio;
    box[2] = width;
    box[3] *= ratio;
    applyBox();
  }, { passive: false });

  /* ---- deep link ---- */

  var initial = location.hash.replace('#', '');
  if (initial && data.nodes[initial]) { select(initial, false); }
})();
