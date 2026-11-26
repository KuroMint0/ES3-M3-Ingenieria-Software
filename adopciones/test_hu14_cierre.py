from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from adopciones import estados


POSTULACION_ID = 'P-000001'


class ColeccionPostulacionFake:
    def __init__(self, controles):
        self.documento = {
            'postulacionId': POSTULACION_ID,
            'animalId': 'SIM-000001',
            'postulanteRut': '11111111-1',
            'estado': estados.ADOPCION_CONCRETADA,
            'seguimientoPosterior': controles,
            'historialEvaluacion': [],
        }
        self.actualizaciones = 0

    def find_one(self, filtro, proyeccion=None):
        if filtro.get('postulacionId') != POSTULACION_ID:
            return None
        return dict(self.documento)

    def update_one(self, filtro, cambios):
        if filtro.get('postulacionId') != POSTULACION_ID:
            return SimpleNamespace(matched_count=0)
        self.documento.update(cambios['$set'])
        self.documento['historialEvaluacion'].append(
            cambios['$push']['historialEvaluacion']
        )
        self.actualizaciones += 1
        return SimpleNamespace(matched_count=1)


class CierreAdopcionTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer funcionario-token')
        self.sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {
                    'rut': '17777777-3',
                    'perfil': 'funcionario',
                },
            ),
        )
        self.sesion.start()
        self.addCleanup(self.sesion.stop)

    def cerrar(self, coleccion):
        with patch(
            'adopciones.modulos_indiv.hu_alexis.db.postulaciones',
            return_value=coleccion,
        ):
            return self.client.patch(
                f'/api/adopciones/postulaciones/{POSTULACION_ID}/estado',
                {'estado': estados.ADOPCION_CERRADA},
                format='json',
            )

    def test_no_cierra_con_cero_o_un_control_valido(self):
        controles_por_caso = (
            [],
            [{'control_valido': True}],
            [{'control_valido': True}, {'control_valido': False}],
        )

        for controles in controles_por_caso:
            with self.subTest(controles=controles):
                coleccion = ColeccionPostulacionFake(controles)

                respuesta = self.cerrar(coleccion)

                self.assertEqual(respuesta.status_code, 409)
                self.assertEqual(
                    respuesta.data['error']['codigo'],
                    'CONTROLES_SEGUIMIENTO_INSUFICIENTES',
                )
                self.assertEqual(
                    coleccion.documento['estado'],
                    estados.ADOPCION_CONCRETADA,
                )
                self.assertEqual(coleccion.actualizaciones, 0)

    def test_cierra_con_dos_controles_validos(self):
        coleccion = ColeccionPostulacionFake([
            {'control_valido': True},
            {'control_valido': True},
        ])

        respuesta = self.cerrar(coleccion)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['estado'], estados.ADOPCION_CERRADA)
        self.assertIn('fechaCierreAdopcion', respuesta.data)
        self.assertEqual(coleccion.actualizaciones, 1)
