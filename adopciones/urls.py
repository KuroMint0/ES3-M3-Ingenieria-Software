"""Rutas del módulo. Todas cuelgan de /api/adopciones/ (ver config/urls.py).

CONVENCIÓN DE EQUIPO: cada integrante trabaja en SU archivo de módulo (modulos_indiv/)
y agrega UNA sola línea aquí abajo. Este es el único archivo compartido.
"""
from django.urls import path
from . import views, views_postulaciones, views_seguimientos
from .modulos_indiv import hu_christopher, hu_eric, hu_alexis

urlpatterns = [
    # --- Base (Eric) ---
    path('salud', views.salud),
    path('disponibles', views.disponibles),

    # --- HU-04/HU-13 Publicar animal (Christopher) ---
    path('publicaciones', hu_christopher.publicar),

    # --- HU-06 Notificaciones (Eric) ---
    path('notificaciones', hu_eric.notificaciones),
    path('notificaciones/<nid>/leida', hu_eric.marcar_leida),
    path('sincronizaciones', hu_eric.sincronizar_tutor),            # HU-11 (prueba/manual)

    # --- HU-12, HU-09, HU-10 y HU-15 (Alexis) ---
    path('postulaciones', hu_alexis.postulaciones),
    path('postulaciones/<str:postulacion_id>', hu_alexis.detalle_postulacion),
    path('postulaciones/<str:postulacion_id>/estado', hu_alexis.cambiar_estado),

    # --- HU-08 Seguimiento posterior (Sebastián) ---
    path('postulaciones/<str:postulacion_id>/seguimientos',
         views_seguimientos.seguimientos),
    path('postulaciones/<str:postulacion_id>/seguimientos/<str:control_id>/archivo',
         views_seguimientos.descargar_archivo),

    # --- Cada integrante agrega su línea aquí ---
    # path('postulaciones/<pid>/estado', evaluacion.cambiar_estado), # HU-11  Eric
]
