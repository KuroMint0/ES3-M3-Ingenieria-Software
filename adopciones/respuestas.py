"""
Helpers de respuesta comunes a todo el módulo.

Centralizan DOS convenciones de la ficha del caso:
  1) El formato de error:  {"error": {"codigo": "...", "mensaje": "..."}}
  2) La paginación de listados: ?page=1&limit=20
Tenerlo en un solo lugar evita el error de la ES2 (formato de error inconsistente).
"""
from rest_framework.response import Response


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
