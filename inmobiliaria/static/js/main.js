// ── Sidebar toggle ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const toggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('collapsed');
    });
  }

  // ── Formateo de montos en tiempo real ─────────────────────────────────────
  document.querySelectorAll('.input-gs').forEach(function (el) {
    el.addEventListener('input', function () {
      let raw = this.value.replace(/\D/g, '');
      if (raw) {
        this.value = parseInt(raw).toLocaleString('es-PY');
      }
    });
    // Al enviar el form, quitar puntos para que Python reciba el número limpio
    const form = el.closest('form');
    if (form) {
      form.addEventListener('submit', function () {
        el.value = el.value.replace(/\./g, '').replace(/,/g, '');
      }, { once: true });
    }
  });

  // ── Confirmación de eliminación ───────────────────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      if (!confirm(this.dataset.confirm || '¿Confirmás esta acción?')) {
        e.preventDefault();
      }
    });
  });

  // ── Tooltips Bootstrap ─────────────────────────────────────────────────────
  const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltips.forEach(function (el) {
    new bootstrap.Tooltip(el);
  });

  // ── Seleccionar/Deseleccionar todos los checkboxes ─────────────────────────
  const chkAll = document.getElementById('chk-all');
  if (chkAll) {
    chkAll.addEventListener('change', function () {
      document.querySelectorAll('.chk-item').forEach(function (c) {
        c.checked = chkAll.checked;
      });
      recalcularTotal();
    });
  }

  // ── Recálculo dinámico de total a cobrar en cobranzas ─────────────────────
  document.querySelectorAll('.chk-item').forEach(function (c) {
    c.addEventListener('change', recalcularTotal);
  });

  function recalcularTotal() {
    let total = 0;
    document.querySelectorAll('.chk-item:checked').forEach(function (c) {
      total += parseFloat(c.dataset.saldo || 0) + parseFloat(c.dataset.recargo || 0);
    });
    const campo = document.getElementById('monto_total');
    if (campo) {
      campo.value = Math.round(total).toLocaleString('es-PY');
    }
    const display = document.getElementById('total-display');
    if (display) {
      display.textContent = 'Gs. ' + Math.round(total).toLocaleString('es-PY');
    }
  }

  // ── Mostrar/ocultar campos de forma de pago ───────────────────────────────
  const medioPago = document.getElementById('medio_pago_id');
  if (medioPago) {
    medioPago.addEventListener('change', toggleCamposPago);
    toggleCamposPago();
  }

  function toggleCamposPago() {
    const medio = document.getElementById('medio_pago_id');
    if (!medio) return;
    const texto = medio.options[medio.selectedIndex]?.text || '';
    document.querySelectorAll('.campo-cheque').forEach(el => {
      el.style.display = texto.toLowerCase().includes('cheque') ? '' : 'none';
    });
    document.querySelectorAll('.campo-deposito').forEach(el => {
      el.style.display = texto.toLowerCase().includes('depósito') ? '' : 'none';
    });
    document.querySelectorAll('.campo-transferencia').forEach(el => {
      el.style.display = texto.toLowerCase().includes('transferencia') ? '' : 'none';
    });
  }
});
