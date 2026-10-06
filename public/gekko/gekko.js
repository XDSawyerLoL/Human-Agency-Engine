(() => {
  const form = document.querySelector('[data-gekko-search]');
  const input = document.getElementById('gekko-omnibox');
  if (!form || !input) return;

  function resolve(value) {
    const raw = String(value || '').trim();
    if (!raw) return null;
    if (/^https?:\/\//i.test(raw)) return raw;
    if (/^[^\s]+\.[a-z]{2,}(?:\/.*)?$/i.test(raw)) return 'https://' + raw;
    return 'https://search.brave.com/search?q=' + encodeURIComponent(raw);
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const target = resolve(input.value);
    if (target) window.open(target, '_blank', 'noopener,noreferrer');
  });

  document.querySelectorAll('[data-gekko-query]').forEach((button) => {
    button.addEventListener('click', () => {
      input.value = button.dataset.gekkoQuery || '';
      input.focus();
    });
  });
})();