# Soportes EPS - Gestor de Radicaciones

Sistema web local para gestionar soportes de radicación de EPS en PDF.

## Ejecutar

Desde PowerShell:

```powershell
cd "C:\Users\romar\Documents\Codex\2026-06-22\files-mentioned-by-the-user-sistema\outputs\eps-radicacion-manager"
.\start.ps1
```

Luego abre:

```text
http://127.0.0.1:8765/
```

## Conectar Supabase

1. Crea un proyecto en Supabase.
2. Abre el SQL Editor de Supabase y ejecuta el archivo `supabase_schema.sql`.
3. Copia `.env.example` como `.env`.
4. En `.env`, pega `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`.
5. Reinicia el sistema con `.\start.ps1`.

Con Supabase configurado, el sistema sincroniza usuarios, EPS, soportes, cortes, facturas y PDFs. En otra PC, al iniciar con el mismo `.env`, restaura los registros desde Supabase y descarga los PDF cuando se consulten o descarguen.

Con `DATA_BACKEND=supabase`, Supabase es la base única del sistema. SQLite no se inicializa ni se usa para usuarios, soportes, EPS, reportes o cortes.

## Subir a Vercel

El proyecto incluye `vercel.json`, `api/index.py`, `requirements.txt` y `.python-version` para desplegarlo como una función Python en Vercel.

En Vercel configura estas Environment Variables antes de desplegar:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` con la llave secreta del servidor (`sb_secret_...`) o la legacy `service_role`
- `SUPABASE_BUCKET=soportes-eps`
- `DATA_BACKEND=supabase`
- `SESSION_SECRET` con un texto largo y aleatorio

No uses `SUPABASE_KEY` ni una llave `sb_publishable_...` para `SUPABASE_SERVICE_ROLE_KEY`, porque Supabase la trata como rol `anon` y bloqueará tablas privadas como `app_users`. No subas `.env` a GitHub. Las variables se configuran en el panel de Vercel o con la CLI.

## Usuarios

El ingreso se hace con nombre de usuario y contraseña. Las contraseñas no se listan ni se guardan en claro; el sistema almacena un hash seguro y permite cambiarlas desde la pantalla de usuarios.

## Funcionalidades incluidas

- Login con roles: Administrador, Digitador y Consulta.
- Rol Consulta en modo solo lectura: puede consultar/reportar/descargar, pero no puede subir, editar, eliminar ni administrar datos.
- Carga múltiple de PDFs por arrastrar y soltar.
- Lectura automática de texto con `pdfplumber` y respaldo con `pypdf`.
- Extracción de EPS, fecha de radicación, número de radicado, factura, NIT y valor radicado cuando aparecen en el PDF.
- Lectura de soportes Gmail/FOMAG, Gmail/Auditool y Gmail/Famisanar con tablas de múltiples facturas, incluso cuando el PDF trae fuentes codificadas y el texto sale dañado.
- Pantalla de revisión cuando faltan EPS o fecha, sin volver a subir el archivo.
- Clasificación física por año, mes y EPS en la carpeta `storage`.
- Detección de duplicados por hash, número de radicado y nombre de archivo.
- Dashboard con estadísticas, agrupación por EPS y últimas cargas.
- Consulta con filtros por EPS, año, mes, fechas, radicado, factura, usuario, estado y archivo.
- Consulta por cortes de radicación como dato operativo del soporte: Corte 1, Corte 2 o Corte 3. El corte no depende de la fecha de radicación.
- Conteo de facturas detectadas dentro de cada PDF/radicado.
- Reporte de EPS por corte, sumando facturas y soportes por cada EPS, con acceso directo al listado filtrado.
- Visor PDF interno, descarga individual y descarga ZIP de todos los soportes filtrados.
- Supabase como base de datos principal y Storage remoto para PDFs, pensado para cambio de PC/IP sin perder datos.
- Administración de EPS, usuarios, configuración básica y reportes.

## Datos y archivos

- Base de datos: Supabase.
- PDFs cargados: Supabase Storage, bucket `soportes-eps`.
- PDFs de prueba: `samples/`

El motor de extracción está aislado en `server.py` para permitir incorporar OCR más adelante sin cambiar la interfaz ni el modelo de datos.
