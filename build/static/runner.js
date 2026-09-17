/* Live cells, activated on request.
   Until the visitor presses the button this file does nothing at all: the
   lesson is a static rendered page. Activation loads Pyodide from the CDN,
   swaps each code cell for an editor, and runs cells in one shared namespace.
   If any of that fails the static lesson is still completely readable. */
(function () {
  'use strict';

  var PYODIDE_VERSION = '0.28.3';
  var PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v' + PYODIDE_VERSION + '/full/';

  var button = document.getElementById('activate');
  var status = document.getElementById('kernel-status');
  var body = document.querySelector('.lesson-body.is-runnable');
  if (!button || !body) { return; }

  var pyodide = null;
  var cells = [];

  // Figures are collected after each cell rather than through a live canvas
  // backend: simpler, and it matches how the saved outputs already look.
  var FIGURE_SHIM = [
    'import base64, io, sys',
    'def _collect_figures():',
    '    figures = []',
    '    plt = sys.modules.get("matplotlib.pyplot")',
    '    if plt is None:',
    '        return figures',
    '    for num in plt.get_fignums():',
    '        buffer = io.BytesIO()',
    '        plt.figure(num).savefig(buffer, format="png", dpi=110, bbox_inches="tight")',
    '        figures.append(base64.b64encode(buffer.getvalue()).decode())',
    '    plt.close("all")',
    '    return figures'
  ].join('\n');

  function say(message) { if (status) { status.textContent = message; } }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var tag = document.createElement('script');
      tag.src = src;
      tag.onload = resolve;
      tag.onerror = function () { reject(new Error('could not load ' + src)); };
      document.head.appendChild(tag);
    });
  }

  /* ---- cell construction ---- */

  function makeEditor(cell) {
    var code = cell.querySelector('.code');
    var source = code ? code.textContent.replace(/\n+$/, '') : '';

    var editor = document.createElement('textarea');
    editor.className = 'cell-editor';
    editor.value = source;
    editor.spellcheck = false;
    editor.setAttribute('aria-label', 'Editable code cell');
    editor.rows = source.split('\n').length + 1;

    // Tab indents rather than leaving the cell.
    editor.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab') { return; }
      event.preventDefault();
      var start = editor.selectionStart;
      editor.value = editor.value.slice(0, start) + '    ' + editor.value.slice(editor.selectionEnd);
      editor.selectionStart = editor.selectionEnd = start + 4;
    });

    var run = document.createElement('button');
    run.type = 'button';
    run.className = 'cell-run';
    run.textContent = 'Run';

    var note = document.createElement('span');
    note.className = 'cell-note';

    var bar = document.createElement('div');
    bar.className = 'cell-bar';
    bar.appendChild(run);
    bar.appendChild(note);

    var outputs = cell.querySelector('.outputs');
    if (!outputs) {
      outputs = document.createElement('div');
      outputs.className = 'outputs';
      cell.appendChild(outputs);
    }

    if (code) { cell.replaceChild(editor, code); }
    cell.insertBefore(bar, outputs);

    var record = {
      element: cell, editor: editor, outputs: outputs,
      note: note, button: run, original: source, hasRun: false
    };
    run.addEventListener('click', function () { runCell(record); });
    return record;
  }

  /* ---- execution ---- */

  function write(outputs, className, text) {
    if (!text) { return; }
    var block = document.createElement('pre');
    block.className = 'out ' + className;
    block.textContent = text;
    outputs.appendChild(block);
  }

  function writeImage(outputs, base64) {
    var wrapper = document.createElement('div');
    wrapper.className = 'out out-image';
    var image = document.createElement('img');
    image.src = 'data:image/png;base64,' + base64;
    image.alt = 'Figure produced by this cell';
    wrapper.appendChild(image);
    outputs.appendChild(wrapper);
  }

  async function runCell(cell) {
    if (!pyodide) { return; }
    cell.outputs.innerHTML = '';
    cell.button.disabled = true;
    cell.note.textContent = 'Running…';

    var captured = [];
    pyodide.setStdout({ batched: function (line) { captured.push(line); } });
    pyodide.setStderr({ batched: function (line) { captured.push(line); } });

    try {
      var result = await pyodide.runPythonAsync(cell.editor.value);
      write(cell.outputs, 'out-stream', captured.join('\n'));
      if (result !== undefined && result !== null) {
        write(cell.outputs, 'out-value', String(result));
      }
      var figures = pyodide.runPython('_collect_figures()').toJs();
      figures.forEach(function (encoded) { writeImage(cell.outputs, encoded); });
      cell.note.textContent = '';
      cell.hasRun = true;
    } catch (error) {
      write(cell.outputs, 'out-stream', captured.join('\n'));
      write(cell.outputs, 'out-error', String(error.message || error));
      cell.note.textContent = '';
    } finally {
      cell.button.disabled = false;
      warnAboutOrder();
    }
  }

  // Cells share one namespace, so running out of order is allowed but worth
  // mentioning — it is the most common reason a live cell raises NameError.
  function warnAboutOrder() {
    for (var i = 0; i < cells.length; i++) {
      var earlierMissed = cells.slice(0, i).some(function (c) { return !c.hasRun; });
      cells[i].note.textContent =
        (cells[i].hasRun && earlierMissed) ? 'cells above this one have not run' : '';
    }
  }

  /* ---- activation ---- */

  async function activate() {
    button.disabled = true;
    say('Loading Python…');

    try {
      await loadScript(PYODIDE_URL + 'pyodide.js');
      pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

      var packages = (button.dataset.packages || '').split(',').filter(Boolean);
      if (packages.length) {
        say('Loading ' + packages.join(', ') + '…');
        await pyodide.loadPackage(packages);
      }
      if (packages.indexOf('matplotlib') !== -1) {
        // Figures are collected after each cell runs, so show() has nothing
        // left to do — and on the AGG backend it only warns. Silence it so
        // live output matches the saved output exactly.
        await pyodide.runPythonAsync([
          'import matplotlib',
          'matplotlib.use("AGG")',
          'import matplotlib.pyplot as plt',
          'plt.show = lambda *args, **kwargs: None'
        ].join('\n'));
      }
      await pyodide.runPythonAsync(FIGURE_SHIM);

      cells = Array.prototype.slice
        .call(body.querySelectorAll('.cell-code'))
        .map(makeEditor);

      button.remove();
      say('Python ' + PYODIDE_VERSION + ' ready — edit any cell and run it.');
    } catch (error) {
      button.disabled = false;
      say('Could not start Python: ' + (error.message || error)
        + '. The lesson below still reads normally.');
    }
  }

  button.addEventListener('click', activate);
})();
