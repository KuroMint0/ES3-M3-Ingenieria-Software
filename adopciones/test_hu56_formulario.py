from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


class ValidacionFormularioPostulacionTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token')
        self.validar_sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {'rut': '11111111-1', 'perfil': 'vecino'},
            ),
        )
        self.validar_sesion.start()
        self.addCleanup(self.validar_sesion.stop)
        self.obtener_animal = patch(
            'adopciones.views_postulaciones.nucleo.obtener_animal'
        )
        self.obtener_animal_mock = self.obtener_animal.start()
        self.addCleanup(self.obtener_animal.stop)

    def enviar_formulario(self, formulario):
        return self.client.post(
            '/api/adopciones/postulaciones',
            data={
                'animalId': 'SIM-000001',
                'formulario': formulario,
            },
            format='json',
        )

    def test_postulacion_sigue_requiriendo_token(self):
        self.client.credentials()

        respuesta = self.enviar_formulario({})

        self.assertEqual(respuesta.status_code, 401)
        self.obtener_animal_mock.assert_not_called()

    def test_postulacion_sigue_restringida_al_perfil_vecino(self):
        with patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {'rut': '17777777-3', 'perfil': 'funcionario'},
            ),
        ):
            respuesta = self.enviar_formulario({})

        self.assertEqual(respuesta.status_code, 403)
        self.obtener_animal_mock.assert_not_called()

    def test_rechaza_formulario_vacio_o_tipo_de_vivienda_vacio(self):
        formularios_invalidos = (
            {},
            {
                'tipoVivienda': '',
                'patioExterior': False,
                'otrosAnimales': False,
                'presenciaNinos': False,
                'consentimientoFamiliar': True,
            },
        )

        for formulario in formularios_invalidos:
            with self.subTest(formulario=formulario):
                respuesta = self.enviar_formulario(formulario)

                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.data['error']['codigo'], 'VALIDACION')
                self.assertIn(
                    'formulario.tipoVivienda',
                    respuesta.data['error']['mensaje'],
                )

        self.obtener_animal_mock.assert_not_called()

    def test_rechaza_formulario_sin_consentimiento_explicito(self):
        respuesta = self.enviar_formulario({
            'tipoVivienda': 'casa',
            'patioExterior': False,
            'otrosAnimales': False,
            'presenciaNinos': False,
            'consentimientoFamiliar': False,
        })

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data['error']['codigo'], 'VALIDACION')
        self.assertIn(
            'formulario.consentimientoFamiliar',
            respuesta.data['error']['mensaje'],
        )
        self.obtener_animal_mock.assert_not_called()
