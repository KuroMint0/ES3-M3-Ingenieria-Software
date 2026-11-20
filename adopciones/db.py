"""
Conexión a MongoDB con pymongo.

Usamos una única conexión perezosa (se crea la primera vez que se pide).
La URI y el nombre de la base vienen de variables de entorno: NUNCA en el código.
"""
import os
from pymongo import MongoClient

_cliente = None


def get_db():
    """Devuelve la base de datos del módulo 3 (la crea la primera vez)."""
    global _cliente
    if _cliente is None:
        uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
        _cliente = MongoClient(uri)
    nombre = os.environ.get('MONGO_DB', 'tr_adopciones')
    return _cliente[nombre]


# Atajos a las colecciones del módulo (cada "tabla" de Mongo).
def postulaciones():
    return get_db()['postulaciones']


def publicaciones():
    return get_db()['publicaciones']        # animales publicados para adopción


def notificaciones():
    return get_db()['notificaciones']       # avisos al vecino (HU-06)
