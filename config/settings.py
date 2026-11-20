"""
Configuración de Django para el Módulo 3 (Adopciones).

Decisión de arquitectura: NO usamos el ORM de Django (que es para bases SQL).
Los datos del módulo viven en MongoDB y los leemos/escribimos con pymongo.
Por eso quitamos las apps que exigen una base SQL (admin, auth, sessions):
el módulo es una API REST pura servida con Django REST Framework.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Carga las variables del archivo .env en desarrollo local.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Seguridad: nada sensible escrito en el código (OWASP / Ley 21.459) ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'inseguro-solo-para-local')
DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

# Solo lo necesario para una API REST con Mongo.
INSTALLED_APPS = [
    'corsheaders',
    'rest_framework',
    'adopciones',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# No usamos base de datos SQL: todo el dominio está en MongoDB (pymongo).
DATABASES = {}

# Plantillas vacías (servimos un index.html estático, no usamos el motor de Django).
TEMPLATES = []

# CORS: el frontend (navegador) llama a esta API. En un prototipo lo dejamos abierto.
CORS_ALLOW_ALL_ORIGINS = True

# DRF: solo respondemos y recibimos JSON. La autenticación la hacemos nosotros
# contra el núcleo (ver adopciones/seguridad.py), no con el sistema de Django.
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PARSER_CLASSES': ['rest_framework.parsers.JSONParser'],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
    'UNAUTHENTICATED_USER': None,
}

LANGUAGE_CODE = 'es'
TIME_ZONE = 'UTC'
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
