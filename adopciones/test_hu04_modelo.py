from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient


ANIMAL_M1 = {
    'animalId': 'SIM-000001',
    'estado': 'con_microchip',
    'nombre': 'Cholito',
    'especie': 'perro',
    'raza': 'mestizo',
    'edadAproximada': 5,
    'microchip': 123456789,
}


class ModeloPublicacionAnimalTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token')
        self.publicaciones = Mock()
        self.publicaciones.find_one.return_value = None
        self.validar_sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: {'rut': '17777777-3', 'perfil': 'funcionario'},
            ),
        )
        self.obtener_animal = patch(
            'adopciones.modulos_indiv.hu_christopher.nucleo.obtener_animal',
            return_value=SimpleNamespace(
                status_code=200,
                json=lambda: dict(ANIMAL_M1),
            ),
        )
        self.publicaciones_db = patch(
            'adopciones.modulos_indiv.hu_christopher.db.publicaciones',
            return_value=self.publicaciones,
        )
        self.validar_sesion.start()
        self.addCleanup(self.validar_sesion.stop)
        self.obtener_animal_mock = self.obtener_animal.start()
        self.addCleanup(self.obtener_animal.stop)
        self.publicaciones_db.start()
        self.addCleanup(self.publicaciones_db.stop)

    def publicar(self, datos):
        return self.client.post(
            '/api/adopciones/publicaciones',
            data=datos,
            format='json',
        )

    def test_crea_documento_con_campos_opcionales_vacios(self):
        respuesta = self.publicar({'animalId': 'SIM-000001'})

        self.assertEqual(respuesta.status_code, 201)
        documento = self.publicaciones.insert_one.call_args.args[0]
        self.assertEqual(documento['estado'], 'disponible')
        self.assertEqual(documento['nombre'], 'Cholito')
        self.assertEqual(documento['especie'], 'perro')
        self.assertEqual(documento['raza'], 'mestizo')
        self.assertEqual(documento['edadAproximada'], 5)
        self.assertIsNone(documento['descripcion'])
        self.assertIsNone(documento['fotografia'])

    def test_guarda_descripcion_y_referencia_fotografica_opcionales(self):
        respuesta = self.publicar({
            'animalId': 'SIM-000001',
            'descripcion': '  Animal tranquilo  ',
            'fotografia': '  https://ejemplo.test/cholito.jpg  ',
        })

        self.assertEqual(respuesta.status_code, 201)
        documento = self.publicaciones.insert_one.call_args.args[0]
        self.assertEqual(documento['descripcion'], 'Animal tranquilo')
        self.assertEqual(documento['fotografia'], 'https://ejemplo.test/cholito.jpg')

    def test_rechaza_campos_opcionales_no_textuales(self):
        respuesta = self.publicar({
            'animalId': 'SIM-000001',
            'descripcion': {'texto': 'inválido'},
        })

        self.assertEqual(respuesta.status_code, 400)
        self.obtener_animal_mock.assert_not_called()
        self.publicaciones.insert_one.assert_not_called()
