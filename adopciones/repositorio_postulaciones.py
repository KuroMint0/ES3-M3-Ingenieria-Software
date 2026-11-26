"""
Acceso a MongoDB de las postulaciones y sus seguimientos.

Las vistas NO escriben consultas: llaman a estas funciones. Así las reglas de
acceso a datos quedan en un solo lugar y son fáciles de explicar y probar.
"""
from pymongo import ASCENDING, ReturnDocument

from . import db, estados, modelos

_indices_creados = False


def siguiente_id():
    """
    Devuelve el próximo código correlativo: P-000001, P-000002...

    Usa un contador ATÓMICO en Mongo ($inc + upsert). Contar documentos y sumar 1
    falla si dos personas postulan al mismo tiempo (obtendrían el mismo número).
    OJO para el grupo: HU-05 y HU-11 deben usar esta misma función.
    """
    doc = db.contadores().find_one_and_update(
        {'_id': 'postulaciones'},
        {'$inc': {'valor': 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"P-{doc['valor']:06d}"


def buscar_activa(animal_id, rut):
    """¿Ese RUT ya tiene una postulación ACTIVA a ese animal? (evita duplicados)."""
    return db.postulaciones().find_one(
        {
            'animalId': animal_id,
            'postulanteRut': rut,
            'estado': {'$in': estados.ACTIVAS},
        },
        {'_id': 0},
    )


def contar_activas_por_postulante(rut):
    """Cuenta las postulaciones activas del RUT autenticado."""
    return db.postulaciones().count_documents(
        {
            'postulanteRut': rut,
            'estado': {'$in': estados.ACTIVAS},
        }
    )


def crear(documento):
    """
    Inserta una postulación y la devuelve SIN el _id de Mongo.

    insert_one agrega una clave _id (ObjectId) al diccionario que le pasamos y
    DRF no sabe convertir un ObjectId a JSON: por eso se quita antes de devolver.
    """
    db.postulaciones().insert_one(documento)
    documento.pop('_id', None)
    return documento


def obtener(postulacion_id):
    """Busca una postulación por su código (P-000842). None si no existe."""
    return db.postulaciones().find_one({'postulacionId': postulacion_id}, {'_id': 0})


def agregar_control(postulacion_id, control):
    """
    Agrega un control de seguimiento a la postulación (HU-08).

    El filtro incluye el estado: si entre la lectura y la escritura la postulación
    dejó de estar en 'adopcion_concretada', no se modifica nada.
    Devuelve True si se agregó.
    """
    resultado = db.postulaciones().update_one(
        {'postulacionId': postulacion_id, 'estado': estados.ADOPCION_CONCRETADA},
        {'$push': {'seguimientoPosterior': control}},
    )
    return resultado.matched_count == 1


def aprobar_animal_y_cancelar_hermanas(animal_id, postulacion_id, fecha):
    """
    Reserva el animal para la postulación aprobada y cierra las demás activas.

    La actualización condicional de la publicación impide que dos aprobaciones
    simultáneas reclamen el mismo animal.
    """
    resultado = db.publicaciones().update_one(
        {'animalId': animal_id, 'estado': 'disponible'},
        {
            '$set': {
                'estado': modelos.ESTADO_ADOPTADO,
                'fechaActualizacion': fecha,
                'postulacionAprobadaId': postulacion_id,
            },
        },
    )
    if resultado.matched_count != 1:
        return False

    db.postulaciones().update_many(
        {
            'animalId': animal_id,
            'postulacionId': {'$ne': postulacion_id},
            'estado': {'$in': estados.CANCELABLES_POR_ADOPCION},
        },
        {
            '$set': {
                'estado': estados.CANCELADA_POR_ADOPCION,
                'fechaCancelacion': fecha,
                'motivoCancelacion': 'adopcion_concretada',
            },
        },
    )
    return True


def asegurar_indices():
    """Crea los índices necesarios una vez por proceso, antes de aceptar envíos."""
    if not _indices_creados:
        crear_indices()


def crear_indices():
    """
    Crea los índices de la colección. Se ejecuta con: python manage.py sembrar_demo

    1) Único PARCIAL sobre (animalId, postulanteRut) solo en estados activos:
       segunda defensa contra duplicados (doble clic, dos peticiones simultáneas).
       Es parcial porque quien fue rechazado puede volver a postular, y es sobre
       postulante + animal (no solo animal) para que varias personas puedan
       postular al mismo animal (HU-05).
       Requiere MongoDB 6.0 o superior (Atlas lo cumple).
    2) Único sobre postulacionId.
    """
    global _indices_creados
    col = db.postulaciones()
    col.create_index(
        [('animalId', ASCENDING), ('postulanteRut', ASCENDING)],
        unique=True,
        partialFilterExpression={'estado': {'$in': estados.ACTIVAS}},
        name='unica_postulacion_activa',
    )
    col.create_index(
        [('postulacionId', ASCENDING)],
        unique=True,
        name='postulacion_id_unico',
    )
    _indices_creados = True