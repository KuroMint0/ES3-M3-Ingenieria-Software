"""Rutas del módulo. Todas cuelgan de /api/adopciones/ (ver config/urls.py)."""
from django.urls import path
from . import views

urlpatterns = [
    path('salud', views.salud),
    path('disponibles', views.disponibles),
    # Las rutas de cada historia se agregan aquí a medida que se implementan.
]
