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
