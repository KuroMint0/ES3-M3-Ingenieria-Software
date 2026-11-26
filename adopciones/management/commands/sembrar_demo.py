"""
Deja la base en el estado que necesitan las verificaciones de entrega.json.

Uso:   python manage.py sembrar_demo

La verificación del docente repite nuestras peticiones sobre la base REAL, y el
resultado depende del estado: si ya existe una postulación del vecino de prueba al
mismo animal, recibiría 409 en vez de 201. Este comando se puede ejecutar todas las
veces que haga falta: siempre deja el mismo estado.

Ejecutarlo antes de entregar y otra vez antes de la conversación.
"""
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from gridfs.errors import NoFile
from pymongo.errors import OperationFailure

from adopciones import db, estados
from adopciones import repositorio_postulaciones as repo

# [VERIFICA] qué animales SIM- sirven (estado en el M1 simulado) y coordinar con
# Christopher (HU-04) y Eric (HU-11) para que cada verificación use animales distintos.
RUT_VECINO_PRUEBA = '11111111-1'
ANIMAL_HU01 = 'SIM-000002'                 # debe quedar YA publicado
POSTULACION_HU08 = 'P-DEMO-0002'           # debe quedar en adopcion_concretada
ANIMAL_HU08 = 'SIM-000003'


class Command(BaseCommand):
    help = 'Deja los datos de demostración en el estado que esperan las verificaciones.'

    def handle(self, *args, **options):
        base = db.get_db()
        self.stdout.write(f'Base de datos: {base.name}')

        # 1) Índices.
        try:
            repo.crear_indices()
            self.stdout.write('Índices creados (o ya existían).')
        except OperationFailure as exc:
            self.stderr.write(f'No se pudo crear un índice: {exc}')

        # 2) HU-01: el animal de la verificación queda publicado.
        db.publicaciones().update_one(
            {'animalId': ANIMAL_HU01},
            {'$set': {'animalId': ANIMAL_HU01, 'estado': 'disponible'}},
            upsert=True,
        )
        self.stdout.write(f'Publicado: {ANIMAL_HU01}')

        # 3) HU-01: sin postulaciones previas del vecino de prueba a ese animal.
        borradas = db.postulaciones().delete_many(
            {'animalId': ANIMAL_HU01, 'postulanteRut': RUT_VECINO_PRUEBA})
        self.stdout.write(f'Postulaciones previas borradas: {borradas.deleted_count}')

        # 4) HU-08: P-DEMO-0002 en adopcion_concretada y sin controles.
        bucket = db.bucket_seguimientos()
        for archivo in base['seguimientos.files'].find(
                {'metadata.postulacionId': POSTULACION_HU08}, {'_id': 1}):
            try:
                bucket.delete(archivo['_id'])
            except NoFile:
                pass

        db.postulaciones().replace_one(
            {'postulacionId': POSTULACION_HU08},
            {
                'postulacionId': POSTULACION_HU08,
                'animalId': ANIMAL_HU08,
                'postulanteRut': RUT_VECINO_PRUEBA,
                'estado': estados.ADOPCION_CONCRETADA,
                'fechaPostulacion': datetime.now(timezone.utc),
                'formulario': {
                    'tipoVivienda': 'casa',
                    'patioExterior': True,
                    'otrosAnimales': False,
                    'presenciaNinos': False,
                    'consentimientoFamiliar': True,
                },
                'historialEvaluacion': [],
                'seguimientoPosterior': [],
            },
            upsert=True,
        )
        self.stdout.write(f'{POSTULACION_HU08} lista en estado {estados.ADOPCION_CONCRETADA}.')
        self.stdout.write(self.style.SUCCESS('Siembra terminada.'))