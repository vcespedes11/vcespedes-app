# empleados_bp.py
from flask import Blueprint, current_app, render_template_string, request, redirect, url_for
import os, json

empleados_bp = Blueprint("empleados", __name__, url_prefix="/admin/empleados")

# ======================
#   Helpers de layout
# ======================
def render_admin_bp(html, active="empleados"):
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)

# ======================
#   Archivo JSON
# ======================
def _data_file():
    # Puedes cambiar el nombre por config: app.config["EMPLEADOS_FILE"] = "empleados.json"
    return current_app.config.get(
        "EMPLEADOS_FILE",
        os.path.join(current_app.root_path, "empleados.json")
    )

def _load_empleados():
    path = _data_file()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _save_empleados(data):
    path = _data_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ======================
#   Templates
# ======================

LIST_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">Empleados</h3>
  <a class="btn btn-primary btn-sm" href="{{ url_for('empleados.nuevo') }}">+ Nuevo empleado</a>
</div>

<form class="card border-0 shadow-sm mb-3" method="get">
  <div class="card-body row g-2 align-items-end">
    <div class="col-md-6">
      <label class="form-label small mb-1">Buscar</label>
      <input type="text" name="q" class="form-control form-control-sm"
             placeholder="Nombre, RUT, cargo..."
             value="{{ q or '' }}">
    </div>
    <div class="col-md-3">
      <label class="form-label small mb-1">Estado</label>
      <select name="estado" class="form-select form-select-sm">
        <option value="all" {{ 'selected' if estado == 'all' else '' }}>Todos</option>
        <option value="activo" {{ 'selected' if estado == 'activo' else '' }}>Activos</option>
        <option value="inactivo" {{ 'selected' if estado == 'inactivo' else '' }}>Inactivos</option>
      </select>
    </div>
    <div class="col-md-3 text-end">
      <button class="btn btn-primary btn-sm w-100" type="submit">Filtrar</button>
    </div>
  </div>
</form>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <h6 class="mb-3">Lista de empleados</h6>
    {% if empleados %}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>RUT</th>
              <th>Teléfono</th>
              <th>Correo</th>
              <th>Cargo</th>
              <th>Estado</th>
              <th class="text-end">Acciones</th>
            </tr>
          </thead>
          <tbody>
          {% for e in empleados %}
            <tr>
              <td>{{ e.nombre }} {{ e.apellido }}</td>
              <td>{{ e.rut or '—' }}</td>
              <td>{{ e.telefono or '—' }}</td>
              <td>{{ e.email or '—' }}</td>
              <td>{{ e.cargo or '—' }}</td>
              <td>
                {% if e.estado == 'activo' %}
                  <span class="badge rounded-pill text-bg-success">Activo</span>
                {% else %}
                  <span class="badge rounded-pill text-bg-secondary">Inactivo</span>
                {% endif %}
              </td>
              <td class="text-end">
                <a class="btn btn-sm btn-outline-secondary"
                   href="{{ url_for('empleados.editar', eid=e.id) }}">Editar</a>
                <button class="btn btn-sm btn-outline-danger btn-del"
                        type="button"
                        data-id="{{ e.id }}">
                  <i class="bi bi-trash3"></i>
                </button>
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="text-secondary small">No hay empleados registrados.</div>
    {% endif %}
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.btn-del').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id = btn.dataset.id;
      if(!confirm('¿Seguro que quieres eliminar al empleado #' + id + '?')) return;
      try {
        const r = await fetch('{{ url_for("empleados.eliminar") }}', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({id})
        });
        if(!r.ok){
          alert('No se pudo eliminar el empleado.');
          return;
        }
        location.reload();
      } catch(e){
        alert('Error de conexión al intentar eliminar.');
      }
    });
  });
});
</script>
"""

FORM_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">
    {{ 'Editar empleado' if emp_default and emp_default.get('id') else 'Nuevo empleado' }}
  </h3>
  <a class="btn btn-outline-light btn-sm" href="{{ url_for('empleados.lista') }}">Volver</a>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <form method="post">
      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <label class="form-label">Nombre</label>
          <input type="text" name="nombre" class="form-control" required
                 value="{{ (emp_default.get('nombre') if emp_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Apellido</label>
          <input type="text" name="apellido" class="form-control" required
                 value="{{ (emp_default.get('apellido') if emp_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">RUT</label>
          <input type="text" name="rut" class="form-control rut"
                 placeholder="12.345.678-9"
                 value="{{ (emp_default.get('rut') if emp_default else '') or '' }}">
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <label class="form-label">Teléfono</label>
          <input type="text" name="telefono" class="form-control"
                 placeholder="+56912345678"
                 value="{{ (emp_default.get('telefono') if emp_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Correo</label>
          <input type="email" name="email" class="form-control"
                 placeholder="empleado@correo.cl"
                 value="{{ (emp_default.get('email') if emp_default else '') or '' }}">
        </div>
        <div class="col-md-4">
          <label class="form-label">Cargo</label>
          <input type="text" name="cargo" class="form-control"
                 placeholder="Ej: Administrativo, Chofer..."
                 value="{{ (emp_default.get('cargo') if emp_default else '') or '' }}">
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <label class="form-label">Estado</label>
          {% set estado_sel = (emp_default.get('estado') if emp_default else 'activo') %}
          <select name="estado" class="form-select">
            <option value="activo" {{ 'selected' if estado_sel == 'activo' else '' }}>Activo</option>
            <option value="inactivo" {{ 'selected' if estado_sel == 'inactivo' else '' }}>Inactivo</option>
          </select>
        </div>
        <div class="col-md-8">
          <label class="form-label">Nota (opcional)</label>
          <input type="text" name="nota" class="form-control"
                 placeholder="Observaciones, horario, etc."
                 value="{{ (emp_default.get('nota') if emp_default else '') or '' }}">
        </div>
      </div>

      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-success">Guardar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('empleados.lista') }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function(){
  function fmtRUT(val){
    val = (val || "").replace(/[^0-9kK]/g, "").toUpperCase();
    if (!val) return "";
    if (val.length === 1) return val;

    const cuerpo = val.slice(0, -1);
    const dv = val.slice(-1);
    const cuerpoFmt = cuerpo.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return (cuerpoFmt ? cuerpoFmt + "-" : "") + dv;
  }

  document.querySelectorAll('input.rut').forEach(function(inp){
    // Formatear si ya viene con valor
    if (inp.value) {
      inp.value = fmtRUT(inp.value);
    }

    inp.addEventListener('input', function(){
      const posRight = inp.value.length - (inp.selectionStart || 0);
      inp.value = fmtRUT(inp.value);
      const newPos = Math.max(0, inp.value.length - posRight);
      inp.setSelectionRange(newPos, newPos);
    });

    inp.addEventListener('blur', function(){
      inp.value = fmtRUT(inp.value);
    });
  });
});
</script>
"""

# ======================
#   Rutas
# ======================

@empleados_bp.route("/")
def lista():
    empleados = _load_empleados()

    # Filtros simples: búsqueda y estado
    q = (request.args.get("q") or "").strip().lower()
    estado = request.args.get("estado", "all")

    filtrados = []
    for e in empleados:
        # Estado
        est = (e.get("estado") or "activo").lower()
        if estado != "all" and est != estado:
            continue

        # Búsqueda texto
        if q:
            blob = " ".join([
                str(e.get("nombre") or ""),
                str(e.get("apellido") or ""),
                str(e.get("rut") or ""),
                str(e.get("cargo") or ""),
            ]).lower()
            if q not in blob:
                continue

        filtrados.append(e)

    # Orden por nombre/apellido
    filtrados = sorted(
        filtrados,
        key=lambda x: (str(x.get("nombre") or "").lower(), str(x.get("apellido") or "").lower())
    )

    html = render_template_string(
        LIST_HTML,
        empleados=filtrados,
        q=q,
        estado=estado,
    )
    return render_admin_bp(html, active="empleados")

@empleados_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        empleados = _load_empleados()

        def next_id():
            return (max([int(e.get("id") or 0) for e in empleados]) + 1) if empleados else 1

        e = {
            "id": next_id(),
            "nombre": (request.form.get("nombre") or "").strip(),
            "apellido": (request.form.get("apellido") or "").strip(),
            "rut": (request.form.get("rut") or "").strip(),
            "telefono": (request.form.get("telefono") or "").strip(),
            "email": (request.form.get("email") or "").strip(),
            "cargo": (request.form.get("cargo") or "").strip(),
            "estado": (request.form.get("estado") or "activo").strip().lower(),
            "nota": (request.form.get("nota") or "").strip(),
        }
        empleados.append(e)
        _save_empleados(empleados)
        return redirect(url_for("empleados.lista"))

    html = render_template_string(FORM_HTML, emp_default=None)
    return render_admin_bp(html, active="empleados")

@empleados_bp.route("/<int:eid>/editar", methods=["GET", "POST"])
def editar(eid):
    empleados = _load_empleados()
    e = next((x for x in empleados if int(x.get("id") or 0) == eid), None)
    if not e:
        return "Empleado no encontrado", 404

    if request.method == "POST":
        e["nombre"] = (request.form.get("nombre") or "").strip()
        e["apellido"] = (request.form.get("apellido") or "").strip()
        e["rut"] = (request.form.get("rut") or "").strip()
        e["telefono"] = (request.form.get("telefono") or "").strip()
        e["email"] = (request.form.get("email") or "").strip()
        e["cargo"] = (request.form.get("cargo") or "").strip()
        e["estado"] = (request.form.get("estado") or "activo").strip().lower()
        e["nota"] = (request.form.get("nota") or "").strip()

        _save_empleados(empleados)
        return redirect(url_for("empleados.lista"))

    html = render_template_string(FORM_HTML, emp_default=e)
    return render_admin_bp(html, active="empleados")

@empleados_bp.route("/eliminar", methods=["POST"])
def eliminar():
    data = request.get_json(silent=True) or {}
    eid = int(data.get("id") or 0)
    empleados = _load_empleados()
    nuevos = [e for e in empleados if int(e.get("id") or 0) != eid]
    if len(nuevos) == len(empleados):
        return {"error": "No encontrado"}, 404
    _save_empleados(nuevos)
    return {"ok": True}