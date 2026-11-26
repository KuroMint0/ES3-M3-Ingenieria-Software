"""Esquemas de documentos MongoDB; este proyecto no usa el ORM de Django."""
from datetime import datetime
from typing import TypedDict


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
    tieneMicrochip: bool
    microchip: int | str | None
    estado: str
    publicadoPorRut: str
    fechaPublicacion: str


class ControlSeguimiento(TypedDict):
    """Control de seguimiento posterior a una adopción."""

    controlId: str
    observaciones: str
    fechaControl: datetime
    registradoPor: str
    archivo: dict | None
    control_valido: bool
