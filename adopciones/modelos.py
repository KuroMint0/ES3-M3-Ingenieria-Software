"""Esquemas de documentos MongoDB; este proyecto no usa el ORM de Django."""
from datetime import datetime
from typing import NotRequired, TypedDict


ESTADO_DISPONIBLE = 'disponible'
ESTADO_ADOPTADO = 'adoptado'


class Animal(TypedDict):
    """Documento de una publicación de animal en la colección publicaciones."""

    animalId: str
    nombre: str
    especie: str
    raza: str
    edadAproximada: int | float | str
    descripcion: str | None
    fotografia: str | None
    microchip: int | str
    estado: str
    publicadoPorRut: str
    fechaPublicacion: str


class FormularioPostulacion(TypedDict):
    tipoVivienda: str
    patioExterior: bool
    otrosAnimales: bool
    presenciaNinos: bool
    consentimientoFamiliar: bool
    observaciones: NotRequired[str]


class Postulacion(TypedDict):
    """Documento Mongo; animalId y postulanteRut referencian M1 y al usuario."""

    postulacionId: str
    animalId: str
    postulanteRut: str
    estado: str
    fechaPostulacion: datetime | str
    formulario: FormularioPostulacion
    historialEvaluacion: list[dict]
    seguimientoPosterior: list[dict]


class ControlSeguimiento(TypedDict):
    """Control embebido en Postulacion; el contenido del archivo vive en GridFS."""

    controlId: str
    observaciones: str
    fechaControl: datetime
    registradoPor: str
    archivo: dict | None
