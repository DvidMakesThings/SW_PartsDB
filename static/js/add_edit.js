/**
 * DMTDB - Dynamic add/edit form.
 *
 * Handles:
 *  - Populating Family (FF) dropdown when Domain (TT) changes
 *  - Populating CC/SS dropdowns from schema guidelines
 *  - Loading template fields from /ui-api/template_fields
 */
(function () {
  "use strict";

  var ttSel = document.getElementById("ttSel");
  var ffSel = document.getElementById("ffSel");
  var ccSel = document.getElementById("ccSel");
  var ssSel = document.getElementById("ssSel");
  var container = document.getElementById("templateFields");
  var label = document.getElementById("templateLabel");

  if (!ttSel) return;  // edit mode has no selectors

  // domainsData is embedded in the page by the template
  var domains = window.domainsData || [];
  var SKIP = new Set([
    "MPN", "Location", "Quantity", "Value", "Manufacturer",
    "Description", "Datasheet", "RoHS", "TT", "FF", "CC", "SS", "XXX", "DMTUID"
  ]);

  ttSel.addEventListener("change", function () {
    var tt = ttSel.value;
    ffSel.innerHTML = '<option value="">Select family…</option>';
    clearCCSS();
    var dom = domains.find(function (d) { return d.tt === tt; });
    if (dom) {
      dom.families.forEach(function (f) {
        var o = document.createElement("option");
        o.value = f.ff;
        o.textContent = f.ff + " - " + f.name;
        ffSel.appendChild(o);
      });
    }
    loadTemplate();
  });

  ffSel.addEventListener("change", loadTemplate);

  function clearCCSS() {
    if (ccSel) ccSel.innerHTML = '<option value="">Select class…</option>';
    if (ssSel) ssSel.innerHTML = '<option value="">Select style…</option>';
  }

  function populateSelect(sel, data, defaultText) {
    sel.innerHTML = '<option value="">' + defaultText + '</option>';
    if (data && typeof data === 'object') {
      Object.entries(data).forEach(function (e) {
        var o = document.createElement("option");
        o.value = e[0].padStart(2, '0');
        o.textContent = e[0].padStart(2, '0') + " - " + e[1];
        sel.appendChild(o);
      });
    }
    // Always add a "Custom" option for manual entry
    var custom = document.createElement("option");
    custom.value = "__custom__";
    custom.textContent = "Other (enter manually)";
    sel.appendChild(custom);
  }

  function setupCustomInput(sel, name) {
    sel.addEventListener("change", function () {
      var existing = sel.parentNode.querySelector(".custom-input");
      if (sel.value === "__custom__") {
        if (!existing) {
          var inp = document.createElement("input");
          inp.type = "text";
          inp.name = name;
          inp.className = "custom-input";
          inp.placeholder = "00-99";
          inp.pattern = "\\d{1,2}";
          inp.maxLength = 2;
          inp.required = true;
          inp.style.marginTop = "0.5rem";
          sel.parentNode.appendChild(inp);
          sel.name = "";  // disable select's name
        }
      } else {
        if (existing) {
          existing.remove();
          sel.name = name;  // restore select's name
        }
      }
    });
  }

  if (ccSel) setupCustomInput(ccSel, "cc");
  if (ssSel) setupCustomInput(ssSel, "ss");

  function loadTemplate() {
    var tt = ttSel.value;
    var ff = ffSel.value;
    clearCCSS();
    if (!tt || !ff) return;

    fetch("/ui-api/template_fields?tt=" + tt + "&ff=" + ff)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        label.textContent = "(template " + tt + ff + ")";

        // Populate CC dropdown
        if (data.guidelines && data.guidelines.cc) {
          populateSelect(ccSel, data.guidelines.cc, "Select class…");
        } else {
          populateSelect(ccSel, {}, "Select class…");
        }

        // Populate SS dropdown - find the ss key (ss, ss_vendor, ss_vendor_families, etc.)
        var ssData = null;
        if (data.guidelines) {
          var ssKey = Object.keys(data.guidelines).find(function (k) {
            return k.startsWith("ss");
          });
          if (ssKey) ssData = data.guidelines[ssKey];
        }
        populateSelect(ssSel, ssData, "Select style…");

        if (!data.fields) {
          container.innerHTML =
            '<p style="color:var(--text-dim); font-size:.85rem;">'
            + "No template for this family. Extra fields stored as JSON.</p>";
          return;
        }

        var html = "";
        data.fields.forEach(function (f) {
          if (SKIP.has(f)) return;
          html += '<div class="form-group"><label>' + f
            + '</label><input type="text" name="' + f + '"></div>';
        });
        container.innerHTML = html
          || '<p style="color:var(--text-dim);">No additional template fields.</p>';
      });
  }

  // Pre-select from template part if provided (Use as Template feature)
  if (window.templatePartData) {
    var tpl = window.templatePartData;
    if (tpl.tt) {
      ttSel.value = tpl.tt;
      // Trigger change to populate FF dropdown
      var evt = new Event("change");
      ttSel.dispatchEvent(evt);
      // Wait a tick for FF options to populate, then select FF
      setTimeout(function () {
        if (tpl.ff) {
          ffSel.value = tpl.ff;
          ffSel.dispatchEvent(new Event("change"));
          // Wait for CC/SS to populate, then select them
          setTimeout(function () {
            if (tpl.cc && ccSel) ccSel.value = tpl.cc;
            if (tpl.ss && ssSel) ssSel.value = tpl.ss;
          }, 100);
        }
      }, 10);
    }
  }
})();

/**
 * KiCad file drag & drop upload with symbol property editor
 * 
 * In ADD mode (no dmtuid): Files are staged in memory until form submission
 * In EDIT mode (has dmtuid): Files are uploaded directly
 */
(function () {
  "use strict";

  var dropzone = document.getElementById("kicadDropzone");
  var symbolInput = document.getElementById("kicadSymbolInput");
  var footprintInput = document.getElementById("kicadFootprintInput");
  var model3dInput = document.getElementById("kicad3dmodelInput");
  var lcscInput = document.getElementById("lcscPartInput");
  var statusEl = document.getElementById("kicadUploadStatus");
  var stagingSessionInput = document.getElementById("stagingSessionId");

  // Modal elements
  var modal = document.getElementById("symbolEditorModal");
  var propsGrid = document.getElementById("symbolPropsGrid");
  var closeBtn = document.getElementById("symbolEditorClose");
  var cancelBtn = document.getElementById("symbolEditorCancel");
  var saveBtn = document.getElementById("symbolEditorSave");

  if (!dropzone) return;

  // Get DMTUID from page (edit mode only)
  var dmtuid = "";
  var match = window.location.pathname.match(/\/part\/([^\/]+)\/edit/);
  if (match) {
    dmtuid = match[1];
  }

  // Staging mode: true for ADD (no dmtuid), false for EDIT (has dmtuid)
  var useStaging = !dmtuid;
  var stagingSessionId = null;

  // Get TT/FF from form dropdowns
  function getTTFF() {
    var ttSel = document.getElementById("ttSel");
    var ffSel = document.getElementById("ffSel");
    return {
      tt: ttSel ? ttSel.value : "",
      ff: ffSel ? ffSel.value : ""
    };
  }

  // Part data for auto-fill (from form fields)
  function getPartData() {
    var rohsSelect = document.querySelector('select[name="RoHS"]');
    var rohsVal = rohsSelect ? (rohsSelect.value === 'No' ? 'NO' : 'YES') : 'YES';
    return {
      Value: document.querySelector('input[name="Value"]')?.value ||
        document.querySelector('input[name="MPN"]')?.value || '',
      Footprint: footprintInput?.value || '',
      Datasheet: document.querySelector('input[name="Datasheet"]')?.value || '',
      Description: document.querySelector('textarea[name="Description"]')?.value || '',
      MFR: document.querySelector('input[name="Manufacturer"]')?.value || '',
      MPN: document.querySelector('input[name="MPN"]')?.value || '',
      ROHS: rohsVal
    };
  }

  // Editable symbol properties
  var SYMBOL_PROPS = ['Value', 'Footprint', 'Datasheet', 'Description', 'MFR', 'MPN', 'ROHS', 'LCSC_PART', 'DIST1'];
  var NO_INHERIT_PROPS = ['LCSC_PART', 'DIST1'];

  var pendingFile = null;
  var pendingFilename = null;

  // Create staging session (called once on first file drop in add mode)
  function ensureStagingSession(callback) {
    if (!useStaging) {
      callback();
      return;
    }
    if (stagingSessionId) {
      callback();
      return;
    }

    fetch('/api/v1/libs/stage/session', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.session_id) {
          stagingSessionId = data.session_id;
          if (stagingSessionInput) {
            stagingSessionInput.value = stagingSessionId;
          }
        }
        callback();
      })
      .catch(function (err) {
        console.error('Failed to create staging session:', err);
        callback();
      });
  }

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      e.stopPropagation();
    });
  });

  dropzone.addEventListener('dragenter', function () { dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragover', function () { dropzone.classList.add('dragover'); });
  dropzone.addEventListener('dragleave', function () { dropzone.classList.remove('dragover'); });

  dropzone.addEventListener('drop', function (e) {
    dropzone.classList.remove('dragover');
    var files = e.dataTransfer.files;
    ensureStagingSession(function () {
      handleFiles(files);
    });
  });

  function handleFiles(files) {
    statusEl.innerHTML = "";

    // Separate files by type
    var symbols = [];
    var footprints = [];
    var models = [];

    Array.from(files).forEach(function (file) {
      var ext = file.name.split('.').pop().toLowerCase();
      if (ext === 'kicad_sym') {
        symbols.push(file);
      } else if (ext === 'kicad_mod') {
        footprints.push(file);
      } else if (['step', 'stp', 'wrl'].indexOf(ext) >= 0) {
        models.push(file);
      }
    });

    // Upload/stage models first, then footprints, then symbols
    var modelFilename = models.length === 1 ? models[0].name : null;

    models.forEach(function (file) { processFile(file, '3dmodel', null); });
    footprints.forEach(function (file) { processFile(file, 'footprint', modelFilename); });
    symbols.forEach(function (file) { previewSymbol(file); });
  }

  function previewSymbol(file) {
    var formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');

    // Use staging endpoint in add mode
    var endpoint = useStaging && stagingSessionId
      ? '/api/v1/libs/stage'
      : '/api/v1/libs/upload';

    if (useStaging && stagingSessionId) {
      formData.append('session_id', stagingSessionId);
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Parsing ' + file.name + '...';
    statusEl.appendChild(statusItem);

    fetch(endpoint, { method: 'POST', body: formData })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.preview) {
          statusItem.textContent = file.name + ' - edit properties below';
          pendingFile = file;
          pendingFilename = data.filename;
          showSymbolEditor(data.properties);
        } else if (data.error) {
          statusItem.className = 'error';
          statusItem.textContent = file.name + ' failed: ' + data.error;
        }
      })
      .catch(function (err) {
        statusItem.className = 'error';
        statusItem.textContent = file.name + ' error: ' + err;
      });
  }

  function showSymbolEditor(existingProps) {
    var modalEl = modal || document.getElementById("symbolEditorModal");
    var gridEl = propsGrid || document.getElementById("symbolPropsGrid");

    if (!modalEl || !gridEl) {
      console.error('Symbol editor modal elements not found');
      return;
    }

    modal = modalEl;
    propsGrid = gridEl;
    attachModalHandlers();

    var partData = getPartData();
    propsGrid.innerHTML = '';

    SYMBOL_PROPS.forEach(function (propName) {
      var existingValue = existingProps[propName] || '';
      var partValue = partData[propName] || '';

      if (NO_INHERIT_PROPS.indexOf(propName) >= 0 && !partValue) {
        existingValue = '';
      }

      var value = partValue || existingValue;
      var autoFilled = partValue && !existingValue;

      var row = document.createElement('div');
      row.className = 'symbol-prop-row';

      var label = document.createElement('label');
      label.textContent = propName;

      var input = document.createElement('input');
      input.type = 'text';
      input.name = 'symbol_' + propName;
      input.value = value;
      input.dataset.propName = propName;
      if (autoFilled) {
        input.className = 'auto-filled';
        input.title = 'Auto-filled from part data';
      }

      row.appendChild(label);
      row.appendChild(input);
      propsGrid.appendChild(row);
    });

    modal.style.display = 'flex';
  }

  function hideSymbolEditor() {
    if (modal) modal.style.display = 'none';
    pendingFile = null;
    pendingFilename = null;
  }

  function saveSymbol() {
    if (!pendingFile) return;

    var props = {};
    var inputs = propsGrid.querySelectorAll('input[data-prop-name]');
    inputs.forEach(function (input) {
      props[input.dataset.propName] = input.value;
    });

    var formData = new FormData();
    formData.append('file', pendingFile);
    formData.append('symbol_props', JSON.stringify(props));

    var endpoint, statusMsg;

    if (useStaging && stagingSessionId) {
      // ADD mode: stage the file
      endpoint = '/api/v1/libs/stage';
      formData.append('session_id', stagingSessionId);
      statusMsg = 'staged';
    } else {
      // EDIT mode: upload directly
      endpoint = '/api/v1/libs/upload';
      if (dmtuid) formData.append('dmtuid', dmtuid);
      var ttff = getTTFF();
      if (ttff.tt) formData.append('tt', ttff.tt);
      if (ttff.ff) formData.append('ff', ttff.ff);
      statusMsg = 'saved';
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Processing ' + pendingFile.name + '...';
    statusEl.appendChild(statusItem);

    fetch(endpoint, { method: 'POST', body: formData })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success || data.staged) {
          statusItem.className = 'success';
          statusItem.textContent = pendingFile.name + ' ' + statusMsg;

          // Update symbol field with expected reference
          if (symbolInput) {
            if (data.linked_value) {
              symbolInput.value = data.linked_value;
            } else if (useStaging) {
              // In staging mode, set a placeholder that will be resolved on submit
              symbolInput.value = '(staged: ' + pendingFile.name + ')';
            }
          }

          if (props.Footprint && footprintInput && !footprintInput.value) {
            footprintInput.value = props.Footprint;
          }
          if (props.LCSC_PART && lcscInput && !lcscInput.value) {
            lcscInput.value = props.LCSC_PART;
          }

          // Store symbol props for later use
          if (useStaging && stagingSessionId) {
            fetch('/api/v1/libs/stage/' + stagingSessionId + '/props', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ symbol_props: props })
            });
          }
        } else {
          statusItem.className = 'error';
          statusItem.textContent = pendingFile.name + ' failed: ' + data.error;
        }
        hideSymbolEditor();
      })
      .catch(function (err) {
        statusItem.className = 'error';
        statusItem.textContent = pendingFile.name + ' error: ' + err;
        hideSymbolEditor();
      });
  }

  function processFile(file, fileType, modelFilename) {
    var formData = new FormData();
    formData.append('file', file);

    var endpoint, statusMsg;

    if (useStaging && stagingSessionId) {
      // ADD mode: stage
      endpoint = '/api/v1/libs/stage';
      formData.append('session_id', stagingSessionId);
      statusMsg = 'staged';
    } else {
      // EDIT mode: upload directly
      endpoint = '/api/v1/libs/upload';
      if (dmtuid) formData.append('dmtuid', dmtuid);
      if (modelFilename) formData.append('model_filename', modelFilename);
      statusMsg = 'uploaded';
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Processing ' + file.name + '...';
    statusEl.appendChild(statusItem);

    fetch(endpoint, { method: 'POST', body: formData })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success || data.staged) {
          statusItem.className = 'success';
          if (data.reused) {
            statusItem.textContent = file.name + ' - using existing';
          } else {
            statusItem.textContent = file.name + ' ' + statusMsg;
          }

          // Update form fields
          if (fileType === 'footprint' && footprintInput) {
            if (data.linked_value) {
              footprintInput.value = data.linked_value;
            } else if (useStaging) {
              footprintInput.value = 'DMTDB:' + file.name.replace('.kicad_mod', '');
            }
          }
          if (fileType === '3dmodel' && model3dInput) {
            model3dInput.value = data.name || file.name;
          }
        } else {
          statusItem.className = 'error';
          statusItem.textContent = file.name + ' failed: ' + data.error;
        }
      })
      .catch(function (err) {
        statusItem.className = 'error';
        statusItem.textContent = file.name + ' error: ' + err;
      });
  }

  var handlersAttached = false;
  function attachModalHandlers() {
    if (handlersAttached) return;

    var closeBtnEl = document.getElementById("symbolEditorClose");
    var cancelBtnEl = document.getElementById("symbolEditorCancel");
    var saveBtnEl = document.getElementById("symbolEditorSave");
    var modalEl = document.getElementById("symbolEditorModal");

    if (closeBtnEl) closeBtnEl.addEventListener('click', hideSymbolEditor);
    if (cancelBtnEl) cancelBtnEl.addEventListener('click', hideSymbolEditor);
    if (saveBtnEl) saveBtnEl.addEventListener('click', saveSymbol);

    if (modalEl) {
      modalEl.addEventListener('click', function (e) {
        if (e.target === modalEl) hideSymbolEditor();
      });
    }

    handlersAttached = true;
  }

  // Try to attach handlers now, will retry when modal is shown
  attachModalHandlers();
})();

/**
 * KiCad library selector dropdowns - select from existing files
 */
(function () {
  "use strict";

  var symbolSelect = document.getElementById("symbolSelect");
  var footprintSelect = document.getElementById("footprintSelect");
  var model3dSelect = document.getElementById("model3dSelect");

  var symbolInput = document.getElementById("kicadSymbolInput");
  var footprintInput = document.getElementById("kicadFootprintInput");

  // TT/FF selectors for footprint filtering
  var ttSel = document.getElementById("ttSel");
  var ffSel = document.getElementById("ffSel");

  // Store all footprints for filtering
  var allFootprints = [];

  // Footprint prefixes by component type (TT-FF)
  var FOOTPRINT_PREFIX_MAP = {
    '01-01': 'C_',   // Capacitors
    '01-02': 'R_',   // Resistors
    '01-03': 'L_',   // Inductors
  };
  var model3dInput = document.getElementById("kicad3dmodelInput");

  var statusEl = document.getElementById("kicadUploadStatus");
  var modal = document.getElementById("symbolEditorModal");
  var propsGrid = document.getElementById("symbolPropsGrid");

  if (!symbolSelect && !footprintSelect && !model3dSelect) return;

  // Get DMTUID from page
  var dmtuid = "";
  var match = window.location.pathname.match(/\/part\/([^\/]+)\/edit/);
  if (match) {
    dmtuid = match[1];
  }

  // Editable symbol properties
  var SYMBOL_PROPS = ['Value', 'Footprint', 'Datasheet', 'Description', 'MFR', 'MPN', 'ROHS', 'LCSC_PART', 'DIST1'];

  // Properties that should NOT inherit from template symbol (part-specific values)
  var NO_INHERIT_PROPS = ['LCSC_PART', 'DIST1'];

  // Part data for auto-fill (from form fields)
  function getPartData() {
    var rohsSelect = document.querySelector('select[name="RoHS"]');
    var rohsVal = rohsSelect ? (rohsSelect.value === 'No' ? 'NO' : 'YES') : 'YES';
    return {
      Value: document.querySelector('input[name="Value"]')?.value ||
        document.querySelector('input[name="MPN"]')?.value || '',
      Footprint: footprintInput?.value || '',
      Datasheet: document.querySelector('input[name="Datasheet"]')?.value || '',
      Description: document.querySelector('textarea[name="Description"]')?.value || '',
      MFR: document.querySelector('input[name="Manufacturer"]')?.value || '',
      MPN: document.querySelector('input[name="MPN"]')?.value || '',
      ROHS: rohsVal
    };
  }

  // Function to filter and populate footprint dropdown based on TT/FF
  function updateFootprintOptions() {
    if (!footprintSelect) return;

    var tt = ttSel ? ttSel.value : '';
    var ff = ffSel ? ffSel.value : '';
    var key = tt + '-' + ff;
    var prefix = FOOTPRINT_PREFIX_MAP[key] || '';

    // Clear existing options (except default)
    footprintSelect.innerHTML = '<option value="">-- Select existing --</option>';

    // Filter footprints by prefix if we have one, otherwise show all
    var filtered = allFootprints;
    if (prefix) {
      filtered = allFootprints.filter(function (fp) {
        return fp.name.startsWith(prefix.replace('_', ''));
      });
    }

    filtered.forEach(function (fp) {
      var opt = document.createElement('option');
      opt.value = fp.filename;
      opt.textContent = fp.name;
      footprintSelect.appendChild(opt);
    });
  }

  // Listen for TT/FF changes to update footprint options
  if (ttSel) {
    ttSel.addEventListener('change', updateFootprintOptions);
  }
  if (ffSel) {
    ffSel.addEventListener('change', updateFootprintOptions);
  }

  // Fetch and populate library dropdowns
  fetch('/api/v1/libs')
    .then(function (r) { return r.json(); })
    .then(function (libs) {
      if (symbolSelect && libs.symbols) {
        libs.symbols.forEach(function (sym) {
          var opt = document.createElement('option');
          opt.value = sym.filename;
          opt.textContent = sym.name;
          opt.dataset.url = sym.url;
          symbolSelect.appendChild(opt);
        });
      }

      if (libs.footprints) {
        // Store all footprints for filtering
        allFootprints = libs.footprints;
        // Initial population (will filter if TT/FF already selected)
        updateFootprintOptions();
      }

      if (model3dSelect && libs['3dmodels']) {
        libs['3dmodels'].forEach(function (m) {
          var opt = document.createElement('option');
          opt.value = m.filename;
          opt.textContent = m.name;
          model3dSelect.appendChild(opt);
        });
      }
    })
    .catch(function (err) {
      console.error('Failed to load library list:', err);
    });

  // Footprint selector - direct selection
  if (footprintSelect) {
    footprintSelect.addEventListener('change', function () {
      var val = footprintSelect.value;
      if (val && footprintInput) {
        var name = val.replace('.kicad_mod', '');
        footprintInput.value = 'DMTDB:' + name;

        // Also update part record if we have dmtuid
        if (dmtuid) {
          linkExistingFile('footprints', val);
        }
      }
      footprintSelect.value = '';  // reset dropdown
    });
  }

  // 3D Model selector - direct selection
  if (model3dSelect) {
    model3dSelect.addEventListener('change', function () {
      var val = model3dSelect.value;
      if (val && model3dInput) {
        model3dInput.value = val;

        // Also update part record if we have dmtuid
        if (dmtuid) {
          linkExistingFile('3dmodels', val);
        }
      }
      model3dSelect.value = '';  // reset dropdown
    });
  }

  // Helper to link existing file to part
  function linkExistingFile(type, filename) {
    var fd = new FormData();
    fd.append('dmtuid', dmtuid);
    fd.append('filename', filename);
    fd.append('type', type);

    fetch('/api/v1/libs/link', {
      method: 'POST',
      body: fd
    }).catch(function (err) {
      console.error('Failed to link file:', err);
    });
  }

  // Symbol selector - copy and edit properties
  if (symbolSelect) {
    symbolSelect.addEventListener('change', function () {
      var selected = symbolSelect.options[symbolSelect.selectedIndex];
      var filename = selected.value;
      var url = selected.dataset.url;

      if (!filename || !url) {
        symbolSelect.value = '';
        return;
      }

      // Fetch the existing symbol file to copy
      fetch(url)
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          var file = new File([blob], filename, { type: 'application/octet-stream' });

          // Preview to get properties, then show editor
          var formData = new FormData();
          formData.append('file', file);
          formData.append('preview', 'true');

          return fetch('/api/v1/libs/upload', {
            method: 'POST',
            body: formData
          });
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.preview) {
            showSymbolEditor(data.properties, filename);
          }
        })
        .catch(function (err) {
          console.error('Failed to load symbol:', err);
        });

      symbolSelect.value = '';  // reset dropdown
    });
  }

  // Pending symbol data for the editor
  var pendingSymbolFile = null;
  var pendingSymbolFilename = null;

  function showSymbolEditor(existingProps, originalFilename) {
    modal = modal || document.getElementById("symbolEditorModal");
    propsGrid = propsGrid || document.getElementById("symbolPropsGrid");

    if (!modal || !propsGrid) {
      console.error('Symbol editor modal not found');
      return;
    }

    var partData = getPartData();
    propsGrid.innerHTML = '';

    SYMBOL_PROPS.forEach(function (propName) {
      var existingValue = existingProps[propName] || '';
      var partValue = partData[propName] || '';

      // For part-specific properties, clear template values (don't inherit)
      if (NO_INHERIT_PROPS.indexOf(propName) >= 0 && !partValue) {
        existingValue = '';
      }

      // Use part data if available, otherwise existing symbol value
      var value = partValue || existingValue;
      var autoFilled = partValue && !existingValue;

      var row = document.createElement('div');
      row.className = 'symbol-prop-row';

      var label = document.createElement('label');
      label.textContent = propName;

      var input = document.createElement('input');
      input.type = 'text';
      input.name = 'symbol_' + propName;
      input.value = value;
      input.dataset.propName = propName;
      if (autoFilled) {
        input.className = 'auto-filled';
        input.title = 'Auto-filled from part data';
      }

      row.appendChild(label);
      row.appendChild(input);
      propsGrid.appendChild(row);
    });

    // Store for save
    pendingSymbolFilename = originalFilename;

    // Fetch the file content for saving later
    var opt = symbolSelect.querySelector('option[value="' + originalFilename + '"]');
    if (opt && opt.dataset.url) {
      fetch(opt.dataset.url)
        .then(function (r) { return r.blob(); })
        .then(function (blob) {
          pendingSymbolFile = new File([blob], originalFilename, { type: 'application/octet-stream' });
        });
    }

    modal.style.display = 'flex';

    // Override save button for this flow
    var saveBtn = document.getElementById("symbolEditorSave");
    if (saveBtn) {
      saveBtn.onclick = function () {
        saveSymbolFromSelector();
      };
    }
  }

  function saveSymbolFromSelector() {
    if (!pendingSymbolFile) {
      console.error('No pending symbol file');
      return;
    }

    // Collect edited properties
    var props = {};
    var inputs = propsGrid.querySelectorAll('input[data-prop-name]');
    inputs.forEach(function (input) {
      props[input.dataset.propName] = input.value;
    });

    var formData = new FormData();
    formData.append('file', pendingSymbolFile);
    formData.append('symbol_props', JSON.stringify(props));
    if (dmtuid) {
      formData.append('dmtuid', dmtuid);
    } else {
      // In add mode, send TT/FF directly for library file routing
      var ttSel = document.getElementById("ttSel");
      var ffSel = document.getElementById("ffSel");
      if (ttSel && ttSel.value) formData.append('tt', ttSel.value);
      if (ffSel && ffSel.value) formData.append('ff', ffSel.value);
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Creating symbol from ' + pendingSymbolFilename + '...';
    statusEl.appendChild(statusItem);

    fetch('/api/v1/libs/upload', {
      method: 'POST',
      body: formData
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          statusItem.className = 'success';
          statusItem.textContent = 'Created ' + data.filename;

          if (symbolInput) {
            symbolInput.value = data.linked_value || ('DMTDB:' + data.name);
          }

          // Also update footprint field if we set it
          if (props.Footprint && footprintInput && !footprintInput.value) {
            footprintInput.value = props.Footprint;
          }

          // Also update LCSC Part field
          var lcscInput = document.getElementById('lcscPartInput');
          if (props.LCSC_PART && lcscInput && !lcscInput.value) {
            lcscInput.value = props.LCSC_PART;
          }
        } else {
          statusItem.className = 'error';
          statusItem.textContent = 'Failed: ' + data.error;
        }

        modal.style.display = 'none';
        pendingSymbolFile = null;
        pendingSymbolFilename = null;
      })
      .catch(function (err) {
        statusItem.className = 'error';
        statusItem.textContent = 'Error: ' + err;
        modal.style.display = 'none';
      });
  }
})();

/**
 * Dynamic Distributor Fields
 * Allows adding/removing multiple distributor entries
 */
(function () {
  "use strict";

  var container = document.getElementById("distributorsContainer");
  var addBtn = document.getElementById("addDistributorBtn");
  var countInput = document.getElementById("distributorCount");

  if (!container || !addBtn) return;

  var nextIndex = parseInt(countInput.value, 10) || 0;

  function createDistributorRow(index) {
    var row = document.createElement("div");
    row.className = "distributor-row";
    row.dataset.index = index;
    row.innerHTML =
      '<div class="form-grid" style="grid-template-columns: 1fr 2fr auto; align-items: end;">' +
      '  <div class="form-group">' +
      '    <label>Name</label>' +
      '    <input type="text" name="dist_name_' + index + '" placeholder="DigiKey, Mouser, etc.">' +
      '  </div>' +
      '  <div class="form-group">' +
      '    <label>URL</label>' +
      '    <input type="text" name="dist_url_' + index + '" placeholder="https://...">' +
      '  </div>' +
      '  <button type="button" class="btn btn-danger btn-sm remove-distributor" title="Remove distributor">🗑</button>' +
      '</div>';
    return row;
  }

  addBtn.addEventListener("click", function () {
    var row = createDistributorRow(nextIndex);
    container.appendChild(row);
    nextIndex++;
    countInput.value = nextIndex;
  });

  container.addEventListener("click", function (e) {
    if (e.target.classList.contains("remove-distributor")) {
      var row = e.target.closest(".distributor-row");
      if (row) {
        row.remove();
      }
    }
  });
})();