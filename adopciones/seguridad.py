"""
Autenticación y autorización del módulo (OWASP A01: Broken Access Control).

Regla de la ficha y del enunciado ES3:
  - Sin token válido           -> 401
  - Token válido, perfil que NO corresponde al endpoint -> 403
  - Núcleo caído               -> 503

No confiamos en el perfil que diga el navegador: SIEMPRE se lo preguntamos al
núcleo con el token (GET /api/nucleo/sesiones/actual). Esa es la única fuente.
"""
from functools import wraps
from . import nucleo
from .respuestas import error


def _leer_token(request):
    cabecera = request.META.get('HTTP_AUTHORIZATION', '')
    if cabecera.startswith('Bearer '):
        return cabecera[7:].strip()
    return None


def requiere_token(vista):
    """Decorador: exige un token válido. Deja request.usuario = {rut, perfil, nombre}."""
    @wraps(vista)
    def envoltorio(request, *args, **kwargs):
        token = _leer_token(request)
        if not token:
            return error(401, 'TOKEN_REQUERIDO',
                         'Falta el encabezado Authorization: Bearer <token>')
        try:
            resp = nucleo.validar_sesion(token)
        except nucleo.NucleoNoDisponible:
            return error(503, 'NUCLEO_NO_DISPONIBLE',
                         'No se pudo validar la sesión con el núcleo')
        if resp.status_code != 200:
            return error(401, 'TOKEN_INVALIDO', 'El token no es válido o expiró')
        request.usuario = resp.json()       # {rut, perfil, nombre}
        request.token = token               # lo reusamos para llamar al M1
        return vista(request, *args, **kwargs)
    return envoltorio


def requiere_perfil(*perfiles):
    """Decorador: exige que el perfil del usuario sea uno de los indicados (si no, 403)."""
    def decorador(vista):
        @wraps(vista)
        @requiere_token
        def envoltorio(request, *args, **kwargs):
            if request.usuario.get('perfil') not in perfiles:
                return error(403, 'PERFIL_NO_AUTORIZADO',
                             f'Se requiere perfil: {", ".join(perfiles)}')
            return vista(request, *args, **kwargs)
        return envoltorio
    return decorador
