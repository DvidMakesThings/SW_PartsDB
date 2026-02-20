/**
 * DMTDB - Advanced Search with DigiKey-style Faceted Filters
 *
 * Handles:
 *  - Toggle advanced search panel
 *  - Populate TT/FF/CC/SS category dropdowns
 *  - Load and display faceted property filters
 *  - Checkbox-based value selection for each property
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        init();
    });

    function init() {
        var toggle = document.getElementById("advSearchToggle");
        var panel = document.getElementById("advSearchPanel");
        var ttSelect = document.getElementById("ttSelect");
        var ttAdvSelect = document.getElementById("ttAdvSelect");
        var ffSelect = document.getElementById("ffSelect");
        var ccSelect = document.getElementById("ccSelect");
        var ssSelect = document.getElementById("ssSelect");
        var facetGrid = document.getElementById("facetGrid");
        var facetCount = document.getElementById("facetCount");
        var propsInput = document.getElementById("propsInput");
        var clearBtn = document.getElementById("clearFilters");
        var form = document.getElementById("searchForm");

        var domains = window.domainsData || [];
        var currentFilters = window.currentFilters || {};
        var selectedProps = {}; // {fieldName: [value1, value2, ...]}

        // Parse existing props from URL
        if (currentFilters.props && typeof currentFilters.props === "object") {
            selectedProps = currentFilters.props;
        }

        console.log("Advanced Search init:", { domains: domains.length });

        // ── Toggle panel visibility ─────────────────────────────────────
        if (toggle && panel) {
            toggle.addEventListener("click", function () {
                panel.classList.toggle("show");
                var isOpen = panel.classList.contains("show");
                toggle.textContent = isOpen ? "▲ Advanced" : "▼ Advanced";

                // Hide/show main TT dropdown
                if (ttSelect) {
                    ttSelect.style.display = isOpen ? "none" : "";
                }

                // Sync and load on open
                if (isOpen && ttAdvSelect && ttSelect) {
                    ttAdvSelect.value = ttSelect.value;
                    if (ttAdvSelect.value) {
                        populateFamilies(ttAdvSelect.value);
                        loadFacets();
                    }
                }
            });

            // Auto-show if filters active
            if (currentFilters.ff || currentFilters.cc || currentFilters.ss ||
                (currentFilters.props && Object.keys(currentFilters.props).length > 0)) {
                panel.classList.add("show");
                toggle.textContent = "▲ Advanced";
                if (ttSelect) ttSelect.style.display = "none";
            }
        }

        // ── TT change (advanced panel) ──────────────────────────────────
        if (ttAdvSelect) {
            ttAdvSelect.addEventListener("change", function () {
                if (ttSelect) ttSelect.value = ttAdvSelect.value;
                populateFamilies(ttAdvSelect.value);
                clearCCSS();
                clearFacets();
                if (ttAdvSelect.value) {
                    loadFacets();
                }
            });
        }

        // ── TT change (main dropdown) ───────────────────────────────────
        if (ttSelect) {
            ttSelect.addEventListener("change", function () {
                if (ttAdvSelect) ttAdvSelect.value = ttSelect.value;
                populateFamilies(ttSelect.value);
                clearCCSS();
                clearFacets();
            });
        }

        // ── FF change ───────────────────────────────────────────────────
        if (ffSelect) {
            ffSelect.addEventListener("change", function () {
                var tt = ttAdvSelect ? ttAdvSelect.value : ttSelect.value;
                if (tt && ffSelect.value) {
                    loadCCSS(tt, ffSelect.value);
                } else {
                    clearCCSS();
                }
                loadFacets();
            });
        }

        // ── CC/SS change ────────────────────────────────────────────────
        if (ccSelect) {
            ccSelect.addEventListener("change", function () {
                loadFacets();
            });
        }
        if (ssSelect) {
            ssSelect.addEventListener("change", function () {
                loadFacets();
            });
        }

        // ── Clear all filters ───────────────────────────────────────────
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                if (ffSelect) ffSelect.value = "";
                clearCCSS();
                clearFacets();
                selectedProps = {};
                if (propsInput) propsInput.value = "";
            });
        }

        // ── Form submit - serialize selections ──────────────────────────
        if (form) {
            form.addEventListener("submit", function () {
                serializeProps();
            });
        }

        // ── Initialize on load ──────────────────────────────────────────
        if (currentFilters.tt) {
            populateFamilies(currentFilters.tt);
            if (currentFilters.ff) {
                ffSelect.value = currentFilters.ff;
                loadCCSS(currentFilters.tt, currentFilters.ff);
            }
            // Load facets if panel should be open
            if (panel && panel.classList.contains("show")) {
                loadFacets();
            }
        }

        // ────────────────────────────────────────────────────────────────
        // FUNCTIONS
        // ────────────────────────────────────────────────────────────────

        function populateFamilies(tt) {
            if (!ffSelect) return;
            ffSelect.innerHTML = '<option value="">All Families</option>';
            var dom = domains.find(function (d) { return d.tt === tt; });
            if (dom && dom.families) {
                dom.families.forEach(function (f) {
                    var o = document.createElement("option");
                    o.value = f.ff;
                    o.textContent = f.ff + " - " + f.name;
                    ffSelect.appendChild(o);
                });
            }
        }

        function clearCCSS() {
            if (ccSelect) ccSelect.innerHTML = '<option value="">All Classes</option>';
            if (ssSelect) ssSelect.innerHTML = '<option value="">All Styles</option>';
        }

        function clearFacets() {
            selectedProps = {};
            if (facetGrid) {
                facetGrid.innerHTML = '<div class="facet-loading">Select a Domain and Family to see available filters</div>';
            }
            if (facetCount) facetCount.textContent = "";
        }

        function loadCCSS(tt, ff) {
            fetch("/ui-api/template_fields?tt=" + tt + "&ff=" + ff)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    // Populate CC
                    if (ccSelect) {
                        ccSelect.innerHTML = '<option value="">All Classes</option>';
                        if (data.guidelines && data.guidelines.cc) {
                            Object.entries(data.guidelines.cc).forEach(function (e) {
                                var o = document.createElement("option");
                                o.value = e[0].toString().padStart(2, "0");
                                o.textContent = e[0].toString().padStart(2, "0") + " - " + e[1];
                                ccSelect.appendChild(o);
                            });
                        }
                        if (currentFilters.cc) ccSelect.value = currentFilters.cc;
                    }

                    // Populate SS
                    if (ssSelect) {
                        ssSelect.innerHTML = '<option value="">All Styles</option>';
                        var ssKey = null;
                        if (data.guidelines) {
                            ssKey = Object.keys(data.guidelines).find(function (k) { return k.startsWith("ss"); });
                        }
                        if (ssKey && data.guidelines[ssKey]) {
                            Object.entries(data.guidelines[ssKey]).forEach(function (e) {
                                var o = document.createElement("option");
                                o.value = e[0].toString().padStart(2, "0");
                                o.textContent = e[0].toString().padStart(2, "0") + " - " + e[1];
                                ssSelect.appendChild(o);
                            });
                        }
                        if (currentFilters.ss) ssSelect.value = currentFilters.ss;
                    }
                });
        }

        function loadFacets() {
            var tt = ttAdvSelect ? ttAdvSelect.value : (ttSelect ? ttSelect.value : "");
            if (!tt) {
                if (facetGrid) {
                    facetGrid.innerHTML = '<div class="facet-loading">Select a Domain to see available filters</div>';
                }
                return;
            }

            var ff = ffSelect ? ffSelect.value : "";
            var cc = ccSelect ? ccSelect.value : "";
            var ss = ssSelect ? ssSelect.value : "";

            var url = "/ui-api/facets?tt=" + tt;
            if (ff) url += "&ff=" + ff;
            if (cc) url += "&cc=" + cc;
            if (ss) url += "&ss=" + ss;

            if (facetGrid) {
                facetGrid.innerHTML = '<div class="facet-loading">Loading filters...</div>';
            }

            fetch(url)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    renderFacets(data.facets, data.total);
                })
                .catch(function (err) {
                    console.error("Facets load error:", err);
                    if (facetGrid) {
                        facetGrid.innerHTML = '<div class="facet-loading">Error loading filters</div>';
                    }
                });
        }

        function renderFacets(facets, total) {
            if (!facetGrid) return;

            if (facetCount) {
                facetCount.textContent = total + " parts match";
            }

            var keys = Object.keys(facets);
            if (keys.length === 0) {
                facetGrid.innerHTML = '<div class="facet-loading">No filterable properties found</div>';
                return;
            }

            facetGrid.innerHTML = "";

            keys.forEach(function (fieldName) {
                var values = facets[fieldName];
                if (!values || values.length === 0) return;

                var facetBox = document.createElement("div");
                facetBox.className = "facet-box";

                // Header (collapsible)
                var header = document.createElement("div");
                header.className = "facet-header";
                header.innerHTML = '<span class="facet-name">' + escapeHtml(fieldName) + '</span>' +
                    '<span class="facet-toggle">▼</span>';

                var list = document.createElement("div");
                list.className = "facet-list";

                // Show first 8 values, collapse rest
                var showAll = values.length <= 10;
                values.forEach(function (v, idx) {
                    var item = document.createElement("label");
                    item.className = "facet-item";
                    if (!showAll && idx >= 8) {
                        item.classList.add("facet-hidden");
                    }

                    var checkbox = document.createElement("input");
                    checkbox.type = "checkbox";
                    checkbox.name = "facet_" + fieldName;
                    checkbox.value = v.value;

                    // Check if already selected
                    if (selectedProps[fieldName] && selectedProps[fieldName].indexOf(v.value) !== -1) {
                        checkbox.checked = true;
                    }

                    checkbox.addEventListener("change", function () {
                        if (checkbox.checked) {
                            if (!selectedProps[fieldName]) selectedProps[fieldName] = [];
                            if (selectedProps[fieldName].indexOf(v.value) === -1) {
                                selectedProps[fieldName].push(v.value);
                            }
                        } else {
                            if (selectedProps[fieldName]) {
                                var i = selectedProps[fieldName].indexOf(v.value);
                                if (i !== -1) selectedProps[fieldName].splice(i, 1);
                                if (selectedProps[fieldName].length === 0) {
                                    delete selectedProps[fieldName];
                                }
                            }
                        }
                    });

                    var text = document.createElement("span");
                    text.className = "facet-value";
                    text.textContent = v.value;

                    var count = document.createElement("span");
                    count.className = "facet-count-badge";
                    count.textContent = "(" + v.count + ")";

                    item.appendChild(checkbox);
                    item.appendChild(text);
                    item.appendChild(count);
                    list.appendChild(item);
                });

                // "Show more" link if needed
                if (!showAll && values.length > 8) {
                    var showMore = document.createElement("div");
                    showMore.className = "facet-show-more";
                    showMore.textContent = "Show " + (values.length - 8) + " more...";
                    showMore.addEventListener("click", function () {
                        var hidden = list.querySelectorAll(".facet-hidden");
                        hidden.forEach(function (el) { el.classList.remove("facet-hidden"); });
                        showMore.style.display = "none";
                    });
                    list.appendChild(showMore);
                }

                // Toggle collapse
                header.addEventListener("click", function () {
                    list.classList.toggle("collapsed");
                    header.querySelector(".facet-toggle").textContent = list.classList.contains("collapsed") ? "▶" : "▼";
                });

                facetBox.appendChild(header);
                facetBox.appendChild(list);
                facetGrid.appendChild(facetBox);
            });
        }

        function serializeProps() {
            if (propsInput) {
                propsInput.value = Object.keys(selectedProps).length > 0 ? JSON.stringify(selectedProps) : "";
            }
        }

        function escapeHtml(str) {
            var div = document.createElement("div");
            div.textContent = str;
            return div.innerHTML;
        }
    }
})();
