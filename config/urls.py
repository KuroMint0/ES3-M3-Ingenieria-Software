"""Rutas raíz del proyecto. Todo el módulo cuelga de /api/adopciones."""
from django.urls import path, include
from django.http import JsonResponse
from adopciones.views import inicio

urlpatterns = [
    path('', inicio),                              # frontend simple (index.html)
    path('api/adopciones/', include('adopciones.urls')),
]


# Handlers de error globales: aseguran que CUALQUIER 404 o 500 salga en JSON
# con el formato de la ficha (se activan cuando DJANGO_DEBUG=False, o sea en Render).
def _no_encontrado(request, exception=None):
    return JsonResponse(
        {'error': {'codigo': 'RUTA_NO_ENCONTRADA',
                   'mensaje': f'No existe {request.method} {request.path}'}},
        status=404,
    )


def _error_interno(request):
    # Nunca exponemos detalles internos (OWASP / Ley 21.459).
    return JsonResponse(
        {'error': {'codigo': 'ERROR_INTERNO', 'mensaje': 'Ocurrió un error interno'}},
        status=500,
    )


handler404 = 'config.urls._no_encontrado'
handler500 = 'config.urls._error_interno'
