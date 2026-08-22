"""Publicaciones demo en varias ciudades — para que el marketplace no esté vacío."""
from __future__ import annotations

import os

from config import DEMO_DIR
from storage import (
    add_listing_photo,
    browse_listings,
    create_listing,
    create_user,
    delete_listing,
    delete_user,
    get_user_by_email,
    init_db,
    list_listing_photos,
    list_user_listings,
)

DEMO_USERS = [
    {"email": "carlos@demo.motorcriollo", "name": "Carlos Peña", "phone": "+58 412 555 0101", "city": "Caracas", "state": "Distrito Capital"},
    {"email": "maria@demo.motorcriollo", "name": "María Gómez", "phone": "+58 414 555 0102", "city": "Maracaibo", "state": "Zulia"},
    {"email": "jose@demo.motorcriollo", "name": "José Ramírez", "phone": "+58 424 555 0103", "city": "Valencia", "state": "Carabobo"},
    {"email": "lucia@demo.motorcriollo", "name": "Lucía Fernández", "phone": "+58 416 555 0104", "city": "Maracay", "state": "Aragua"},
]

LISTINGS = [
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Toyota Corolla 2019 — único dueño",
        "brand": "Toyota", "model": "Corolla", "year": 2019, "price": 14500,
        "mileage": 52000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Corolla 2019 en excelente estado, mantenimientos al día, sin choques, "
                        "aire frío, todo original. Listo para traspaso.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#e63946",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Honda CR-V 2021 — como nueva",
        "brand": "Honda", "model": "CR-V", "year": 2021, "price": 23900,
        "mileage": 31000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "CR-V 2021, cámara de reversa, apple carplay, techo panorámico. "
                        "Cero detalles mecánicos.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#457b9d",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Nissan Sentra 2017 — económico",
        "brand": "Nissan", "model": "Sentra", "year": 2017, "price": 9800,
        "mileage": 88000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Sentra 2017 ideal para uso diario o Uber/Lyft. Bajo consumo, "
                        "llantas nuevas, batería nueva.",
        "city": "Maracaibo", "state": "Zulia", "color": "#2a9d8f",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Chevrolet Silverado 2020 4x4",
        "brand": "Chevrolet", "model": "Silverado", "year": 2020, "price": 34500,
        "mileage": 45000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Silverado 2020 doble cabina, 4x4, gancho de arrastre, para trabajo o "
                        "familia grande.",
        "city": "Maracaibo", "state": "Zulia", "color": "#e76f51",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Hyundai Elantra 2022",
        "brand": "Hyundai", "model": "Elantra", "year": 2022, "price": 18700,
        "mileage": 18000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Elantra 2022 prácticamente nuevo, garantía de fábrica vigente, "
                        "un solo dueño, no fumador.",
        "city": "Valencia", "state": "Carabobo", "color": "#264653",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Ford Mustang 2018 GT",
        "brand": "Ford", "model": "Mustang", "year": 2018, "price": 27500,
        "mileage": 39000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Mustang GT V8, sonido de escape deportivo, interior en piel, "
                        "impecable. Solo compradores serios.",
        "city": "Valencia", "state": "Carabobo", "color": "#1d3557",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Kia Sportage 2020",
        "brand": "Kia", "model": "Sportage", "year": 2020, "price": 19900,
        "mileage": 41000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Sportage 2020, espaciosa, ideal familia, aire y calefacción "
                        "funcionando perfecto, título limpio.",
        "city": "Maracay", "state": "Aragua", "color": "#f4a261",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Tesla Model 3 2022 — eléctrico",
        "brand": "Otro", "model": "Model 3", "year": 2022, "price": 31900,
        "mileage": 22000, "transmission": "Automática", "fuel_type": "Eléctrico",
        "condition": "Usado - excelente",
        "description": "Model 3 con autopilot, batería con gran autonomía, cero "
                        "mantenimiento de motor. Carga rápida incluida.",
        "city": "Maracay", "state": "Aragua", "color": "#6d597a",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Volkswagen Jetta 2016",
        "brand": "Volkswagen", "model": "Jetta", "year": 2016, "price": 8900,
        "mileage": 95000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - regular",
        "description": "Jetta 2016 funcional, motor y transmisión en buen estado, "
                        "algunos detalles estéticos. Precio negociable.",
        "city": "Maracaibo", "state": "Zulia", "color": "#3a5a40",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Jeep Wrangler 2019 Sahara",
        "brand": "Jeep", "model": "Wrangler", "year": 2019, "price": 29900,
        "mileage": 37000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Wrangler Sahara 4x4, techo removible, perfecto para playa y "
                        "aventura. Mantenimientos al día.",
        "city": "Valencia", "state": "Carabobo", "color": "#606c38",
    },
]


def _ensure_photo(slug: str, color: str, label: str) -> str:
    fname = f"{slug}.svg"
    path = os.path.join(DEMO_DIR, fname)
    if not os.path.exists(path):
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="420" viewBox="0 0 640 420">
<rect width="640" height="420" fill="{color}"/>
<rect y="260" width="640" height="160" fill="rgba(0,0,0,0.18)"/>
<circle cx="180" cy="330" r="42" fill="#1a1a1a"/>
<circle cx="180" cy="330" r="18" fill="#ccc"/>
<circle cx="460" cy="330" r="42" fill="#1a1a1a"/>
<circle cx="460" cy="330" r="18" fill="#ccc"/>
<path d="M120 260 L170 180 L470 180 L520 260 Z" fill="rgba(255,255,255,0.22)"/>
<text x="320" y="90" font-family="Arial, sans-serif" font-size="34" fill="rgba(255,255,255,0.85)" text-anchor="middle" font-weight="bold">{label}</text>
</svg>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
    return f"/static/demo/{fname}"


def _clear_stale_demo() -> None:
    """Elimina la data demo de una versión anterior (ej. ciudades de EE.UU.) para poder resembrar."""
    for u in DEMO_USERS:
        existing = get_user_by_email(u["email"])
        if not existing:
            continue
        uid = existing["id"] if not isinstance(existing, dict) else existing.get("id")
        if existing["city"] == u["city"]:
            continue
        for listing in list_user_listings(uid):
            delete_listing(listing["id"])
        delete_user(uid)


def seed() -> int:
    init_db()
    _clear_stale_demo()
    if browse_listings(limit=1):
        return 0

    users_by_email = {}
    for u in DEMO_USERS:
        existing = get_user_by_email(u["email"])
        if existing:
            uid = existing["id"] if not isinstance(existing, dict) else existing.get("id")
        else:
            user = create_user(
                email=u["email"],
                password="demo1234",
                name=u["name"],
                phone=u["phone"],
                city=u["city"],
                state=u["state"],
                is_demo=True,
            )
            uid = user["id"]
        users_by_email[u["email"]] = uid

    created = 0
    for item in LISTINGS:
        owner_id = users_by_email[item["owner"]]
        listing = create_listing(
            user_id=owner_id,
            title=item["title"],
            brand=item["brand"],
            model=item["model"],
            year=item["year"],
            price=item["price"],
            mileage=item["mileage"],
            transmission=item["transmission"],
            fuel_type=item["fuel_type"],
            condition=item["condition"],
            description=item["description"],
            city=item["city"],
            state=item["state"],
            phone=next(u["phone"] for u in DEMO_USERS if u["email"] == item["owner"]),
            is_demo=True,
        )
        slug = f"{item['brand']}-{item['model']}-{item['year']}".lower().replace(" ", "-")
        label = f"{item['brand']} {item['model']} {item['year']}"
        photo = _ensure_photo(slug, item["color"], label)
        add_listing_photo(listing["id"], photo, 0)
        created += 1

    return created


if __name__ == "__main__":
    n = seed()
    print(f"Publicaciones demo creadas: {n}")
