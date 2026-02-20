/**
 * DMTDB - Live search with barcode-scanner support.
 *
 * Behaviour:
 *  - Typing fires debounced AJAX search (120 ms)
 *  - Arrow keys navigate dropdown
 *  - Enter:
 *      1. If an item is highlighted → open it
 *      2. If exactly one result → open it
 *      3. If exact DMTUID match → open it
 *      4. If results exist → open top result
 *      5. Else → submit the search form
 *  - Escape closes dropdown
 */
(function () {
  "use strict";

  var input = document.getElementById("searchInput");
  var dropdown = document.getElementById("searchDropdown");
  var form = document.getElementById("searchForm");
  if (!input || !dropdown || !form) return;

  var debounce = null;
  var selectedIdx = -1;
  var items = [];

  function render(results) {
    items = results;
    selectedIdx = -1;
    if (!results.length) { dropdown.classList.remove("show"); return; }

    dropdown.innerHTML = results.map(function (r, i) {
      return '<div class="sd-item" data-idx="' + i + '" data-uid="' + r.dmtuid + '">'
        + '<span class="sd-uid">' + r.dmtuid + '</span>'
        + '<span class="sd-mpn">' + (r.mpn || '') + '</span>'
        + '<span class="sd-desc">' + (r.description || r.value || '') + '</span>'
        + '<span class="sd-qty">' + (r.quantity || '') + '</span>'
        + '</div>';
    }).join("");
    dropdown.classList.add("show");

    dropdown.querySelectorAll(".sd-item").forEach(function (el) {
      el.addEventListener("mousedown", function (e) {
        e.preventDefault();
        window.location.href = "/part/" + el.dataset.uid;
      });
    });
  }

  function highlight(idx) {
    dropdown.querySelectorAll(".sd-item").forEach(function (el, i) {
      el.classList.toggle("selected", i === idx);
    });
    selectedIdx = idx;
  }

  input.addEventListener("input", function () {
    clearTimeout(debounce);
    var q = input.value.trim();
    if (!q) { dropdown.classList.remove("show"); return; }
    debounce = setTimeout(function () {
      fetch("/ui-api/search?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(render);
    }, 120);
  });

  input.addEventListener("keydown", function (e) {
    if (!dropdown.classList.contains("show") && e.key !== "Enter") return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      highlight(Math.min(selectedIdx + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      highlight(Math.max(selectedIdx - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIdx >= 0 && items[selectedIdx]) {
        window.location.href = "/part/" + items[selectedIdx].dmtuid;
      } else if (items.length === 1) {
        window.location.href = "/part/" + items[0].dmtuid;
      } else {
        var q = input.value.trim().toUpperCase();
        var exact = items.find(function (r) { return r.dmtuid === q; });
        if (exact) {
          window.location.href = "/part/" + exact.dmtuid;
        } else if (items.length > 0) {
          window.location.href = "/part/" + items[0].dmtuid;
        } else {
          form.submit();
        }
      }
    } else if (e.key === "Escape") {
      dropdown.classList.remove("show");
    }
  });

  input.addEventListener("blur", function () {
    setTimeout(function () { dropdown.classList.remove("show"); }, 200);
  });
  input.addEventListener("focus", function () {
    if (items.length && input.value.trim()) dropdown.classList.add("show");
  });
})();
