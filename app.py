import os, json, re
from datetime import datetime, date, timedelta

from flask import Flask, render_template_string, url_for, request, redirect, session
   
from werkzeug.utils import secure_filename

# -----------------------------
# Helpers de fechas y estados
# -----------------------------
def parse_ddmmyyyy(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except ValueError:
        return None

def format_ddmmyyyy(d):
    return d.strftime("%d-%m-%Y") if isinstance(d, (datetime, date)) else ""

def dias_restantes(fecha_txt):
    f = parse_ddmmyyyy(fecha_txt)
    if not f:
        return None
    return (f - date.today()).days

def status_color_por_vencimiento(fecha_txt):
    f = parse_ddmmyyyy(fecha_txt)
    if not f:
        return ("Sin fecha", "secondary")
    hoy = date.today()
    if f < hoy:
        return ("Vencido", "danger")
    dias = (f - hoy).days
    if dias <= 30:
        return ("Por vencer", "warning")
    return ("Vigente", "success")

def parse_km(s):
    s = (s or "").replace(".", "").replace(" ", "").strip()
    try:
        return int(s)
    except ValueError:
        return 0

def fmt_km(n):
    try:
        return "{:,}".format(int(n or 0)).replace(",", ".")
    except (ValueError, TypeError):
        return "0"

def km_restantes(km_actual, km_proximo):
    try:
        km_actual = int(km_actual or 0)
        km_proximo = int(km_proximo or 0)
    except ValueError:
        return None
    if km_proximo <= 0:
        return None
    return km_proximo - km_actual

def status_km(km_actual, km_proximo):
    try:
        km_actual = int(km_actual or 0)
        km_proximo = int(km_proximo or 0)
    except ValueError:
        return ("Sin dato", "secondary")

    if km_proximo <= 0:
        return ("Sin dato", "secondary")
    if km_actual >= km_proximo:
        return ("Vencido", "danger")
    if (km_proximo - km_actual) <= 1000:
        return ("Por vencer", "warning")
    return ("Vigente", "success")

def docs_overall(v):
    orden = {"danger": 3, "warning": 2, "success": 1, "secondary": 0}
    peor = ("Sin fecha", "secondary")
    peor_fecha = None

    if not v:
        return peor

    docs = [
        v.get("rev_tecnica_venc", ""),
        v.get("permiso_circ_venc", ""),
        v.get("seguro_obl_venc", "")
    ]

    for fecha in docs:
        st, cls = status_color_por_vencimiento(fecha)
        if orden.get(cls, 0) > orden.get(peor[1], 0):
            peor = (st, cls)
            peor_fecha = fecha
            if cls == "danger":
                break

    if peor_fecha:
        dias = dias_restantes(peor_fecha)
        if dias is not None:
            if dias < 0:
                peor = (f"{peor[0]} (hace {-dias} días)", peor[1])
            elif dias == 0:
                peor = (f"{peor[0]} (vence hoy)", peor[1])
            elif dias <= 30:
                peor = (f"{peor[0]} (faltan {dias} días)", peor[1])

    return peor

def mant_overall(v):
    orden = {"danger": 3, "warning": 2, "success": 1, "secondary": 0}
    peor = ("Sin dato", "secondary", None)
    km_actual = v.get("km", 0)

    if not v or "mant" not in v:
        return (peor[0], peor[1])

    items = ["aceite","filtro_aceite","filtro_combustible","filtro_aire","filtro_polen","pastillas_freno","correa_distribucion"]

    for k in items:
        item = v["mant"].get(k, {})
        proximo = item.get("proximo_km", 0)
        st, cls = status_km(km_actual, proximo)
        if orden.get(cls, 0) > orden.get(peor[1], 0):
            peor = (st, cls, proximo)
            if cls == "danger":
                break

    texto, clase, prox = peor
    if prox is not None:
        diferencia = prox - km_actual
        if diferencia < 0:
            texto = f"{texto} (hace {-diferencia} km)"
        elif diferencia == 0:
            texto = f"{texto} (es ahora)"
        elif diferencia <= 1000:
            texto = f"{texto} (faltan {diferencia} km)"

    return (texto, clase)

# -----------------------------
# Imágenes / uploads
# -----------------------------
UPLOAD_FOLDER = os.path.join("static", "vehiculos")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def listar_imagenes():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    return [f for f in os.listdir(UPLOAD_FOLDER) if allowed_file(f)]

# -----------------------------
# Helpers vehículo
# -----------------------------
def veh_display(v: dict) -> str:
    marca = (v.get("marca") or "").strip()
    modelo = (v.get("modelo") or "").strip()
    anio = str(v.get("anio") or "").strip()
    if marca or modelo or anio:
        return " ".join([x for x in [marca, modelo, anio] if x]).strip()
    return (v.get("modelo") or "").strip()

def ensure_vehicle_fields(v: dict):
    v.setdefault("marca", "")
    v.setdefault("modelo", (v.get("modelo") or ""))

    if not v.get("anio"):
        m = re.search(r"(19|20)\d{2}$", (v.get("modelo","") or "").strip())
        if m:
            v["anio"] = int(m.group(0))
        else:
            v.setdefault("anio", "")

def ensure_mant_dict(_v):
    _v.setdefault("mant", {})
    def item():
        return {"ultimo_km": 0, "ultimo_fecha": "", "intervalo_km": 0, "proximo_km": 0, "observaciones": ""}

    _v["mant"].setdefault("aceite",               item())
    _v["mant"].setdefault("filtro_aceite",        item())
    _v["mant"].setdefault("filtro_combustible",   item())
    _v["mant"].setdefault("filtro_aire",          item())
    _v["mant"].setdefault("filtro_polen",         item())
    _v["mant"].setdefault("pastillas_freno",      item())
    _v["mant"].setdefault("correa_distribucion",  item())

# -----------------------------
# App / sesión
# -----------------------------
app = Flask(__name__)

from flask import session, g

from flask import current_app

def get_vehiculos():
    # siempre usa lo que cargó _sync_tenant_files en g.vehiculos
    return list(getattr(g, "vehiculos", []) or [])

def save_vehiculos(vehiculos_list):
    # guarda en el archivo del tenant actual
    path = current_app.config["VEHICULOS_FILE"]
    save_json_list(path, vehiculos_list)

def find_vehiculo(vehiculos_list, vid: int):
    return next((x for x in vehiculos_list if int(x.get("id", 0)) == int(vid)), None)

def next_id(lista):
    return (max([int(x.get("id", 0)) for x in lista]) + 1) if lista else 1

# Carpeta donde estarán los JSON por cuenta
DATA_DIR = os.path.join(app.root_path, "data")
os.makedirs(DATA_DIR, exist_ok=True)

TENANT_DEFAULT = "victor"  # si no hay tenant elegido, usa Victor

def get_tenant() -> str:
    t = (session.get("tenant") or "").strip().lower()
    if t in ("victor", "rodrigo", "rutasur"):
        return t
    return TENANT_DEFAULT

def tenant_file(kind: str) -> str:
    """
    kind: 'vehiculos' | 'gastos' | 'finanzas' | 'contratos' | 'empleados' | 'eventos' | 'manuales'
    retorna el path data/<kind>_<tenant>.json
    """
    return os.path.join(DATA_DIR, f"{kind}_{get_tenant()}.json")

def load_json_list(path: str):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_json_list(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_vehiculos():
    # Siempre desde g (ya cargado por _sync_tenant_files)
    return getattr(g, "vehiculos", []) or []

def save_vehiculos(vehs):
    # Guarda en el archivo del tenant actual
    save_json_list(app.config["VEHICULOS_FILE"], vehs)
    g.vehiculos = vehs

@app.before_request
def _sync_tenant_files():
    """
    En cada request:
    - define qué archivos usar según la cuenta elegida
    - carga datos del tenant y los deja disponibles
    """
    app.config["VEHICULOS_FILE"] = tenant_file("vehiculos")
    app.config["GASTOS_FILE"]    = tenant_file("gastos")
    app.config["FINANZAS_FILE"]  = tenant_file("finanzas")
    app.config["CONTRATOS_FILE"] = tenant_file("contratos")
    app.config["EMPLEADOS_FILE"] = tenant_file("empleados")
    app.config["EVENTOS_FILE"]   = tenant_file("eventos")
    app.config["MANUALES_FILE"]  = tenant_file("manuales")

    # Vehículos: siempre del tenant actual
    vehs = load_json_list(app.config["VEHICULOS_FILE"])

    # Normalizar estructura para evitar tablas vacías / errores
    for v in vehs:
        ensure_vehicle_fields(v)
        ensure_mant_dict(v)
        v.setdefault("rev_tecnica_venc", "")
        v.setdefault("permiso_circ_venc", "")
        v.setdefault("seguro_obl_venc", "")
        v.setdefault("notas", "")

    g.vehiculos = vehs

# clave única, no la pises después
app.secret_key = "ruta-sur-2026-clave-larga-cambiame-por-una-random-muy-larga"
app.permanent_session_lifetime = timedelta(days=30)

# -----------------------------
# Protección global (login + tenant)
# -----------------------------
@app.before_request
def proteger_todo():
    allow = {
        "auth.login", "auth.logout", "auth.elegir", "auth.set_tenant",
        "static", "favicon"
    }
    ep = request.endpoint or ""
    if ep in allow or ep.startswith("static"):
        return None

    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))

    if not session.get("tenant"):
        return redirect(url_for("auth.elegir"))

    return None

# -----------------------------
# Data por cuenta (tenant)
# -----------------------------
DATA_DIR = os.path.join(app.root_path, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def get_tenant():
    return session.get("tenant") or "rutasur"

def get_data_file():
    # data/data_victor.json, data/data_rodrigo.json, data/data_rutasur.json
    return os.path.join(DATA_DIR, f"data_{get_tenant()}.json")

def cargar_datos():
    data_file = get_data_file()
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = []

    # normalizar
    for v in data:
        ensure_vehicle_fields(v)
        v.setdefault("rev_tecnica_venc", "")
        v.setdefault("permiso_circ_venc", "")
        v.setdefault("seguro_obl_venc", "")
        ensure_mant_dict(v)

    return data

def guardar_datos(data):
    data_file = get_data_file()
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def next_id(lista):
    return (max([x["id"] for x in lista]) + 1) if lista else 1

# -----------------------------
# Layout base (tu diseño)
# -----------------------------
LAYOUT_BASE = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Ruta Sur Rent A Car — Panel Administrador</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css">

  <link rel="icon" type="image/png" sizes="32x32" href="{{ url_for('static', filename='img/favicon.png') }}">
  <link rel="shortcut icon" type="image/png" href="{{ url_for('static', filename='img/favicon.png') }}">
  <link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='img/apple-touch-icon.png') }}">

  <style>
    body { background:#0f172a; color:#e5e7eb; }
    .topbar {
      background: linear-gradient(to bottom, #0F172A, #1E3A8A);
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .logo-chip {
      display:flex;align-items:center;justify-content:center;
      padding:6px 10px;border-radius:12px;
      background: rgba(255, 255, 255, 0.24);
      border: 1px solid rgba(255, 255, 255, 0.25);
      backdrop-filter: blur(6px);
    }
    .img-logo { height:110px; filter: drop-shadow(0 0 6px rgba(255, 255, 255, 0.4)); }
    .sidebar {
      width:260px;
      background: linear-gradient(to bottom, #0F172A, #1E3A8A);
      min-height:100vh;
      border-right:1px solid rgba(255,255,255,0.08);
    }
    .sidebar a { color:#94a3b8; text-decoration:none; padding:.5rem .75rem; border-radius:.5rem; }
    .sidebar a.active, .sidebar a:hover { background:rgba(255,255,255,.06); color:#fff; }
    .content { padding:24px; }
    .brand { font-weight:700; letter-spacing:.2px; color:#ffffff; }

    .vehiculo-card {
      cursor: pointer;
      border-radius: 1rem;
      border: 1px solid transparent;
      transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease, background-color .12s ease;
    }
    .vehiculo-card:hover {
      transform: translateY(-4px);
      box-shadow: 0 .5rem 1.2rem rgba(15,23,42,.45);
      border-color: #7dd3fc;
      background-color: #e0f2fe;
    }
  </style>
</head>
<body>
  <div class="topbar py-2">
    <div class="container-fluid d-flex align-items-center justify-content-between">
      <div class="d-flex align-items-center gap-3">
        <div class="logo-chip">
          <img class="img-logo" src="{{ url_for('static', filename='img/logo.png') }}" alt="Ruta Sur">
        </div>
        <div>
          <div class="brand">Ruta Sur Rent A Car — Panel Administrador</div>
          <div class="small" style="color:#94a3b8;">
            Cuenta: {{ session.get('tenant','—') }} ·
            <a href="{{ url_for('auth.elegir') }}" style="color:#7dd3fc; text-decoration:none;">cambiar</a> ·
            <a href="{{ url_for('auth.logout') }}" style="color:#fecaca; text-decoration:none;">salir</a>
          </div>
        </div>
      </div>
      <div class="text-secondary small">v1 • con login</div>
    </div>
  </div>

  <div class="d-flex">
    <aside class="sidebar p-3">
      <nav class="nav flex-column gap-1">
        <a class="{{ 'active' if active=='inicio' else '' }}" href="{{ url_for('inicio.inicio') }}">Inicio</a>
        <a class="{{ 'active' if active=='vehiculos' else '' }}" href="{{ url_for('admin_vehiculos') }}">Vehículos</a>
        <a class="{{ 'active' if active=='calendario' else '' }}" href="{{ url_for('cal.home') }}">Calendario</a>
        <a class="{{ 'active' if active=='finanzas' else '' }}" href="{{ url_for('finanzas.lista') }}">Finanzas</a>
        <a class="{{ 'active' if active=='gastos' else '' }}" href="{{ url_for('gastos.lista') }}">Gastos</a>
        <a class="{{ 'active' if active=='contratos' else '' }}" href="{{ url_for('contratos.lista') }}">Contratos</a>
        <a class="{{ 'active' if active=='manuales' else '' }}" href="{{ url_for('manuales.home') }}">Manuales</a>
        <a class="{{ 'active' if active=='empleados' else '' }}" href="{{ url_for('empleados.lista') }}">Empleados</a>
      </nav>
    </aside>

    <main class="flex-grow-1 content">
      {{ content|safe }}
    </main>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

def render_admin(content_html, active="", **ctx):
    return render_template_string(LAYOUT_BASE, content=content_html, active=active, **ctx)

app.config["LAYOUT_BASE"] = LAYOUT_BASE

# -----------------------------
# Registrar auth blueprint (login)
# -----------------------------
from auth_bp import auth_bp
app.register_blueprint(auth_bp)

# -----------------------------
# Globals Jinja
# -----------------------------
app.jinja_env.globals["status_color_por_vencimiento"] = status_color_por_vencimiento
app.jinja_env.globals["status_km"] = status_km
app.jinja_env.globals["mant_overall"] = mant_overall
app.jinja_env.globals["docs_overall"] = docs_overall
app.jinja_env.globals["dias_restantes"] = dias_restantes
app.jinja_env.globals["km_restantes"] = km_restantes
app.jinja_env.globals["fmt_km"] = fmt_km
app.jinja_env.globals["veh_display"] = veh_display

# -----------------------------
# Blueprints existentes (los tuyos)
# -----------------------------
app.config["EVENTOS_FILE"] = os.path.join(app.root_path, "data_eventos.json")

from calendario_bp import cal_bp
app.register_blueprint(cal_bp, url_prefix="/admin/calendario")

from inicio_bp import inicio_bp
app.register_blueprint(inicio_bp)

from contratos_bp import contratos_bp
app.register_blueprint(contratos_bp)

from finanzas_bp import finanzas_bp
app.register_blueprint(finanzas_bp)

from manuales_bp import manuales_bp
app.register_blueprint(manuales_bp)

from empleados_bp import empleados_bp
app.register_blueprint(empleados_bp)

from gastos_bp import gastos_bp
app.register_blueprint(gastos_bp)

# -----------------------------
# Templates (contenido)
# -----------------------------
ADMIN_VEHICULOS = r"""
<div class="d-flex align-items-center justify-content-between mb-2">
  <h3 class="mb-0 text-white">Vehículos</h3>
</div>

<div class="d-flex align-items-center justify-content-between mb-3 mt-2">
  <div class="d-flex flex-wrap gap-2">
    <a href="{{ url_for('admin_vehiculos') }}"
       class="btn btn-outline-light btn-sm {% if not filtro_sel %}active{% endif %}">
      Todos ({{ counts.total }})
    </a>
    <a href="{{ url_for('admin_vehiculos', filtro='verde') }}"
       class="btn btn-success btn-sm {% if filtro_sel=='verde' %}active{% endif %}">
      Verdes ({{ counts.verde }})
    </a>
    <a href="{{ url_for('admin_vehiculos', filtro='amarillo') }}"
       class="btn btn-warning btn-sm {% if filtro_sel=='amarillo' %}active{% endif %}">
      Amarillos ({{ counts.amarillo }})
    </a>
    <a href="{{ url_for('admin_vehiculos', filtro='rojo') }}"
       class="btn btn-danger btn-sm {% if filtro_sel=='rojo' %}active{% endif %}">
      Rojos ({{ counts.rojo }})
    </a>
  </div>

  <a href="{{ url_for('nuevo') }}" class="btn btn-primary btn-sm flex-shrink-0" style="white-space:nowrap;">
     + Agregar vehículo
  </a>
</div>

<div class="row g-4">
  {% for v in vehiculos %}
  <div class="col-12 col-md-6 col-lg-4">
    <a href="{{ url_for('detalle', vid=v.id) }}" class="text-decoration-none text-dark">
      <div class="card border-0 h-100 vehiculo-card">
        {% if v.foto %}
          <img src="{{ url_for('static', filename='vehiculos/' + v.foto) }}"
               alt="foto {{ veh_display(v) }}"
               style="width:100%;aspect-ratio:16/9;object-fit:contain;background:transparent">
        {% endif %}

        <div class="card-body">
          <h5 class="card-title mb-2">{{ veh_display(v) }}</h5>
          <p class="mb-2">{{ v.patente }}</p>

          <ul class="list-unstyled mb-3">
            <li>Kilometraje: <span class="fw-semibold">{{ fmt_km(v.km) }} km</span></li>
          </ul>

          {% set stg, clsg = mant_overall(v) %}
          {% set std, clsd = docs_overall(v) %}
          <div class="d-flex flex-column gap-1 mb-3">
            <span class="badge bg-{{ clsg }}">Mantención: {{ stg }}</span>
            <span class="badge bg-{{ clsd }}">Documentación: {{ std }}</span>
          </div>

          <div class="d-flex gap-2">
            <a class="btn btn-outline-danger btn-sm"
               href="{{ url_for('eliminar', vid=v.id) }}"
               onclick="event.stopPropagation();">
               Eliminar
            </a>
          </div>
        </div>
      </div>
    </a>
  </div>
  {% endfor %}
</div>
"""

FORM_NUEVO = r"""
<div class="container py-1">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h3 class="mb-0 text-white">Agregar vehículo</h3>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('admin_vehiculos') }}">Volver</a>
  </div>

  <div class="card p-4 border-0" style="border-radius:1rem;">
    <form method="post" enctype="multipart/form-data">
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Marca</label>
          <input name="marca" class="form-control" required placeholder="Kia">
        </div>
        <div class="col-md-4">
          <label class="form-label">Modelo</label>
          <input name="modelo" class="form-control" required placeholder="Sorento">
        </div>
        <div class="col-md-4">
          <label class="form-label">Año</label>
          <input name="anio" type="number" class="form-control" required placeholder="2012" min="1980" max="2099">
        </div>

        <div class="col-md-3">
          <label class="form-label">Patente</label>
          <input name="patente" class="form-control" required placeholder="KIA-SOR-2012">
        </div>
        <div class="col-md-3">
          <label class="form-label">Kilometraje</label>
          <input name="km" type="text" class="form-control km" inputmode="numeric" autocomplete="off" required placeholder="185.300">
        </div>

        <div class="col-12">
          <label class="form-label">Notas (opcional)</label>
          <textarea name="notas" class="form-control" rows="2" placeholder="Observaciones..."></textarea>
        </div>

        <div class="col-12">
          <label class="form-label mb-1">Imagen del vehículo</label>
          <div class="row g-3 align-items-start">
            <div class="col-md-6">
              <div class="form-text mb-1">A) Elegir una imagen existente de la carpeta:</div>
              <select name="foto_select" id="foto_select" class="form-select">
                <option value="">— Elegir de la carpeta —</option>
                {% for nombre in imagenes %}
                  <option value="{{ nombre }}">{{ nombre }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="col-md-6">
              <div class="form-text mb-1">B) O subir una imagen desde tu equipo:</div>
              <input name="foto_file" id="foto_file" type="file" class="form-control" accept=".jpg,.jpeg,.png,.webp">
            </div>

            <div class="col-12">
              <div class="mt-2 p-2 border rounded bg-body-tertiary" style="max-width: 220px;">
                <div class="small text-secondary mb-1">Vista previa</div>
                <img id="veh_preview" alt="Preview" style="width:200px;height:120px;object-fit:contain;display:none;background:#fff;">
              </div>
            </div>
          </div>
        </div>

        <div class="mt-3 d-flex gap-2">
          <button class="btn btn-primary">Guardar</button>
          <a class="btn btn-outline-secondary" href="{{ url_for('admin_vehiculos') }}">Cancelar</a>
        </div>
      </div>
    </form>
  </div>
</div>

<script>
(function(){
  function fmtKM(val){ val=(val||"").replace(/\\D+/g,""); return val.replace(/\\B(?=(\\d{3})+(?!\\d))/g,"."); }
  function rawKM(val){ return (val||"").replace(/\\./g,""); }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('input.km').forEach(inp=>{
      inp.value = fmtKM(inp.value);
      inp.addEventListener('input', ()=>{
        const start = inp.selectionStart;
        const old = inp.value;
        const digits = old.replace(/\\D+/g,'');
        const formatted = fmtKM(digits);
        const right = old.length - start;
        inp.value = formatted;
        const newPos = Math.max(0, inp.value.length - right);
        inp.setSelectionRange(newPos, newPos);
      });
      if (inp.form){
        inp.form.addEventListener('submit', ()=>{ inp.value = rawKM(inp.value); });
      }
    });

    const sel = document.getElementById('foto_select');
    const file = document.getElementById('foto_file');
    const img = document.getElementById('veh_preview');

    function showPreview(src){
      if (!img) return;
      if (src) { img.src = src; img.style.display = 'block'; }
      else { img.removeAttribute('src'); img.style.display = 'none'; }
    }

    if (sel) sel.addEventListener('change', ()=>{
      if (file) file.value = '';
      const v = sel.value ? ('/static/vehiculos/' + sel.value) : '';
      showPreview(v);
    });

    if (file) file.addEventListener('change', ()=>{
      if (sel) sel.value = '';
      const f = file.files && file.files[0];
      if (f) showPreview(URL.createObjectURL(f)); else showPreview('');
    });
  });
})();
</script>
"""

CONFIRMAR_ELIMINAR = r"""
<div class="container py-1">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h3 class="mb-0 text-white">Eliminar vehículo</h3>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('admin_vehiculos') }}">Volver</a>
  </div>

  <div class="card p-4 border-0" style="border-radius:1rem;">
    <p>¿Seguro que quieres eliminar el vehículo {{ veh_display(v) }} ({{ v.patente }})?</p>
    <form method="post">
      <div class="d-flex gap-2">
        <button class="btn btn-danger">Sí, eliminar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('admin_vehiculos') }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>
"""

DETALLE = r"""
<div class="container py-1">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h3 class="mb-0 text-white">Detalle vehículo</h3>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('admin_vehiculos') }}">Volver</a>
  </div>

  <div class="card p-4 mb-4 border-0" style="border-radius:1rem;">
    <div class="d-flex align-items-center justify-content-between gap-3 mb-3">
      <div class="d-flex align-items-center gap-3">
        {% if v.foto %}
          <img src="{{ url_for('static', filename='vehiculos/' + v.foto) }}" alt="foto {{ veh_display(v) }}"
               style="height:80px; width:120px; object-fit:contain; background:transparent;">
        {% endif %}
        <div>
          <h4 class="mb-1">{{ veh_display(v) }}</h4>
          <div class="text-muted">{{ v.patente }}</div>
        </div>
      </div>

      <div class="d-flex flex-column align-items-end gap-2">
        {% set stg, clsg = mant_overall(v) %}
        <span class="badge bg-{{ clsg }} px-3 py-2">Mantención: {{ stg }}</span>

        {% set std, clsd = docs_overall(v) %}
        <span class="badge bg-{{ clsd }} px-3 py-2">Documentación: {{ std }}</span>
      </div>
    </div>

    <hr>
    <div class="row">
      <div class="col-md-6">
        <h5>Datos generales</h5>
        <div>Kilometraje: <span class="fw-semibold">{{ fmt_km(v.km) }} km</span></div>
      </div>
      <div class="col-md-6">
        <h5>Notas</h5>
        <div>{{ v.notas or "—" }}</div>
      </div>
    </div>
  </div>

  <div class="card p-4 border-0" style="border-radius:1rem;">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h4 class="mb-0">Documentación</h4>
      <a class="btn btn-primary btn-sm" href="{{ url_for('editar_documentos', vid=v.id) }}">Editar fechas</a>
    </div>

    <div class="table-responsive">
      <table class="table table-dark table-striped align-middle mb-0">
        <thead>
          <tr>
            <th>Documento</th>
            <th>Vence</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {% set st, cls = status_color_por_vencimiento(v.rev_tecnica_venc) %}
          <tr>
            <td>Revisión técnica</td>
            <td>{{ v.rev_tecnica_venc or "—" }}</td>
            <td>
              <span class="badge bg-{{ cls }}">{{ st }}</span>
              {% set d = dias_restantes(v.rev_tecnica_venc) %}
              {% if d is not none %}
                {% if d < 0 %}<div class="small text-danger">Venció hace {{ (-d) }} días</div>{% endif %}
                {% if d == 0 %}<div class="small text-warning">Vence hoy</div>{% endif %}
                {% if d > 0 and d <= 30 %}<div class="small text-warning">Faltan {{ d }} días</div>{% endif %}
              {% endif %}
            </td>
          </tr>

          {% set st2, cls2 = status_color_por_vencimiento(v.permiso_circ_venc) %}
          <tr>
            <td>Permiso de circulación</td>
            <td>{{ v.permiso_circ_venc or "—" }}</td>
            <td>
              <span class="badge bg-{{ cls2 }}">{{ st2 }}</span>
              {% set d2 = dias_restantes(v.permiso_circ_venc) %}
              {% if d2 is not none %}
                {% if d2 < 0 %}<div class="small text-danger">Venció hace {{ (-d2) }} días</div>{% endif %}
                {% if d2 == 0 %}<div class="small text-warning">Vence hoy</div>{% endif %}
                {% if d2 > 0 and d2 <= 30 %}<div class="small text-warning">Faltan {{ d2 }} días</div>{% endif %}
              {% endif %}
            </td>
          </tr>

          {% set st3, cls3 = status_color_por_vencimiento(v.seguro_obl_venc) %}
          <tr>
            <td>Seguro obligatorio</td>
            <td>{{ v.seguro_obl_venc or "—" }}</td>
            <td>
              <span class="badge bg-{{ cls3 }}">{{ st3 }}</span>
              {% set d3 = dias_restantes(v.seguro_obl_venc) %}
              {% if d3 is not none %}
                {% if d3 < 0 %}<div class="small text-danger">Venció hace {{ (-d3) }} días</div>{% endif %}
                {% if d3 == 0 %}<div class="small text-warning">Vence hoy</div>{% endif %}
                {% if d3 > 0 and d3 <= 30 %}<div class="small text-warning">Faltan {{ d3 }} días</div>{% endif %}
              {% endif %}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card p-4 mt-4 border-0" style="border-radius:1rem;">
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h4 class="mb-0">Mantención</h4>
      <a class="btn btn-success btn-sm" href="{{ url_for('editar_mantencion', vid=v.id) }}">Editar mantenimiento</a>
    </div>

    <div class="mb-2">
      Kilometraje actual: <span class="fw-semibold">{{ fmt_km(v.km) }} km</span>
    </div>

    <div class="table-responsive">
      <table class="table table-dark table-striped align-middle mb-0">
        <thead>
          <tr>
            <th>Ítem</th>
            <th>Último km</th>
            <th>Fecha</th>
            <th>Intervalo km</th>
            <th>Próximo km</th>
            <th>Estado</th>
          </tr>
        </thead>
        <tbody>
          {% macro fila_item(nombre, key) -%}
          <tr>
            <td>{{ nombre }}</td>
            <td>{{ fmt_km(v.mant[key].get('ultimo_km', 0)) }}</td>
            <td>{{ v.mant[key].get('ultimo_fecha','') or "—" }}</td>
            <td>{{ fmt_km(v.mant[key].get('intervalo_km', 0)) }}</td>
            <td>{{ fmt_km(v.mant[key].get('proximo_km', 0)) }}</td>
            <td>
              {% set stx, clsx = status_km(v.km, v.mant[key].get('proximo_km', 0)) %}
              <span class="badge bg-{{ clsx }}">{{ stx }}</span>
              {% set k = km_restantes(v.km, v.mant[key].get('proximo_km', 0)) %}
              {% if k is not none %}
                {% if k < 0 %}<div class="small text-danger">Vencido hace {{ (-k) }} km</div>{% endif %}
                {% if k == 0 %}<div class="small text-warning">Es ahora</div>{% endif %}
                {% if k > 0 and k <= 1000 %}<div class="small text-warning">Faltan {{ k }} km</div>{% endif %}
              {% endif %}
            </td>
          </tr>
          {%- endmacro %}

          {{ fila_item("Aceite", "aceite") }}
          {{ fila_item("Filtro de aceite", "filtro_aceite") }}
          {{ fila_item("Filtro de combustible", "filtro_combustible") }}
          {{ fila_item("Filtro de aire", "filtro_aire") }}
          {{ fila_item("Filtro de polen", "filtro_polen") }}
          {{ fila_item("Pastillas de freno", "pastillas_freno") }}
          {{ fila_item("Correa de distribución", "correa_distribucion") }}
        </tbody>
      </table>
    </div>
  </div>

</div>
"""

EDIT_DOCS = r"""
<div class="container py-1">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h3 class="mb-0 text-white">Editar documentación</h3>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('detalle', vid=v.id) }}">Volver</a>
  </div>

  <div class="card p-4 border-0" style="border-radius:1rem;">
    <h5 class="mb-3">{{ veh_display(v) }} ({{ v.patente }})</h5>
    <form method="post">
      <div class="row g-3">
        <div class="col-md-4">
          <label class="form-label">Revisión técnica (DD-MM-AAAA)</label>
          <input name="rev_tecnica_venc" type="text" class="form-control fecha" placeholder="25-10-2025" value="{{ v.rev_tecnica_venc or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Permiso de circulación (DD-MM-AAAA)</label>
          <input name="permiso_circ_venc" type="text" class="form-control fecha" placeholder="25-03-2026" value="{{ v.permiso_circ_venc or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Seguro obligatorio (DD-MM-AAAA)</label>
          <input name="seguro_obl_venc" type="text" class="form-control fecha" placeholder="25-03-2026" value="{{ v.seguro_obl_venc or '' }}">
        </div>
      </div>

      <div class="mt-4 d-flex gap-2">
        <button class="btn btn-primary">Guardar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('detalle', vid=v.id) }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/es.js"></script>
<script>
  flatpickr(".fecha", { dateFormat: "d-m-Y", locale: "es" });
</script>
"""

EDIT_MANT = r"""
<div class="container py-1">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <h3 class="mb-0 text-white">Editar mantenimiento</h3>
    <a class="btn btn-outline-light btn-sm" href="{{ url_for('detalle', vid=v.id) }}">Volver</a>
  </div>

  <div class="card p-4 border-0" style="border-radius:1rem;">
    <h5 class="mb-3">{{ veh_display(v) }} ({{ v.patente }})</h5>

    <form method="post">
      <div class="row g-3 align-items-end">
        <div class="col-md-4">
          <label class="form-label fw-semibold">KM ACTUAL</label>
          <input name="km_actual" type="text" class="form-control km" inputmode="numeric" autocomplete="off" required value="{{ v.km }}">
        </div>
      </div>

      <hr class="my-4">

      {% macro fila_item(nombre_visible, key) -%}
      <div class="row g-3 mb-3">
        <div class="col-12"><div class="fw-semibold mb-2">{{ nombre_visible }}</div></div>

        <div class="col-md-3">
          <label class="form-label">Último km</label>
          <input type="text" class="form-control form-control-sm km js-ultimo"
                 name="{{ key }}_ultimo_km"
                 value="{{ v.mant[key].get('ultimo_km') or '' }}"
                 inputmode="numeric" autocomplete="off">
        </div>

        <div class="col-md-3">
          <label class="form-label">Fecha</label>
          <input type="text" class="form-control form-control-sm fecha"
                 name="{{ key }}_ultimo_fecha"
                 value="{{ v.mant[key].get('ultimo_fecha','') }}"
                 autocomplete="off">
        </div>

        <div class="col-md-3">
          <label class="form-label">Intervalo km</label>
          <input type="text" class="form-control form-control-sm km js-intervalo"
                 name="{{ key }}_intervalo_km"
                 value="{{ v.mant[key].get('intervalo_km') or '' }}"
                 inputmode="numeric" autocomplete="off">
        </div>

        <div class="col-md-3">
          <label class="form-label">Próximo km</label>
          <div class="form-control-plaintext">
            <span class="badge text-bg-secondary js-proximo">{{ fmt_km(v.mant[key].get('proximo_km', 0)) }}</span>
          </div>
        </div>
      </div>
      {%- endmacro %}

      {{ fila_item("Aceite", "aceite") }}
      {{ fila_item("Filtro de aceite", "filtro_aceite") }}
      {{ fila_item("Filtro de combustible", "filtro_combustible") }}
      {{ fila_item("Filtro de aire", "filtro_aire") }}
      {{ fila_item("Filtro de polen", "filtro_polen") }}
      {{ fila_item("Pastillas de freno", "pastillas_freno") }}
      {{ fila_item("Correa de distribución", "correa_distribucion") }}

      <div class="mt-4 d-flex gap-2">
        <button class="btn btn-success">Guardar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('detalle', vid=v.id) }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/es.js"></script>
<script>
  flatpickr(".fecha", { dateFormat: "d-m-Y", locale: "es" });
</script>

<script>
(function(){
  function fmtKM(val){ val=(val||"").replace(/\\D+/g,""); return val.replace(/\\B(?=(\\d{3})+(?!\\d))/g,"."); }
  function rawKM(val){ return (val||"").replace(/\\./g,""); }

  function recalcProximo(row){
    const ultimoEl = row.querySelector('.js-ultimo');
    const intervaloEl = row.querySelector('.js-intervalo');
    const proxEl = row.querySelector('.js-proximo');
    if(!ultimoEl || !intervaloEl || !proxEl) return;

    const u = parseInt(rawKM(ultimoEl.value) || '0', 10);
    const i = parseInt(rawKM(intervaloEl.value) || '0', 10);
    const proximo = (Number.isFinite(u) && Number.isFinite(i)) ? (u + i) : 0;
    proxEl.textContent = fmtKM(String(proximo));
  }

  document.addEventListener('DOMContentLoaded', ()=>{
    document.querySelectorAll('input.km').forEach(inp=>{
      inp.value = fmtKM(inp.value);
      inp.addEventListener('input', ()=>{
        const old = inp.value;
        const start = inp.selectionStart;
        const right = old.length - start;
        const digits = old.replace(/\\D+/g,'');
        inp.value = fmtKM(digits);
        const newPos = Math.max(0, inp.value.length - right);
        inp.setSelectionRange(newPos, newPos);

        const row = inp.closest('.row');
        if(row) recalcProximo(row);
      });

      if(inp.form){
        inp.form.addEventListener('submit', ()=>{ inp.value = rawKM(inp.value); });
      }
    });

    document.querySelectorAll('.js-ultimo, .js-intervalo').forEach(inp=>{
      const row = inp.closest('.row');
      if(row) recalcProximo(row);
    });
  });
})();
</script>
"""

# -----------------------------
# Rutas propias de vehículos  (MULTI-CUENTA)
# -----------------------------
def next_id(lista):
    return (max([x.get("id", 0) for x in lista]) + 1) if lista else 1

def cargar_vehiculos_tenant():
    # Siempre leemos el JSON correspondiente al tenant actual
    vehs = load_json_list(app.config["VEHICULOS_FILE"])

    # Normalizar estructura mínima para que no se caiga nada
    for _v in vehs:
        ensure_vehicle_fields(_v)
        ensure_mant_dict(_v)
        _v.setdefault("rev_tecnica_venc", "")
        _v.setdefault("permiso_circ_venc", "")
        _v.setdefault("seguro_obl_venc", "")

    return vehs

def guardar_vehiculos_tenant(vehs):
    save_json_list(app.config["VEHICULOS_FILE"], vehs)

@app.route("/admin/vehiculos")
def admin_vehiculos():
    vehiculos = cargar_vehiculos_tenant()
    filtro = request.args.get("filtro")  # None | verde | amarillo | rojo

    def clase_color(color):
        return {"verde": "success", "amarillo": "warning", "rojo": "danger"}.get(color)

    def coincide_color(v, color_cls):
        _, mcls = mant_overall(v)
        _, dcls = docs_overall(v)
        return (mcls == color_cls) or (dcls == color_cls)

    if filtro in ("verde", "amarillo", "rojo"):
        wanted = clase_color(filtro)
        vehs = [v for v in vehiculos if coincide_color(v, wanted)]
    else:
        vehs = vehiculos

    def cuenta(color_cls):
        return sum(1 for v in vehiculos if coincide_color(v, color_cls))

    counts = {
        "total": len(vehiculos),
        "verde": cuenta("success"),
        "amarillo": cuenta("warning"),
        "rojo": cuenta("danger"),
    }

    html = render_template_string(
        ADMIN_VEHICULOS,
        vehiculos=vehs,
        filtro_sel=filtro,
        counts=counts
    )
    return render_admin(html, active="vehiculos")

@app.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    vehiculos = cargar_vehiculos_tenant()

    if request.method == "POST":
        marca   = (request.form.get("marca") or "").strip()
        modelo  = (request.form.get("modelo") or "").strip()
        anio    = (request.form.get("anio") or "").strip()
        patente = (request.form.get("patente") or "").strip()
        km      = parse_km(request.form.get("km"))
        notas   = (request.form.get("notas") or "").strip()

        foto = ""
        file = request.files.get("foto_file")
        if file and file.filename and allowed_file(file.filename):
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            foto = filename
        else:
            foto_select = (request.form.get("foto_select") or "").strip()
            if foto_select:
                foto = foto_select

        v = {
            "id": next_id(vehiculos),
            "marca": marca,
            "modelo": modelo,
            "anio": int(anio) if anio.isdigit() else anio,
            "patente": patente,
            "km": km,
            "notas": notas,
            "foto": foto,
            "rev_tecnica_venc": "",
            "permiso_circ_venc": "",
            "seguro_obl_venc": "",
        }
        ensure_vehicle_fields(v)
        ensure_mant_dict(v)

        vehiculos.append(v)
        guardar_vehiculos_tenant(vehiculos)
        return redirect(url_for("admin_vehiculos"))

    html = render_template_string(FORM_NUEVO, imagenes=listar_imagenes())
    return render_admin(html, active="vehiculos")

@app.route("/eliminar/<int:vid>", methods=["GET", "POST"])
def eliminar(vid):
    vehiculos = cargar_vehiculos_tenant()
    v = next((x for x in vehiculos if x.get("id") == vid), None)
    if not v:
        return "Vehículo no encontrado", 404

    if request.method == "POST":
        vehiculos = [x for x in vehiculos if x.get("id") != vid]
        guardar_vehiculos_tenant(vehiculos)
        return redirect(url_for("admin_vehiculos"))

    html = render_template_string(CONFIRMAR_ELIMINAR, v=v)
    return render_admin(html, active="vehiculos")

@app.route("/detalle/<int:vid>")
def detalle(vid):
    vehs = cargar_vehiculos_tenant()
    v = next((x for x in vehs if x.get("id") == vid), None)
    if not v:
        return "Vehículo no encontrado", 404

    html = render_template_string(DETALLE, v=v)
    return render_admin(html, active="vehiculos")

@app.route("/vehiculo/<int:vid>/documentos", methods=["GET", "POST"])
def editar_documentos(vid):
    vehiculos = cargar_vehiculos_tenant()
    v = next((x for x in vehiculos if x.get("id") == vid), None)
    if not v:
        return "Vehículo no encontrado", 404

    if request.method == "POST":
        v["rev_tecnica_venc"]   = (request.form.get("rev_tecnica_venc") or "").strip()
        v["permiso_circ_venc"]  = (request.form.get("permiso_circ_venc") or "").strip()
        v["seguro_obl_venc"]    = (request.form.get("seguro_obl_venc") or "").strip()
        guardar_vehiculos_tenant(vehiculos)
        return redirect(url_for("detalle", vid=vid))

    html = render_template_string(EDIT_DOCS, v=v)
    return render_admin(html, active="vehiculos")

@app.route("/vehiculo/<int:vid>/mantencion/editar", methods=["GET", "POST"])
def editar_mantencion(vid):
    vehiculos = cargar_vehiculos_tenant()
    v = next((x for x in vehiculos if x.get("id") == vid), None)
    if not v:
        return "Vehículo no encontrado", 404

    ensure_mant_dict(v)

    if request.method == "POST":
        form = request.form
        v["km"] = parse_km(form.get("km_actual"))

        def upd(key: str):
            vi = v["mant"].setdefault(key, {"ultimo_km":0,"ultimo_fecha":"","intervalo_km":0,"proximo_km":0,"observaciones":""})
            ultimo_km    = parse_km(form.get(f"{key}_ultimo_km"))
            ultimo_fecha = (form.get(f"{key}_ultimo_fecha") or "").strip()
            intervalo_km = parse_km(form.get(f"{key}_intervalo_km"))

            vi["ultimo_km"]    = ultimo_km
            vi["ultimo_fecha"] = ultimo_fecha
            vi["intervalo_km"] = intervalo_km
            vi["proximo_km"]   = (ultimo_km + intervalo_km) if (ultimo_km and intervalo_km) else 0

        for k in ["aceite","filtro_aceite","filtro_combustible","filtro_aire","filtro_polen","pastillas_freno","correa_distribucion"]:
            upd(k)

        guardar_vehiculos_tenant(vehiculos)
        return redirect(url_for("detalle", vid=vid))

    html = render_template_string(EDIT_MANT, v=v)
    return render_admin(html, active="vehiculos")

# -----------------------------
# Favicon route (opcional)
# -----------------------------
@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static", "img"),
        "favicon.png",
        mimetype="image/png"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)