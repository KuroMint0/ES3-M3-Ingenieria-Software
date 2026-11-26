from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


RUT_VECINO = '11111111-1'


class CursorPostulacionesFake:
    def __init__(self, documentos):
        self.documentos = documentos

    def sort(self, campo, direccion):
        self.documentos.sort(
            key=lambda documento: documento[campo],
            reverse=direccion == -1,
        )
        return self

    def __iter__(self):
        return iter(self.documentos)


class MisPostulacionesApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token')
        self.sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {'rut': RUT_VECINO, 'perfil': 'vecino'},
            ),
        )
        self.sesion.start()
        self.addCleanup(self.sesion.stop)

    def test_lista_solo_las_del_token_ordenadas_y_paginadas(self):
        documentos = [
            {
                'postulacionId': 'P-000001',
                'postulanteRut': RUT_VECINO,
                'animalId': 'SIM-000001',
                'estado': 'recibida',
                'fechaPostulacion': '2026-01-10T12:00:00Z',
            },
            {
                'postulacionId': 'P-000002',
                'postulanteRut': RUT_VECINO,
                'animalId': 'SIM-000002',
                'estado': 'aprobada',
                'fechaPostulacion': '2026-02-10T12:00:00Z',
            },
            {
                'postulacionId': 'P-000003',
                'postulanteRut': '22222222-2',
                'animalId': 'SIM-000003',
                'estado': 'recibida',
                'fechaPostulacion': '2026-03-10T12:00:00Z',
            },
        ]
        publicaciones = Mock()
        publicaciones.find.return_value = CursorPostulacionesFake([
            documento for documento in documentos
            if documento['postulanteRut'] == RUT_VECINO
        ])

        with patch(
            'adopciones.modulos_indiv.hu_alexis.db.postulaciones',
            return_value=publicaciones,
        ):
            respuesta = self.client.get(
                '/api/adopciones/postulaciones'
                '?rut=22222222-2&page=1&limit=1'
            )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['total'], 2)
        self.assertEqual(respuesta.data['page'], 1)
        self.assertEqual(respuesta.data['limit'], 1)
        self.assertEqual(respuesta.data['datos'][0]['postulacionId'], 'P-000002')
        self.assertTrue(all(
            documento['postulanteRut'] == RUT_VECINO
            for documento in respuesta.data['datos']
        ))
        publicaciones.find.assert_called_once_with(
            {'postulanteRut': RUT_VECINO},
            {'_id': 0},
        )
