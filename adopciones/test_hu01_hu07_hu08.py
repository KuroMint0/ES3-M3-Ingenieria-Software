from types import SimpleNamespace
from unittest.mock import Mock, patch

from bson import ObjectId
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from adopciones import estados
from adopciones.validadores import MAX_ARCHIVO


ANIMAL_ID = 'SIM-000001'
POSTULACION_ID = 'P-000001'
RUT_VECINO = '11111111-1'
FORMULARIO = {
    'tipoVivienda': 'casa',
    'patioExterior': True,
    'otrosAnimales': False,
    'presenciaNinos': False,
    'consentimientoFamiliar': True,
}


def respuesta_nucleo(datos, status_code=200):
    return SimpleNamespace(status_code=status_code, json=lambda: dict(datos))


class PostulacionApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer test-token')
        self.sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=respuesta_nucleo({
                'rut': RUT_VECINO,
                'perfil': 'vecino',
            }),
        )
        self.sesion.start()
        self.addCleanup(self.sesion.stop)

    def crear(self, cuerpo):
        return self.client.post('/api/adopciones/postulaciones', cuerpo, format='json')

    def preparar_dependencias(self, postulacion_existente=None, postulaciones_activas=0):
        publicaciones = Mock()
        publicaciones.find_one.return_value = {'animalId': ANIMAL_ID}
        mocks = [
            patch(
                'adopciones.views_postulaciones.nucleo.obtener_animal',
                return_value=respuesta_nucleo({'estado': 'con_microchip'}),
            ),
            patch(
                'adopciones.views_postulaciones.nucleo.obtener_usuario',
                return_value=respuesta_nucleo({'prohibicionTenencia': False}),
            ),
            patch(
                'adopciones.views_postulaciones.db.publicaciones',
                return_value=publicaciones,
            ),
            patch(
                'adopciones.views_postulaciones.repo.buscar_activa',
                return_value=postulacion_existente,
            ),
            patch(
                'adopciones.views_postulaciones.repo.contar_activas_por_postulante',
                return_value=postulaciones_activas,
            ),
            patch('adopciones.views_postulaciones.repo.asegurar_indices'),
            patch(
                'adopciones.modulos_indiv.hu_alexis.validar_antecedentes_postulante',
                return_value={},
            ),
            patch(
                'adopciones.views_postulaciones.repo.siguiente_id',
                return_value=POSTULACION_ID,
            ),
            patch(
                'adopciones.views_postulaciones.repo.crear',
                side_effect=lambda documento: documento,
            ),
        ]
        return [mock.start() for mock in mocks], mocks

    def test_rechaza_formulario_incompleto_y_sin_consentimiento(self):
        incompleto = self.crear({'animalId': ANIMAL_ID, 'formulario': {}})
        sin_consentimiento = self.crear({
            'animalId': ANIMAL_ID,
            'formulario': {**FORMULARIO, 'consentimientoFamiliar': False},
        })

        self.assertEqual(incompleto.status_code, 400)
        self.assertEqual(sin_consentimiento.status_code, 400)
        self.assertEqual(incompleto.data['error']['codigo'], 'VALIDACION')
        self.assertEqual(sin_consentimiento.data['error']['codigo'], 'VALIDACION')

    def test_guarda_postulacion_con_tutor_de_sesion_y_formulario(self):
        started, mocks = self.preparar_dependencias()
        for mock in mocks:
            self.addCleanup(mock.stop)
        crear_mock = started[-1]

        respuesta = self.crear({
            'animalId': ANIMAL_ID,
            'formulario': {**FORMULARIO, 'observaciones': 'Patio cerrado'},
        })

        self.assertEqual(respuesta.status_code, 201)
        documento = crear_mock.call_args.args[0]
        self.assertEqual(documento['postulanteRut'], RUT_VECINO)
        self.assertEqual(documento['estado'], estados.RECIBIDA)
        self.assertTrue(documento['formulario']['consentimientoFamiliar'])
        self.assertEqual(documento['formulario']['observaciones'], 'Patio cerrado')

    def test_permite_postular_con_una_postulacion_activa(self):
        started, mocks = self.preparar_dependencias(postulaciones_activas=1)
        for mock in mocks:
            self.addCleanup(mock.stop)

        respuesta = self.crear({
            'animalId': ANIMAL_ID,
            'formulario': FORMULARIO,
        })

        self.assertEqual(respuesta.status_code, 201)

    def test_rechaza_tercera_postulacion_activa(self):
        started, mocks = self.preparar_dependencias(postulaciones_activas=2)
        for mock in mocks:
            self.addCleanup(mock.stop)
        animal_m1_mock = started[0]
        crear_mock = started[-1]

        respuesta = self.crear({
            'animalId': ANIMAL_ID,
            'formulario': FORMULARIO,
        })

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(
            respuesta.data['error']['codigo'],
            'MAXIMO_POSTULACIONES_ACTIVAS',
        )
        animal_m1_mock.assert_not_called()
        crear_mock.assert_not_called()

    def test_rechaza_postulacion_activa_duplicada(self):
        started, mocks = self.preparar_dependencias({'postulacionId': 'P-ANTERIOR'})
        for mock in mocks:
            self.addCleanup(mock.stop)
        crear_mock = started[-1]

        respuesta = self.crear({'animalId': ANIMAL_ID, 'formulario': FORMULARIO})

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['error']['codigo'], 'POSTULACION_DUPLICADA')
        crear_mock.assert_not_called()


class _ColeccionPostulaciones:
    def __init__(self, documentos):
        self.documentos = documentos

    def find_one(self, filtro, projection=None):
        resultado = next(
            (
                dict(documento)
                for documento in self.documentos
                if documento['postulacionId'] == filtro['postulacionId']
            ),
            None,
        )
        if resultado is not None and projection and projection.get('_id') == 0:
            resultado.pop('_id', None)
        return resultado

    def update_many(self, filtro, cambios):
        estados_objetivo = filtro['estado']['$in']
        for documento in self.documentos:
            if (
                documento['animalId'] == filtro['animalId']
                and documento['postulacionId'] != filtro['postulacionId']['$ne']
                and documento['estado'] in estados_objetivo
            ):
                documento.update(cambios['$set'])

    def update_one(self, filtro, cambios):
        documento = self.find_one(filtro)
        if documento is None:
            return SimpleNamespace(matched_count=0)
        for original in self.documentos:
            if original['postulacionId'] == filtro['postulacionId']:
                original.update(cambios['$set'])
                original.setdefault('historialEvaluacion', []).extend(
                    [cambios['$push']['historialEvaluacion']]
                )
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


class _ColeccionPublicaciones:
    def __init__(self, documentos):
        self.documentos = documentos

    def update_one(self, filtro, cambios):
        for documento in self.documentos:
            if (
                documento['animalId'] == filtro['animalId']
                and documento['estado'] == filtro['estado']
            ):
                documento.update(cambios['$set'])
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    def find(self, filtro, projection):
        resultados = [
            dict(documento)
            for documento in self.documentos
            if documento['estado'] == filtro['estado']
        ]
        if projection and projection.get('_id') == 0:
            for documento in resultados:
                documento.pop('_id', None)
        return resultados


class AprobacionPostulacionTests(SimpleTestCase):
    def test_aprobar_cancela_otras_y_oculta_animal_del_catalogo(self):
        documentos = [
            {
                'postulacionId': POSTULACION_ID,
                'animalId': ANIMAL_ID,
                'postulanteRut': RUT_VECINO,
                'estado': estados.RECIBIDA,
                'historialEvaluacion': [],
            },
            {
                'postulacionId': 'P-000002',
                'animalId': ANIMAL_ID,
                'postulanteRut': '22222222-2',
                'estado': estados.EN_EVALUACION,
                'historialEvaluacion': [],
            },
            {
                'postulacionId': 'P-000003',
                'animalId': ANIMAL_ID,
                'postulanteRut': '33333333-3',
                'estado': estados.RECIBIDA,
                'historialEvaluacion': [],
            },
        ]
        aplicaciones = _ColeccionPostulaciones(documentos)
        publicaciones = _ColeccionPublicaciones([{
            'animalId': ANIMAL_ID,
            'estado': 'disponible',
        }])
        sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=respuesta_nucleo({
                'rut': '17777777-3',
                'perfil': 'funcionario',
            }),
        )
        post_collection = patch(
            'adopciones.modulos_indiv.hu_alexis.db.postulaciones',
            return_value=aplicaciones,
        )
        publication_collection = patch(
            'adopciones.modulos_indiv.hu_alexis.db.publicaciones',
            return_value=publicaciones,
        )
        sync_tutor = patch('adopciones.modulos_indiv.hu_eric.actualizar_tutor_m1')
        notification = patch('adopciones.modulos_indiv.hu_eric.crear_notificacion')
        for mock in (sesion, post_collection, publication_collection, sync_tutor, notification):
            mock.start()
            self.addCleanup(mock.stop)

        respuesta = APIClient().patch(
            f'/api/adopciones/postulaciones/{POSTULACION_ID}/estado',
            {'estado': estados.APROBADA},
            format='json',
            HTTP_AUTHORIZATION='Bearer funcionario-token',
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(documentos[0]['estado'], estados.APROBADA)
        self.assertEqual(documentos[1]['estado'], estados.CANCELADA_POR_ADOPCION)
        self.assertEqual(documentos[2]['estado'], estados.CANCELADA_POR_ADOPCION)
        self.assertEqual(publicaciones.documentos[0]['estado'], 'adoptado')

        with patch('adopciones.views.db.publicaciones', return_value=publicaciones):
            catalogo = APIClient().get('/api/adopciones/disponibles')
        self.assertEqual(catalogo.status_code, 200)
        self.assertEqual(catalogo.data['total'], 0)


class SeguimientoArchivoTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer funcionario-token')
        self.sesion = patch(
            'adopciones.seguridad.nucleo.validar_sesion',
            return_value=respuesta_nucleo({
                'rut': '17777777-3',
                'perfil': 'funcionario',
            }),
        )
        self.postulacion = patch(
            'adopciones.views_seguimientos.repo.obtener',
            return_value={
                'postulacionId': POSTULACION_ID,
                'estado': estados.ADOPCION_CONCRETADA,
                'seguimientoPosterior': [],
            },
        )
        self.bucket = Mock()
        self.bucket.upload_from_stream.return_value = ObjectId()
        self.archivos = patch(
            'adopciones.views_seguimientos.db.bucket_seguimientos',
            return_value=self.bucket,
        )
        self.agregar_control = patch(
            'adopciones.views_seguimientos.repo.agregar_control',
            return_value=True,
        )
        for mock in (self.sesion, self.postulacion, self.archivos, self.agregar_control):
            mock.start()
            self.addCleanup(mock.stop)

    def subir(self, nombre, contenido):
        return self.client.post(
            f'/api/adopciones/postulaciones/{POSTULACION_ID}/seguimientos',
            {
                'observaciones': 'Control realizado',
                'archivo': SimpleUploadedFile(nombre, contenido),
            },
            format='multipart',
        )

    def test_acepta_pdf_jpg_y_png(self):
        archivos = (
            ('control.pdf', b'%PDF-1.7\n'),
            ('control.jpg', b'\xff\xd8\xff\xe0'),
            ('control.png', b'\x89PNG\r\n\x1a\n'),
        )
        for nombre, contenido in archivos:
            with self.subTest(nombre=nombre):
                respuesta = self.subir(nombre, contenido)
                self.assertEqual(respuesta.status_code, 201)
                self.assertNotIn('archivoId', respuesta.data['archivo'])
                self.assertTrue(respuesta.data['control_valido'])

        self.assertEqual(self.bucket.upload_from_stream.call_count, 3)

    def test_lista_incluye_estado_de_postulacion(self):
        respuesta = self.client.get(
            f'/api/adopciones/postulaciones/{POSTULACION_ID}/seguimientos?page=1&limit=100'
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.data['estadoPostulacion'],
            estados.ADOPCION_CONCRETADA,
        )

    def test_acepta_archivo_en_el_limite_de_5_mb(self):
        contenido = b'%PDF-' + b'x' * (MAX_ARCHIVO - len(b'%PDF-'))

        respuesta = self.subir('limite.pdf', contenido)

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data['archivo']['tamano'], MAX_ARCHIVO)

    def test_rechaza_formatos_no_permitidos_y_archivos_sobredimensionados(self):
        invalidos = (
            ('malware.exe', b'MZcontenido'),
            ('documento.docx', b'PKcontenido'),
            ('firma-falsa.jpg', b'MZcontenido'),
        )
        for nombre, contenido in invalidos:
            with self.subTest(nombre=nombre):
                respuesta = self.subir(nombre, contenido)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(respuesta.data['error']['codigo'], 'ARCHIVO_INVALIDO')

        grande = self.subir(
            'grande.pdf',
            b'%PDF-' + b'x' * (MAX_ARCHIVO + 64 * 1024),
        )
        self.assertEqual(grande.status_code, 400)
        self.assertEqual(grande.data['error']['codigo'], 'ARCHIVO_DEMASIADO_GRANDE')
        self.bucket.upload_from_stream.assert_not_called()
