"""
HU-05 · Postulaciones (crear).

POST /api/adopciones/postulaciones   (perfil: vecino)

El núcleo de HU-05: VARIOS vecinos distintos pueden postular al MISMO animal.
No se bloquea por existir otras postulaciones; solo por reglas del negocio:
  - RN-04: un postulante con prohibición de tenencia no puede postular.
  - RN-11: un vecino no puede tener más de 2 postulaciones activas a la vez.
  - El animal debe existir y tener microchip en el M1 (RN-06) y no estar ya adoptado (RN-07).
"""
import uuid
from datetime import datetime, timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import db, nucleo
from .seguridad import requiere_perfil
from .estados import RECIBIDA, ACTIVAS, APROBADA, ADOPCION_CONCRETADA
from .respuestas import error


def _ahora_iso():
    # Fecha en ISO 8601 UTC, como exige la ficha (2026-11-25T19:00:00Z).
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


@api_view(['POST'])
@requiere_perfil('vecino')
def crear_postulacion(request):
    datos = request.data or {}
    animal_id = datos.get('animalId')
    if not animal_id:
        return error(400, 'DATOS_FALTANTES', 'Falta animalId')

    rut = request.usuario['rut']
    token = request.token

    # RN-04: prohibición de tenencia (se lo preguntamos al núcleo).
    try:
        ru = nucleo.obtener_usuario(rut, token)
    except nucleo.NucleoNoDisponible:
        return error(503, 'NUCLEO_NO_DISPONIBLE', 'No se pudo consultar al núcleo')
    if ru.status_code == 200 and ru.json().get('prohibicionTenencia'):
        return error(409, 'PROHIBICION_TENENCIA',
                     'La persona tiene prohibición de tenencia y no puede adoptar')

    # El animal debe existir y tener microchip en el M1.
    try:
        ra = nucleo.obtener_animal(animal_id, token)
    except nucleo.NucleoNoDisponible:
        return error(503, 'NUCLEO_NO_DISPONIBLE', 'No se pudo consultar el animal en el Módulo 1')
    if ra.status_code == 404:
        return error(404, 'ANIMAL_NO_ENCONTRADO', f'No existe el animal {animal_id}')
    if ra.status_code != 200:
        return error(502, 'ERROR_MODULO1', 'El Módulo 1 respondió con un error')
    animal = ra.json()
    if animal.get('estado') != 'con_microchip':
        return error(409, 'ANIMAL_NO_ADOPTABLE',
                     'El animal no está disponible para adopción (requiere estado con_microchip)')

    col = db.postulaciones()

    # RN-07: el animal no puede estar ya adoptado / en adopción concretada.
    if col.find_one({'animalId': animal_id, 'estado': {'$in': [APROBADA, ADOPCION_CONCRETADA]}}):
        return error(409, 'ANIMAL_YA_ADOPTADO', 'Este animal ya tiene una adopción en curso')

    # RN-11: máximo 2 postulaciones activas por persona.
    activas = col.count_documents({'postulanteRut': rut, 'estado': {'$in': ACTIVAS}})
    if activas >= 2:
        return error(409, 'LIMITE_POSTULACIONES',
                     'Ya tienes 2 postulaciones activas (máximo permitido)')

    postulacion = {
        'postulacionId': 'P-' + uuid.uuid4().hex[:8].upper(),
        'animalId': animal_id,
        'postulanteRut': rut,
        'estado': RECIBIDA,
        'fechaPostulacion': _ahora_iso(),
        'formulario': datos.get('formulario', {}),
    }
    col.insert_one(dict(postulacion))   # la copia recibe el _id de Mongo; no lo exponemos
    return Response(postulacion, status=201)
