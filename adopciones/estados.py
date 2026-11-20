"""
Máquina de estados de la entidad POSTULACIÓN (la entidad con estados de la ficha).

Estados de la ficha:
  recibida -> en_evaluacion -> aprobada -> adopcion_concretada -> devuelto
                             -> rechazada

Aquí definimos qué transiciones son válidas. Cada endpoint que cambie el estado
debe preguntar primero 'puede_transicionar(...)'. Si no es válida -> 409 (choca
con una regla del negocio).
"""
RECIBIDA = 'recibida'
EN_EVALUACION = 'en_evaluacion'
APROBADA = 'aprobada'
RECHAZADA = 'rechazada'
ADOPCION_CONCRETADA = 'adopcion_concretada'
DEVUELTO = 'devuelto'

ESTADOS = [RECIBIDA, EN_EVALUACION, APROBADA, RECHAZADA, ADOPCION_CONCRETADA, DEVUELTO]

# De cada estado, a qué estados se puede pasar.
TRANSICIONES = {
    RECIBIDA: [EN_EVALUACION, APROBADA, RECHAZADA],
    EN_EVALUACION: [APROBADA, RECHAZADA],
    APROBADA: [ADOPCION_CONCRETADA],
    ADOPCION_CONCRETADA: [DEVUELTO],
    RECHAZADA: [],
    DEVUELTO: [],
}

# Estados en los que la postulación "sigue viva" (cuenta para el máximo de 2, RN-11).
ACTIVAS = [RECIBIDA, EN_EVALUACION]


def puede_transicionar(actual, nuevo):
    return nuevo in TRANSICIONES.get(actual, [])
