/* 站点交互：主题、菜单、搜索、目录、阅读进度、代码复制、首页过滤 */
(function () {
  'use strict';

  var root = document.documentElement;
  var header = document.getElementById('site-header');
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 主题切换 ---------- */
  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
    });
  }

  /* ---------- 滚动时页头加分隔线 ---------- */
  if (header) {
    var onScrollHeader = function () {
      header.classList.toggle('is-stuck', window.scrollY > 4);
    };
    window.addEventListener('scroll', onScrollHeader, { passive: true });
    onScrollHeader();
  }

  /* ---------- 移动端菜单 ---------- */
  var menuBtn = document.getElementById('menu-btn');
  var nav = document.getElementById('nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') {
        nav.classList.remove('is-open');
        menuBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  /* ---------- 搜索 ---------- */
  var searchInput = document.getElementById('search-input');
  var panel = document.getElementById('search-panel');
  var results = document.getElementById('results-container');
  var searchBtn = document.querySelector('.search-btn');
  var searchIndex = null;

  function loadIndex() {
    if (searchIndex) return Promise.resolve(searchIndex);
    return fetch(searchIndexUrl())
      .then(function (r) { return r.json(); })
      .then(function (data) { searchIndex = data; return data; })
      .catch(function () { return []; });
  }

  function searchIndexUrl() {
    var el = document.getElementById('site-header');
    return (el && el.getAttribute('data-search-json')) || '/search.json';
  }

  function showPanel(show) {
    if (!panel) return;
    panel.hidden = !show;
  }

  function renderResults(items, query) {
    if (!results) return;
    results.innerHTML = '';
    if (!query) { showPanel(false); return; }
    if (!items.length) {
      var li = document.createElement('li');
      li.className = 'search-empty';
      li.textContent = '没有匹配的文章';
      results.appendChild(li);
      showPanel(true);
      return;
    }
    items.slice(0, 8).forEach(function (item) {
      var li = document.createElement('li');
      var a = document.createElement('a');
      a.href = item.url;
      a.textContent = item.title;
      li.appendChild(a);
      if (item.category) {
        var c = document.createElement('span');
        c.className = 'search-cat';
        c.textContent = item.category;
        li.appendChild(c);
      }
      results.appendChild(li);
    });
    showPanel(true);
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      var q = searchInput.value.trim().toLowerCase();
      if (!q) { renderResults([], ''); return; }
      loadIndex().then(function (data) {
        var hits = data.filter(function (p) {
          return (p.title || '').toLowerCase().indexOf(q) > -1 ||
                 (p.tags || '').toLowerCase().indexOf(q) > -1 ||
                 (p.category || '').toLowerCase().indexOf(q) > -1;
        });
        renderResults(hits, q);
      });
    });

    document.addEventListener('click', function (e) {
      if (panel && !panel.hidden && !panel.contains(e.target) && e.target !== searchInput) {
        showPanel(false);
      }
    });

    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
      if (e.key === 'Escape') {
        showPanel(false);
        searchInput.blur();
      }
    });
  }

  if (searchBtn && searchInput) {
    searchBtn.addEventListener('click', function () {
      header.classList.toggle('is-search-open');
      if (header.classList.contains('is-search-open')) {
        setTimeout(function () { searchInput.focus(); }, 60);
      }
    });
  }

  /* ---------- 首页实时过滤 ---------- */
  var list = document.getElementById('post-list');
  var emptyState = document.getElementById('empty-state');
  if (list && searchInput) {
    searchInput.addEventListener('input', function () {
      var q = searchInput.value.trim().toLowerCase();
      var shown = 0;
      Array.prototype.forEach.call(list.querySelectorAll('.post-card'), function (card) {
        var hay = (card.getAttribute('data-title') || '') + ' ' + (card.getAttribute('data-tags') || '');
        var hit = !q || hay.indexOf(q) > -1;
        card.hidden = !hit;
        if (hit) shown++;
      });
      if (emptyState) emptyState.hidden = shown > 0;
    });
  }

  /* ---------- 阅读进度 ---------- */
  var progress = document.getElementById('progress');
  if (progress) {
    var onScrollProgress = function () {
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      var pct = max > 0 ? (h.scrollTop || document.body.scrollTop) / max : 0;
      progress.style.width = (pct * 100) + '%';
    };
    window.addEventListener('scroll', onScrollProgress, { passive: true });
    window.addEventListener('resize', onScrollProgress);
    onScrollProgress();
  }

  /* ---------- 目录 ---------- */
  var tocWrap = document.getElementById('toc-wrap');
  var toc = document.getElementById('toc');
  var body = document.querySelector('.article-body');

  if (tocWrap && toc && body) {
    var heads = body.querySelectorAll('h2, h3');
    if (heads.length >= 2) {
      var frag = document.createDocumentFragment();
      var links = [];
      Array.prototype.forEach.call(heads, function (h, i) {
        if (!h.id) h.id = 'h-' + i;
        var a = document.createElement('a');
        a.href = '#' + h.id;
        a.textContent = h.textContent;
        a.className = 'toc-link toc-link--h' + h.tagName.slice(1);
        a.addEventListener('click', function (e) {
          if (reduceMotion) return;
          e.preventDefault();
          var top = h.getBoundingClientRect().top + window.scrollY - 84;
          window.scrollTo({ top: top, behavior: 'smooth' });
          history.replaceState(null, '', '#' + h.id);
        });
        links.push({ el: a, head: h });
        frag.appendChild(a);
      });
      toc.appendChild(frag);
      tocWrap.hidden = false;

      var setActive = function () {
        var active = null;
        var offset = 100;
        links.forEach(function (item) {
          if (item.head.getBoundingClientRect().top <= offset) active = item;
        });
        links.forEach(function (item) {
          item.el.classList.toggle('is-active', item === active);
        });
      };
      window.addEventListener('scroll', setActive, { passive: true });
      setActive();
    }
  }

  /* ---------- 代码块复制 ---------- */
  Array.prototype.forEach.call(document.querySelectorAll('.article-body pre'), function (pre) {
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.type = 'button';
    btn.textContent = '复制';
    btn.addEventListener('click', function () {
      var code = pre.querySelector('code');
      var text = code ? code.innerText : pre.innerText;
      var done = function () {
        btn.textContent = '已复制';
        setTimeout(function () { btn.textContent = '复制'; }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () {});
      } else {
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
    pre.appendChild(btn);
  });
})();

  /* ---------- 标签页：把 #标签名 定位到对应分组 ---------- */
  (function () {
    var page = document.querySelector('.tag-page');
    if (!page) return;
    function jump() {
      var raw = '';
      try { raw = decodeURIComponent(location.hash.replace(/^#/, '')); } catch (e) { raw = location.hash.replace(/^#/, ''); }
      if (!raw) return;
      if (document.getElementById(raw)) return;
      var hit = page.querySelector('.tag-section[data-tag="' + raw + '"]');
      if (hit) {
        hit.scrollIntoView({ behavior: 'smooth', block: 'start' });
        hit.classList.add('is-target');
        setTimeout(function () { hit.classList.remove('is-target'); }, 1600);
      }
    }
    window.addEventListener('hashchange', jump);
    jump();
  })();
