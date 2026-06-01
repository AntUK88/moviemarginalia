(function () {
  function updateLabel() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.setAttribute('aria-label',
      document.documentElement.getAttribute('data-theme') === 'dark'
        ? 'Switch to light mode'
        : 'Switch to dark mode'
    );
  }

  window.toggleTheme = function () {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
      document.documentElement.removeAttribute('data-theme');
      localStorage.setItem('theme', 'light');
    } else {
      document.documentElement.setAttribute('data-theme', 'dark');
      localStorage.setItem('theme', 'dark');
    }
    updateLabel();
  };

  document.addEventListener('DOMContentLoaded', updateLabel);
})();
