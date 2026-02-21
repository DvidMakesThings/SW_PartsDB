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
})();

/**
 * KiCad file drag & drop upload with symbol property editor
 */
(function () {
  "use strict";

  var dropzone = document.getElementById("kicadDropzone");
  var symbolInput = document.getElementById("kicadSymbolInput");
  var footprintInput = document.getElementById("kicadFootprintInput");
  var model3dInput = document.getElementById("kicad3dmodelInput");
  var lcscInput = document.getElementById("lcscPartInput");
  var statusEl = document.getElementById("kicadUploadStatus");

  // Modal elements
  var modal = document.getElementById("symbolEditorModal");
  var propsGrid = document.getElementById("symbolPropsGrid");
  var closeBtn = document.getElementById("symbolEditorClose");
  var cancelBtn = document.getElementById("symbolEditorCancel");
  var saveBtn = document.getElementById("symbolEditorSave");

  if (!dropzone) return;

  // Get DMTUID and part data from page
  var dmtuid = "";
  var match = window.location.pathname.match(/\/part\/([^\/]+)\/edit/);
  if (match) {
    dmtuid = match[1];
  }

  // Part data for auto-fill (from form fields)
  function getPartData() {
    return {
      Value: document.querySelector('input[name="Value"]')?.value ||
        document.querySelector('input[name="MPN"]')?.value || '',
      Footprint: footprintInput?.value || '',
      Datasheet: document.querySelector('input[name="Datasheet"]')?.value || '',
      Description: document.querySelector('textarea[name="Description"]')?.value || '',
      MFR: document.querySelector('input[name="Manufacturer"]')?.value || '',
      MPN: document.querySelector('input[name="MPN"]')?.value || '',
      ROHS: 'YES'
    };
  }

  // Editable symbol properties
  var SYMBOL_PROPS = ['Value', 'Footprint', 'Datasheet', 'Description', 'MFR', 'MPN', 'ROHS', 'LCSC_PART', 'DIST1'];

  var pendingFile = null;
  var pendingFilename = null;

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
    handleFiles(files);
  });

  function handleFiles(files) {
    statusEl.innerHTML = "";

    Array.from(files).forEach(function (file) {
      var ext = file.name.split('.').pop().toLowerCase();

      // For symbols, show the property editor
      if (ext === 'kicad_sym') {
        previewSymbol(file);
      } else {
        // For footprints and 3D models, upload directly
        uploadFile(file);
      }
    });
  }

  function previewSymbol(file) {
    var formData = new FormData();
    formData.append('file', file);
    formData.append('preview', 'true');

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Parsing ' + file.name + '...';
    statusEl.appendChild(statusItem);

    fetch('/api/v1/libs/upload', {
      method: 'POST',
      body: formData
    })
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
    // Look up modal elements dynamically in case they weren't available at init
    var modalEl = modal || document.getElementById("symbolEditorModal");
    var gridEl = propsGrid || document.getElementById("symbolPropsGrid");

    if (!modalEl || !gridEl) {
      console.error('Symbol editor modal elements not found');
      return;
    }

    // Update references
    modal = modalEl;
    propsGrid = gridEl;

    // Ensure event handlers are attached
    attachModalHandlers();

    var partData = getPartData();
    propsGrid.innerHTML = '';

    SYMBOL_PROPS.forEach(function (propName) {
      var existingValue = existingProps[propName] || '';
      var partValue = partData[propName] || '';

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

    modal.style.display = 'flex';
  }

  function hideSymbolEditor() {
    if (modal) modal.style.display = 'none';
    pendingFile = null;
    pendingFilename = null;
  }

  function saveSymbol() {
    if (!pendingFile) return;

    // Collect edited properties
    var props = {};
    var inputs = propsGrid.querySelectorAll('input[data-prop-name]');
    inputs.forEach(function (input) {
      props[input.dataset.propName] = input.value;
    });

    var formData = new FormData();
    formData.append('file', pendingFile);
    formData.append('symbol_props', JSON.stringify(props));
    if (dmtuid) {
      formData.append('dmtuid', dmtuid);
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Saving ' + pendingFile.name + '...';
    statusEl.appendChild(statusItem);

    fetch('/api/v1/libs/upload', {
      method: 'POST',
      body: formData
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          statusItem.className = 'success';
          statusItem.textContent = pendingFile.name + ' saved with properties';

          if (symbolInput) {
            symbolInput.value = data.linked_value || ('DMTDB:' + data.name);
          }

          // Also update footprint field if we set it
          if (props.Footprint && footprintInput && !footprintInput.value) {
            footprintInput.value = props.Footprint;
          }

          // Also update LCSC Part field if we set it
          if (props.LCSC_PART && lcscInput && !lcscInput.value) {
            lcscInput.value = props.LCSC_PART;
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

  function uploadFile(file) {
    var formData = new FormData();
    formData.append('file', file);
    if (dmtuid) {
      formData.append('dmtuid', dmtuid);
    }

    var statusItem = document.createElement('div');
    statusItem.textContent = 'Uploading ' + file.name + '...';
    statusEl.appendChild(statusItem);

    fetch('/api/v1/libs/upload', {
      method: 'POST',
      body: formData
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          statusItem.className = 'success';
          if (data.reused) {
            statusItem.textContent = file.name + ' - using existing ' + data.name;
          } else {
            statusItem.textContent = file.name + ' uploaded to ' + data.type;
          }

          if (data.type === 'footprints' && footprintInput) {
            footprintInput.value = data.linked_value || ('DMTDB:' + data.name);
          }
          if (data.type === '3dmodels' && model3dInput) {
            model3dInput.value = data.name;
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

  // Set up modal event handlers (called once when modal is first shown)
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

  // Part data for auto-fill (from form fields)
  function getPartData() {
    return {
      Value: document.querySelector('input[name="Value"]')?.value ||
        document.querySelector('input[name="MPN"]')?.value || '',
      Footprint: footprintInput?.value || '',
      Datasheet: document.querySelector('input[name="Datasheet"]')?.value || '',
      Description: document.querySelector('textarea[name="Description"]')?.value || '',
      MFR: document.querySelector('input[name="Manufacturer"]')?.value || '',
      MPN: document.querySelector('input[name="MPN"]')?.value || '',
      ROHS: 'YES'
    };
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

      if (footprintSelect && libs.footprints) {
        libs.footprints.forEach(function (fp) {
          var opt = document.createElement('option');
          opt.value = fp.filename;
          opt.textContent = fp.name;
          footprintSelect.appendChild(opt);
        });
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