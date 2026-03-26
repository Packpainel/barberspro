/* ── Custom Modals ────────────────────────────── */
function showModal({ title, message, showInput = false, inputType = 'text', inputValue = '', confirmText = 'Confirmar', cancelText = 'Cancelar' }) {
  return new Promise((resolve) => {
    const modal = document.getElementById('customModal');
    const titleEl = document.getElementById('modalTitle');
    const msgEl = document.getElementById('modalMessage');
    const inputEl = document.getElementById('modalInput');
    const confirmBtn = document.getElementById('modalBtnConfirm');
    const cancelBtn = document.getElementById('modalBtnCancel');

    titleEl.textContent = title;
    msgEl.textContent = message;
    
    if (showInput) {
      inputEl.style.display = 'block';
      inputEl.type = inputType;
      inputEl.value = inputValue;
    } else {
      inputEl.style.display = 'none';
    }

    confirmBtn.textContent = confirmText;
    cancelBtn.textContent = cancelText;

    const cleanup = () => {
      modal.classList.remove('active');
      confirmBtn.onclick = null;
      cancelBtn.onclick = null;
    };

    confirmBtn.onclick = () => {
      const val = inputEl.value;
      cleanup();
      resolve(showInput ? val : true);
    };

    cancelBtn.onclick = () => {
      cleanup();
      resolve(showInput ? null : false);
    };

    modal.classList.add('active');
    if (showInput) setTimeout(() => inputEl.focus(), 100);
  });
}

const showAlert = (title, message) => showModal({ title, message, cancelText: 'OK', confirmText: 'OK' });
const showConfirm = (title, message) => showModal({ title, message });
const showPrompt = (title, message, defaultValue = '') => showModal({ title, message, showInput: true, inputValue: defaultValue });

/* ── Toast container ─────────────────────────── */
const toastContainer = (() => {
  const el = document.createElement('div');
  el.id = 'toast-container';
  document.body.appendChild(el);
  return el;
})();

function showToast(msg, type = 'info', duration = 3000) {
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  toastContainer.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(24px)';
    t.style.transition = 'opacity .3s, transform .3s';
    setTimeout(() => t.remove(), 300);
  }, duration);
}

/* ── Formatters ───────────────────────────────── */
function formatBRL(value) {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const [y, m, d] = dateStr.split('-');
  return `${d}/${m}/${y}`;
}

function todayISO() {
  return new Date().toLocaleDateString('sv-SE'); // returns YYYY-MM-DD local time
}

/* ── Active nav highlight ─────────────────────── */
function setActiveNav() {
  const path = window.location.pathname;
  document.querySelectorAll('.nav-item').forEach(a => {
    const href = a.getAttribute('href');
    a.classList.toggle('active',
      href === path || (href === '/' && path === '/') ||
      (href !== '/' && path.startsWith(href))
    );
  });
}
document.addEventListener('DOMContentLoaded', setActiveNav);

/* ── API helpers ──────────────────────────────── */
async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.erro || 'Erro na requisição');
  return data;
}

function formatWppLink(phone, message) {
  if (!phone) return '#';
  let num = phone.replace(/\D/g, '');
  if (num.length === 10 || num.length === 11) {
    if (!num.startsWith('55')) num = '55' + num;
  }
  return `https://wa.me/${num}?text=${encodeURIComponent(message)}`;
}

/* ══════════════════════════════════════════════
   DASHBOARD
══════════════════════════════════════════════ */
async function loadDashboard() {
  const el = id => document.getElementById(id);
  if (!el('kpi-faturamento')) return;

  try {
    const d = await apiFetch('/api/dashboard');

    el('kpi-faturamento').textContent  = formatBRL(d.faturamento_mes);
    el('kpi-atendimentos').textContent = d.atendimentos_mes;
    el('kpi-ativos').textContent       = d.clientes_ativos;
    el('kpi-inativos').textContent     = d.clientes_inativos;

    const tbody = el('tbody-inativos');
    if (!d.lista_inativos.length) {
      tbody.innerHTML = `<tr><td colspan="3" class="empty-state"><span class="empty-icon">🎉</span>Nenhum cliente inativo!</td></tr>`;
      return;
    }
    tbody.innerHTML = d.lista_inativos.map(c => {
      let fName = c.nome.split(' ')[0];
      let msg = `Fala ${fName}, sumiu hein! Que tal dar um trato no visual? Tenho horários sobrando essa semana!`;
      let wpp = formatWppLink(c.telefone, msg);
      return `
      <tr>
        <td><strong>${esc(c.nome)}</strong></td>
        <td>
          ${c.telefone ? `<a class="btn btn-sm btn-success" style="padding:4px 8px;font-size:0.8rem;text-decoration:none" href="${wpp}" target="_blank">📱 Wpp</a>` : '—'}
        </td>
        <td style="color:var(--danger);font-weight:600">${c.dias_ausente || '?'} dias</td>
      </tr>`;
    }).join('');
  } catch (e) {
    showToast('Erro Dashboard: ' + e.message, 'error');
  }
}

/* ══════════════════════════════════════════════
   CLIENTES
══════════════════════════════════════════════ */
let allClientes = [];

async function loadClientes() {
  const tbody = document.getElementById('tbody-clientes');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="4" class="loading-overlay"><span class="spinner"></span></td></tr>`;
  try {
    allClientes = await apiFetch('/api/clientes');
    renderClientes(allClientes);
  } catch (e) {
    showToast('Erro Clientes: ' + e.message, 'error');
  }
}

function renderClientes(list) {
  const tbody = document.getElementById('tbody-clientes');
  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="4" class="empty-state"><span class="empty-icon">👤</span>Nenhum cliente cadastrado</td></tr>`;
    return;
  }
  tbody.innerHTML = list.map(c => `
    <tr>
      <td><strong>${esc(c.nome)}</strong></td>
      <td>${c.telefone ? `<a class="tel-link" href="tel:${esc(c.telefone)}">${esc(c.telefone)}</a>` : '—'}</td>
      <td>${formatDate(c.ultima_visita)}</td>
      <td><span class="badge ${c.status === 'ativo' ? 'badge-success' : 'badge-danger'}">${c.status}</span></td>
    </tr>`).join('');
}

function filterClientes() {
  const q = (document.getElementById('search-cliente')?.value || '').toLowerCase();
  renderClientes(allClientes.filter(c => c.nome.toLowerCase().includes(q)));
}

async function submitNovoCliente(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-salvar-cliente');
  btn.disabled = true;
  btn.textContent = 'Salvando…';
  try {
    await apiFetch('/api/clientes', {
      method: 'POST',
      body: JSON.stringify({
        nome:     document.getElementById('nome').value.trim(),
        telefone: document.getElementById('telefone').value.trim()
      })
    });
    showToast('Cliente cadastrado com sucesso!', 'success');
    e.target.reset();
    loadClientes();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar Cliente';
  }
}

/* ══════════════════════════════════════════════
   NOVO ATENDIMENTO
══════════════════════════════════════════════ */
let selectedServico = null;

async function loadNovoAtendimento() {
  const sel = document.getElementById('cliente-sel');
  if (!sel) return;

  // Set today's date
  const dateInput = document.getElementById('data-atend');
  if (dateInput) dateInput.value = todayISO();

  // Set current time
  const timeInput = document.getElementById('hora-atend');
  if (timeInput) timeInput.value = new Date().toTimeString().slice(0, 5);

  // Initialize Agenda
  const agendaDate = document.getElementById('data-agenda');
  if (agendaDate) {
    agendaDate.value = todayISO();
    agendaDate.addEventListener('change', () => loadAgenda(agendaDate.value));
    loadAgenda(agendaDate.value);
  }

  try {
    const clientes = await apiFetch('/api/clientes');
    sel.innerHTML = '<option value="">— Selecione o cliente —</option>' +
      clientes.map(c => `<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  } catch (e) {
    showToast('Erro Carregar: ' + e.message, 'error');
  }

  // Chips de serviço
  document.querySelectorAll('.chip[data-servico]').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      selectedServico = chip.dataset.servico;
      document.getElementById('servico-hidden').value = selectedServico;
    });
  });
}

async function submitAtendimento(e) {
  e.preventDefault();
  const clienteId = document.getElementById('cliente-sel').value;
  const servico   = document.getElementById('servico-hidden').value;
  const valor     = document.getElementById('valor').value;
  const data      = document.getElementById('data-atend').value;
  const hora      = document.getElementById('hora-atend').value;

  if (!clienteId) return showToast('Selecione um cliente', 'error');
  if (!servico)   return showToast('Selecione o serviço', 'error');
  if (!valor || valor <= 0) return showToast('Informe um valor válido', 'error');

  const btn = document.getElementById('btn-salvar-atend');
  btn.disabled = true;
  btn.textContent = 'Salvando…';

  try {
    await apiFetch('/api/atendimentos', {
      method: 'POST',
      body: JSON.stringify({ cliente_id: clienteId, servico, valor, data, hora })
    });
    showToast('Atendimento registrado! ✅', 'success');
    e.target.reset();
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    selectedServico = null;
    document.getElementById('servico-hidden').value = '';
    document.getElementById('data-atend').value = todayISO();
    
    const hInput = document.getElementById('hora-atend');
    if (hInput) hInput.value = new Date().toTimeString().slice(0, 5);

    setTimeout(() => { window.location.href = '/agenda'; }, 1000);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Registrar na Agenda';
  }
}

/* ══════════════════════════════════════════════
   AGENDA DO DIA
══════════════════════════════════════════════ */
async function loadAgenda(dataStr) {
  const tbody = document.getElementById('tbody-agenda');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="5" class="loading-overlay"><span class="spinner"></span></td></tr>`;
  try {
    const list = await apiFetch(`/api/atendimentos/dia?data=${dataStr}`);
    if (!list.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Nenhum compromisso marcado.</td></tr>`;
      return;
    }
    let html = '';
    list.map(a => {
      const isConcluido = a.status === 'concluido';
      const isCancelled = a.status === 'cancelado';
      const statusClass = isCancelled ? 'opacity-50 line-through' : '';
      const actionBtn = isConcluido
        ? '<span style="color:var(--success);font-weight:bold;font-size:0.85rem">✅ Concluído</span>'
        : isCancelled 
          ? '<span style="color:var(--danger);font-weight:bold;font-size:0.85rem">CANCELADO</span>'
          : `<div class="flex gap-2">
              <button class="btn btn-sm btn-outline" style="padding:4px 8px;font-size:0.8rem;white-space:nowrap" onclick="concluirAtendimento(${a.id}, '${dataStr}')">✔️ Concluir</button>
              <button class="btn btn-sm btn-outline border-red-900 text-red-500" style="padding:4px 8px;font-size:0.8rem;white-space:nowrap" onclick="solicitarCancelamentoBarbeiro(${a.id}, '${dataStr}')">❌</button>
             </div>`;

      let wppBtn = '';
      if (!isConcluido && !isCancelled && a.cliente_telefone) {
        let msg = `Olá ${a.cliente_nome.split(' ')[0]}! Passando pra avisar que seu horário de ${a.servico} está confirmado hoje às ${a.hora}. Te espero aqui!`;
        let wLink = formatWppLink(a.cliente_telefone, msg);
        wppBtn = `<a href="${wLink}" target="_blank" class="btn btn-sm btn-success" style="padding:4px 8px;font-size:0.8rem;margin-left:4px;text-decoration:none" title="Enviar Lembrete">💬 Wpp</a>`;
      }

      const statusBadge = isConcluido
        ? `<span class="badge badge-success" style="font-size:0.75rem">Concluído</span>`
        : isCancelled
          ? `<span class="badge badge-danger" style="font-size:0.75rem">Cancelado</span>`
          : `<span class="badge badge-gold" style="font-size:0.75rem">Agendado</span>`;

      html += `
      <tr style="${isConcluido ? 'opacity:0.6' : ''} ${isCancelled ? 'opacity:0.5; text-decoration:line-through;' : ''}">
        <td style="font-weight:600;color:var(--gold)">${a.hora || '—'}</td>
        <td><strong>${esc(a.cliente_nome)}</strong></td>
        <td>
          ${esc(a.servico)}<br>
          <small style="color:var(--text-muted)">${esc(a.barbeiro_nome || '—')}</small>
        </td>
        <td>${statusBadge}</td>
        <td>${actionBtn}${wppBtn}</td>
      </tr>`;
    }).join('');
    tbody.innerHTML = html;
  } catch (e) {
    showToast('Erro Agenda: ' + e.message, 'error');
  }
}

window.concluirAtendimento = async function(id, dataStr) {
  let valStr = await showPrompt("Concluir Atendimento", "Qual o valor final do serviço? (Ex: 40.00)", "0.00");
  if (valStr === null) return; // Operação cancelada
  
  let valor = parseFloat(valStr.replace(',', '.'));
  if (isNaN(valor) || valor < 0) {
    return showAlert("Erro", "Valor inválido. Tente novamente.");
  }

  try {
    const res = await fetch(`/api/atendimentos/${id}/concluir`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ valor: valor })
    });
    
    if (!res.ok) throw new Error("Erro na solicitação");
    
    showToast('Corte concluído e contabilizado!', 'success');
    loadAgenda(dataStr);
  } catch (e) {
    showToast('Erro: ' + e.message, 'error');
  }
}

/* ══════════════════════════════════════════════
   HISTÓRICO
══════════════════════════════════════════════ */
async function loadHistorico(inicio, fim) {
  const tbody = document.getElementById('tbody-historico');
  const totalEl = document.getElementById('total-periodo');
  const qtdEl   = document.getElementById('qtd-periodo');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="4" class="loading-overlay"><span class="spinner"></span></td></tr>`;
  try {
    const d = await apiFetch(`/api/historico?inicio=${inicio}&fim=${fim}`);

    if (totalEl) totalEl.textContent = formatBRL(d.total);
    if (qtdEl)   qtdEl.textContent = `${d.quantidade} atendimento${d.quantidade !== 1 ? 's' : ''}`;

    if (!d.atendimentos.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="empty-state"><span class="empty-icon">📋</span>Nenhum atendimento no período</td></tr>`;
      return;
    }
    tbody.innerHTML = d.atendimentos.map(a => `
      <tr>
        <td>${formatDate(a.data)}</td>
        <td><strong>${esc(a.cliente_nome)}</strong></td>
        <td>${esc(a.servico)}</td>
        <td style="color:var(--gold);font-weight:600">${formatBRL(a.valor)}</td>
      </tr>`).join('');
  } catch (e) {
    showToast('Erro Histórico: ' + e.message, 'error');
  }
}

/* ── XSS escape ───────────────────────────────── */
function esc(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Boot ─────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  loadClientes();
  loadNovoAtendimento();

  // Form hooks
  const formCliente = document.getElementById('form-cliente');
  if (formCliente) formCliente.addEventListener('submit', submitNovoCliente);

  const formAtend = document.getElementById('form-atendimento');
  if (formAtend) formAtend.addEventListener('submit', submitAtendimento);

  const searchInput = document.getElementById('search-cliente');
  if (searchInput) searchInput.addEventListener('input', filterClientes);

  // Histórico — filtro
  const btnFiltrar = document.getElementById('btn-filtrar');
  if (btnFiltrar) {
    // Default to current month
    const hoje = todayISO();
    const inicioMes = hoje.slice(0, 7) + '-01';
    document.getElementById('inicio-date').value = inicioMes;
    document.getElementById('fim-date').value = hoje;
    loadHistorico(inicioMes, hoje);

    btnFiltrar.addEventListener('click', () => {
      const i = document.getElementById('inicio-date').value;
      const f = document.getElementById('fim-date').value;
      if (!i || !f) return showToast('Selecione as datas', 'error');
      loadHistorico(i, f);
    });
  }

  // Agenda — init
  const agendaDate = document.getElementById('data-agenda');
  if (agendaDate) {
    agendaDate.value = todayISO();
    agendaDate.addEventListener('change', () => loadAgenda(agendaDate.value));
    loadAgenda(agendaDate.value);
  }
});

async function cancelarAgendamentoPublico(token) {
  const ok = await showConfirm("Cancelar Agendamento", "Tem certeza que deseja cancelar este agendamento?");
  if (!ok) return;
  
  const btn = document.getElementById('btn-cancelar-publico');
  if (btn) btn.disabled = true;

  try {
    await apiFetch(`/api/public/cancelar/${token}`, { method: 'POST' });
    showToast('Agendamento cancelado com sucesso!', 'success');
    setTimeout(() => {
      location.reload();
    }, 1500);
  } catch (e) {
    showToast('Erro ao cancelar: ' + e.message, 'error');
    if (btn) btn.disabled = false;
  }
}

async function solicitarCancelamentoBarbeiro(id, dataStr) {
  const ok = await showConfirm("Cancelar Atendimento", "Deseja realmente cancelar este atendimento?");
  if (!ok) return;
  try {
    await apiFetch(`/api/atendimentos/${id}/cancelar`, { method: 'POST' });
    showToast('Atendimento cancelado.', 'success');
    loadAgenda(dataStr);
  } catch (e) {
    showToast('Erro ao cancelar: ' + e.message, 'error');
  }
}

/* ══════════════════════════════════════════════
   ALTERAR SENHA
══════════════════════════════════════════════ */
function abrirAlterarSenha() {
  const modal = document.getElementById('modalSenha');
  if (modal) {
    document.getElementById('senha-atual').value = '';
    document.getElementById('nova-senha').value = '';
    modal.classList.add('active');
  }
}

function fecharModalSenha() {
  const modal = document.getElementById('modalSenha');
  if (modal) modal.classList.remove('active');
}

async function salvarNovaSenha() {
  const senhaAtual = document.getElementById('senha-atual').value;
  const novaSenha = document.getElementById('nova-senha').value;

  if (!senhaAtual || !novaSenha) {
    showToast('Preencha todos os campos', 'error');
    return;
  }
  if (novaSenha.length < 6) {
    showToast('A nova senha deve ter pelo menos 6 caracteres', 'error');
    return;
  }

  const btn = document.getElementById('btn-salvar-senha');
  btn.disabled = true;
  btn.textContent = 'Salvando…';

  try {
    await apiFetch('/api/alterar-senha', {
      method: 'POST',
      body: JSON.stringify({ senha_atual: senhaAtual, nova_senha: novaSenha })
    });
    showToast('Senha alterada com sucesso! 🔒', 'success');
    fecharModalSenha();
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Salvar';
  }
}

/* ══════════════════════════════════════════════
   MÁSCARA DE TELEFONE (Clientes)
══════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  const telInput = document.getElementById('telefone');
  if (telInput) {
    telInput.maxLength = 15;
    telInput.addEventListener('input', function (e) {
      let x = e.target.value.replace(/\D/g, '').match(/(\d{0,2})(\d{0,5})(\d{0,4})/);
      e.target.value = !x[2] ? x[1] : '(' + x[1] + ') ' + x[2] + (x[3] ? '-' + x[3] : '');
    });
  }
});

console.log("App Version: 3.0 - Bug fixes & new features");
