import secrets
import httpx
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app import config
from app.db import (
    get_pool,
    dashboard_metrics,
    daily_chart,
    citas_chart,
    get_citas,
    cancelar_cita,
    get_escalados,
    liberar_escalado,
    get_pausados,
    reanudar_bot,
    pausar_bot,
    is_pausado,
    get_recientes,
    get_control_slots,
    insert_control,
)

admin_router = APIRouter(prefix="/admin")


def _require_login(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})
    return user


# ── SHELL WRAPPER ──────────────────────────────────────────

def _shell(content: str, request: Request, active: str = "") -> str:
    user = request.session.get("user", "")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Panel — Casa Angelical</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{{--bg:#0d0d0d;--panel:#1a1a1a;--ink:#e0e0e0;--muted:#888;--line:#2a2a2a;--green:#5fa87f;--green-dark:#3d7a55;--red:#e53935;--blue:#42a5f5;--wa:#25D366;--shadow:0 4px 20px rgba(0,0,0,.3)}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--ink);min-height:100vh;display:flex}}
.sidebar{{width:220px;min-height:100vh;background:var(--panel);border-right:1px solid var(--line);padding:20px 0;position:fixed;top:0;left:0;bottom:0;z-index:100;display:flex;flex-direction:column;transition:transform .25s}}
.sidebar-brand{{padding:0 20px 24px;border-bottom:1px solid var(--line);margin-bottom:8px}}
.sidebar-brand h1{{color:var(--green);font-size:16px;letter-spacing:0.5px}}
.sidebar-brand p{{color:var(--muted);font-size:11px;margin-top:2px}}
.sidebar nav{{flex:1;padding:8px 12px}}
.sidebar a{{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:8px;color:var(--muted);text-decoration:none;font-size:13.5px;font-weight:500;margin-bottom:2px;transition:all .15s}}
.sidebar a:hover,.sidebar a.active{{background:rgba(95,168,127,.12);color:var(--green)}}
.sidebar a.active{{font-weight:600}}
.sidebar-footer{{padding:12px 20px;border-top:1px solid var(--line)}}
.sidebar-footer form{{margin:0}}
.btn-logout{{width:100%;padding:8px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--muted);cursor:pointer;font-size:12px;transition:all .15s}}
.btn-logout:hover{{border-color:var(--red);color:var(--red)}}
.main{{margin-left:220px;flex:1;padding:24px 28px 40px;min-height:100vh;width:calc(100% - 220px)}}
.topbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.topbar h2{{font-size:20px;color:var(--green);font-weight:700}}
.topbar .user-info{{color:var(--muted);font-size:12px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;margin-bottom:18px}}
.card-title{{font-size:14px;color:var(--green);font-weight:700;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:6px}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}}
.kpi-card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center}}
.kpi-num{{font-size:28px;font-weight:800;color:var(--ink)}}
.kpi-num.verde{{color:var(--green)}}
.kpi-num.naranja{{color:#ff9800}}
.kpi-num.azul{{color:var(--blue)}}
.kpi-label{{font-size:11px;color:var(--muted);margin-top:3px}}
.chart-container{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}}
.chart-box{{width:100%;height:280px}}
.item{{background:#111;border:1px solid var(--line);border-radius:10px;padding:14px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}}
.item-info{{flex:1;min-width:160px}}
.item-nombre{{font-size:14px;color:var(--ink);font-weight:600}}
.item-meta{{font-size:12px;color:var(--muted);margin-top:3px}}
.item-msg{{font-size:12px;color:#aaa;margin-top:4px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.item-actions{{display:flex;gap:6px;flex-wrap:wrap}}
.btn{{padding:8px 16px;border-radius:8px;border:none;font-size:13px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:4px;transition:all .15s}}
.btn-green{{background:var(--green);color:#fff}}
.btn-green:hover{{background:var(--green-dark)}}
.btn-red{{background:var(--red);color:#fff}}
.btn-red:hover{{background:#c62828}}
.btn-wa{{background:var(--wa);color:#fff}}
.btn-wa:hover{{background:#1fa851}}
.btn-outline{{background:transparent;border:1px solid var(--line);color:var(--muted)}}
.btn-outline:hover{{border-color:var(--green);color:var(--green)}}
.empty{{color:var(--muted);font-size:13px;text-align:center;padding:30px 0}}
.badge{{font-size:10px;padding:3px 8px;border-radius:20px;font-weight:700;white-space:nowrap}}
.badge-green{{background:rgba(95,168,127,.15);color:var(--green)}}
.badge-red{{background:rgba(229,57,53,.15);color:var(--red)}}
.badge-orange{{background:rgba(255,152,0,.15);color:#ff9800}}
.inp,select{{width:100%;padding:11px 14px;border-radius:10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);font-size:14px;margin-bottom:12px;-webkit-appearance:none;appearance:none}}
.inp:focus,select:focus{{outline:none;border-color:var(--green)}}
.inp[type="date"]{{min-height:44px;color-scheme:dark}}
.inp[type="date"]::-webkit-calendar-picker-indicator{{filter:invert(1);opacity:0.6}}
select{{background-image:url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/></svg>");background-repeat:no-repeat;background-position:right 10px center}}
label{{font-size:12px;color:var(--muted);display:block;margin-bottom:4px}}
.search-box{{display:flex;gap:8px;margin-bottom:14px}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.slots-grid{{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}}
.slot-btn{{padding:9px 16px;border-radius:8px;border:1px solid var(--line);background:#222;color:var(--ink);font-size:13px;cursor:pointer;transition:all .15s}}
.slot-btn:hover,.slot-btn.sel{{background:var(--green);border-color:var(--green);color:#fff;font-weight:700}}
.msg-inline{{display:none;margin-top:10px;padding:11px;border-radius:8px;font-size:13px;text-align:center}}
.msg-ok{{background:#1a3a1a;color:#4caf50;border:1px solid #4caf50}}
.msg-err{{background:#3a1a1a;color:#f44336;border:1px solid #3a1a1a}}
.toast{{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:11px 22px;border-radius:10px;font-size:13px;font-weight:600;z-index:999;opacity:0;transition:opacity .3s;white-space:nowrap}}
.toast.ok{{background:#1b5e20;color:#a5d6a7;border:1px solid #2e7d32;opacity:1}}
.toast.err{{background:#b71c1c;color:#ffcdd2;border:1px solid #c62828;opacity:1}}
.hamburger{{display:none;background:none;border:none;color:var(--ink);font-size:24px;cursor:pointer;padding:4px}}
@media(max-width:780px){{
  .sidebar{{transform:translateX(-100%)}}
  .sidebar.open{{transform:translateX(0)}}
  .main{{margin-left:0;width:100%;padding:16px}}
  .hamburger{{display:block}}
  .kpi-grid{{grid-template-columns:1fr 1fr}}
  .grid-2{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
<div class="sidebar" id="sidebar">
  <div class="sidebar-brand">
    <h1>🏥 CASA ANGELICAL</h1>
    <p>Panel de Gestión</p>
  </div>
  <nav>
    <a href="/admin/dashboard" class="{'active' if active=='dashboard' else ''}">📊 Dashboard</a>
    <a href="/admin/citas" class="{'active' if active=='citas' else ''}">📅 Citas</a>
    <a href="/admin/escalados" class="{'active' if active=='escalados' else ''}">🚨 Escalados</a>
    <a href="/admin/pausados" class="{'active' if active=='pausados' else ''}">⏸️ Pausados</a>
    <a href="/admin/agendar" class="{'active' if active=='agendar' else ''}">📅 Agendar</a>
    <a href="/admin/recientes" class="{'active' if active=='recientes' else ''}">💬 Recientes</a>
  </nav>
  <div class="sidebar-footer">
    <form action="/admin/logout" method="post">
      <button class="btn-logout">⬅️ Cerrar sesión</button>
    </form>
  </div>
</div>
<div class="overlay" id="overlay" onclick="closeSidebar()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:90"></div>
<div class="main">
  <div class="topbar">
    <div style="display:flex;align-items:center;gap:12px">
      <button class="hamburger" onclick="toggleSidebar()">☰</button>
    </div>
    <div class="user-info">{user} · Panel Casa Angelical</div>
  </div>
{content}
</div>
<div class="toast" id="toast"></div>
<script>
function toggleSidebar() {{
  var s = document.getElementById('sidebar');
  var o = document.getElementById('overlay');
  s.classList.toggle('open');
  o.style.display = s.classList.contains('open') ? 'block' : 'none';
}}
function closeSidebar() {{
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('overlay').style.display = 'none';
}}
function toast(msg, type) {{
  var t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast ' + (type||'ok');
  setTimeout(function(){{t.className='toast'}}, 3000);
}}
function waLink(tel) {{
  var n = tel.replace(/\\D/g,'');
  if(!n.startsWith('57') && n.length===10) n = '57'+n;
  return 'https://wa.me/'+n;
}}
function fmtNum(n){{return n==null||!isFinite(n)?'-':Number(n).toLocaleString('es-CO')}}
</script>
</body>
</html>"""


# ── LOGIN ──────────────────────────────────────────────────

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>Login — Casa Angelical</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#0d0d0d;color:#e0e0e0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.login-box{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:16px;padding:40px 32px;width:90%;max-width:380px;text-align:center}
.login-box h1{color:#5fa87f;font-size:20px;margin-bottom:4px}
.login-box p{color:#888;font-size:12px;margin-bottom:24px}
.login-box input{width:100%;padding:12px 16px;border-radius:10px;border:1px solid #2a2a2a;background:#111;color:#fff;font-size:14px;margin-bottom:14px}
.login-box input:focus{outline:none;border-color:#5fa87f}
.login-box button{width:100%;padding:13px;border-radius:10px;border:none;background:#5fa87f;color:#fff;font-size:15px;font-weight:700;cursor:pointer}
.login-box button:hover{background:#3d7a55}
.login-err{color:#e53935;font-size:12px;margin-top:8px}
</style>
</head>
<body>
<div class="login-box">
  <h1>🏥 Casa Angelical</h1>
  <p>Panel de Gestión</p>
  <form method="post">
    <input type="text" name="username" placeholder="Usuario" required autofocus />
    <input type="password" name="password" placeholder="Contraseña" required />
    <button type="submit">Ingresar</button>
  </form>
  __ERROR__
</div>
</body>
</html>"""


@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return LOGIN_PAGE.replace("__ERROR__", "")


@admin_router.post("/login", response_class=HTMLResponse)
async def login_post(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user_ok = secrets.compare_digest(username, config.ADMIN_USER)
    pass_ok = secrets.compare_digest(password, config.ADMIN_PASSWORD)

    if user_ok and pass_ok:
        request.session["user"] = username
        return RedirectResponse(url="/admin/dashboard", status_code=302)

    error = "Usuario o contraseña incorrectos"
    return LOGIN_PAGE.replace("__ERROR__", f'<div class="login-err">{error}</div>')


@admin_router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)


# ── DASHBOARD ──────────────────────────────────────────────

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    _require_login(request)
    pool = await get_pool()
    metrics = await dashboard_metrics(pool)
    daily = await daily_chart(pool)
    citas_daily = await citas_chart(pool)

    kpis = f"""
<div class="kpi-grid">
  <div class="kpi-card"><div class="kpi-num verde">{fmt(metrics['conversaciones_hoy'])}</div><div class="kpi-label">Conversaciones Hoy</div></div>
  <div class="kpi-card">
    <div style="display:flex;justify-content:center;gap:16px">
      <div style="text-align:center"><div class="kpi-num azul">{fmt(metrics['nuevos_hoy'])}</div><div class="kpi-label">Nuevos</div></div>
      <div style="text-align:center"><div style="font-size:28px;font-weight:800;color:#aaa">{fmt(metrics['recurrentes_hoy'])}</div><div class="kpi-label">Recurrentes</div></div>
    </div>
    <div class="kpi-label" style="margin-top:6px">Pacientes Hoy</div>
  </div>
  <div class="kpi-card"><div class="kpi-num verde">{fmt(metrics['citas_semana'])}</div><div class="kpi-label">Citas Próx. 7d</div></div>
  <div class="kpi-card"><div class="kpi-num naranja">{fmt(metrics['escalados_pendientes'])}</div><div class="kpi-label">Escalados Pend.</div></div>
  <div class="kpi-card"><div class="kpi-num" style="color:#888">{fmt(metrics['abandonadas'])}</div><div class="kpi-label">Abandonaron Conv.</div></div>
</div>"""

    chart_js = _render_charts(daily, citas_daily)
    content = f"{kpis}{chart_js}"
    return HTMLResponse(_shell(content, request, "dashboard"))


def fmt(val):
    if val is None or (isinstance(val, float) and not val == val):
        return "-"
    if isinstance(val, float):
        return f"{int(val)}" if val == int(val) else f"{val:.1f}"
    return str(val)


def _render_charts(daily: list[dict], citas_daily: list[dict]) -> str:
    dias_json = [d["dia"] for d in daily]
    msgs_json = [d["mensajes"] for d in daily]
    citas_dias = [c["dia"] for c in citas_daily]
    citas_vals = [c["citas"] for c in citas_daily]

    return f"""
<div class="chart-container">
  <div class="card-title">📊 Mensajes por Día (últimos 7 días)</div>
  <div class="chart-box" id="chart-diario"></div>
</div>
<div class="chart-container">
  <div class="card-title">📅 Citas Agendadas por Día (próximos 7 días)</div>
  <div class="chart-box" id="chart-citas"></div>
</div>
<script>
(function() {{
  Plotly.newPlot('chart-diario', [{{
    x: {dias_json}, y: {msgs_json}, type: 'bar',
    marker: {{color: '#5fa87f', line: {{color: '#3d7a55', width: 1}}}}
  }}], {{
    margin: {{t:10,r:10,b:40,l:30}}, plot_bgcolor:'#1a1a1a', paper_bgcolor:'#1a1a1a',
    font: {{color:'#888',size:11}}, xaxis: {{gridcolor:'#2a2a2a'}}, yaxis: {{gridcolor:'#2a2a2a',dtick:1}}
  }}, {{displayModeBar:false,responsive:true}});
  Plotly.newPlot('chart-citas', [{{
    x: {citas_dias}, y: {citas_vals}, type: 'bar',
    marker: {{color: '#42a5f5', line: {{color: '#1e88e5', width: 1}}}}
  }}], {{
    margin: {{t:10,r:10,b:40,l:30}}, plot_bgcolor:'#1a1a1a', paper_bgcolor:'#1a1a1a',
    font: {{color:'#888',size:11}}, xaxis: {{gridcolor:'#2a2a2a'}}, yaxis: {{gridcolor:'#2a2a2a',dtick:1}}
  }}, {{displayModeBar:false,responsive:true}});
}})();
</script>"""


# ── CITAS ──────────────────────────────────────────────────

@admin_router.get("/citas", response_class=HTMLResponse)
async def citas_page(request: Request):
    _require_login(request)
    pool = await get_pool()
    citas = await get_citas(pool)

    rows = ""
    for c in citas:
        fecha_str = c["fecha"].strftime("%d/%m/%Y") if c["fecha"] else ""
        hora_str = str(c["hora"])[:5] if c["hora"] else ""
        motivo = c.get("motivo") or ""
        rows += f"""
<tr class="item">
  <div class="item-info">
    <div class="item-nombre">{c['nombre']}</div>
    <div class="item-meta">📅 {fecha_str} · 🕐 {hora_str}</div>
    {f'<div class="item-msg">💊 {motivo}</div>' if motivo else ''}
    <div class="item-meta">+{clean_tel(c.get('telefono',''))} · {c.get('email','')}</div>
  </div>
  <div class="item-actions">
    <a href="{_wa_link(c.get('telefono',''))}" target="_blank" class="btn btn-wa btn-sm">💬 WhatsApp</a>
    <button class="btn btn-red btn-sm" onclick="cancelarCita({c['id']})">✖ Cancelar</button>
  </div>
</tr>"""

    if not rows:
        rows = '<div class="empty">No hay citas activas en este momento 🎉</div>'

    content = f"""<div class="card"><div class="card-title">📅 Citas Próximas</div>{rows}</div>
<script>
async function cancelarCita(id) {{
  if(!confirm('¿Cancelar esta cita?')) return;
  try {{
    var r = await fetch('/admin/citas/'+id+'/cancelar', {{method:'POST'}});
    if(r.ok) {{ toast('Cita cancelada'); setTimeout(function(){{location.reload()}},500); }}
    else toast('Error','err');
  }} catch(e) {{ toast('Error','err'); }}
}}
</script>"""
    return HTMLResponse(_shell(content, request, "citas"))


@admin_router.post("/citas/{cita_id}/cancelar")
async def citas_cancel(cita_id: int, request: Request):
    _require_login(request)
    pool = await get_pool()
    ok = await cancelar_cita(pool, cita_id)
    return JSONResponse({"ok": ok})



def clean_tel(tel: str) -> str:
    """Normaliza teléfono: elimina todo lo que no sea dígito y +, mantiene solo un +57"""
    if not tel:
        return ""
    digits = "".join(c for c in tel if c.isdigit())
    if len(digits) == 10:
        return "57" + digits
    if len(digits) > 10 and digits.startswith("57"):
        return digits
    if digits.startswith("57"):
        return digits
    return "57" + digits[-10:] if len(digits) >= 10 else digits


def _wa_link(tel: str) -> str:
    if not tel:
        return "#"
    n = "".join(c for c in tel if c.isdigit())
    if len(n) == 10 and not n.startswith("57"):
        n = "57" + n
    return f"https://wa.me/{n}"


# ── ESCALADOS ──────────────────────────────────────────────

@admin_router.get("/escalados", response_class=HTMLResponse)
async def escalados_page(request: Request):
    _require_login(request)
    pool = await get_pool()
    items = await get_escalados(pool)

    rows = ""
    for e in items:
        ts = e.get("escalado_at")
        ts_str = ts.strftime("%d/%m/%Y %H:%M") if ts else ""
        rows += f"""
<tr class="item">
  <div class="item-info">
    <div class="item-nombre">{e['telefono']} <span class="badge badge-orange">Escalado</span></div>
    <div class="item-meta">📅 {ts_str}</div>
  </div>
  <div class="item-actions">
    <a href="{_wa_link(e['telefono'])}" target="_blank" class="btn btn-wa btn-sm">💬 WhatsApp</a>
    <button class="btn btn-green btn-sm" onclick="liberar('{e['telefono']}')">🔓 Liberar</button>
  </div>
</tr>"""
    if not rows:
        rows = '<div class="empty">No hay escalados activos 🎉</div>'

    content = f"""<div class="card"><div class="card-title">🚨 Escalados Activos</div>{rows}</div>
<script>
async function liberar(tel) {{
  var r = await fetch('/admin/escalados/'+encodeURIComponent(tel)+'/liberar', {{method:'POST'}});
  var d = await r.json();
  if(d.ok){{toast('Liberado: '+tel);setTimeout(function(){{location.reload()}},500);}}
  else toast('Error','err');
}}
</script>"""
    return HTMLResponse(_shell(content, request, "escalados"))


@admin_router.post("/escalados/{tel}/liberar")
async def escalados_liberar(tel: str, request: Request):
    _require_login(request)
    pool = await get_pool()
    ok = await liberar_escalado(pool, tel)
    return JSONResponse({"ok": ok})


# ── PAUSADOS ───────────────────────────────────────────────

@admin_router.get("/pausados", response_class=HTMLResponse)
async def pausados_page(request: Request):
    _require_login(request)
    pool = await get_pool()
    pausados = await get_pausados(pool)

    rows = ""
    for p in pausados:
        rows += f"""
<tr class="item" data-tel="{p['telefono']}">
  <div class="item-info">
    <div class="item-nombre">{p['telefono']} <span class="badge badge-red">Pausado</span></div>
  </div>
  <div class="item-actions">
    <a href="{_wa_link(p['telefono'])}" target="_blank" class="btn btn-wa btn-sm">💬 WhatsApp</a>
    <button class="btn btn-green btn-sm" onclick="reanudar('{p['telefono']}')">▶ Reanudar</button>
  </div>
</tr>"""
    if not rows:
        rows = '<div class="empty">No hay bots pausados 🎉</div>'

    content = f"""<div class="card">
<div class="card-title">⏸️ Bots Pausados</div>
<div class="search-box">
  <input type="text" class="inp" id="buscarPausado" placeholder="Buscar por número..." oninput="filtrarPausados()" style="margin:0" />
</div>
<div id="lista-pausados">{rows}</div>
<div id="sin-resultados" class="empty" style="display:none">Sin resultados</div>
</div>
<script>
async function reanudar(tel) {{
  var r = await fetch('/admin/pausados/'+encodeURIComponent(tel)+'/reanudar', {{method:'POST'}});
  var d = await r.json();
  if(d.ok){{toast('Reanudado: '+tel);setTimeout(function(){{location.reload()}},500);}}
  else toast('Error','err');
}}
function filtrarPausados() {{
  var q = document.getElementById('buscarPausado').value.trim().replace(/\\D/g,'');
  var items = document.querySelectorAll('#lista-pausados .item');
  var found = 0;
  items.forEach(function(it){{
    var t = (it.getAttribute('data-tel')||'').replace(/\\D/g,'');
    if(!q || t.includes(q)){{it.style.display='flex';found++;}}
    else{{it.style.display='none';}}
  }});
  document.getElementById('sin-resultados').style.display = found ? 'none' : 'block';
}}
</script>"""
    return HTMLResponse(_shell(content, request, "pausados"))


@admin_router.post("/pausados/{tel}/reanudar")
async def pausados_reanudar(tel: str, request: Request):
    _require_login(request)
    pool = await get_pool()
    ok = await reanudar_bot(pool, tel)
    return JSONResponse({"ok": ok})


# ── AGENDAR ────────────────────────────────────────────────

@admin_router.get("/agendar", response_class=HTMLResponse)
async def agendar_page(request: Request):
    _require_login(request)
    content = """<div class="card">
<div class="card-title">📅 Agendar Consulta</div>
<div class="grid-2">
  <div>
    <label>Tipo de Cita</label>
    <select id="agTipo" onchange="resetForm()">
      <option value="primera">Primera Consulta</option>
      <option value="control">Cita de Control</option>
    </select>
  </div>
  <div>
    <label>Fecha</label>
    <input type="date" id="agFecha" class="inp" onchange="cargarSlots()" />
  </div>
</div>
<div id="slotsContainer" style="display:none">
  <label id="slotsLabel">Horarios disponibles</label>
  <div class="slots-grid" id="slotsGrid"></div>
</div>
<div id="agForm" style="display:none">
  <div class="grid-2">
    <div><label>Nombre completo</label><input type="text" id="agNombre" class="inp" placeholder="Nombre del paciente" /></div>
    <div><label>Teléfono (WhatsApp)</label><input type="tel" id="agTelefono" class="inp" placeholder="+573001234567" /></div>
  </div>
  <label>Correo electrónico</label>
  <input type="email" id="agEmail" class="inp" placeholder="correo@ejemplo.com" />
  <label>Motivo (opcional)</label>
  <input type="text" id="agMotivo" class="inp" placeholder="Ej: dolor de espalda, migraña..." />
  <button class="btn btn-green" style="width:100%;padding:13px;font-size:15px" onclick="confirmar()">✅ Confirmar Cita</button>
  <div class="msg-inline" id="agMsg"></div>
</div>
</div>
<script>
var selSlot = null, selHora = null, selTipo = null;
var VALIDOS = [2,3,5,6];
var FESTIVOS = ['2026-01-01','2026-01-12','2026-03-23','2026-04-02','2026-04-03','2026-05-01','2026-05-18','2026-06-08','2026-06-15','2026-06-29','2026-07-20','2026-08-07','2026-08-17','2026-10-12','2026-11-02','2026-11-16','2026-12-08','2026-12-25'];
var VACACIONES_INICIO = '2026-07-23';
var VACACIONES_FIN = '2026-07-31';

function fechaValida(f) { var d = new Date(f+'T12:00:00'); if(f>=VACACIONES_INICIO && f<=VACACIONES_FIN) return false; return VALIDOS.includes(d.getDay()) && !FESTIVOS.includes(f); }

function proxValido(desde) {
  var d = new Date(desde+'T12:00:00');
  for(var i=0;i<60;i++) { var t = new Date(d.getTime()+i*86400000); var s = t.toISOString().split('T')[0]; if(s>=VACACIONES_INICIO && s<=VACACIONES_FIN) continue; if(VALIDOS.includes(t.getDay())&&!FESTIVOS.includes(s)) return s; }
  return desde;
}

var hoy = new Date().toISOString().split('T')[0];
var agFecha = document.getElementById('agFecha');
agFecha.min = hoy;
agFecha.value = proxValido(hoy);
agFecha.addEventListener('input', function() {
  if(this.value>=VACACIONES_INICIO && this.value<=VACACIONES_FIN) { this.value = proxValido(this.value); toast('Vacaciones del 23 al 31 de julio. Se retoman consultas el 1 de agosto.','err'); }
  else if(!fechaValida(this.value)) { this.value = proxValido(this.value); toast('Solo atendemos martes, miércoles, viernes y sábado','err'); }
  cargarSlots();
});

function resetForm() { selSlot=null;selHora=null;document.getElementById('agForm').style.display='none';cargarSlots(); }

async function cargarSlots() {
  var tipo = document.getElementById('agTipo').value;
  selTipo = tipo;
  var fecha = document.getElementById('agFecha').value;
  if(!fecha) return;
  var cont = document.getElementById('slotsContainer');
  var grid = document.getElementById('slotsGrid');
  var label = document.getElementById('slotsLabel');
  cont.style.display = 'block';
  grid.innerHTML = '<div style="color:#888;padding:8px">Cargando horarios...</div>';
  selSlot=null;selHora=null;document.getElementById('agForm').style.display='none';
  try {
    if(tipo === 'primera') {
      label.textContent = 'Horarios disponibles (Cal.com · 30 min)';
      var r = await fetch('/admin/slots?fecha='+fecha+'&tipo=primera');
      var d = await r.json();
      var slots = d.slots || [];
      if(!slots.length){grid.innerHTML='<div style="color:#666;padding:8px">Sin disponibilidad para esta fecha</div>';return;}
      grid.innerHTML = slots.map(function(s){
        var h = new Date(s).toLocaleTimeString('es-CO',{hour:'2-digit',minute:'2-digit',hour12:true,timeZone:'America/Bogota'});
        return '<button class="slot-btn" data-start="'+s+'" onclick="selPrimera(this)">'+h+'</button>';
      }).join('');
    } else {
      label.textContent = 'Horarios disponibles (Control · 15 min)';
      var r = await fetch('/admin/slots?fecha='+fecha+'&tipo=control');
      var d = await r.json();
      var slots = d.slots || [];
      if(!slots.length){grid.innerHTML='<div style="color:#666;padding:8px">Sin disponibilidad</div>';return;}
      grid.innerHTML = slots.map(function(h){
        return '<button class="slot-btn" onclick="selControl(this)">'+h.substring(0,5)+'</button>';
      }).join('');
    }
  } catch(e) { grid.innerHTML='<div style="color:#f44336;padding:8px">Error cargando horarios</div>'; }
}

function selPrimera(btn) {
  selSlot = btn.dataset.start; selHora = null;
  document.querySelectorAll('.slot-btn').forEach(function(b){b.classList.remove('sel')});
  btn.classList.add('sel');
  document.getElementById('agForm').style.display = 'block';
  document.getElementById('agMsg').style.display = 'none';
}
function selControl(btn) {
  selHora = btn.textContent.trim(); selSlot = null;
  document.querySelectorAll('.slot-btn').forEach(function(b){b.classList.remove('sel')});
  btn.classList.add('sel');
  document.getElementById('agForm').style.display = 'block';
  document.getElementById('agMsg').style.display = 'none';
}

async function confirmar() {
  var nombre = document.getElementById('agNombre').value.trim();
  var telefono = document.getElementById('agTelefono').value.trim();
  var email = document.getElementById('agEmail').value.trim();
  var motivo = document.getElementById('agMotivo').value.trim();
  var fecha = document.getElementById('agFecha').value;
  var msg = document.getElementById('agMsg');
  if(!nombre||!telefono||!fecha){ msg.className='msg-inline msg-err';msg.style.display='block';msg.textContent='Complete nombre, teléfono y fecha';return; }
  if(selTipo==='primera' && !selSlot){ msg.className='msg-inline msg-err';msg.style.display='block';msg.textContent='Seleccione un horario';return; }
  if(selTipo==='control' && !selHora){ msg.className='msg-inline msg-err';msg.style.display='block';msg.textContent='Seleccione un horario';return; }
  msg.style.display='block';msg.style.background='#1a1a2a';msg.style.color='#aaa';msg.style.border='1px solid #444';msg.textContent='Agendando...';
  try {
    var r = await fetch('/admin/agendar', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tipo:selTipo,nombre,telefono,email,fecha,motivo,start:selSlot,hora:selHora})});
    var d = await r.json();
    if(d.id||d.uid||d.ok){msg.className='msg-inline msg-ok';msg.textContent='✅ Cita confirmada para '+nombre;setTimeout(function(){location.reload()},1500);}
    else{msg.className='msg-inline msg-err';msg.textContent=(d.error&&d.error.message)||d.error||'Error al agendar';}
  } catch(e) { msg.className='msg-inline msg-err';msg.textContent='Error de conexión'; }
}
cargarSlots();
</script>"""
    return HTMLResponse(_shell(content, request, "agendar"))
@admin_router.get("/slots")
async def slots(request: Request, fecha: str = "", tipo: str = "primera"):
    _require_login(request)

    if tipo == "control":
        try:
            pool = await get_pool()
            horas = await get_control_slots(pool, fecha)
            return JSONResponse({"slots": horas})
        except Exception as e:
            return JSONResponse({"slots": [], "error": str(e)})

    # tipo == primera → Cal.com API
    try:
        import logging
        logger = logging.getLogger("uvicorn.error")
        params = {
            "start": fecha,
            "end": _next_day(fecha),
            "username": config.CAL_USERNAME,
            "eventTypeSlug": config.CAL_EVENT_SLUG,
        }
        headers = {"cal-api-version": config.CAL_API_VERSION_SLOTS}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.cal.com/v2/slots",
                params=params,
                headers=headers,
            )
            logger.info(f"Cal.com response status: {resp.status_code}")
            data = resp.json()
            slots = []
            if isinstance(data, dict):
                slots_data = data.get("data", data)
                if isinstance(slots_data, dict):
                    for day, times in slots_data.items():
                        if day == fecha:
                            slots.extend(t.get("start", t.get("time", t)) for t in (times or []))
            logger.info(f"Slots found: {len(slots)}")
            return JSONResponse({"slots": slots})
    except Exception as e:
        logger.error(f"Slots error: {e}")
        return JSONResponse({"slots": [], "error": str(e)})


def _next_day(date_str: str) -> str:
    from datetime import timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@admin_router.post("/agendar")
async def agendar_post(request: Request):
    _require_login(request)
    data = await request.json()
    pool = await get_pool()
    tipo = data.get("tipo", "primera")

    if tipo == "control":
        row = await insert_control(
            pool,
            nombre=data.get("nombre", ""),
            telefono=data.get("telefono", ""),
            email=data.get("email", ""),
            fecha=data.get("fecha", ""),
            hora=data.get("hora", ""),
            motivo=data.get("motivo", ""),
        )
        return JSONResponse({"ok": True, "id": row["id"]})

    # tipo == primera → Cal.com booking
    try:
        headers = {
            "cal-api-version": config.CAL_API_VERSION_BOOKINGS,
            "Authorization": f"Bearer {config.CAL_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "start": data.get("start", ""),
            "attendee": {
                "name": data.get("nombre", ""),
                "email": data.get("email", ""),
                "phoneNumber": data.get("telefono", ""),
                "timeZone": config.BOT_TIMEZONE,
            },
            "eventTypeSlug": config.CAL_EVENT_SLUG,
            "username": config.CAL_USERNAME,
            "metadata": {"motivo": data.get("motivo", "")},
        }
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.cal.com/v2/bookings",
                headers=headers,
                json=body,
            )
            result = resp.json()
            if resp.status_code in (200, 201) or result.get("status") == "success" or result.get("uid"):
                return JSONResponse({"ok": True, "uid": result.get("uid", "ok")})
            return JSONResponse({"ok": False, "error": result.get("message", "Error al agendar")})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})


# ── RECIENTES ──────────────────────────────────────────────

@admin_router.get("/recientes", response_class=HTMLResponse)
async def recientes_page(request: Request):
    _require_login(request)
    pool = await get_pool()
    recs = await get_recientes(pool)

    rows = ""
    for c in recs:
        ts = c.get("ultimo_mensaje_at")
        ts_str = ts.strftime("%d/%m %H:%M") if ts else ""
        tel = c['telefono']
        msg = (c.get("ultimo_mensaje") or "")[:100]
        pausado = await is_pausado(pool, tel)
        pause_btn = (
            '<button class="btn btn-green btn-sm" onclick="togglePausaReciente(\'{}\', false)">▶ Reanudar</button>'.format(tel)
            if pausado else
            '<button class="btn btn-red btn-sm" onclick="togglePausaReciente(\'{}\', true)">⏸ Pausar</button>'.format(tel)
        )
        pausado_badge = ' <span class="badge badge-red">Pausado</span>' if pausado else ''
        rows += f"""
<tr class="item" data-tel="{tel}">
  <div class="item-info">
    <div class="item-nombre" style="display:flex;align-items:center;gap:8px">+{clean_tel(tel)}{pausado_badge} <span class="badge badge-recentes" style="background:rgba(95,168,127,.12);color:#5fa87f">{c['total_mensajes']} msgs</span></div>
    <div class="item-meta">{ts_str}</div>
    {f'<div class="item-msg" style="background:#111;padding:8px 12px;border-radius:8px;margin-top:6px;max-width:450px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;border-left:3px solid #5fa87f">💬 {msg}</div>' if msg else ''}
  </div>
  <div class="item-actions">
    <a href="{_wa_link(tel)}" target="_blank" class="btn btn-wa btn-sm">💬 WhatsApp</a>
    {pause_btn}
  </div>
</tr>"""
    if not rows:
        rows = '<div class="empty">Sin conversaciones recientes</div>'

    content = f"<div class=\"card\"><div class=\"card-title\">💬 Conversaciones Recientes (48h)</div>{rows}</div>"
    content += """
<script>
async function togglePausaReciente(tel, pausar) {
  var accion = pausar ? 'Pausar' : 'Reanudar';
  if(!confirm('¿'+accion+' el bot para '+tel+'?')) return;
  var endpoint = pausar ? '/admin/recientes/'+encodeURIComponent(tel)+'/pausar' : '/admin/pausados/'+encodeURIComponent(tel)+'/reanudar';
  var r = await fetch(endpoint, {method:'POST'});
  var d = await r.json();
  if(d.ok){toast(accion+'ado: '+tel);setTimeout(function(){location.reload()},500);}
  else toast('Error','err');
}
</script>"""
    return HTMLResponse(_shell(content, request, "recientes"))


# ── REDIRECTS ──────────────────────────────────────────────

@admin_router.post("/recientes/{tel}/pausar")
async def recientes_pausar(tel: str, request: Request):
    _require_login(request)
    pool = await get_pool()
    ok = await pausar_bot(pool, tel)
    return JSONResponse({"ok": ok})


@admin_router.get("/", response_class=HTMLResponse)
async def admin_root():
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@admin_router.get("/{path:path}", response_class=HTMLResponse)
async def catch_all(path: str):
    return RedirectResponse(url="/admin/dashboard", status_code=302)
