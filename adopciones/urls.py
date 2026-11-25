"""Rutas del módulo. Todas cuelgan de /api/adopciones/ (ver config/urls.py).

CONVENCIÓN DE EQUIPO: cada integrante trabaja en SU archivo de módulo y agrega
UNA sola línea aquí abajo para publicar su ruta. Este es el único archivo compartido.
"""
from django.urls import path
from . import views, postulaciones

urlpatterns = [
    # --- Base (Eric) ---
    path('salud', views.salud),
    path('disponibles', views.disponibles),

    # --- HU-05 Postulaciones (Eric) ---
    path('postulaciones', postulaciones.crear_postulacion),

    # --- Cada integrante agrega su línea aquí ---
    # path('publicaciones', publicaciones.publicar),                 # HU-04  Christopher
    # path('postulaciones/<pid>/seguimientos', seguimientos.crear),  # HU-08  Alexis
    # path('postulaciones/<pid>/estado', evaluacion.cambiar_estado), # HU-11  Eric (commit 4)
    # path('notificaciones', notificaciones.listar),                 # HU-06  Eric (commit 3)
]
