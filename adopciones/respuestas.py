"""
Helpers de respuesta comunes a todo el módulo.

Centralizan DOS convenciones de la ficha del caso:
  1) El formato de error:  {"error": {"codigo": "...", "mensaje": "..."}}
  2) La paginación de listados: ?page=1&limit=20
Tenerlo en un solo lugar evita el error de la ES2 (formato de error inconsistente).
"""
from pymongo.errors import PyMongoError
from rest_framework import exceptions
from rest_framework.response import Response

from . import nucleo


def error(status, codigo, mensaje):
    """Devuelve un error con el formato EXACTO que exige la ficha."""
    return Response({'error': {'codigo': codigo, 'mensaje': mensaje}}, status=status)


def paginar(lista, request):
    """Pagina una lista de Python según ?page y ?limit (convención de la ficha)."""
    try:
        page = int(request.query_params.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(request.query_params.get('limit', 20))
    except (TypeError, ValueError):
        limit = 20
    if page < 1:
        page = 1
    if limit < 1:
        limit = 20
    if limit > 100:
        limit = 100

    total = len(lista)
    inicio = (page - 1) * limit
    datos = lista[inicio:inicio + limit]
    total_paginas = max(1, (total + limit - 1) // limit)
    return {
        'page': page,
        'limit': limit,
        'total': total,
        'totalPaginas': total_paginas,
        'datos': datos,
    }


_ERRORES_DRF = (
    (exceptions.ParseError, 'JSON_INVALIDO',
     'El cuerpo de la petición no tiene un formato válido'),
    (exceptions.MethodNotAllowed, 'METODO_NO_PERMITIDO',
     'Método no permitido para esta ruta'),
    (exceptions.UnsupportedMediaType, 'TIPO_NO_SOPORTADO',
     'El tipo de contenido no está soportado'),
    (exceptions.NotAcceptable, 'FORMATO_NO_ACEPTABLE',
     'El formato de respuesta pedido no está disponible'),
)


def manejador_excepciones(exc, context):
    if isinstance(exc, nucleo.NucleoNoDisponible):
        return error(503, 'NUCLEO_NO_DISPONIBLE',
                     'No se pudo comunicar con el núcleo')
    if isinstance(exc, PyMongoError):
        return error(503, 'BASE_DE_DATOS_NO_DISPONIBLE',
                     'La base de datos no está disponible')

    if isinstance(exc, exceptions.APIException):
        for clase, codigo, mensaje in _ERRORES_DRF:
            if isinstance(exc, clase):
                return error(exc.status_code, codigo, mensaje)
        return error(exc.status_code, 'ERROR_DE_PETICION',
                     'No se pudo procesar la petición')

    return None
