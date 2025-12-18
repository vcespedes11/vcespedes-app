# gastos_bp.py
from flask import Blueprint, current_app, render_template_string, request, redirect, url_for
from datetime import datetime, date
import os, json

gastos_bp = Blueprint("gastos", __name__, url_prefix="/admin/gastos")

# ======================
#   Helpers de layout
# ======================
def render_admin_bp(html, active="gastos"):
    base = current_app.config.get("LAYOUT_BASE")
    if not base:
        return html
    tpl = current_app.jinja_env.from_string(base)
    return tpl.render(content=html, active=active)

# ======================
#   Archivo JSON
# ======================
def _data_file():
    # Puedes cambiar el nombre si quieres
    return current_app.config.get("GASTOS_FILE", os.path.join(current_app.root_path, "gastos.json"))

def _load_gastos():
    path = _data_file()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _save_gastos(data):
    path = _data_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def parse_dmy(s):
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except Exception:
        return None

def fmt_miles(n):
    try:
        return "{:,}".format(int(n or 0)).replace(",", ".")
    except Exception:
        return "0"

# categorías de gasto
CATEGORIAS = [
    ("mantencion", "Mantención"),
    ("seguro", "Seguro"),
    ("empleado", "Empleado"),
    ("lavado", "Lavado"),
    ("arriendo", "Arriendo"),
    ("otro", "Otro"),
]

# ======================
#   Templates
# ======================

LIST_HTML = r"""
<div class="d-flex align-items-center justify-content-between mb-3">
  <h3 class="mb-0">Gastos</h3>
  <a class="btn btn-primary btn-sm" href="{{ url_for('gastos.nuevo') }}">+ Nuevo gasto</a>
</div>

<form class="card border-0 shadow-sm mb-3" method="get">
  <div class="card-body row g-2 align-items-end">
    <div class="col-md-3">
      <label class="form-label small mb-1">Año</label>
      <select class="form-select form-select-sm" name="year">
        <option value="all" {{ 'selected' if year == 'all' else '' }}>Todos</option>
        {% for y in years %}
          <option value="{{ y }}" {{ 'selected' if year == y|string else '' }}>{{ y }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label small mb-1">Mes</label>
      <select class="form-select form-select-sm" name="month">
        <option value="all" {{ 'selected' if month == 'all' else '' }}>Todo el año</option>
        {% for code, label in months %}
          <option value="{{ code }}" {{ 'selected' if month == code else '' }}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label small mb-1">Categoría</label>
      <select class="form-select form-select-sm" name="cat">
        <option value="all" {{ 'selected' if cat == 'all' else '' }}>Todas</option>
        {% for code, label in categorias %}
          <option value="{{ code }}" {{ 'selected' if cat == code else '' }}>{{ label }}</option>
        {% endfor %}
      </select>
    </div>
    <div class="col-md-3 text-end">
      <button class="btn btn-primary btn-sm w-100" type="submit">Filtrar</button>
    </div>
  </div>
</form>

<div class="row g-3 mb-3">
  <div class="col-md-4">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary">Total del período</div>
        <div class="h4 mb-0">$ {{ fmt_miles(total_periodo) }}</div>
      </div>
    </div>
  </div>
  <div class="col-md-8">
    <div class="card border-0 shadow-sm h-100">
      <div class="card-body">
        <div class="small text-secondary mb-1">Totales por categoría (período)</div>
        {% if totales_categoria %}
          <div class="table-responsive">
            <table class="table table-sm mb-0 align-middle">
              <tbody>
              {% for item in totales_categoria %}
                <tr>
                  <td>{{ item.label }}</td>
                  <td class="text-end">$ {{ fmt_miles(item.total) }}</td>
                </tr>
              {% endfor %}
              </tbody>
            </table>
          </div>
        {% else %}
          <div class="text-secondary small">No hay montos para mostrar por categoría.</div>
        {% endif %}
      </div>
    </div>
  </div>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <h6 class="mb-3">Detalle de gastos</h6>
    {% if rows %}
      <div class="table-responsive">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Categoría</th>
              <th>Descripción</th>
              <th class="text-end">Monto</th>
              <th class="text-end">Acciones</th>
            </tr>
          </thead>
          <tbody>
          {% for g in rows %}
            <tr>
              <td>{{ g.fecha }}</td>
              <td>
                {{ g.categoria_label }}
                {% if g.recurrente %}
                <span class="badge rounded-pill text-bg-warning ms-1">Mensual</span>
                {% endif %}
              </td>
              <td>{{ g.descripcion }}</td>
              <td class="text-end">$ {{ fmt_miles(g.monto) }}</td>
              <td class="text-end">
                <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('gastos.editar', gid=g.id) }}">Editar</a>
                <button class="btn btn-sm btn-outline-danger btn-del" data-id="{{ g.id }}" type="button">
                  <i class="bi bi-trash3"></i>
                </button>
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      </div>
    {% else %}
      <div class="text-secondary small">No hay gastos en este período.</div>
    {% endif %}
  </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('.btn-del').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id = btn.dataset.id;
      if(!confirm('¿Seguro que quieres eliminar el gasto #' + id + '?')) return;
      try {
        const r = await fetch('{{ url_for("gastos.eliminar") }}', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({id})
        });
        if(!r.ok){
          alert('No se pudo eliminar el gasto.');
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
  <h3 class="mb-0">{{ 'Editar gasto' if g_default and g_default.get('id') else 'Nuevo gasto' }}</h3>
  <a class="btn btn-outline-light btn-sm" href="{{ url_for('gastos.lista') }}">Volver</a>
</div>

<div class="card border-0 shadow-sm">
  <div class="card-body">
    <form method="post">
      <div class="row g-3 mb-3">
        <div class="col-md-3">
          <label class="form-label">Fecha</label>
          <input type="text" name="fecha" class="form-control fecha"
                 placeholder="DD-MM-YYYY"
                 autocomplete="off"
                 value="{{ (g_default.get('fecha') if g_default else '') or '' }}" required>
        </div>
        <div class="col-md-3">
          <label class="form-label">Categoría</label>
          <select name="categoria" class="form-select" required>
            {% set cat_sel = (g_default.get('categoria') if g_default else 'mantencion') %}
            {% for code, label in categorias %}
            <option value="{{ code }}" {{ 'selected' if cat_sel == code else '' }}>{{ label }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label">Descripción</label>
          <input type="text" name="descripcion" class="form-control"
                 value="{{ (g_default.get('descripcion') if g_default else '') or '' }}" required>
        </div>
      </div>

      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <label class="form-label">Monto</label>
          <input type="number" name="monto" class="form-control" min="0" step="1"
                 value="{{ (g_default.get('monto') if g_default else '') or '' }}" required>
        </div>
        <div class="col-md-8">
          <label class="form-label">Nota (opcional)</label>
          <input type="text" name="nota" class="form-control"
                 value="{{ (g_default.get('nota') if g_default else '') or '' }}">
        </div>
      </div>

      <!-- Configuración de gasto mensual -->
      <div class="row g-3 mb-3">
        <div class="col-md-4">
          <div class="form-check mt-4">
            <input class="form-check-input" type="checkbox" id="recurrente" name="recurrente"
                   {% if g_default and g_default.get('recurrente') %}checked{% endif %}>
            <label class="form-check-label" for="recurrente">
              Gasto mensual (se repite todos los meses)
            </label>
          </div>
        </div>
        <div class="col-md-4">
          <label class="form-label">Repetir hasta (opcional)</label>
          <input type="text" name="fin_recurrencia" class="form-control fecha"
                 placeholder="DD-MM-YYYY" autocomplete="off"
                 value="{{ (g_default.get('fin_recurrencia') if g_default else '') or '' }}">
          <div class="form-text">Si lo dejas vacío, se repetirá indefinidamente.</div>
        </div>
      </div>

      <div class="mt-3 d-flex gap-2">
        <button class="btn btn-success">Guardar</button>
        <a class="btn btn-outline-secondary" href="{{ url_for('gastos.lista') }}">Cancelar</a>
      </div>
    </form>
  </div>
</div>

<!-- Flatpickr igual que en contratos -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/es.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function(){
  if (window.flatpickr){
    flatpickr("input.fecha", {
      dateFormat: "d-m-Y",
      locale: "es"
    });
  }
});
</script>
"""

# ======================
#   Rutas
# ======================

@gastos_bp.route("/")
def lista():
    gastos = _load_gastos()

    # filtros
    year = request.args.get("year", "all")
    month = request.args.get("month", "all")
    cat = request.args.get("cat", "all")

    # años disponibles (desde la fecha base de cada gasto)
    years_found = set()
    for g in gastos:
        d = parse_dmy(g.get("fecha"))
        if d:
            years_found.add(d.year)
    years = sorted(years_found, reverse=True)

    # meses
    months = [
        ("01","Enero"),("02","Febrero"),("03","Marzo"),
        ("04","Abril"),("05","Mayo"),("06","Junio"),
        ("07","Julio"),("08","Agosto"),("09","Septiembre"),
        ("10","Octubre"),("11","Noviembre"),("12","Diciembre"),
    ]

    # aplicar filtros
    rows = []
    total_periodo = 0

    cat_labels = {c: lbl for c, lbl in CATEGORIAS}
    # acumulador de totales por categoría
    totales_cat = {c: 0 for c, _ in CATEGORIAS}

    for g in gastos:
        d_ini = parse_dmy(g.get("fecha"))
        if not d_ini:
            continue

        g_cat = (g.get("categoria") or "otro")

        # filtro de categoría
        if cat != "all" and g_cat != cat:
            continue

        monto = int(g.get("monto") or 0)
        recurrente = bool(g.get("recurrente"))
        fin_rec_txt = g.get("fin_recurrencia") or ""
        d_fin = parse_dmy(fin_rec_txt) if fin_rec_txt else None

        # Caso 1: NO recurrente, o filtro year = "all" -> comportamiento clásico
        if not recurrente or year == "all":
            if year != "all" and str(d_ini.year) != str(year):
                continue
            if month != "all" and f"{d_ini.month:02d}" != month:
                continue

            total_periodo += monto
            totales_cat[g_cat] = totales_cat.get(g_cat, 0) + monto

            rows.append({
                "id": g.get("id"),
                "fecha": d_ini.strftime("%d-%m-%Y"),
                "categoria": g_cat,
                "categoria_label": cat_labels.get(g_cat, "Otro"),
                "descripcion": g.get("descripcion") or "",
                "monto": monto,
                "recurrente": recurrente,
            })
            continue

        # Caso 2: recurrente y año específico
        year_int = int(year)

        # 2a) Filtro por todo el año: generamos una fila por cada mes válido de ese año
        if month == "all":
            for m in range(1, 13):
                # este mes/año está antes del inicio de la recurrencia
                if (year_int, m) < (d_ini.year, d_ini.month):
                    continue
                # si hay fecha de fin de recurrencia, no pasarse
                if d_fin and (year_int, m) > (d_fin.year, d_fin.month):
                    continue

                # día "seguro" para todos los meses
                day = min(d_ini.day or 1, 28)
                d_occ = date(year_int, m, day)

                total_periodo += monto
                totales_cat[g_cat] = totales_cat.get(g_cat, 0) + monto

                rows.append({
                    "id": g.get("id"),
                    "fecha": d_occ.strftime("%d-%m-%Y"),
                    "categoria": g_cat,
                    "categoria_label": cat_labels.get(g_cat, "Otro"),
                    "descripcion": g.get("descripcion") or "",
                    "monto": monto,
                    "recurrente": recurrente,
                })
        # 2b) Filtro por un mes concreto del año
        else:
            m = int(month)
            # antes del inicio
            if (year_int, m) < (d_ini.year, d_ini.month):
                continue
            # después del fin (si existe)
            if d_fin and (year_int, m) > (d_fin.year, d_fin.month):
                continue

            day = min(d_ini.day or 1, 28)
            d_occ = date(year_int, m, day)

            total_periodo += monto
            totales_cat[g_cat] = totales_cat.get(g_cat, 0) + monto

            rows.append({
                "id": g.get("id"),
                "fecha": d_occ.strftime("%d-%m-%Y"),
                "categoria": g_cat,
                "categoria_label": cat_labels.get(g_cat, "Otro"),
                "descripcion": g.get("descripcion") or "",
                "monto": monto,
                "recurrente": recurrente,
            })

    # ordenar por fecha desc
    rows = sorted(rows, key=lambda r: datetime.strptime(r["fecha"], "%d-%m-%Y"), reverse=True)

    # armar lista amigable para el template
    totales_categoria = []
    for code, label in CATEGORIAS:
        total_cat = totales_cat.get(code, 0)
        if total_cat > 0:
            totales_categoria.append({
                "code": code,
                "label": label,
                "total": total_cat,
            })

    html = render_template_string(
        LIST_HTML,
        years=years,
        year=year,
        month=month,
        months=months,
        cat=cat,
        categorias=CATEGORIAS,
        rows=rows,
        total_periodo=total_periodo,
        totales_categoria=totales_categoria,
        fmt_miles=fmt_miles,
    )
    return render_admin_bp(html, active="gastos")

@gastos_bp.route("/nuevo", methods=["GET", "POST"])
def nuevo():
    if request.method == "POST":
        gastos = _load_gastos()

        def next_id():
            return (max([g.get("id", 0) for g in gastos]) + 1) if gastos else 1

        g = {
            "id": next_id(),
            "fecha": (request.form.get("fecha") or "").strip(),        # DD-MM-YYYY
            "categoria": (request.form.get("categoria") or "otro").strip(),
            "descripcion": (request.form.get("descripcion") or "").strip(),
            "monto": int(request.form.get("monto") or 0),
            "nota": (request.form.get("nota") or "").strip(),
            # NUEVO:
            "recurrente": bool(request.form.get("recurrente")),
            "fin_recurrencia": (request.form.get("fin_recurrencia") or "").strip(),
        }
        gastos.append(g)
        _save_gastos(gastos)
        return redirect(url_for("gastos.lista"))

    html = render_template_string(FORM_HTML, g_default=None, categorias=CATEGORIAS)
    return render_admin_bp(html, active="gastos")

@gastos_bp.route("/<int:gid>/editar", methods=["GET", "POST"])
def editar(gid):
    gastos = _load_gastos()
    g = next((x for x in gastos if int(x.get("id") or 0) == gid), None)
    if not g:
        return "Gasto no encontrado", 404

    if request.method == "POST":
        g["fecha"] = (request.form.get("fecha") or "").strip()
        g["categoria"] = (request.form.get("categoria") or "otro").strip()
        g["descripcion"] = (request.form.get("descripcion") or "").strip()
        g["monto"] = int(request.form.get("monto") or 0)
        g["nota"] = (request.form.get("nota") or "").strip()
        # NUEVO:
        g["recurrente"] = bool(request.form.get("recurrente"))
        g["fin_recurrencia"] = (request.form.get("fin_recurrencia") or "").strip()

        _save_gastos(gastos)
        return redirect(url_for("gastos.lista"))

    html = render_template_string(FORM_HTML, g_default=g, categorias=CATEGORIAS)
    return render_admin_bp(html, active="gastos")

@gastos_bp.route("/eliminar", methods=["POST"])
def eliminar():
    data = request.get_json(silent=True) or {}
    gid = int(data.get("id") or 0)
    gastos = _load_gastos()
    nuevos = [g for g in gastos if int(g.get("id") or 0) != gid]
    if len(nuevos) == len(gastos):
        return {"error": "No encontrado"}, 404
    _save_gastos(nuevos)
    return {"ok": True}