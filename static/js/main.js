// ═══════════════════════════════════════════════════════
//  PASSMANAGER — MASTER JS
// ═══════════════════════════════════════════════════════

// ── CSRF COOKIE HELPER ──────────────────────────────────
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    for (const cookie of document.cookie.split(';')) {
      const c = cookie.trim();
      if (c.startsWith(name + '=')) {
        cookieValue = decodeURIComponent(c.slice(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// ── TOAST NOTIFICATION ─────────────────────────────────
function showToast(msg, type = 'info') {
  let toast = document.getElementById('global-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'global-toast';
    toast.className = 'toast-msg';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('show'), 3000);
}

// ── SIDEBAR TOGGLE (mobile) ─────────────────────────────
function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  let overlay = document.getElementById('sidebar-overlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'sidebar-overlay';
    overlay.className = 'sidebar-overlay';
    overlay.onclick = closeSidebar;
    document.body.appendChild(overlay);
  }
  const isOpen = sidebar.classList.toggle('open');
  overlay.classList.toggle('show', isOpen);
  document.body.style.overflow = isOpen ? 'hidden' : '';
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if (sidebar) sidebar.classList.remove('open');
  if (overlay) overlay.classList.remove('show');
  document.body.style.overflow = '';
}

// ── AUTO-DISMISS ALERTS ─────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alert messages
  document.querySelectorAll('.alert').forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.4s, transform 0.4s';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-8px)';
      setTimeout(() => alert.remove(), 400);
    }, 5000);
  });

  // Active nav item (if not already set by template)
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(item => {
    const href = item.getAttribute('href');
    if (href && href !== '/' && path.startsWith(href)) {
      item.classList.add('active');
    }
  });

  // Auto-uppercase pass ID inputs
  document.querySelectorAll('input[name="unique_id"], #search-id').forEach(input => {
    input.addEventListener('input', () => { input.value = input.value.toUpperCase(); });
  });
});

// ── PASS SEARCH FORM (validate page) ─────────────────────
function initValidatePage() {
  const input = document.getElementById('search-id');
  if (!input) return;
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      e.preventDefault();
      lookupPass();
    }
  });
}
document.addEventListener('DOMContentLoaded', initValidatePage);

// ── COPY TO CLIPBOARD ────────────────────────────────────
function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => showToast('Copied!'));
  } else {
    // Fallback
    const el = document.createElement('textarea');
    el.value = text;
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    document.execCommand('copy');
    document.body.removeChild(el);
    showToast('Copied!');
  }
}

// ── FETCH WRAPPER with CSRF ───────────────────────────────
async function apiPost(url, data = {}) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(data),
  });
  return res;
}

// ── CONFIRM DIALOG ────────────────────────────────────────
function confirmAction(message, callback) {
  if (window.confirm(message)) callback();
}

// ── PRINT PASS ────────────────────────────────────────────
function printPass() {
  window.print();
}

// ── PHONE VALIDATION ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const phoneInput = document.getElementById('phone');
  if (!phoneInput) return;
  phoneInput.addEventListener('input', () => {
    const val = phoneInput.value.replace(/[^\d\s\-\+\(\)]/g, '');
    phoneInput.value = val;
  });
});
