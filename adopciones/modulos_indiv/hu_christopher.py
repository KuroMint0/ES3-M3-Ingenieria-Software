"""HU-04/HU-13 : publicar un animal con microchip."""
from collections.abc import Mapping
from datetime import datetime, timezone

from rest_framework.decorators import api_view
from rest_framework.response import Response

from adopciones import db, modelos, nucleo
from adopciones.respuestas import error
from adopciones.seguridad import requiere_perfil


_CAMPOS_ANIMAL = ('nombre', 'especie', 'raza', 'edadAproximada', 'microchip')


@api_view(['POST'])
@requiere_perfil('funcionario')
def publicar(request):
    animal_id = request.data.get('animalId') if isinstance(request.data, Mapping) else None
    if not isinstance(animal_id, str) or not animal_id.strip():
        return error(400, 'ANIMAL_ID_INVALIDO', 'animalId debe ser un texto no vacío')
    animal_id = animal_id.strip()

    campos_opcionales = {}
    for campo in ('descripcion', 'fotografia'):
        valor = request.data.get(campo)
        if valor is not None and not isinstance(valor, str):
            return error(400, 'CAMPO_INVALIDO', f'{campo} debe ser texto o estar vacío')
        campos_opcionales[campo] = valor.strip() or None if valor is not None else None

    try:
        respuesta = nucleo.obtener_animal(animal_id, request.token)
    except nucleo.NucleoNoDisponible:
        return error(503, 'NUCLEO_NO_DISPONIBLE',
                     'No se pudo consultar el animal en el núcleo')

    if respuesta.status_code == 404:
        return error(404, 'ANIMAL_NO_ENCONTRADO', 'El animal no existe en el M1')
    if respuesta.status_code != 200:
        return error(502, 'ERROR_CONSULTA_M1', 'No se pudo consultar el animal en el M1')

    try:
        animal = respuesta.json()
    except ValueError:
        return error(502, 'RESPUESTA_M1_INVALIDA',
                     'El M1 respondió con un documento inválido')

    if not isinstance(animal, Mapping):
        return error(502, 'RESPUESTA_M1_INVALIDA',
                     'El M1 respondió con un documento inválido')
    if animal.get('estado') != 'con_microchip':
        return error(409, 'ANIMAL_SIN_MICROCHIP',
                     'El animal debe tener microchip para ser publicado')
    if any(campo not in animal for campo in _CAMPOS_ANIMAL):
        return error(502, 'RESPUESTA_M1_INVALIDA',
                     'El M1 respondió con datos del animal incompletos')

    publicaciones = db.publicaciones()
    if publicaciones.find_one({'animalId': animal_id}, {'_id': 1}):
        return error(409, 'ANIMAL_YA_PUBLICADO',
                     'El animal ya tiene una publicación')

    documento: modelos.Animal = {
        'animalId': animal_id,
        'nombre': animal['nombre'],
        'especie': animal['especie'],
        'raza': animal['raza'],
        'edadAproximada': animal['edadAproximada'],
        'tieneMicrochip': True,
        'microchip': animal['microchip'],
        'estado': modelos.ESTADO_DISPONIBLE,
        'publicadoPorRut': request.usuario['rut'],
        'fechaPublicacion': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'descripcion': campos_opcionales['descripcion'],
        'fotografia': campos_opcionales['fotografia'],
    }
    publicaciones.insert_one(dict(documento))
    return Response(documento, status=201)
