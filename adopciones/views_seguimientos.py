"""
HU-08: seguimiento posterior a la adopción, con archivos de evidencia.

POST /api/adopciones/postulaciones/{id}/seguimientos                (funcionario)
GET  /api/adopciones/postulaciones/{id}/seguimientos                (funcionario, jefatura)
GET  /api/adopciones/postulaciones/{id}/seguimientos/{controlId}/archivo
                                                                    (funcionario, jefatura)

El POST acepta DOS formas de entrada:
  - JSON      {"observaciones": "..."}          (lo usa la verificación de entrega.json)
  - multipart observaciones + archivo (opcional: PDF, JPG o PNG)

Los archivos se guardan en GridFS (dentro de la misma base de MongoDB): el disco de
Render en el plan gratuito es efímero y los archivos se perderían al reiniciar.
"""
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from django.http import HttpResponse
from gridfs.errors import NoFile
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from . import db, estados
from . import repositorio_postulaciones as repo
from .respuestas import error, paginar
from .seguridad import requiere_perfil, requiere_token
from .validadores import (
    EXTENSIONES,
    MAX_ARCHIVO,
    ArchivoInvalido,
    SeguimientoSerializer,
    campos_no_permitidos,
    es_control_id,
    es_postulacion_id,
    mensaje_errores,
    validar_archivo,
)

# Tope del cuerpo completo: archivo + margen para los campos y separadores multipart.
LIMITE_CUERPO = MAX_ARCHIVO + 64 * 1024


def _cuerpo_demasiado_grande(request):
    """
    Revisa Content-Length ANTES de leer request.data (DRF solo procesa el cuerpo
    cuando se accede a él). Si el encabezado no es un número, se rechaza.
    """
    try:
        largo = int(request.META.get('CONTENT_LENGTH') or 0)
    except (TypeError, ValueError):
        return True
    return largo > LIMITE_CUERPO


def _publico(control):
    """Copia del control SIN el archivoId interno de GridFS."""
    publico = dict(control)
    archivo = publico.get('archivo')
    if archivo:
        publico['archivo'] = {k: v for k, v in archivo.items() if k != 'archivoId'}
    return publico


# ---------------------------------------------------------------------------
# /postulaciones/{id}/seguimientos  (GET lista, POST crea)
# Django no enruta por método: una ruta, una vista que reparte según el método.
# El perfil se revisa DENTRO porque cada método tiene perfiles distintos.
# Orden de decoradores: @api_view siempre arriba de @parser_classes.
# ---------------------------------------------------------------------------
@api_view(['GET', 'POST'])
@parser_classes([JSONParser, MultiPartParser])   # multipart SOLO en esta vista
@requiere_token
def seguimientos(request, postulacion_id):
    if request.method == 'POST':
        return _crear_seguimiento(request, postulacion_id)
    return _listar_seguimientos(request, postulacion_id)


def _crear_seguimiento(request, postulacion_id):
    # 1) Perfil.
    if request.usuario.get('perfil') != 'funcionario':
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario')

    # 2) El id tiene forma válida (si no, para el cliente "no existe").
    if not es_postulacion_id(postulacion_id):
        return error(404, 'POSTULACION_NO_ENCONTRADA', 'La postulación no existe')

    # 3) Tamaño del cuerpo, antes de leerlo.
    if _cuerpo_demasiado_grande(request):
        return error(400, 'ARCHIVO_DEMASIADO_GRANDE', 'La petición supera el tamaño máximo permitido')

    # 4) La postulación existe.
    postulacion = repo.obtener(postulacion_id)
    if postulacion is None:
        return error(404, 'POSTULACION_NO_ENCONTRADA', 'La postulación no existe')

    # 5) Regla del negocio: solo se hace seguimiento de adopciones concretadas.
    if postulacion.get('estado') != estados.ADOPCION_CONCRETADA:
        return error(409, 'ESTADO_NO_PERMITE_SEGUIMIENTO',
                     'Solo se registra seguimiento en adopciones concretadas')

    # 6) Campos permitidos: observaciones y archivo (este último solo como multipart).
    datos = request.data
    archivo = request.FILES.get('archivo')
    if campos_no_permitidos(datos, SeguimientoSerializer, extras=('archivo',)):
        return error(400, 'VALIDACION', 'El cuerpo incluye campos que no están permitidos')
    if isinstance(datos, dict) and 'archivo' in datos and archivo is None:
        return error(400, 'VALIDACION', 'El archivo debe enviarse como multipart/form-data')

    # 7) Observaciones.
    serializador = SeguimientoSerializer(data=datos)
    if not serializador.is_valid():
        return error(400, 'VALIDACION', mensaje_errores(serializador.errors))

    # 8) Archivo (si viene).
    info = None
    if archivo is not None:
        try:
            info = validar_archivo(archivo)
        except ArchivoInvalido as exc:
            return error(400, 'ARCHIVO_INVALIDO', str(exc))

    # 9) Identificador aleatorio (no secuencial: no se puede adivinar el siguiente).
    control_id = uuid.uuid4().hex

    # 10) Guardar el archivo en GridFS. El nombre interno lo generamos nosotros.
    bucket = db.bucket_seguimientos()
    file_id = None
    registro_archivo = None
    if info is not None:
        file_id = bucket.upload_from_stream(
            f"{control_id}.{info['extension']}",
            archivo,
            metadata={
                'postulacionId': postulacion_id,
                'controlId': control_id,
                'tipo': info['tipo'],
            },
        )
        registro_archivo = {
            'nombreOriginal': info['nombreOriginal'],   # solo como dato
            'extension': info['extension'],
            'tipo': info['tipo'],
            'tamano': archivo.size,
            'archivoId': str(file_id),                  # interno: no se devuelve
        }

    # 11) Agregar el control a la postulación.
    control = {
        'controlId': control_id,
        'observaciones': serializador.validated_data['observaciones'],
        'fechaControl': datetime.now(timezone.utc),     # la fija el servidor
        'registradoPor': request.usuario.get('rut'),
        'archivo': registro_archivo,
    }
    try:
        agregado = repo.agregar_control(postulacion_id, control)
    except Exception:
        if file_id is not None:
            bucket.delete(file_id)                      # que no quede un archivo huérfano
        raise

    # 12) Si el estado cambió mientras tanto, se deshace el archivo.
    if not agregado:
        if file_id is not None:
            bucket.delete(file_id)
        return error(409, 'ESTADO_NO_PERMITE_SEGUIMIENTO',
                     'Solo se registra seguimiento en adopciones concretadas')

    # 13) Creado.
    return Response(_publico(control), status=201)


def _listar_seguimientos(request, postulacion_id):
    if request.usuario.get('perfil') not in ('funcionario', 'jefatura'):
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario, jefatura')
    if not es_postulacion_id(postulacion_id):
        return error(404, 'POSTULACION_NO_ENCONTRADA', 'La postulación no existe')
    postulacion = repo.obtener(postulacion_id)
    if postulacion is None:
        return error(404, 'POSTULACION_NO_ENCONTRADA', 'La postulación no existe')

    controles = [_publico(c) for c in postulacion.get('seguimientoPosterior', [])]
    return Response(paginar(controles, request))


# ---------------------------------------------------------------------------
# Descarga de un archivo de evidencia.
# ---------------------------------------------------------------------------
@api_view(['GET'])
@requiere_perfil('funcionario', 'jefatura')
def descargar_archivo(request, postulacion_id, control_id):
    if not es_postulacion_id(postulacion_id) or not es_control_id(control_id):
        return error(404, 'ARCHIVO_NO_ENCONTRADO', 'El archivo no existe')

    postulacion = repo.obtener(postulacion_id)
    if postulacion is None:
        return error(404, 'ARCHIVO_NO_ENCONTRADO', 'El archivo no existe')

    control = next(
        (c for c in postulacion.get('seguimientoPosterior', [])
         if c.get('controlId') == control_id),
        None,
    )
    if control is None or not control.get('archivo'):
        return error(404, 'ARCHIVO_NO_ENCONTRADO', 'El archivo no existe')

    extension = control['archivo'].get('extension')
    if extension not in EXTENSIONES:
        return error(404, 'ARCHIVO_NO_ENCONTRADO', 'El archivo no existe')

    try:
        oid = ObjectId(control['archivo']['archivoId'])
        flujo = db.bucket_seguimientos().open_download_stream(oid)
    except (InvalidId, KeyError, TypeError, NoFile):
        return error(404, 'ARCHIVO_NO_ENCONTRADO', 'El archivo no existe')

    contenido = flujo.read()
    flujo.close()

    # Tipo de contenido sale de NUESTRA tabla (no del cliente) y se entrega como
    # adjunto, con un nombre generado por nosotros (no el original).
    respuesta = HttpResponse(contenido, content_type=EXTENSIONES[extension])
    respuesta['Content-Disposition'] = f'attachment; filename="seguimiento-{control_id}.{extension}"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta