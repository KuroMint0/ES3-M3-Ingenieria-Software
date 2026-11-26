# Módulo 3 · Adopciones — Sistema municipal de tenencia responsable de mascotas

Ingeniería de Software (TI3043) · INACAP Antofagasta · Sección FB50-C1 · Grupo G03

Módulo de Adopciones: publicar animales disponibles, registrar postulaciones de
vecinos, evaluarlas (aprobar/rechazar), concretar la adopción (actualizando el tutor
en el Módulo 1) y hacer el seguimiento posterior.

## Stack

- **Python 3.11+** · **Django 5 + Django REST Framework** (API REST)
- **MongoDB** (vía `pymongo`) — base propia del módulo: `tr_adopciones`
- Integración con el **núcleo del docente** y el **M1 simulado** por API REST + JSON

> No se usa el ORM de Django (es para bases SQL). El dominio vive en MongoDB.

## Cómo levantarlo localmente

```bash
# 1. Clonar y entrar
git clone https://github.com/KuroMint0/ES3-M3-Ingenieria-Software
cd ES3-M3-Ingenieria-Software

# 2. Entorno virtual e instalación
python -m venv .venv
Windows: .venv\Scripts\activate        # source .venv/bin/activate
pip install -r requirements.txt

# 3. Variables de entorno
Windows: copy .env.example .env            
#   edita .env: pon tu MONGO_URI (Atlas o mongodb://localhost:27017)

# 4. Levantar
python manage.py runserver       # http://localhost:8000
```

Abre `http://localhost:8000`: inicia sesión con un usuario de prueba del núcleo y
prueba el botón **GET /api/adopciones/disponibles**.

## Variables de entorno

| Variable | Para qué |
|---|---|
| `DJANGO_SECRET_KEY` | Clave de Django (no subir la real) |
| `DJANGO_DEBUG` | `True` en local, `False` en producción |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos (coma-separados) |
| `NUCLEO_URL` | URL del núcleo del docente (M1 simulado incluido) |
| `MONGO_URI` | Cadena de conexión a MongoDB |
| `MONGO_DB` | Nombre de la base (`tr_adopciones`) |

## Usuarios de prueba (núcleo) — clave común `tenencia2026`

| RUT | Perfil | Para probar |
|---|---|---|
| 17777777-3 | funcionario | Publicar, evaluar, seguimiento |
| 11111111-1 | vecino | Postular |
| 9876543-3 | vecino | Vecino con **prohibición de tenencia** (RN-04) |

## Endpoints (contrato del módulo)

| Método y ruta | Perfil | Historia |
|---|---|---|
| `GET /api/adopciones/salud` | público | — |
| `GET /api/adopciones/disponibles` | público | lista de animales publicados disponibles |
| `POST /api/adopciones/publicaciones` | funcionario | HU-04/HU-13: publicar animal con microchip |
| `POST /api/adopciones/postulaciones` | vecino | HU-01/HU-07: crear postulación |
| `PATCH /api/adopciones/postulaciones/{id}/estado` | funcionario | HU-14: cerrar adopción con dos controles válidos |
| `GET /api/adopciones/postulaciones/{id}/seguimientos` | funcionario, jefatura | HU-08: listar controles |
| `POST /api/adopciones/postulaciones/{id}/seguimientos` | funcionario | HU-08: registrar control |
| `GET /api/adopciones/postulaciones/{id}/seguimientos/{controlId}/archivo` | funcionario, jefatura | HU-08: descargar evidencia |

La postulación se envía en JSON con `animalId` y el objeto `formulario`.
`tipoVivienda`, `patioExterior`, `otrosAnimales`, `presenciaNinos` y
`consentimientoFamiliar` son obligatorios; el consentimiento debe ser `true`.
Las postulaciones activas duplicadas del mismo vecino al mismo animal se rechazan.
Al aprobar una postulación, el animal pasa a `adoptado` y las demás postulaciones
pendientes para ese animal quedan `cancelada_por_adopcion_concretada`.

Los controles HU-08 se guardan en GridFS de MongoDB (no en el disco local) y
aceptan PDF, JPG y PNG de hasta 5 MB; se valida tanto la extensión como la firma
del contenido. Se pueden registrar controles cuando la postulación está en estado
`adopcion_concretada`. Los nuevos controles quedan marcados `control_valido: true`;
el proceso solo se puede cerrar desde `adopcion_concretada` cuando ya tiene dos
controles válidos. El cierre actualiza el estado a `adopcion_cerrada`.

Para dejar los datos de demostración listos para las verificaciones:

```bash
python manage.py sembrar_demo
```

Convenciones: rutas en plural, respuestas JSON, errores `{"error":{"codigo","mensaje"}}`,
listados `?page=1&limit=20`, fechas ISO 8601 UTC, `404` para lo que no existe,
`401` sin token, `403` perfil sin permiso.

## Despliegue (Render)

- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn config.wsgi:application`
- Define `DJANGO_DEBUG=False` y `NUCLEO_URL=https://nucleo-tr.onrender.com`.
- Configura `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `MONGO_URI` y `MONGO_DB`
  desde las variables de entorno del servicio en Render. No agregues secretos al
  repositorio ni al archivo `render.yaml`.
- Al crear el servicio desde `render.yaml`, su nombre será `adopciones-tr`; confirma
  la URL asignada por Render antes de actualizar `entrega.json`.
