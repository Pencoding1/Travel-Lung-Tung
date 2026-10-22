/* Tài liệu Travel Lung Tung: chuyển sáng/tối, tô mục lục đang xem, nút sao chép lệnh. */
(function () {
  "use strict";

  // 1. Chủ đề sáng/tối, ghi nhớ lựa chọn
  var KEY = "tvlt-docs-theme";
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    var b = document.getElementById("theme-toggle");
    if (b) b.textContent = t === "dark" ? "Nền sáng" : "Nền tối";
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) { saved = null; }
  var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
  document.addEventListener("click", function (ev) {
    if (ev.target && ev.target.id === "theme-toggle") {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
    }
  });

  // 2. Tô đậm mục lục theo vị trí đang đọc
  function navHighlight() {
    var links = Array.prototype.slice.call(document.querySelectorAll("nav.toc a[href^='#']"));
    if (!links.length) return;
    var targets = links.map(function (a) {
      var id = a.getAttribute("href").slice(1);
      return { link: a, el: document.getElementById(id) };
    }).filter(function (t) { return t.el; });
    if (!targets.length) return;

    function update() {
      var y = window.scrollY + 120;
      var current = targets[0];
      for (var i = 0; i < targets.length; i++) {
        if (targets[i].el.offsetTop <= y) current = targets[i];
      }
      links.forEach(function (a) { a.classList.remove("active"); });
      current.link.classList.add("active");
    }
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
  }
  navHighlight();

  // 3. Neo sâu: mở sẵn khối tham số khi được trỏ tới
  function openTargetedDetails() {
    if (!location.hash) return;
    var el = document.getElementById(location.hash.slice(1));
    if (!el) return;
    var d = el.closest ? el.closest("details.params") : null;
    if (d) d.open = true;
  }
  openTargetedDetails();
  window.addEventListener("hashchange", openTargetedDetails);

  // 4. Nút sao chép cho khối lệnh
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest ? ev.target.closest("[data-copy]") : null;
    if (!btn) return;
    var src = btn.getAttribute("data-copy");
    var node = document.querySelector(src);
    if (!node) return;
    var text = node.innerText;
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "Đã chép";
      setTimeout(function () { btn.textContent = old; }, 1400);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      var ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta); done();
    }
  });
})();
