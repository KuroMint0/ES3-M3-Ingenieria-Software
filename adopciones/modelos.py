"""Esquemas de documentos MongoDB; este proyecto no usa el ORM de Django."""
from typing import TypedDict


ESTADO_DISPONIBLE = 'disponible'


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
