"""
Endpoints del Módulo 3.

En la BASE dejamos funcionando el circuito completo de una petición protegida:
  navegador -> API (valida token con el núcleo) -> MongoDB -> respuesta JSON.

Los endpoints de cada historia (HU-05, HU-06, HU-11, ...) se agregan encima,
cada integrante el suyo. Están marcados como TODO más abajo.
"""
import os
from django.http import FileResponse
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import db
from .respuestas import paginar


def inicio(request):
    """Sirve el frontend simple (frontend/index.html)."""
    ruta = os.path.join(settings.BASE_DIR, 'frontend', 'index.html')
    return FileResponse(open(ruta, 'rb'))


@api_view(['GET'])
def salud(request):
    """Estado del servicio. Público, sirve para saber si el prototipo está despierto."""
    return Response({'estado': 'ok', 'modulo': 3, 'nombre': 'adopciones'})


@api_view(['GET'])
def disponibles(request):
    """
    GET /api/adopciones/disponibles
    Lista paginada pública de animales publicados para adopción.
    """
    docs = list(db.publicaciones().find({'estado': 'disponible'}, {'_id': 0}))
    return Response(paginar(docs, request))


# ---------------------------------------------------------------------------
# TODO (historias de cada integrante; se construyen sobre lo de arriba):
#   HU-01  POST   /api/adopciones/postulaciones                 (Sebastián)
#   HU-04  POST   /api/adopciones/publicaciones                 (Christopher)
#   HU-05  POST   /api/adopciones/postulaciones  (múltiples)    (Eric)
#   HU-06  GET    /api/adopciones/notificaciones                (Eric)
#   HU-11  PATCH  /api/adopciones/postulaciones/{id}/estado     (Eric)
# ---------------------------------------------------------------------------
