/* Shared CheatSheet chrome: dark sidebar + topbar.
   Each page sets: <body data-active="dashboard" data-org="Distribuidora La Esquina" data-cuit="30-71428953-1">
   Then calls CheatSheet.mount() (auto-runs on DOMContentLoaded). */
(function () {
  const I = {
    dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    ingesta:   '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    factura:   '<path d="M6 2h9l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z"/><path d="M14 2v5h5"/><path d="M8 13h8M8 17h5"/>',
    cobros:    '<rect x="2.5" y="5.5" width="19" height="13" rx="2"/><path d="M2.5 9.5h19"/><path d="M6 14.5h3"/>',
    wpp:       '<path d="M12 3a9 9 0 0 0-7.8 13.5L3 21l4.7-1.2A9 9 0 1 0 12 3Z"/>',
    reportes:  '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    logs:      '<path d="M8 4h11M8 9h11M8 14h11M8 19h11"/><circle cx="3.5" cy="4" r="1.2"/><circle cx="3.5" cy="9" r="1.2"/><circle cx="3.5" cy="14" r="1.2"/><circle cx="3.5" cy="19" r="1.2"/>',
    config:    '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 13.5a7.5 7.5 0 0 0 .1-3l1.8-1.4-1.8-3.1-2.2.8a7.5 7.5 0 0 0-2.6-1.5L14 2h-3.6l-.5 2.3a7.5 7.5 0 0 0-2.6 1.5l-2.2-.8L2.3 8.1l1.8 1.4a7.5 7.5 0 0 0 0 3l-1.8 1.4 1.8 3.1 2.2-.8a7.5 7.5 0 0 0 2.6 1.5l.5 2.3H14l.5-2.3a7.5 7.5 0 0 0 2.6-1.5l2.2.8 1.8-3.1-1.7-1.4Z"/>',
    datos:     '<path d="M16 7a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z"/><path d="M3 21v-1a6 6 0 0 1 12 0v1"/><path d="M19.5 21v-1a5 5 0 0 0-3.5-4.8"/>',
    agenda:    '<rect x="3" y="4.5" width="18" height="16" rx="2"/><path d="M3 9h18M8 2.5v4M16 2.5v4"/>',
    help:      '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 4.5 1.5c0 1.5-2 2-2 3.5"/><circle cx="12" cy="17.5" r=".6" fill="currentColor"/>',
    refresh:   '<path d="M21 12a9 9 0 1 1-2.6-6.3M21 4v4h-4"/>',
    bell:      '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"/><path d="M10.5 21a1.8 1.8 0 0 0 3 0"/>',
    chev:      '<path d="m6 9 6 6 6-6"/>',
    search:    '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  };
  const svg = (p, w) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w||1.8}" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;

  const NAV = [
    { group: 'General', items: [
      { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', href: 'dashboard.html' },
    ]},
    { group: 'Operaciones', items: [
      { id: 'ingesta',  label: 'Ingesta de Datos', icon: 'ingesta',  href: 'ingesta.html' },
      { id: 'datos',    label: 'Datos Maestros',   icon: 'datos',    href: '#' },
      { id: 'factura',  label: 'Facturación',      icon: 'factura',  href: '#' },
      { id: 'cobros',   label: 'Cobros',           icon: 'cobros',   href: 'cobros.html', badge: '3' },
      { id: 'agenda',   label: 'Agenda',           icon: 'agenda',   href: '#' },
      { id: 'wpp',      label: 'Agente WhatsApp',  icon: 'wpp',      href: 'agente-whatsapp.html' },
    ]},
    { group: 'Análisis', items: [
      { id: 'reportes', label: 'Reportes',          icon: 'reportes', href: 'reportes.html' },
      { id: 'logs',     label: 'Log de Operaciones',icon: 'logs',     href: 'logs.html' },
    ]},
    { group: 'Sistema', items: [
      { id: 'config',   label: 'Configuración',     icon: 'config',   href: '#' },
    ]},
  ];

  function sidebar(active) {
    let html = `<aside class="sidebar">
      <div class="sidebar__brand">
        <div class="sidebar__logo">CS</div>
        <div><h1>CheatSheet</h1><p>iPaaS · v2.4</p></div>
      </div>
      <nav class="nav">`;
    NAV.forEach(g => {
      html += `<div class="nav__group"><div class="nav__label">${g.group}</div>`;
      g.items.forEach(it => {
        const on = it.id === active ? ' is-active' : '';
        const badge = it.badge ? `<span class="nav__badge">${it.badge}</span>` : '';
        html += `<a class="nav__item${on}" href="${it.href}">${svg(I[it.icon])}<span>${it.label}</span>${badge}</a>`;
      });
      html += `</div>`;
    });
    html += `</nav>
      <div class="sidebar__help">
        ${svg(I.help)}
        <div><b>¿Necesitás ayuda?</b><span>Soporte por WhatsApp</span></div>
      </div>
    </aside>`;
    return html;
  }

  function topbar(org, cuit) {
    const initials = (org || 'LE').split(' ').filter(Boolean).slice(0,2).map(w=>w[0]).join('').toUpperCase();
    return `<header class="topbar">
      <div class="org-switch">
        <div class="avatar">${initials}</div>
        <div><b>${org}</b><small>CUIT ${cuit}</small></div>
        <span class="chev">${svg(I.chev,2)}</span>
      </div>
      <div class="search">${svg(I.search,2)}<input placeholder="Buscar facturas, clientes, operaciones..."><kbd>⌘K</kbd></div>
      <div class="topbar__right">
        <button class="icon-btn">${svg(I.refresh,1.8)}</button>
        <button class="icon-btn">${svg(I.bell,1.8)}<span class="dot"></span></button>
        <div class="user"><div class="meta"><b>Martín Ferreyra</b><small>Admin · Propietario</small></div><div class="avatar">MF</div></div>
      </div>
    </header>`;
  }

  function mount() {
    const b = document.body;
    const active = b.dataset.active || '';
    const org = b.dataset.org || 'Distribuidora La Esquina';
    const cuit = b.dataset.cuit || '30-71428953-1';

    const shell = document.createElement('div');
    shell.className = 'app';
    shell.innerHTML = sidebar(active);

    const main = document.createElement('div');
    main.className = 'app__main';
    main.innerHTML = topbar(org, cuit);

    // move existing page content into main
    const content = document.getElementById('page') || (function(){const d=document.createElement('div');d.id='page';while(b.firstChild)d.appendChild(b.firstChild);return d;})();
    main.appendChild(content);
    shell.appendChild(main);
    b.appendChild(shell);

    // toggles
    b.addEventListener('click', e => {
      const t = e.target.closest('.toggle');
      if (t) t.classList.toggle('is-on');
      const c = e.target.closest('.chip[data-group]');
      if (c) { c.parentElement.querySelectorAll('.chip').forEach(x=>x.classList.remove('is-active')); c.classList.add('is-active'); }
    });
  }

  window.CheatSheet = { mount, svg, I };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
