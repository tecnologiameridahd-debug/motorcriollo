# MotorCriollo

Marketplace de carros usados: publica, busca, filtra y contacta al vendedor. Sin swipes, sin matches — como Facebook Marketplace u OfferUp.

Sitio local: **http://127.0.0.1:8789**

## Arrancar

```bat
cd C:\Users\Alberto\motorcriollo
iniciar.bat
```

1. Abre http://127.0.0.1:8789
2. Crea tu cuenta o entra con un usuario demo
3. El marketplace ya trae publicaciones demo en varias ciudades de Florida

## Qué hay

- Registro / login (+ Google/Apple listos para conectar)
- Explorar / buscar con filtros (precio, marca, año, ciudad, palabra clave)
- Ficha de publicación con galería de fotos y datos del vendedor
- Contactar vendedor por WhatsApp o mensaje (se envía por correo)
- Publicar, editar, marcar como vendido y eliminar tus propios anuncios
- "Mis publicaciones" — panel del vendedor

## Demo

Los usuarios de muestra usan emails `*@demo.motorcriollo` y clave `demo1234` (por ejemplo `carlos@demo.motorcriollo` / `demo1234`).

## Gmail y Apple

Botones en login y registro. Claves en `config_local.py` — mismo patrón que DateRadar, variables `MOTORCRIOLLO_GOOGLE_CLIENT_ID` / `MOTORCRIOLLO_GOOGLE_CLIENT_SECRET`.

## Publicar (Render)

Pasos: **[PUBLICAR.md](PUBLICAR.md)**

Repo propio. Servicio propio. Base `motorcriollo-db` propia.

## Stack

FastAPI + Jinja2 + SQLite local / **Postgres en Render** (`DATABASE_URL`)
