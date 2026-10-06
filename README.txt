AGENDA COMPA V4

Nueva versión basada en Agenda Compa V3.

NOVEDAD PRINCIPAL: AUXILIO FUNCIONAL
- Hasta 3 referentes de emergencia por estudiante.
- Alta y eliminación de referentes.
- Selección del referente.
- Solicitud de geolocalización desde el navegador.
- Generación de enlace de Google Maps.
- Mensaje de emergencia personalizado.
- Registro del pedido en SQLite.
- Apertura de WhatsApp con el mensaje preparado.
- El estudiante conserva el control y debe confirmar/enviar el mensaje en WhatsApp.

NOTA: La V4 implementa ubicación puntual. No realiza seguimiento continuo de ubicación.

INSTALACIÓN
1. pip install -r requirements.txt
2. python app.py
3. Abrir http://127.0.0.1:5000

ESTRUCTURA
app.py
agenda_compa.db
requirements.txt
templates/base.html
templates/login.html
templates/register.html
templates/index.html
static/style.css
