# manuales_bp.py
from flask import Blueprint, current_app, render_template_string, request, redirect, url_for
import os
import json

manuales_bp = Blueprint("manuales", __name__, url_prefix="/admin/manuales")


def render_admin_bp(html, active="manuales"):
    """
    Usa el mismo layout base que el resto del admin.
    En app.py debería estar configurado algo como:
    app.config["LAYOUT_BASE"] = open("templates/layout_base.html").read()
    """
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)


# =========================
#   Soporte JSON manuales
# =========================

# Versión por defecto del checklist (por si el JSON todavía no lo trae)
DEFAULT_CHECKLIST_HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Checklist de entrega y recepción</title>
  <style>
    * { box-sizing: border-box; }
    body {
        font-family: Arial, Helvetica, sans-serif;
        color: #111;
        background: #fff;
        margin: 6mm 20mm 10mm 20mm;
    }
    .header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        margin-bottom: 5px;
    }
    .logo {
        height: 80px;
        display: block;
        margin: 0;
        padding: 0;
    }
    .title-block {
      text-align:right;
      font-size: 12px;
      line-height: 1.3;
    }
    h1 {
        text-align: center;
        margin: 0 0 10px 0;
        font-size: 20px;
    }
    h2 {
      margin-top: 18px;
      font-size: 15px;
      border-bottom: 1px solid #ccc;
      padding-bottom: 3px;
    }
    ul.checklist {
      list-style: none;
      padding-left: 0;
      margin-top: 6px;
      margin-bottom: 10px;
    }
    ul.checklist li {
      margin-bottom: 4px;
    }
    ul.checklist label {
      display:flex;
      align-items:flex-start;
      gap: 6px;
    }
    ul.checklist input[type="checkbox"] {
      margin-top: 2px;
    }
    .firma {
      margin-top: 40px;
    }
    .firma .linea {
      border-top: 1px solid #000;
      width: 60%;
      margin-top: 40px;
    }
    .toolbar {
      text-align: right;
      margin-bottom: 10px;
    }
    .toolbar button {
      padding: 6px 10px;
      font-size: 12px;
      border-radius: 4px;
      border: 1px solid #999;
      background:#f5f5f5;
      cursor:pointer;
    }
    .toolbar button:hover {
      background:#e5e5e5;
    }
    @page { size: A4; margin: 20mm; }
    @media print {
      .toolbar { display:none; }
    }
    @media print {
      .btn-imprimir {
        display: none !important;
      }
    }
  </style>
</head>
<body>

  <div class="header">
    <img src="{{ url_for('static', filename='img/logo_informal.png') }}" class="logo">
    <div class="header-text">
      <div class="title">Ruta Sur Rent a Car</div>
      <div class="subtitle">Checklist entrega/recepción de vehículos</div>
      <div class="print-actions">
        <button class="btn btn-primary btn-imprimir" onclick="window.print()">🖨️Imprimir</button>
      </div>
    </div>
  </div>

  <h1>Checklist de entrega y recepción de vehículos</h1>

  <h2>Entrega de vehículo</h2>
  <ul class="checklist">
    <li>
      <label><input type="checkbox">
        Revisar reserva y datos del cliente en el sistema (nombre, RUT, fechas, vehículo).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Verificar documentos del cliente: cédula y licencia de conducir vigentes.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Revisar limpieza general del vehículo (interior y exterior).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Registrar nivel de combustible inicial.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Registrar kilómetros iniciales.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Revisar y fotografiar daños existentes (rayas, golpes, vidrios, llantas, etc.).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Verificar accesorios: gata, rueda de repuesto, llave de ruedas, extintor, triángulos, etc.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Explicar condiciones básicas: horario de devolución, combustible, multas, uso responsable.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Firmar contrato y checklist junto con el cliente.
      </label>
    </li>
  </ul>

  <h2>Recepción de vehículo</h2>
  <ul class="checklist">
    <li>
      <label><input type="checkbox">
        Revisar hora de devolución (retrasos respecto al horario acordado).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Revisar nivel de combustible y compararlo con el de la entrega.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Registrar kilómetros finales.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Verificar que todos los accesorios estén presentes (gata, rueda, extintor, etc.).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Revisar carrocería y interior por daños nuevos, comparando con las fotos de entrega.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Tomar fotografías si se detectan daños o novedades.
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Registrar observaciones importantes en el sistema (multas, daños, comentarios del cliente).
      </label>
    </li>
    <li>
      <label><input type="checkbox">
        Confirmar con el cliente monto final y pagos pendientes (si corresponde).
      </label>
    </li>
  </ul>

  <div class="firma">
    <p>En Punta Arenas, a ____ de __________________ de 20____.</p>
    <div class="linea"></div>
    <p>Firma encargado / trabajador</p>
  </div>

</body>
</html>
"""


def _manuales_json_path():
    # ruta-sur-app/data/manuales.json
    return os.path.join(current_app.root_path, "data", "manuales.json")


def load_manuales():
    """
    Lee data/manuales.json.
    Si no existe o está incompleto, devuelve una estructura segura.
    """
    base = {
        "manuales": [],
        "checklist_html": DEFAULT_CHECKLIST_HTML,
    }

    path = _manuales_json_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        # Normalizar
        manuales = data.get("manuales")
        if not isinstance(manuales, list):
            manuales = []
        checklist_html = data.get("checklist_html") or DEFAULT_CHECKLIST_HTML
        base["manuales"] = manuales
        base["checklist_html"] = checklist_html

    return base


def save_manuales(data):
    """
    Guarda en data/manuales.json, sólo las claves que nos interesan.
    """
    path = _manuales_json_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    out = {
        "manuales": data.get("manuales", []),
        "checklist_html": data.get("checklist_html", DEFAULT_CHECKLIST_HTML),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def _next_id(manuales):
    if not manuales:
        return 1
    return max((m.get("id") or 0) for m in manuales) + 1


def _slug_from_title(titulo):
    """
    Genera un ancla simple a partir del título del menú.
    """
    if not titulo:
        return "manual"
    slug = "".join(
        c.lower() if c.isalnum() else "-"
        for c in titulo
    )
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "manual"


# =========================
#   Templates en memoria
# =========================

MANUALES_LIST_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <div>
    <h3 class="mb-0">Manuales de operación</h3>
    <span class="text-secondary small">Uso interno · Ruta Sur Rent a Car</span>
  </div>
  <div class="d-flex gap-2">
    <a class="btn btn-sm btn-outline-primary" href="{{ url_for('manuales.checklist') }}" target="_blank">
      🖨️ Imprimir checklist
    </a>
    <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('manuales.editar_checklist') }}">
      ✏️ Editar checklist
    </a>
     <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('manuales.nuevo_manual') }}">
      ➕ Agregar manual
    </a>
  </div>
</div>

<div class="row g-3">
  <!-- Índice lateral -->
  <div class="col-12 col-lg-3">
    <div class="card border-0 shadow-sm sticky-top" style="top:80px">
      <div class="card-body p-3" style="color:#000;">
  <div class="fw-semibold mb-2" style="color:#000;">Índice rápido</div>
  <div class="list-group list-group-flush" style="color:#000;">
          {% for m in manuales %}
            <a href="#{{ m.ancla }}" class="list-group-item list-group-item-action py-1 small">
              {{ m.titulo_menu }}
            </a>
          {% endfor %}
          {% if not manuales %}
            <div style="color:#000; font-size:14px;">
              Aún no hay manuales creados.
            </div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <!-- Contenido principal -->
  <div class="col-12 col-lg-9">
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-3 p-md-4" style="color:#000;">

        {% for m in manuales %}
          <section id="{{ m.ancla }}" class="mb-4">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <h5 class="mb-0">{{ m.titulo_bloque }}</h5>
              <div class="btn-group btn-group-sm" role="group">
                <a class="btn btn-outline-secondary" href="{{ url_for('manuales.editar_manual', manual_id=m.id) }}">Editar</a>
                <form method="post" action="{{ url_for('manuales.eliminar_manual', manual_id=m.id) }}" onsubmit="return confirm('¿Eliminar este manual?');">
                  <button type="submit" class="btn btn-outline-danger">Eliminar</button>
                </form>
              </div>
            </div>
            <div style="color:#000; font-size:14px;">
              {{ m.contenido_html | safe }}
            </div>
            {% if not loop.last %}
              <hr>
            {% endif %}
          </section>
        {% endfor %}

        {% if not manuales %}
          <p style="color:#000; font-size:14px;">
            No hay manuales registrados todavía. Usa el botón "Agregar manual" para crear el primero.
          </p>
        {% endif %}

      </div>
    </div>
  </div>
</div>
"""


MANUAL_EDIT_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">{{ 'Editar manual' if manual.id else 'Nuevo manual' }}</h3>
  <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('manuales.home') }}">← Volver a manuales</a>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body" style="color:#000;">
    <form method="post">
      <div class="mb-3">
        <label class="form-label small">Título para el índice (ej: "2. Entrega de vehículo al cliente")</label>
        <input type="text" name="titulo_menu" class="form-control form-control-sm" required
               value="{{ manual.titulo_menu or '' }}">
      </div>

      <div class="mb-3">
        <label class="form-label small">
          Ancla (opcional, se usa para el enlace interno, ej: "entrega"). Si lo dejas en blanco, se genera automáticamente.
        </label>
        <input type="text" name="ancla" class="form-control form-control-sm"
               value="{{ manual.ancla or '' }}">
      </div>

      <div class="mb-3">
        <label class="form-label small">Título dentro del bloque</label>
        <input type="text" name="titulo_bloque" class="form-control form-control-sm" required
               value="{{ manual.titulo_bloque or '' }}">
      </div>

      <div class="mb-3">
        <label class="form-label small">
          Contenido (HTML). Puedes copiar y pegar el texto con listas, párrafos, etc.
        </label>
        <textarea name="contenido_html" rows="15" class="form-control form-control-sm"
                  style="font-family: monospace;">{{ manual.contenido_html or '' }}</textarea>
      </div>

      <button type="submit" class="btn btn-primary btn-sm">Guardar</button>
      <a href="{{ url_for('manuales.home') }}" class="btn btn-outline-secondary btn-sm">Cancelar</a>
    </form>
  </div>
</div>
"""


CHECKLIST_EDIT_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">Editar checklist de entrega/recepción</h3>
  <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('manuales.home') }}">← Volver a manuales</a>
</div>

<div class="alert alert-warning" style="color:#000;">
  Ten cuidado al editar este HTML. Si sólo quieres cambiar textos (frases, títulos),
  puedes modificar el contenido sin tocar las partes con <code>{{'{{'}} ... {{'}}'}}</code>.
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body" style="color:#000;">
    <form method="post">
      <div class="mb-3">
        <label class="form-label small">HTML del checklist</label>
        <textarea name="checklist_html" rows="25" class="form-control form-control-sm"
                  style="font-family: monospace;">{{ checklist_html }}</textarea>
      </div>

      <button type="submit" class="btn btn-primary btn-sm">Guardar checklist</button>
      <a href="{{ url_for('manuales.home') }}" class="btn btn-outline-secondary btn-sm">Cancelar</a>
    </form>
  </div>
</div>
"""


# =========================
#       Rutas
# =========================

@manuales_bp.route("/")
def home():
    data = load_manuales()
    manuales = data["manuales"]

    # Asegurar que cada manual tenga los campos básicos
    norm = []
    for m in manuales:
        norm.append({
            "id": m.get("id"),
            "titulo_menu": m.get("titulo_menu", ""),
            "ancla": m.get("ancla", "") or _slug_from_title(m.get("titulo_menu", "")),
            "titulo_bloque": m.get("titulo_bloque", m.get("titulo_menu", "")),
            "contenido_html": m.get("contenido_html", ""),
        })
    manuales = norm

    html = render_template_string(MANUALES_LIST_HTML, manuales=manuales)
    return render_admin_bp(html, active="manuales")


@manuales_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo_manual():
    data = load_manuales()
    manuales = data["manuales"]

    if request.method == "POST":
        titulo_menu = (request.form.get("titulo_menu") or "").strip()
        ancla = (request.form.get("ancla") or "").strip()
        titulo_bloque = (request.form.get("titulo_bloque") or "").strip()
        contenido_html = request.form.get("contenido_html") or ""

        if not ancla:
            ancla = _slug_from_title(titulo_menu)

        nuevo = {
            "id": _next_id(manuales),
            "titulo_menu": titulo_menu,
            "ancla": ancla,
            "titulo_bloque": titulo_bloque or titulo_menu,
            "contenido_html": contenido_html,
        }
        manuales.append(nuevo)
        data["manuales"] = manuales
        save_manuales(data)
        return redirect(url_for("manuales.home"))

    manual = {
        "id": None,
        "titulo_menu": "",
        "ancla": "",
        "titulo_bloque": "",
        "contenido_html": "",
    }
    html = render_template_string(MANUAL_EDIT_HTML, manual=manual)
    return render_admin_bp(html, active="manuales")


@manuales_bp.route("/editar/<int:manual_id>", methods=["GET", "POST"])
def editar_manual(manual_id):
    data = load_manuales()
    manuales = data["manuales"]

    manual = next((m for m in manuales if m.get("id") == manual_id), None)
    if not manual:
        # Si no se encuentra, volver a la lista
        return redirect(url_for("manuales.home"))

    if request.method == "POST":
        titulo_menu = (request.form.get("titulo_menu") or "").strip()
        ancla = (request.form.get("ancla") or "").strip()
        titulo_bloque = (request.form.get("titulo_bloque") or "").strip()
        contenido_html = request.form.get("contenido_html") or ""

        if not ancla:
            ancla = _slug_from_title(titulo_menu)

        manual["titulo_menu"] = titulo_menu
        manual["ancla"] = ancla
        manual["titulo_bloque"] = titulo_bloque or titulo_menu
        manual["contenido_html"] = contenido_html

        save_manuales(data)
        return redirect(url_for("manuales.home"))

    html = render_template_string(MANUAL_EDIT_HTML, manual=manual)
    return render_admin_bp(html, active="manuales")


@manuales_bp.route("/eliminar/<int:manual_id>", methods=["POST"])
def eliminar_manual(manual_id):
    data = load_manuales()
    manuales = data["manuales"]
    manuales = [m for m in manuales if m.get("id") != manual_id]
    data["manuales"] = manuales
    save_manuales(data)
    return redirect(url_for("manuales.home"))


@manuales_bp.route("/checklist")
def checklist():
    data = load_manuales()
    html = data.get("checklist_html") or DEFAULT_CHECKLIST_HTML
    # OJO: aquí NO pasamos por render_admin_bp, esto debe ser una página limpia para imprimir
    return render_template_string(html)


@manuales_bp.route("/checklist/editar", methods=["GET", "POST"])
def editar_checklist():
    data = load_manuales()

    if request.method == "POST":
        checklist_html = request.form.get("checklist_html") or DEFAULT_CHECKLIST_HTML
        data["checklist_html"] = checklist_html
        save_manuales(data)
        return redirect(url_for("manuales.home"))

    html = render_template_string(
        CHECKLIST_EDIT_HTML,
        checklist_html=data.get("checklist_html", DEFAULT_CHECKLIST_HTML)
    )
    return render_admin_bp(html, active="manuales")