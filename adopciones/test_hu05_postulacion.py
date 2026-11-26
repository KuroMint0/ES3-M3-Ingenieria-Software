"""
HU-05 (#29) · Postular aunque el animal ya tenga otros postulantes.

#50 [Backend]: crear una postulación NO se bloquea por postulaciones previas de
               OTROS tutores (estados activos: recibida / en_evaluacion).
#52 [QA]:      dos o más tutores distintos pueden postular al MISMO animal.

Se mockean el núcleo (M1) y Mongo para probar solo la lógica de la vista, sin
depender de servicios externos. Correr con:  python manage.py test adopciones.test_hu05_postulacion
"""
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from adopciones import estados, seguridad
from adopciones import views_postulaciones as v


class RespFake:
    def __init__(self, code, data):
        self.status_code = code
        self._data = data

    def json(self):
        return self._data


class ColeccionPostulacionesFake:
    """Colección en memoria que respeta el mismo filtro que buscar_activa."""

    def __init__(self):
        self.docs = []

    def find_one(self, filtro, proyeccion=None):
        activos = filtro.get('estado', {}).get('$in', [])
        for d in self.docs:
            if (d['animalId'] == filtro.get('animalId')
                    and d['postulanteRut'] == filtro.get('postulanteRut')
                    and d['estado'] in activos):
                return dict(d)
        return None

    def count_documents(self, filtro):
        activos = filtro['estado']['$in']
        return sum(
            1 for documento in self.docs
            if documento['postulanteRut'] == filtro['postulanteRut']
            and documento['estado'] in activos
        )

    def insert_one(self, doc):
        doc.setdefault('_id', len(self.docs) + 1)
        self.docs.append(dict(doc))
        return mock.Mock(inserted_id=doc['_id'])


FORMULARIO = {
    'tipoVivienda': 'casa',
    'patioExterior': True,
    'otrosAnimales': False,
    'presenciaNinos': False,
    'consentimientoFamiliar': True,
}


class HU05Postulacion(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.col = ColeccionPostulacionesFake()
        self._n = 0

    def _siguiente_id(self):
        self._n += 1
        return f'P-{self._n:06d}'

    def _postular(self, rut):
        req = self.factory.post(
            '/x', {'animalId': 'SIM-000001', 'formulario': FORMULARIO},
            format='json', HTTP_AUTHORIZATION='Bearer tok')
        sesion = {'rut': rut, 'perfil': 'vecino', 'nombre': 'T'}
        pub = mock.Mock()
        pub.find_one.return_value = {'_id': 1}  # animal publicado y disponible
        with mock.patch.object(seguridad.nucleo, 'validar_sesion', return_value=RespFake(200, sesion)), \
                mock.patch.object(v.nucleo, 'obtener_animal', return_value=RespFake(200, {'estado': 'disponible'})), \
                mock.patch.object(v.db, 'publicaciones', return_value=pub), \
                mock.patch.object(v.db, 'postulaciones', return_value=self.col), \
                mock.patch.object(v.nucleo, 'obtener_usuario', return_value=RespFake(200, {'prohibicionTenencia': False})), \
                mock.patch.object(v.repo, 'siguiente_id', side_effect=self._siguiente_id), \
                mock.patch('adopciones.modulos_indiv.hu_alexis.validar_antecedentes_postulante', return_value=None):
            return v.crear_postulacion(req)

    def test_dos_tutores_distintos_mismo_animal(self):
        """#50 / #52: dos RUT distintos postulan al mismo animal -> ambos 201."""
        r1 = self._postular('11.111.111-1')
        r2 = self._postular('22.222.222-2')
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(len(self.col.docs), 2)

    def test_mismo_tutor_no_duplica(self):
        """El mismo RUT no puede postular dos veces al mismo animal -> 409."""
        r1 = self._postular('11.111.111-1')
        r2 = self._postular('11.111.111-1')
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 409)
        self.assertEqual(r2.data['error']['codigo'], 'POSTULACION_DUPLICADA')

    def test_estados_activos_son_los_esperados(self):
        """Las postulaciones 'vivas' (Pendiente/En Revisión) son recibida y en_evaluacion."""
        self.assertEqual(set(estados.ACTIVAS), {estados.RECIBIDA, estados.EN_EVALUACION})
