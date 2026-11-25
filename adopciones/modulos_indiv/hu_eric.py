"""HU-06 · Avisos/notificaciones al tutor.

Modelo Notificacion (colección 'notificaciones'):
    { notificacionId, rut, mensaje, leida (bool), fechaCreacion }

Endpoints:
    POST  /api/adopciones/notificaciones             (funcionario) crea un aviso a un tutor
    GET   /api/adopciones/notificaciones             (vecino) lista los avisos propios
    PATCH /api/adopciones/notificaciones/<id>/leida  (vecino) marca un aviso como leído

La generación AUTOMÁTICA al cancelarse una postulación (HU-16 Sebastián / HU-09 Alexis)
reutilizará crear_notificacion(); esa conexión se hace cuando esos flujos existan.
"""
import uuid
from datetime import datetime, timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from adopciones import db
from adopciones.respuestas import error, paginar
from adopciones.seguridad import requiere_token


def _ahora_iso():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def crear_notificacion(rut, mensaje):
    """Crea un aviso para un tutor. Reutilizable por otros flujos (HU-16 / HU-09)."""
    doc = {
        'notificacionId': 'N-' + uuid.uuid4().hex[:8].upper(),
        'rut': rut,
        'mensaje': mensaje,
        'leida': False,
        'fechaCreacion': _ahora_iso(),
    }
    db.notificaciones().insert_one(dict(doc))   # la copia recibe el _id; no lo exponemos
    return doc


@api_view(['GET', 'POST'])
@requiere_token
def notificaciones(request):
    perfil = request.usuario['perfil']

    if request.method == 'POST':
        # Crear un aviso (funcionario). Corresponde a HU-06 #82 (creación manual del aviso).
        if perfil != 'funcionario':
            return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario')
        datos = request.data or {}
        rut = datos.get('rut')
        mensaje = datos.get('mensaje')
        if not rut or not mensaje:
            return error(400, 'DATOS_FALTANTES', 'Se requieren rut y mensaje')
        return Response(crear_notificacion(rut, mensaje), status=201)

    # GET: el vecino ve solo sus propios avisos (RN-05), más nuevos primero.
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
    if noti['rut'] != request.usuario['rut']:          # RN-05: solo las propias
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Solo puedes modificar tus propias notificaciones')
    col.update_one({'notificacionId': nid}, {'$set': {'leida': True}})
    noti['leida'] = True
    return Response(noti)
