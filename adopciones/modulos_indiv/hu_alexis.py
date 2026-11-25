from datetime import date, datetime, timezone
import os
import uuid

import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response

from adopciones import db, estados, nucleo
from adopciones.respuestas import error, paginar
from adopciones.seguridad import requiere_perfil, requiere_token

M1_URL = nucleo.NUCLEO_URL
TIMEOUT_M1 = 8

MAX_ANIMALES_POR_TUTOR = 3
DIAS_SIN_JUSTIFICACION = 30

class ErrorReglaNegocio(Exception):
    def __init__(self, status, codigo, mensaje):
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje

def utc_actual():
    return datetime.now(timezone.utc)

def a_iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def desde_iso_utc(valor):
    if not valor:
        return None
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(timezone.utc)

def _llamar_m1(metodo, ruta, token, json_body=None):
    try:
        respuesta = requests.request(
            method=metodo,
            url=f'{M1_URL}{ruta}',
            headers={'Authorization': f'Bearer {token}'},
            json=json_body,
            timeout=TIMEOUT_M1,
        )
    except requests.RequestException:
        raise ErrorReglaNegocio(503, 'm1_no_disponible', 'El M1 no respondió')

    es_simulado = respuesta.headers.get('X-Simulado', '').strip().lower() == 'true'
    return respuesta, es_simulado

def _validar_animal_id(animal_id, es_simulado=None):
    "Se valida que el animalId tenga prefijo SIM- o A-"
    if not animal_id.startswith(('SIM-', 'A-')):
        raise ErrorReglaNegocio(
            400, 
            'animal_id_invalido',
            f'El animalId {animal_id} no tiene prefijo SIM- o A-'
        )
    if es_simulado is True and not animal_id.startswith('SIM-'):
        raise ErrorReglaNegocio(
            400, 
            'animal_id_invalido',
            f'El entorno M1 actual es simulado, pero el animalId {animal_id} no tiene prefijo SIM-'
        )
    if es_simulado is False and not animal_id.startswith('A-'):
        raise ErrorReglaNegocio(
            400, 
            'animal_id_invalido',
            f'El entorno M1 actual es real, pero el animalId {animal_id} no tiene prefijo A-'
        )

def consultar_tutor(rut, token):
    respuesta, es_simulado = _llamar_m1('GET', f'/api/registro/tutores/{rut}', token)

    if respuesta.status_code == 200:
        datos = respuesta.json()
        datos['_simulado'] = es_simulado
        return datos
    if respuesta.status_code == 404:
        raise ErrorReglaNegocio(404, 'tutor_no_encontrado', f'No se encontró tutor con rut {rut}')
    if respuesta.status_code == 403:
        raise ErrorReglaNegocio(403, 'tutor_no_autorizado', f'No autorizado para consultar tutor con rut {rut}')

    raise ErrorReglaNegocio(502, 'error_m1', f'Error al consultar tutor con rut {rut}')

def calcular_animales_tutor(rut, datos_tutor):
    raw_cargo = datos_tutor.get('animalesACargo')
    cargo_m1 = raw_cargo if (isinstance(raw_cargo, int) and not isinstance(raw_cargo, bool)) else 0

    ids_m1 = set(datos_tutor.get('animalIds') or [])
    ids_m3 = set(
        db.postulaciones().distinct(
            'animalId',
            {'postulanteRut': rut, 'estado': estados.ADOPCION_CONCRETADA},
        )
    )
    return max(cargo_m1, len(ids_m1 | ids_m3))

# Funciones importables para los demás integrantes del grupo

# Función para validar los antecedentes del postulante
def validar_antecedentes_postulante(rut, token):
    tutor = consultar_tutor(rut, token)
    motivos = []
    codigos = []

    # Validar prohibición de tenencia
    if bool(tutor.get('prohibicionTenencia')):
        codigos.append('prohibicion_tenencia')
        motivos.append('El postulante tiene prohibición de tenencia de animales.')

    # Validar la cantidad de animales a cargo actuales (no cuenta comunitarios)
    cant_animales = calcular_animales_tutor(rut, tutor)
    if cant_animales >= MAX_ANIMALES_POR_TUTOR:
        codigos.append('max_animales')
        motivos.append(f'El postulante tiene a cargo {cant_animales} animales, supenrando el máximo permitido de {MAX_ANIMALES_POR_TUTOR}.')

    if motivos:
        codigo_principal = codigos[0] if len(codigos) == 1 else 'postulacion_bloqueada_multiple'
        raise ErrorReglaNegocio(
            409,
            codigo_principal,
            f'Postulación bloqueada: {", ".join(motivos)}.',
        )
    return tutor

# Función para listar las postulaciones
def _preparar_formulario(raw_formulario):
    if not isinstance(raw_formulario, dict):
        raw_formulario = {}

    if raw_formulario and raw_formulario.get('consentimientoLey21719') is False:
        raise ErrorReglaNegocio(
            400,
            'CONSENTIMIENTO_REQUERIDO',
            'Debe aceptar el consentimiento explícito de cohabitantes (Ley 21.719) para postular.',
        )

    formulario_guardado = {
        'tipoVivienda': str(raw_formulario.get('tipoVivienda') or 'No especificado').strip(),
        'patioExterior': bool(raw_formulario.get('patioExterior', False)),
        'otrosAnimales': bool(raw_formulario.get('otrosAnimales', False)),
        'presenciaNiños': bool(
            raw_formulario.get('presenciaNiños')
            if 'presenciaNiños' in raw_formulario
            else raw_formulario.get('presenciaNinos', False)
        ),
        'consentimientoLey21719': bool(raw_formulario.get('consentimientoLey21719', True)),
    }
    for clave, valor in raw_formulario.items():
        if clave not in formulario_guardado and clave != 'presenciaNinos':
            formulario_guardado[clave] = valor
    return formulario_guardado

def listar_postulaciones_formulario(animal_id=None, estado=None):
    
    filtro = {}
    if animal_id:
        filtro['animalId'] = animal_id
    if estado:
        filtro['estado'] = estado
    docs = list(db.postulaciones().find(filtro, {'_id': 0}).sort('fechaPostulacion', -1))
    for doc in docs:
        if not isinstance(doc.get('formulario'), dict):
            doc['formulario'] = {}
        doc['estadosDisponibles'] = list(estados.ESTADOS)
    return docs

def procesar_cambio_estado(postulacion_id, nuevo_estado, funcionario_rut, token, justificacion_devolucion=None):
    
    if nuevo_estado not in estados.ESTADOS:
        raise ErrorReglaNegocio(400, 'ESTADO_INVALIDO', f'El estado "{nuevo_estado}" no es válido.')

    postulacion = db.postulaciones().find_one({'postulacionId': postulacion_id}, {'_id': 0})
    if not postulacion:
        raise ErrorReglaNegocio(404, 'POSTULACION_NO_ENCONTRADA', f'No existe la postulación {postulacion_id}.')

    estado_actual = postulacion['estado']
    if not estados.puede_transicionar(estado_actual, nuevo_estado):
        raise ErrorReglaNegocio(
            409,
            'TRANSICION_INVALIDA',
            f'No se puede pasar de "{estado_actual}" a "{nuevo_estado}".',
        )

    ahora = utc_actual()
    ahora_str = a_iso_utc(ahora)
    cambios = {'estado': nuevo_estado}

    # Integración con el módulo del Eric
    from adopciones.modulos_indiv import hu_eric

    if nuevo_estado == estados.APROBADA:
        hu_eric.actualizar_tutor_m1(postulacion['animalId'], postulacion['postulanteRut'], token)
        hu_eric.crear_notificacion(
            postulacion['postulanteRut'],
            f'Tu postulación {postulacion_id} para el animal {postulacion["animalId"]} fue APROBADA.',
        )

    if nuevo_estado == estados.RECHAZADA:
        hu_eric.crear_notificacion(
            postulacion['postulanteRut'],
            f'Tu postulación {postulacion_id} para el animal {postulacion["animalId"]} fue RECHAZADA.',
        )

    if nuevo_estado == estados.ADOPCION_CONCRETADA:
        cambios['fechaAdopcion'] = ahora_str
        db.publicaciones().update_one(
            {'animalId': postulacion['animalId']},
            {'$set': {'estado': 'adoptado', 'fechaActualizacion': ahora_str}},
            upsert=True,
        )
        hu_eric.actualizar_tutor_m1(postulacion['animalId'], postulacion['postulanteRut'], token)

    if nuevo_estado == estados.DEVUELTO:
        fecha_inicio = desde_iso_utc(postulacion.get('fechaAdopcion')) or desde_iso_utc(postulacion.get('fechaPostulacion'))
        dias_transcurridos = (ahora - fecha_inicio).days if fecha_inicio else 0
        justificacion_limpia = (justificacion_devolucion or '').strip()

        # HU-15 (RN-09): Obligatorio justificar si la devolución ocurre después de 30 días
        if dias_transcurridos > DIAS_SIN_JUSTIFICACION and not justificacion_limpia:
            raise ErrorReglaNegocio(
                400,
                'JUSTIFICACION_OBLIGATORIA',
                f'Han transcurrido {dias_transcurridos} días desde la adopción (> 30 días). Debe ingresar una justificación obligatoria.',
            )

        # HU-10: Desvincular tutor en M1 mediante PATCH /api/registro/animales/{animalId}/tutor con null
        resp_m1, es_simulado = _llamar_m1(
            'PATCH',
            f'/api/registro/animales/{postulacion["animalId"]}/tutor',
            token,
            json_body={'tutorRut': None},
        )
        if resp_m1.status_code not in (200, 204):
            raise ErrorReglaNegocio(
                409 if resp_m1.status_code == 409 else 502,
                'ERROR_ACTUALIZAR_TUTOR_M1',
                'Módulo 1 rechazó la desvinculación del tutor al registrar la devolución.',
            )

        cambios['fechaDevolucion'] = ahora_str
        cambios['diasDesdeAdopcion'] = dias_transcurridos
        cambios['justificacion_devolucion'] = justificacion_limpia or None
        cambios['m1Simulado'] = es_simulado

        # HU-10: El animal vuelve a estar disponible en el catálogo público de M3
        db.publicaciones().update_one(
            {'animalId': postulacion['animalId']},
            {'$set': {'estado': 'disponible', 'fechaActualizacion': ahora_str}},
            upsert=True,
        )

    entrada_historial = {
        'estadoAnterior': estado_actual,
        'estadoNuevo': nuevo_estado,
        'funcionarioRut': funcionario_rut,
        'fecha': ahora_str,
    }
    if nuevo_estado == estados.DEVUELTO and cambios.get('justificacion_devolucion'):
        entrada_historial['justificacion_devolucion'] = cambios['justificacion_devolucion']

    db.postulaciones().update_one(
        {'postulacionId': postulacion_id},
        {
            '$set': cambios,
            '$push': {'historialEvaluacion': entrada_historial},
        },
    )

    return db.postulaciones().find_one({'postulacionId': postulacion_id}, {'_id': 0})

# ENDPOINTS

@api_view(['GET', 'POST'])
@requiere_token
def postulaciones(request):
    """
    GET  /api/adopciones/postulaciones -> HU-09 (Tarea #75): Listado para evaluación (funcionario).
    POST /api/adopciones/postulaciones -> HU-12 (Tarea #58): Postular con bloqueo previo (vecino).
    """
    perfil = request.usuario.get('perfil')

    # --- HU-09: Panel de evaluación del funcionario ---
    if request.method == 'GET':
        if perfil != 'funcionario':
            return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: funcionario')
        animal_id = request.query_params.get('animalId')
        estado = request.query_params.get('estado')
        lista = listar_postulaciones_formulario(animal_id=animal_id, estado=estado)
        return Response(paginar(lista, request))

    # --- HU-12: Interceptar clic en "Postular" antes de persistir ---
    if perfil != 'vecino':
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Se requiere perfil: vecino')

    rut = request.usuario.get('rut')
    animal_id = (request.data.get('animalId') or '').strip()
    if not animal_id:
        return error(400, 'DATOS_INCOMPLETOS', 'El campo animalId es obligatorio.')

    try:
        _validar_animal_id(animal_id)
        tutor = validar_antecedentes_postulante(rut, request.token)
        _validar_animal_id(animal_id, es_simulado=tutor.get('_simulado'))
        formulario_guardado = _preparar_formulario(request.data.get('formulario'))
    except ErrorReglaNegocio as exc:
        return error(exc.status, exc.codigo, exc.mensaje)

    # Validar disponibilidad en M3 (HU-04 y HU-10)
    publicacion = db.publicaciones().find_one({'animalId': animal_id})
    if publicacion and publicacion.get('estado') != 'disponible':
        return error(409, 'ANIMAL_NO_DISPONIBLE', 'El animal ya no está disponible para adopción.')

    # Validar animal en M1 tolerando 403 cuando el vecino aún no es su tutor (RN-05)
    try:
        resp_animal, es_simulado = _llamar_m1('GET', f'/api/registro/animales/{animal_id}', request.token)
        _validar_animal_id(animal_id, es_simulado=es_simulado)
    except ErrorReglaNegocio as exc:
        return error(exc.status, exc.codigo, exc.mensaje)

    if resp_animal.status_code == 404:
        return error(404, 'ANIMAL_NO_ENCONTRADO', f'No existe el animal {animal_id} en Módulo 1.')
    if resp_animal.status_code == 200:
        animal_m1 = resp_animal.json()
        if animal_m1.get('estado') != 'con_microchip':
            return error(409, 'ANIMAL_NO_ADOPTABLE', 'El animal requiere estado con_microchip en Módulo 1 (RN-06).')
    elif resp_animal.status_code == 403:
        if not publicacion:
            return error(404, 'ANIMAL_NO_PUBLICADO', 'El animal no está publicado como disponible en Módulo 3.')
    else:
        return error(502, 'ERROR_MODULO_1', 'Error al consultar el animal en Módulo 1.')

    col = db.postulaciones()
    # RN-07: no permitir si ya existe una adopción aprobada/concretada para este animal
    if col.find_one({'animalId': animal_id, 'estado': {'$in': [estados.APROBADA, estados.ADOPCION_CONCRETADA]}}):
        return error(409, 'ANIMAL_YA_ADOPTADO', 'Este animal ya tiene una adopción aprobada o concretada.')

    # RN-11: máximo 2 postulaciones activas por vecino
    if col.count_documents({'postulanteRut': rut, 'estado': {'$in': estados.ACTIVAS}}) >= 2:
        return error(409, 'LIMITE_POSTULACIONES', 'Ya tienes 2 postulaciones activas (máximo permitido).')

    nueva_postulacion = {
        'postulacionId': f'P-{uuid.uuid4().hex[:8].upper()}',
        'animalId': animal_id,
        'postulanteRut': rut,
        'postulanteNombre': request.usuario.get('nombre') or tutor.get('nombre'),
        'estado': estados.RECIBIDA,
        'fechaPostulacion': a_iso_utc(utc_actual()),
        'formulario': formulario_guardado,
        'historialEvaluacion': [],
    }
    col.insert_one(dict(nueva_postulacion))
    return Response(nueva_postulacion, status=201)


@api_view(['GET'])
@requiere_token
def detalle_postulacion(request, postulacion_id):
    """
    GET /api/adopciones/postulaciones/{postulacionId}
    Entrega la postulación y los datos del formulario guardado para el panel del funcionario
    (o al vecino dueño según RN-05).
    """
    doc = db.postulaciones().find_one({'postulacionId': postulacion_id}, {'_id': 0})
    if not doc:
        return error(404, 'POSTULACION_NO_ENCONTRADA', f'No existe la postulación {postulacion_id}.')

    if request.usuario.get('perfil') == 'vecino' and doc.get('postulanteRut') != request.usuario.get('rut'):
        return error(403, 'PERFIL_NO_AUTORIZADO', 'Solo puedes consultar tus propias postulaciones (RN-05).')

    return Response(doc, status=200)


@api_view(['PATCH'])
@requiere_perfil('funcionario')
def cambiar_estado(request, postulacion_id):
    """
    PATCH /api/adopciones/postulaciones/{postulacionId}/estado
    Acepta tanto {"estado": "..."} como {"accion": "aprobar"} para compatibilidad con el equipo.
    """
    datos = request.data or {}
    nuevo_estado = (datos.get('estado') or '').strip()

    # Compatibilidad con el formato {"accion": "aprobar"} usado en entrega.json de Eric
    mapa_acciones = {
        'evaluar': estados.EN_EVALUACION,
        'aprobar': estados.APROBADA,
        'rechazar': estados.RECHAZADA,
        'concretar': estados.ADOPCION_CONCRETADA,
        'devolver': estados.DEVUELTO,
    }
    if not nuevo_estado and datos.get('accion'):
        nuevo_estado = mapa_acciones.get(str(datos.get('accion')).strip().lower(), '')

    justificacion = datos.get('justificacion_devolucion')
    funcionario_rut = request.usuario.get('rut')

    try:
        actualizada = procesar_cambio_estado(
            postulacion_id=postulacion_id,
            nuevo_estado=nuevo_estado,
            funcionario_rut=funcionario_rut,
            token=request.token,
            justificacion_devolucion=justificacion,
        )
    except ErrorReglaNegocio as exc:
        return error(exc.status, exc.codigo, exc.mensaje)

    return Response(actualizada, status=200)