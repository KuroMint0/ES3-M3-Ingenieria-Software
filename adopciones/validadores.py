"""
Validación de entradas del módulo (OWASP A03: inyección, A04: diseño inseguro).

Todo dato que viene del cliente se valida AQUÍ antes de usarlo: antes de
consultar Mongo, antes de armar una URL hacia el núcleo, antes de guardar.
Usamos Serializer de DRF (no ModelSerializer: no hay ORM).
"""
import os
import re

from rest_framework import serializers

# --- Constantes -------------------------------------------------------------
TIPOS_VIVIENDA = ['casa', 'departamento', 'parcela', 'otro']

# \Z (y no $) para que "SIM-1\n" NO pase: $ acepta un salto de línea final.
PATRON_ANIMAL_ID = r'^[A-Z]{1,5}-[0-9]{1,10}\Z'          # SIM-000001, A-000123
PATRON_POSTULACION_ID = r'^P-[A-Z0-9-]{1,20}\Z'          # P-000842, P-DEMO-0002
PATRON_CONTROL_ID = r'^[0-9a-f]{32}\Z'                   # uuid4 en hexadecimal

MAX_ARCHIVO = 5 * 1024 * 1024                            # 5 MB

# Extensión permitida -> tipo de contenido (lo decidimos nosotros, no el cliente).
EXTENSIONES = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'png': 'image/png',
}

# Primeros bytes ("firma") de cada formato. Con esto detectamos un .exe
# renombrado a .jpg: el nombre se falsifica, el contenido no.
FIRMAS = {
    'pdf': b'%PDF-',
    'png': b'\x89PNG\r\n\x1a\n',
    'jpg': b'\xff\xd8\xff',
}


def es_postulacion_id(valor):
    return re.match(PATRON_POSTULACION_ID, valor) is not None


def es_control_id(valor):
    return re.match(PATRON_CONTROL_ID, valor) is not None


# --- Booleano estricto -------------------------------------------------------
class BooleanoEstricto(serializers.BooleanField):
    """
    Solo acepta los booleanos reales de JSON (true / false).

    El BooleanField normal de DRF también acepta "true", "1", "yes", 1...
    Para un consentimiento EXPLÍCITO (Ley 21.719) eso no sirve.
    Ojo: en Python bool es subclase de int y 1 == True, por eso se
    comprueba el TIPO con isinstance y no el valor.
    """

    def to_internal_value(self, data):
        if isinstance(data, bool):
            return data
        self.fail('invalid', input=data)


# --- HU-07: formulario de adopción -------------------------------------------
class FormularioSerializer(serializers.Serializer):
    tipoVivienda = serializers.ChoiceField(choices=TIPOS_VIVIENDA)
    patioExterior = BooleanoEstricto()
    otrosAnimales = BooleanoEstricto()
    presenciaNinos = BooleanoEstricto()
    consentimientoFamiliar = BooleanoEstricto()

    def validate_consentimientoFamiliar(self, value):
        # El consentimiento debe ser true: false NO basta (Ley 21.719).
        if value is not True:
            raise serializers.ValidationError('Debes aceptar el consentimiento familiar.')
        return value


# --- HU-01: postulación -------------------------------------------------------
class PostulacionSerializer(serializers.Serializer):
    # RegexField es un CharField: rechaza objetos y listas, así que
    # {"$ne": null} no llega a Mongo (inyección NoSQL). El patrón es la 2.ª capa.
    animalId = serializers.RegexField(PATRON_ANIMAL_ID, max_length=20)
    formulario = FormularioSerializer()


# --- HU-08: seguimiento -------------------------------------------------------
class SeguimientoSerializer(serializers.Serializer):
    observaciones = serializers.CharField(max_length=1000)


# --- Campos que el cliente NO puede enviar -------------------------------------
def campos_no_permitidos(datos, serializador, extras=()):
    """
    Claves enviadas por el cliente que no están en el serializador.

    DRF ignora en silencio lo que no conoce. Rechazarlo deja claro que campos
    como estado, postulanteRut o fechaPostulacion los asigna SOLO el servidor
    (asignación masiva / mass assignment).
    """
    if not isinstance(datos, dict):
        return []
    permitidos = set(serializador().fields.keys()) | set(extras)
    return sorted(set(datos.keys()) - permitidos)


def campos_no_permitidos_postulacion(datos):
    """Igual, pero también revisa las claves dentro de 'formulario'."""
    sobrantes = campos_no_permitidos(datos, PostulacionSerializer)
    if isinstance(datos, dict) and isinstance(datos.get('formulario'), dict):
        sobrantes += ['formulario.' + c
                      for c in campos_no_permitidos(datos['formulario'], FormularioSerializer)]
    return sobrantes


# --- Mensaje de error sin repetir lo que escribió la persona -------------------
def _aplanar(errores, prefijo=''):
    campos = []
    if isinstance(errores, dict):
        for clave, valor in errores.items():
            nombre = f'{prefijo}{clave}'
            if isinstance(valor, dict):
                campos += _aplanar(valor, nombre + '.')
            else:
                campos.append(nombre)
    return campos


def mensaje_errores(errores):
    """Solo nombra los CAMPOS que fallaron (nombres nuestros, no del cliente)."""
    campos = ['cuerpo' if c == 'non_field_errors' else c for c in _aplanar(errores)]
    return 'Datos inválidos en: ' + ', '.join(campos)


# --- HU-08: validación de archivos ---------------------------------------------
class ArchivoInvalido(Exception):
    """El archivo no cumple las reglas. str(exc) es un mensaje seguro para el cliente."""


def validar_archivo(archivo):
    """
    Valida un archivo subido (UploadedFile de Django).
    Devuelve {'extension', 'tipo', 'nombreOriginal'} o lanza ArchivoInvalido.
    """
    # 1) Tamaño.
    if archivo.size == 0:
        raise ArchivoInvalido('El archivo está vacío.')
    if archivo.size > MAX_ARCHIVO:
        raise ArchivoInvalido('El archivo supera el tamaño máximo de 5 MB.')

    # 2) Extensión: solo la ÚLTIMA cuenta ("foto.jpg.exe" termina en "exe").
    nombre = os.path.basename(archivo.name or '')
    extension = nombre.rsplit('.', 1)[-1].lower() if '.' in nombre else ''
    if extension not in EXTENSIONES:
        raise ArchivoInvalido('Formato no permitido. Solo se aceptan PDF, JPG y PNG.')

    # 3) Contenido real: los primeros bytes deben coincidir con la extensión.
    inicio = archivo.read(8)
    archivo.seek(0)          # volver al inicio, o el archivo se guardaría cortado
    if not inicio.startswith(FIRMAS[extension]):
        raise ArchivoInvalido('El contenido del archivo no corresponde a su extensión.')

    # 4) El nombre original solo se guarda como DATO (limpio y recortado).
    nombre_limpio = ''.join(c for c in nombre if c.isprintable())[:100]
    return {
        'extension': extension,
        'tipo': EXTENSIONES[extension],     # sale de nuestra tabla, no del cliente
        'nombreOriginal': nombre_limpio or 'archivo',
    }