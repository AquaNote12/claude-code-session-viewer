(function () {
  // Keep the HTML as it was before any UI state changed; copy and download use this snapshot.
  var SNAPSHOT = "<!DOCTYPE html>\n" + document.documentElement.outerHTML;
  // Values computed by ccsv/render.py, passed as JSON so that this file stays plain JavaScript.
  var DATA = JSON.parse(document.getElementById("ccsv-data").textContent);
  var FILENAME = DATA.filename;
  var MSG = DATA.messages;
  var body = document.body;

  function store(key, val) { try { localStorage.setItem("ccsv:" + key, val); } catch (e) {} }
  function load(key) { try { return localStorage.getItem("ccsv:" + key); } catch (e) { return null; } }
  function toast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.classList.remove("show"); }, 1800);
  }

  // Table of contents on/off (a sidebar on wide screens, an overlay on narrow ones)
  var narrow = window.matchMedia("(max-width: 860px)");
  var btnToc = document.getElementById("btn-toc");
  function tocVisible() {
    return narrow.matches ? body.classList.contains("toc-open") : !body.classList.contains("toc-off");
  }
  function syncTocButton() { btnToc.setAttribute("aria-pressed", tocVisible() ? "true" : "false"); }
  if (load("toc") === "off") body.classList.add("toc-off");
  syncTocButton();
  btnToc.addEventListener("click", function () {
    if (narrow.matches) {
      body.classList.toggle("toc-open");
    } else {
      var off = body.classList.toggle("toc-off");
      store("toc", off ? "off" : "on");
    }
    syncTocButton();
  });
  if (narrow.addEventListener) narrow.addEventListener("change", syncTocButton);

  // Show or hide tools, thinking and system rows
  [["btn-tools", "hide-tools"], ["btn-thinking", "hide-thinking"], ["btn-system", "hide-system"]].forEach(function (pair) {
    var b = document.getElementById(pair[0]);
    b.addEventListener("click", function () {
      var hidden = body.classList.toggle(pair[1]);
      b.setAttribute("aria-pressed", hidden ? "false" : "true");
    });
  });

  // Collapsing messages
  function setCollapsed(msg, collapsed) {
    msg.classList.toggle("collapsed", collapsed);
    var b = msg.querySelector(":scope > .bubble > .fold-btn");
    if (b) { b.textContent = collapsed ? MSG.show_full : MSG.collapse; b.setAttribute("aria-expanded", collapsed ? "false" : "true"); }
  }
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest(".fold-btn");
    if (!b) return;
    var msg = b.closest(".msg");
    var wasCollapsed = msg.classList.contains("collapsed");
    setCollapsed(msg, !wasCollapsed);
    if (!wasCollapsed) msg.scrollIntoView({ block: "nearest" });
  });
  document.addEventListener("click", function (ev) {
    var s = ev.target.closest(".msg-summary");
    if (s) setCollapsed(s.closest(".msg"), false);
  });
  document.getElementById("btn-expand").addEventListener("click", function () {
    document.querySelectorAll(".msg.long").forEach(function (m) { setCollapsed(m, false); });
  });
  document.getElementById("btn-collapse").addEventListener("click", function () {
    document.querySelectorAll(".msg.long").forEach(function (m) { setCollapsed(m, true); });
  });

  // On narrow screens, close the table of contents after picking an entry
  document.querySelectorAll(".toc a").forEach(function (a) {
    a.addEventListener("click", function () {
      if (narrow.matches) { body.classList.remove("toc-open"); syncTocButton(); }
    });
  });

  // Highlight the message currently in view in the table of contents
  var links = {};
  document.querySelectorAll(".toc a").forEach(function (a) { links[a.getAttribute("href").slice(1)] = a; });
  var toc = document.querySelector(".toc");
  var current = null;
  function setActive(a) {
    if (a === current) return;
    if (current) current.classList.remove("active");
    current = a;
    if (a) {
      a.classList.add("active");
      if (tocVisible()) revealInToc(a);
    }
  }
  function revealInToc(a) {
    // Scroll only the TOC box. Do not use scrollIntoView() here: it also acts on the page itself and
    // interrupts the user's own (momentum) scrolling, which made scrolling up from the bottom stutter.
    var r = a.getBoundingClientRect(), tr = toc.getBoundingClientRect();
    if (r.top < tr.top) toc.scrollTop -= tr.top - r.top;
    else if (r.bottom > tr.bottom) toc.scrollTop += r.bottom - tr.bottom;
  }
  if ("IntersectionObserver" in window) {
    var facts = document.querySelector(".facts");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        // Back at the session facts above the first message: nothing is highlighted.
        setActive(e.target === facts ? null : (links[e.target.id] || current));
      });
    }, { rootMargin: "-60px 0px -70% 0px" });
    if (facts) io.observe(facts);
    document.querySelectorAll(".thread > .msg[id]").forEach(function (m) { io.observe(m); });
  }

  // Download
  document.getElementById("btn-download").addEventListener("click", function () {
    var blob = new Blob([SNAPSHOT], { type: "text/html;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = FILENAME;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    toast(MSG.toast_downloaded);
  });

  // Copy to the clipboard (fall back to execCommand where the Clipboard API is unavailable, e.g. file://)
  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) {}
    ta.remove();
    return ok;
  }
  document.getElementById("btn-copy").addEventListener("click", function () {
    var done = function () { toast(MSG.toast_copied); };
    var fail = function () { toast(legacyCopy(SNAPSHOT) ? MSG.toast_copied : MSG.toast_copy_failed); };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(SNAPSHOT).then(done, fail);
    } else {
      fail();
    }
  });
})();
