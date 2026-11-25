"""Módulo de Eric (Arquitecto).

HU-06 · Avisos/notificaciones al tutor.
HU-11 · Al aprobar una adopción, actualizar el RUT del tutor en el M1 (con reintentos y log).
"""
import uuid
from datetime import datetime, timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from adopciones import db, nucleo
from adopciones.respuestas import error, paginar
from adopciones.seguridad import requiere_token


def _ahora_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# =====================================================================
# HU-06 · NOTIFICACIONES
#   Colección 'notificaciones': { notificacionId, rut, mensaje, leida, fechaCreacion }
# =====================================================================
def crear_notificacion(rut, mensaje):
    """Crea un aviso para un tutor. Reutilizable por otros flujos (HU-16 / HU-09)."""
    doc = {
        'notificacionId': 'N-' + uuid.uuid4().hex[:8].upper(),
        'rut': rut,
        'mensaje': mensaje,
        'leida': False,
        'fechaCreacion': _ahora_iso(),
    }
    db.notificaciones().insert_one(dict(doc))
    return doc


@api_view(['GET', 'POST'])
@requiere_token
def notificaciones(request):
    perfil = request.usuario['perfil']
    if request.method == 'POST':
        if perfil != 'funcionario':
            return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario')
        datos = request.data or {}
        rut = datos.get('rut')
        mensaje = datos.get('mensaje')
        if not rut or not mensaje:
            return error(400, 'DATOS_FALTANTES', 'Se requieren rut y mensaje')
        return Response(crear_notificacion(rut, mensaje), status=201)

    if perfil != 'vecino':
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: vecino')
    docs = list(
        db.notificaciones()
        .find({'rut': request.usuario['rut']}, {'_id': 0})
        .sort('fechaCreacion', -1)
    )
    return Response(paginar(docs, request))


@api_view(['PATCH'])
@requiere_token
def marcar_leida(request, nid):
    if request.usuario['perfil'] != 'vecino':
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: vecino')
    col = db.notificaciones()
    noti = col.find_one({'notificacionId': nid}, {'_id': 0})
    if not noti:
        return error(404, 'NOTIFICACION_NO_ENCONTRADA', f'No existe la notificación {nid}')
    if noti['rut'] != request.usuario['rut']:
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Solo puedes modificar tus propias notificaciones')
    col.update_one({'notificacionId': nid}, {'$set': {'leida': True}})
    noti['leida'] = True
    return Response(noti)


# =====================================================================
# HU-11 · ACTUALIZAR TUTOR EN EL M1 AL APROBAR
#   #66 cliente HTTP con reintentos  ·  #67 log de sincronización
#   Colección propia 'sincronizaciones' (desacoplada de la postulación de Sebastián).
# =====================================================================
MAX_REINTENTOS = 3


def _sincronizaciones():
    return db.get_db()['sincronizaciones']


def _mensaje_error(r):
    try:
        return r.json().get('error', {}).get('mensaje')
    except Exception:
        return None


def _log_sync(animal_id, tutor_rut, intentos, status, resultado, detalle=None):
    """#67 · guarda el resultado de la sincronización para trazabilidad ante fallos de red."""
    doc = {
        'sincronizacionId': 'S-' + uuid.uuid4().hex[:8].upper(),
        'animalId': animal_id,
        'nuevoTutorRut': tutor_rut,
        'intentos': intentos,
        'httpStatus': status,
        'resultado': resultado,      # ok | rechazado | fallo
        'detalle': detalle,
        'fecha': _ahora_iso(),
    }
    _sincronizaciones().insert_one(dict(doc))
    return doc


def actualizar_tutor_m1(animal_id, nuevo_tutor_rut, token):
    """#66 · Actualiza el tutor del animal en el M1 con reintentos. Devuelve el log.

    Esta es la función que el endpoint de APROBAR de Alexis (HU-09) debe llamar
    justo después de marcar la postulación como 'aprobada':

        from adopciones.modulos_indiv.hu_eric import actualizar_tutor_m1
        actualizar_tutor_m1(animalId, nuevoTutorRut, token)
    """
    ultimo_status = None
    detalle = None
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            r = nucleo.actualizar_tutor(animal_id, nuevo_tutor_rut, token)
        except nucleo.NucleoNoDisponible as e:
            detalle = str(e)                       # red caída: reintenta
            ultimo_status = None
            continue
        ultimo_status = r.status_code
        if r.status_code in (200, 201):
            return _log_sync(animal_id, nuevo_tutor_rut, intento, r.status_code, 'ok')
        if r.status_code in (404, 409):
            # no existe / conflicto de negocio (fallecido o nuevo tutor con prohibición):
            # reintentar no cambia el resultado.
            return _log_sync(animal_id, nuevo_tutor_rut, intento, r.status_code,
                             'rechazado', _mensaje_error(r))
        detalle = _mensaje_error(r)                 # 5xx u otro: reintenta
    return _log_sync(animal_id, nuevo_tutor_rut, MAX_REINTENTOS, ultimo_status, 'fallo', detalle)


@api_view(['POST'])
@requiere_token
def sincronizar_tutor(request):
    """Endpoint de prueba/manual de HU-11 (funcionario). Permite verificar la
    actualización del tutor en el M1 sin depender aún del endpoint de aprobar.
    Cuerpo: { "animalId": "...", "tutorRut": "..." }."""
    if request.usuario['perfil'] not in ('funcionario', 'admin'):
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario')
    datos = request.data or {}
    animal_id = datos.get('animalId')
    tutor_rut = datos.get('tutorRut')
    if not animal_id or not tutor_rut:
        return error(400, 'DATOS_FALTANTES', 'Se requieren animalId y tutorRut')

    log = actualizar_tutor_m1(animal_id, tutor_rut, request.token)
    codigo = {'ok': 200, 'rechazado': 409}.get(log['resultado'], 502)
    return Response(log, status=codigo)
