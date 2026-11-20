"""
Cliente del NÚCLEO del docente y del M1 simulado.

Todo lo que el módulo necesita de "afuera" pasa por aquí:
  - validar un token y saber el perfil (núcleo)
  - consultar datos de una persona  (núcleo)
  - consultar un animal del M1       (M1 simulado, dentro del mismo núcleo)
  - cambiar el tutor de un animal    (M1 simulado) -> lo usa HU-11

La URL del núcleo viene de la variable de entorno NUCLEO_URL.
Para pasar del M1 simulado al M1 real (ES4) basta cambiar esa URL: nada más.
"""
import os
import requests

NUCLEO_URL = os.environ.get('NUCLEO_URL', 'https://nucleo-tr.onrender.com')
TIMEOUT = 8  # segundos; si el núcleo está dormido, no esperamos para siempre


class NucleoNoDisponible(Exception):
    """El núcleo no respondió. Quien llame debe responder 503."""


def _get(ruta, token):
    try:
        return requests.get(
            f'{NUCLEO_URL}{ruta}',
            headers={'Authorization': f'Bearer {token}'},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise NucleoNoDisponible(str(exc))


def validar_sesion(token):
    """GET /api/nucleo/sesiones/actual -> requests.Response (200 = {rut, perfil, nombre})."""
    return _get('/api/nucleo/sesiones/actual', token)


def obtener_usuario(rut, token):
    """GET /api/nucleo/usuarios/{rut} -> prohibición de tenencia, perfil, nombre."""
    return _get(f'/api/nucleo/usuarios/{rut}', token)


def obtener_animal(animal_id, token):
    """GET /api/registro/animales/{id} (M1 simulado) -> estado, microchip, tutorRut..."""
    return _get(f'/api/registro/animales/{animal_id}', token)


def actualizar_tutor(animal_id, tutor_rut, token):
    """PATCH /api/registro/animales/{id}/tutor (M1 simulado). Lo usa HU-11."""
    try:
        return requests.patch(
            f'{NUCLEO_URL}/api/registro/animales/{animal_id}/tutor',
            headers={'Authorization': f'Bearer {token}'},
            json={'tutorRut': tutor_rut},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise NucleoNoDisponible(str(exc))
