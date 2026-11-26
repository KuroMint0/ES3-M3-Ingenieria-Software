"""
HU-01 (postular) y HU-07 (formulario con consentimiento).

POST /api/adopciones/postulaciones   (perfil: vecino)

Es UN solo endpoint: el cuerpo trae animalId y formulario. Así nunca queda
guardada una postulación sin los datos legales (RF-04, Ley 21.719).
"""
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError
from rest_framework.response import Response

from . import db, estados, nucleo
from . import repositorio_postulaciones as repo
from .respuestas import error
from .validadores import (
    PostulacionSerializer,
    campos_no_permitidos_postulacion,
    mensaje_errores,
)

# [VERIFICA] con las respuestas reales del núcleo / M1 simulado:
ESTADO_ANIMAL_FALLECIDO = 'fallecido'       # valor de "estado" de un animal fallecido
CAMPO_PROHIBICION = 'prohibicionTenencia'   # nombre del campo en GET /usuarios/{rut}


def _json(respuesta):
    """Cuerpo JSON de una respuesta del núcleo, o None si no es JSON válido."""
    try:
        return respuesta.json()
    except ValueError:
        return None


def crear_postulacion(request):
    # --- Paso 3: validar el cuerpo ANTES de usarlo en cualquier otra cosa ------
    datos = request.data            # JSON roto -> ParseError -> 400 (manejador_excepciones)

    if campos_no_permitidos_postulacion(datos):
        return error(400, 'VALIDACION', 'El cuerpo incluye campos que no están permitidos')

    serializador = PostulacionSerializer(data=datos)
    if not serializador.is_valid():
        return error(400, 'VALIDACION', mensaje_errores(serializador.errors))
    validados = serializador.validated_data
    animal_id = validados['animalId']

    # El postulante es SIEMPRE el RUT de la sesión, nunca uno enviado en el cuerpo
    # (si no, cualquiera postularía a nombre de otra persona: OWASP A01).
    rut = request.usuario.get('rut')
    if not rut:
        return error(401, 'TOKEN_INVALIDO', 'La sesión no entregó un RUT válido')

    # --- Paso 4: el animal existe en el Módulo 1 (RN-01) ------------------------
    resp_animal = nucleo.obtener_animal(animal_id, request.token)
    if resp_animal.status_code == 404:
        return error(404, 'ANIMAL_NO_ENCONTRADO', 'El animal no existe en el registro')
    if resp_animal.status_code == 401:
        return error(401, 'TOKEN_INVALIDO', 'El token no es válido o expiró')
    animal = _json(resp_animal)
    if resp_animal.status_code != 200 or not isinstance(animal, dict):
        return error(503, 'NUCLEO_NO_DISPONIBLE', 'No se pudo consultar el registro de animales')

    # --- Paso 5: animal fallecido -------------------------------------------------
    if animal.get('estado') == ESTADO_ANIMAL_FALLECIDO:
        return error(409, 'ANIMAL_NO_DISPONIBLE', 'El animal no está disponible para adopción')

    # --- Paso 6: el animal está publicado para adopción (HU-04) -------------------
    publicado = db.publicaciones().find_one(
        {'animalId': animal_id, 'estado': 'disponible'}, {'_id': 1})
    if publicado is None:
        return error(409, 'ANIMAL_NO_DISPONIBLE', 'El animal no está disponible para adopción')

    # --- Paso 7: prohibición de tenencia (RN-04) -----------------------------------
    resp_usuario = nucleo.obtener_usuario(rut, request.token)
    usuario = _json(resp_usuario)
    if resp_usuario.status_code != 200 or not isinstance(usuario, dict):
        # Si no podemos comprobar la prohibición, NO dejamos postular (falla cerrado).
        return error(503, 'NUCLEO_NO_DISPONIBLE', 'No se pudo verificar al postulante')
    if CAMPO_PROHIBICION not in usuario:
        # Nombre de campo equivocado: que falle fuerte, no que deje pasar a todos.
        return error(503, 'RESPUESTA_INESPERADA', 'El núcleo respondió con un formato inesperado')
    if usuario[CAMPO_PROHIBICION]:
        return error(409, 'PROHIBICION_TENENCIA',
                     'La persona tiene prohibición de tenencia y no puede postular')

    # --- Paso 8: duplicado (1.ª capa, mensaje claro) -------------------------------
    repo.asegurar_indices()
    if repo.buscar_activa(animal_id, rut):
        return error(409, 'POSTULACION_DUPLICADA',
                     'Ya tienes una postulación activa para este animal')

    # --- Paso 8.5: antecedentes del postulante (HU-12, RN-10) ----------------------
    # Reconecta la validación de Alexis (máximo de animales a cargo). La prohibición
    # de tenencia ya se verificó en el Paso 7, así que aquí el aporte real es el tope
    # de animales. Import local para evitar import circular con hu_alexis, que delega
    # el POST a esta misma función.
    from .modulos_indiv.hu_alexis import (
        ErrorReglaNegocio,
        validar_antecedentes_postulante,
    )
    try:
        validar_antecedentes_postulante(rut, request.token)
    except ErrorReglaNegocio as exc:
        if exc.status == 409:
            # Bloqueo real de negocio (p. ej. supera el máximo de animales a cargo).
            return error(409, exc.codigo, exc.mensaje)
        if exc.status != 404:
            # 404 = la persona no tiene ficha de tutor todavía (0 animales a cargo):
            # se permite postular. Cualquier otro fallo (M1 caído) cierra el paso.
            return error(503, 'NUCLEO_NO_DISPONIBLE',
                         'No se pudieron verificar los antecedentes del postulante')

    # --- Paso 9: armar el documento. TODO lo sensible lo asigna el servidor ---------
    documento = {
        'postulacionId': repo.siguiente_id(),
        'animalId': animal_id,
        'postulanteRut': rut,                           # de la sesión
        'estado': estados.RECIBIDA,                     # estado inicial de la ficha
        'fechaPostulacion': datetime.now(timezone.utc),
        'formulario': dict(validados['formulario']),
        'historialEvaluacion': [],
        'seguimientoPosterior': [],
    }
    try:
        creado = repo.crear(documento)
    except DuplicateKeyError:
        # 2.ª capa: el índice único parcial atrapó un doble envío simultáneo.
        return error(409, 'POSTULACION_DUPLICADA',
                     'Ya tienes una postulación activa para este animal')

    # --- Paso 10 ---------------------------------------------------------------------
    return Response(creado, status=201)


@api_view(['POST'])
@requiere_perfil('vecino')
def crear_postulacion(request):
    return procesar_creacion_postulacion(request)