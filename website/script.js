/* Gheychi Premium — shared behaviour. Progressive: the page is complete without it. */

document.documentElement.classList.add('js');

/* ---- Mobile navigation ---- */
(function () {
  var toggle = document.querySelector('[data-nav-toggle]');
  var drawer = document.querySelector('[data-nav-drawer]');
  if (!toggle || !drawer) return;

  toggle.addEventListener('click', function () {
    var open = drawer.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && drawer.classList.contains('open')) {
      drawer.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.focus();
    }
  });
})();

/* ---- Mark the current page in the nav ---- */
(function () {
  var here = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .nav-drawer a').forEach(function (a) {
    if (a.getAttribute('href') === here) a.setAttribute('aria-current', 'page');
  });
})();

/* ---- Reveal on entry, and draw the dimension lines once ---- */
(function () {
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var targets = document.querySelectorAll('.rise, .dim');

  if (reduced || !('IntersectionObserver' in window)) {
    targets.forEach(function (el) { el.classList.add('in', 'drawn'); });
    return;
  }

  /* Give each stroke its own length so the draw reads as measurement,
     not as a generic dash animation. */
  document.querySelectorAll('.dim').forEach(function (svg) {
    svg.querySelectorAll('line, path, polyline').forEach(function (s) {
      var len;
      try { len = s.getTotalLength(); } catch (err) { len = 600; }
      s.style.setProperty('--len', Math.ceil(len));
    });
  });

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('in', 'drawn');
      io.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 });

  targets.forEach(function (el) { io.observe(el); });
})();

/* ---- Stagger siblings so a group reveals as a sequence ---- */
(function () {
  document.querySelectorAll('[data-stagger]').forEach(function (group) {
    Array.prototype.forEach.call(group.children, function (child, i) {
      if (child.classList.contains('rise')) {
        child.style.transitionDelay = Math.min(i * 55, 330) + 'ms';
      }
    });
  });
})();
