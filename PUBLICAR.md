# Subir MotorCriollo a Render

MotorCriollo es su **propio repo** y **propio servicio**. No toca DateRadar, CoachRadar ni GasRadar.

## Regla de oro

- NO abras los servicios de otros proyectos
- NO cambies su repo, su start command ni su `DATABASE_URL`
- NO hagas Blueprint sobre otro repo
- MotorCriollo = servicio nuevo + (opcional) base nueva `motorcriollo-db`

## Si tarda la primera vez

El plan **Free** de Render se duerme a los ~15 min sin visitas. La primera petición puede tardar 30–90 s. Después va rápido.

Para que no se duerma: en [cron-job.org](https://cron-job.org) (gratis) crea un GET cada 10 min a:

```text
https://motorcriollo.store/api/health
```

## 1. Código

Repo: `https://github.com/TU-USUARIO/MotorCriollo`

Cada cambio:

```powershell
cd C:\Users\Alberto\motorcriollo
git add .
git commit -m "cambio"
git push origin main
```

## 2. Servicio web nuevo en Render

1. Entra a https://dashboard.render.com
2. **New** → **Web Service**
3. Conecta el repo **MotorCriollo**
4. Configura:
   - **Name:** `MotorCriollo`
   - **Runtime:** Python
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Plan: **Free**
5. **Create Web Service**

URL del servicio (ejemplo):

```text
https://motorcriollo.onrender.com
```

## 2b. Dominio `motorcriollo.store` (Namecheap → MotorCriollo)

Cuando compres el dominio, apúntalo al servicio **MotorCriollo**.

**En Render** (servicio MotorCriollo):

1. Settings → **Custom Domains** → Add
2. Agrega `www.motorcriollo.store`
3. Agrega `motorcriollo.store`
4. Copia el hostname de tu servicio, tipo `motorcriollo-xxxx.onrender.com`

**En Namecheap** → Domain List → `motorcriollo.store` → **Advanced DNS**

Borra los registros de parking (URL Redirect, CNAME a `parkingpage.namecheap.com`, A raros).

Pon solo esto:

| Tipo | Host | Value | TTL |
|---|---|---|---|
| **A** | `@` | `216.24.57.1` | Automatic |
| **CNAME** | `www` | `motorcriollo.onrender.com` | Automatic |

Si hay un registro **AAAA**, bórralo.

Espera 5–30 min. Render pone el HTTPS (candado). La web queda:

- https://www.motorcriollo.store
- https://motorcriollo.store

Comprueba: https://www.motorcriollo.store/api/health

## 3. Disco en el Web Service de $7 (recomendado)

Si ya pagaste el Starter ($7) del servicio **MotorCriollo**:

1. MotorCriollo → **Disks** → **Add disk**
2. Name: `motorcriollo-data`
3. **Mount path:** `/var/data`
4. Size: `1 GB`
5. Environment → Add:
   - `MOTORCRIOLLO_DATA` = `/var/data`
6. Manual Deploy

Así cuentas, publicaciones y fotos **no se borran**. No uses el disco de otro proyecto.

`/api/health` debe decir `"persistent": true`.

## 3b. Postgres (opcional, si no usas disco)

En Render Free, SQLite se borra al redeploy. Hay que pegar una **Postgres NUEVA**:

1. **New** → **PostgreSQL**
2. Nombre: `motorcriollo-db` (no uses la de otro proyecto)
3. Copia **Internal Database URL**
4. En el servicio **MotorCriollo** → Environment:
   - `DATABASE_URL` = esa URL
5. Manual Deploy

Comprueba: `https://TU-URL/api/health`
debe decir `"backend":"postgres"` y `"persistent":true`.

## 4. Correo (SendGrid)

Clave del **dashboard** (tú verificas cédulas y das el ID de vendedor):

- `MOTORCRIOLLO_ADMIN` = una clave larga solo tuya

Panel: `https://www.motorcriollo.store/admin/entrar`

En MotorCriollo → Environment pega:

- `SENDGRID_API_KEY` = tu `SG.…`
- `SENDGRID_FROM_EMAIL` = `soporte@motorcriollo.store`
- `SENDGRID_REPLY_TO` = `soporte@motorcriollo.store`

En SendGrid: **Sender Authentication** → autentica el dominio `motorcriollo.store` (o un Single Sender con ese correo). Si el From no está verificado, el correo no sale.

Al registrarse con email se envía un enlace de confirmación. También hay "Olvidé mi contraseña" y notificación al vendedor cuando un comprador escribe. Google/Apple no necesitan ese correo.

Comprueba: `https://www.motorcriollo.store/api/health` → `"email":{"configured":true}`

## 5. Gmail / Apple (después)

En Environment de **MotorCriollo**:

- `MOTORCRIOLLO_GOOGLE_CLIENT_ID`
- `MOTORCRIOLLO_GOOGLE_CLIENT_SECRET`

Callback de Google:

`https://TU-URL-DE-MOTORCRIOLLO/auth/google/callback`
