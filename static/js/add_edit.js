/**
 * DMTDB - Dynamic add/edit form.
 *
 * Handles:
 *  - Populating Family (FF) dropdown when Domain (TT) changes
 *  - Loading template fields from /ui-api/template_fields
 *  - Showing CC/SS guideline hints
 */
(function () {
  "use strict";

  var ttSel = document.getElementById("ttSel");
  var ffSel = document.getElementById("ffSel");
  var ccHint = document.getElementById("ccHint");
  var ssHint = document.getElementById("ssHint");
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

  function loadTemplate() {
    var tt = ttSel.value;
    var ff = ffSel.value;
    if (!tt || !ff) return;

    fetch("/ui-api/template_fields?tt=" + tt + "&ff=" + ff)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        label.textContent = "(template " + tt + ff + ")";

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

        // CC / SS hints
        if (data.guidelines) {
          var g = data.guidelines;
          var ccText = "", ssText = "";
          if (g.cc) {
            ccText = Object.entries(g.cc)
              .map(function (e) { return e[0] + "=" + e[1]; }).join(", ");
          }
          var ssKey = Object.keys(g).find(function (k) { return k.startsWith("ss"); });
          if (ssKey && g[ssKey]) {
            ssText = Object.entries(g[ssKey])
              .map(function (e) { return e[0] + "=" + e[1]; }).join(", ");
          }
          if (ccHint) ccHint.textContent = ccText ? "Options: " + ccText.substring(0, 250) : "";
          if (ssHint) ssHint.textContent = ssText ? "Options: " + ssText.substring(0, 250) : "";
        }
      });
  }
})();
