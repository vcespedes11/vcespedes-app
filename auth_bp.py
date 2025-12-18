# auth_bp.py
from flask import Blueprint, render_template_string, request, redirect, url_for, session

auth_bp = Blueprint("auth", __name__, url_prefix="")

USUARIO_OK = "Ruta Sur"
PASSWORD_OK = "Brigada2026*"

TENANTS = [
    ("victor",  "Víctor Céspedes"),
    ("rodrigo", "Rodrigo Tapia"),
    ("rutasur", "Ruta Sur"),
]

LOGIN_HTML = r"""
<div class="d-flex align-items-center justify-content-center" style="min-height: calc(100vh - 80px);">
  <div class="card p-4" style="max-width:440px;width:100%; border:1px solid rgba(255,255,255,.12); background: rgba(15,23,42,.75); backdrop-filter: blur(8px); border-radius: 18px; box-shadow: 0 18px 50px rgba(0,0,0,.35);">
    <div class="text-center mb-3">
      <div class="h4 mb-1 text-white">Ruta Sur Rent A Car</div>
      <div class="small" style="color:#94a3b8;">Ingreso al panel</div>
    </div>

    {% if error %}
      <div class="alert alert-danger py-2 small mb-3">{{ error }}</div>
    {% endif %}

    <form method="post" autocomplete="off">
      <div class="mb-3">
        <label class="form-label text-white">Usuario</label>
        <input name="usuario" class="form-control" placeholder="Ruta Sur" required
               style="background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#fff;">
      </div>

      <div class="mb-3">
        <label class="form-label text-white">Contraseña</label>

        <div class="input-group">
          <input id="password" name="password" type="password" class="form-control" placeholder="Brigada2026*" required
                 style="background: rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.14); color:#fff;">
          <button class="btn btn-outline-light" type="button" id="togglePassword"
                  style="border:1px solid rgba(255,255,255,.14);">
            <span id="eyeIcon">👁</span>
          </button>
        </div>

        <div class="form-text" style="color:#94a3b8;">Toca el ojo para ver/ocultar.</div>
      </div>

      <div class="form-check mb-3 d-flex align-items-center gap-2">
        <input class="form-check-input m-0"
               type="checkbox"
               value="1"
               id="remember"
               name="remember"
               style="width: 20px; height: 20px; cursor: pointer; accent-color:#0ea5e9;">
        <label class="form-check-label"
               for="remember"
               style="color:#94a3b8; cursor:pointer; user-select:none;">
          Recordarme por 30 días
        </label>
      </div>

      <button class="btn w-100" style="background:#0ea5e9; border-color:#0ea5e9; color:#fff;">Ingresar</button>
    </form>

    <div class="text-center mt-3 small" style="color:#94a3b8;">
      Si no marcas el ticket, la sesión se cerrará al salir del navegador.
    </div>
  </div>
</div>

<script>
(function(){
  const btn = document.getElementById('togglePassword');
  const input = document.getElementById('password');
  const icon = document.getElementById('eyeIcon');
  if(!btn || !input) return;

  btn.addEventListener('click', function(){
    const isPwd = input.getAttribute('type') === 'password';
    input.setAttribute('type', isPwd ? 'text' : 'password');
    if(icon) icon.textContent = isPwd ? '🙈' : '👁';
  });
})();
</script>
"""

ELEGIR_HTML = r"""
<div class="d-flex align-items-center justify-content-center" style="min-height: calc(100vh - 80px);">
  <div style="max-width: 720px; width:100%;">
    <div class="d-flex align-items-center justify-content-between mb-3">
      <div>
        <div class="h4 mb-1 text-white">Elegir cuenta</div>
        <div class="small" style="color:#94a3b8;">Puedes cambiar cuando quieras</div>
      </div>
      <a class="btn btn-outline-light btn-sm" href="{{ url_for('auth.logout') }}">Salir</a>
    </div>

    <div class="row g-3">
      {% for key, label in tenants %}
        <div class="col-12 col-md-4">
          <a href="{{ url_for('auth.set_tenant', tenant=key) }}" style="text-decoration:none;">
            <div class="p-3"
                 style="border:1px solid rgba(255,255,255,.12);
                        background: rgba(15,23,42,.75);
                        border-radius: 18px;
                        box-shadow: 0 18px 50px rgba(0,0,0,.25);
                        cursor:pointer;
                        transition: transform .12s ease, border-color .12s ease, background-color .12s ease;"
                 onmouseover="this.style.transform='translateY(-3px)'; this.style.borderColor='#7dd3fc'; this.style.backgroundColor='rgba(224,242,254,.08)';"
                 onmouseout="this.style.transform='translateY(0px)'; this.style.borderColor='rgba(255,255,255,.12)'; this.style.backgroundColor='rgba(15,23,42,.75)';">
              <div class="h5 mb-1 text-white">{{ label }}</div>
              <div class="small" style="color:#94a3b8;">Entrar</div>
            </div>
          </a>
        </div>
      {% endfor %}
    </div>
  </div>
</div>
"""

def _render_in_layout(layout_base, inner_html, **ctx):
    return render_template_string(
        layout_base,
        content=render_template_string(inner_html, **ctx),
        active=""
    )

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    from flask import current_app
    layout = current_app.config.get("LAYOUT_BASE")

    # GET: mostrar login
    if request.method == "GET":
        return _render_in_layout(layout, LOGIN_HTML, error=None)

    # POST: validar credenciales
    u = (request.form.get("usuario") or "").strip()
    p = (request.form.get("password") or "").strip()

    if u == USUARIO_OK and p == PASSWORD_OK:
        session["logged_in"] = True

        # ✔ recordar sesión solo si el usuario lo marcó
        recordar = request.form.get("remember")
        session.permanent = True if recordar else False

        # si ya tenía tenant guardado, entra directo
        if session.get("tenant"):
            return redirect(url_for("inicio.inicio"))

        return redirect(url_for("auth.elegir"))

    # credenciales malas
    return _render_in_layout(layout, LOGIN_HTML, error="Usuario o contraseña incorrectos.")

@auth_bp.route("/elegir")
def elegir():
    from flask import current_app
    layout = current_app.config.get("LAYOUT_BASE")

    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))

    return _render_in_layout(layout, ELEGIR_HTML, tenants=TENANTS)

@auth_bp.route("/set/<tenant>")
def set_tenant(tenant):
    if not session.get("logged_in"):
        return redirect(url_for("auth.login"))

    keys = {k for k, _ in TENANTS}
    if tenant not in keys:
        return redirect(url_for("auth.elegir"))

    session["tenant"] = tenant
    # ✅ No tocar session.permanent aquí; se define en el login por el ticket.
    return redirect(url_for("inicio.inicio"))

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))