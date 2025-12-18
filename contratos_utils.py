# contratos_utils.py
import os, json
from datetime import datetime
from flask import current_app

def _data_file():
    # Usa la misma ruta configurada en app.py
    return current_app.config.get("CONTRACTS_FILE", os.path.join(current_app.root_path, "contracts.json"))

def _load_contracts():
    path = _data_file()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []
    return []

def _save_contracts(data):
    path = _data_file()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def iso_to_dmy(iso):
    try:
        return datetime.strptime((iso or "").strip(), "%Y-%m-%d").strftime("%d-%m-%Y")
    except Exception:
        return (iso or "")

def _next_id(contratos):
    return (max([c.get("id", 0) for c in contratos]) + 1) if contratos else 1

def upsert_contract_from_event(ev: dict, veh: dict | None):
    """
    Crea o actualiza un contrato a partir de un evento de calendario (reserva).
    - Si existe contrato con mismo evento_id => actualiza.
    - Si no existe => crea uno nuevo.
    """
    if not ev or (ev.get("tipo") or "reserva") != "reserva":
        return  # Solo sincronizamos reservas

    contratos = _load_contracts()

    # Buscar contrato existente por evento_id
    cid = None
    for c in contratos:
        if int(c.get("evento_id") or 0) == int(ev.get("id") or 0):
            cid = c.get("id")
            break

    # Datos del cliente (ev.cliente {...} o campos sueltos)
    cli = ev.get("cliente") or {}
    nombre  = (ev.get("cliente_nombre") or cli.get("nombre") or ev.get("nombre") or "").strip()
    apellido= (ev.get("cliente_apellido") or cli.get("apellido") or ev.get("apellido") or "").strip()
    rut     = (cli.get("rut") or ev.get("rut") or ev.get("cliente_rut") or "").strip()
    fono    = (cli.get("telefono") or ev.get("telefono") or ev.get("cliente_telefono") or "").strip()
    email   = (cli.get("email") or ev.get("email") or ev.get("correo") or ev.get("cliente_email") or "").strip()
    nac     = (cli.get("nacionalidad") or ev.get("nacionalidad") or "").strip()

    # Fechas y monto
    desde = iso_to_dmy(ev.get("inicio"))
    hasta = iso_to_dmy(ev.get("fin"))
    monto = int(ev.get("total_amount") or 0)

    # Datos del vehículo
    marca   = (veh or {}).get("marca") or ""
    modelo  = (veh or {}).get("modelo") or ""
    anio    = (veh or {}).get("anio") or ""
    patente = (veh or {}).get("patente") or ""

    base = {
        "cliente_nombre": nombre,
        "cliente_apellido": apellido,
        "cliente_rut": rut,
        "cliente_telefono": fono,
        "cliente_email": email,
        "cliente_nacionalidad": nac,
        "vehiculo_marca": marca,
        "vehiculo_modelo": modelo,
        "vehiculo_anio": anio,
        "vehiculo_patente": patente,
        "desde": desde,
        "hasta": hasta,
        "monto": monto,
        # Por defecto, una reserva viva debería quedar "vigente"
        "estado": "vigente",
        "obs": (ev.get("tooltip") or ev.get("label") or "").strip(),
        "evento_id": int(ev.get("id") or 0),
    }

    if cid is None:
        # Crear
        base["id"] = _next_id(contratos)
        contratos.append(base)
    else:
        # Actualizar
        for i, c in enumerate(contratos):
            if int(c.get("id")) == int(cid):
                base["id"] = cid
                contratos[i] = base
                break

    _save_contracts(contratos)