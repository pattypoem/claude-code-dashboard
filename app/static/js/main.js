/* CC Dashboard - clipboard copy & search */

(function () {
    "use strict";

    /* ---- Toast notification ---- */
    let toastEl = null;
    let toastTimer = null;

    function showToast(msg) {
        if (!toastEl) {
            toastEl = document.createElement("div");
            toastEl.className = "toast";
            document.body.appendChild(toastEl);
        }
        toastEl.textContent = msg;
        toastEl.classList.add("show");
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            toastEl.classList.remove("show");
        }, 2000);
    }

    /* ---- Resume button: copy command to clipboard ---- */
    document.addEventListener("click", function (e) {
        const btn = e.target.closest(".resume-btn");
        if (!btn) return;

        const sessionId = btn.dataset.sessionId;
        if (!sessionId) return;

        fetch("/api/resume-command/" + sessionId)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.error) {
                    showToast("Error: " + data.error);
                    return;
                }
                return navigator.clipboard.writeText(data.command).then(function () {
                    showToast("Copied: " + data.command);
                });
            })
            .catch(function () {
                showToast("Failed to copy command");
            });
    });

    /* ---- Live search with debounce ---- */
    var searchInput = document.getElementById("search-input");
    var sessionList = document.getElementById("session-list");
    var debounceTimer = null;

    if (searchInput && sessionList) {
        searchInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(function () {
                var q = searchInput.value.trim();
                // Update URL without reload
                var url = q ? "/?q=" + encodeURIComponent(q) : "/";
                history.replaceState(null, "", url);

                fetch("/api/search?q=" + encodeURIComponent(q))
                    .then(function (r) { return r.text(); })
                    .then(function (html) {
                        sessionList.innerHTML = html;
                    });
            }, 300);
        });
    }
})();
