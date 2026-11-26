from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from adopciones import estados


POSTULACION_ID = 'P-000123'
RUT_VECINO = '11111111-1'


class CancelacionPostulacionTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token')
        self.postulaciones = Mock()
        self.postulaciones.find_one.return_value = {
            'postulacionId': POSTULACION_ID,
            'animalId': 'SIM-000001',
            'postulanteRut': RUT_VECINO,
            'estado': estados.RECIBIDA,
        }
        self.sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {'rut': RUT_VECINO, 'perfil': 'vecino'},
            ),
        )
        self.collection = patch(
            'adopciones.modulos_indiv.hu_eric.db.postulaciones',
            return_value=self.postulaciones,
        )
        self.notificacion = patch(
            'adopciones.modulos_indiv.hu_eric.crear_notificacion',
            return_value={'notificacionId': 'N-000001'},
        )
        for mock in (self.sesion, self.collection):
            mock.start()
            self.addCleanup(mock.stop)
        self.notificacion_mock = self.notificacion.start()
        self.addCleanup(self.notificacion.stop)

    def cancelar(self):
        return self.client.post(
            f'/api/adopciones/postulaciones/{POSTULACION_ID}/cancelar',
        )

    def test_vecino_cancela_su_postulacion_y_recibe_aviso(self):
        self.postulaciones.update_one.return_value = SimpleNamespace(matched_count=1)

        respuesta = self.cancelar()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['estado'], estados.CANCELADA)
        self.postulaciones.update_one.assert_called_once()
        self.assertEqual(
            self.postulaciones.update_one.call_args.args[0],
            {'postulacionId': POSTULACION_ID, 'estado': estados.RECIBIDA},
        )
        self.notificacion_mock.assert_called_once()

    def test_no_envia_aviso_si_el_estado_cambio_en_paralelo(self):
        self.postulaciones.update_one.return_value = SimpleNamespace(matched_count=0)

        respuesta = self.cancelar()

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['error']['codigo'], 'TRANSICION_INVALIDA')
        self.notificacion_mock.assert_not_called()
