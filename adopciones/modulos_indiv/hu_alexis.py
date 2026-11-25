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