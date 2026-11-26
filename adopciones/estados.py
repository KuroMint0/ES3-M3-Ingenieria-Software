"""
Máquina de estados de la entidad POSTULACIÓN (la entidad con estados de la ficha).

Estados de la ficha:
  recibida -> en_evaluacion -> aprobada -> adopcion_concretada -> devuelto
                             -> rechazada
  adopcion_concretada -> adopcion_cerrada (requiere dos controles válidos)

Aquí definimos qué transiciones son válidas. Cada endpoint que cambie el estado
debe preguntar primero 'puede_transicionar(...)'. Si no es válida -> 409 (choca
con una regla del negocio).
"""
RECIBIDA = 'recibida'
EN_EVALUACION = 'en_evaluacion'
APROBADA = 'aprobada'
RECHAZADA = 'rechazada'
ADOPCION_CONCRETADA = 'adopcion_concretada'
ADOPCION_CERRADA = 'adopcion_cerrada'
DEVUELTO = 'devuelto'
CANCELADA = 'cancelada'
CANCELADA_POR_ADOPCION = 'cancelada_por_adopcion_concretada'

ESTADOS = [
    RECIBIDA,
    EN_EVALUACION,
    APROBADA,
    RECHAZADA,
    ADOPCION_CONCRETADA,
    ADOPCION_CERRADA,
    DEVUELTO,
    CANCELADA,
    CANCELADA_POR_ADOPCION,
]

# De cada estado, a qué estados se puede pasar.
# Solo se puede cancelar una postulación que sigue "viva" (recibida o en evaluación).
TRANSICIONES = {
    RECIBIDA: [EN_EVALUACION, APROBADA, RECHAZADA, CANCELADA],
    EN_EVALUACION: [APROBADA, RECHAZADA, CANCELADA],
    APROBADA: [ADOPCION_CONCRETADA],
    ADOPCION_CONCRETADA: [DEVUELTO, ADOPCION_CERRADA],
    ADOPCION_CERRADA: [],
    RECHAZADA: [],
    DEVUELTO: [],
    CANCELADA: [],
    CANCELADA_POR_ADOPCION: [],
}

# Estados en los que la postulación "sigue viva" (cuenta para el máximo de 2, RN-11).
ACTIVAS = [RECIBIDA, EN_EVALUACION]
MAX_POSTULACIONES_ACTIVAS = 2
MIN_CONTROLES_VALIDOS_PARA_CIERRE = 2

# Estados de otras postulaciones que se cierran cuando se aprueba una adopción.
CANCELABLES_POR_ADOPCION = [RECIBIDA, EN_EVALUACION, APROBADA]


def puede_transicionar(actual, nuevo):
    return nuevo in TRANSICIONES.get(actual, [])
