"""Publicaciones demo en ciudades de Venezuela — para que el marketplace no esté vacío."""
from __future__ import annotations

import os

from config import DEMO_DIR
from storage import (
    add_listing_photo,
    approve_kyc,
    browse_listings,
    create_listing,
    create_user,
    delete_listing,
    delete_user,
    get_user,
    get_user_by_email,
    init_db,
    list_user_listings,
)

DEMO_USERS = [
    {"email": "carlos@demo.motorcriollo", "name": "Carlos Peña", "phone": "+58 412 555 0101", "city": "Caracas", "state": "Distrito Capital"},
    {"email": "maria@demo.motorcriollo", "name": "María Gómez", "phone": "+58 414 555 0102", "city": "Maracaibo", "state": "Zulia"},
    {"email": "jose@demo.motorcriollo", "name": "José Ramírez", "phone": "+58 424 555 0103", "city": "Valencia", "state": "Carabobo"},
    {"email": "lucia@demo.motorcriollo", "name": "Lucía Fernández", "phone": "+58 416 555 0104", "city": "Maracay", "state": "Aragua"},
    {"email": "ana@demo.motorcriollo", "name": "Ana Torres", "phone": "+58 412 555 0105", "city": "Barquisimeto", "state": "Lara"},
    {"email": "pedro@demo.motorcriollo", "name": "Pedro Rivas", "phone": "+58 414 555 0106", "city": "Mérida", "state": "Mérida"},
    {"email": "rosa@demo.motorcriollo", "name": "Rosa Méndez", "phone": "+58 424 555 0107", "city": "Barcelona", "state": "Anzoátegui"},
    {"email": "diego@demo.motorcriollo", "name": "Diego Silva", "phone": "+58 416 555 0108", "city": "Puerto Ordaz", "state": "Bolívar"},
    {"email": "carmen@demo.motorcriollo", "name": "Carmen Díaz", "phone": "+58 412 555 0109", "city": "San Cristóbal", "state": "Táchira"},
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
        "description": "Sentra 2017 ideal para uso diario. Bajo consumo, "
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
        "description": "Elantra 2022 prácticamente nuevo, un solo dueño, no fumador.",
        "city": "Valencia", "state": "Carabobo", "color": "#264653",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Ford Mustang 2018 GT",
        "brand": "Ford", "model": "Mustang", "year": 2018, "price": 27500,
        "mileage": 39000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Mustang GT V8, sonido de escape deportivo, interior en piel. "
                        "Solo compradores serios.",
        "city": "Valencia", "state": "Carabobo", "color": "#1d3557",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Kia Sportage 2020",
        "brand": "Kia", "model": "Sportage", "year": 2020, "price": 19900,
        "mileage": 41000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Sportage 2020, espaciosa, ideal familia, título limpio.",
        "city": "Maracay", "state": "Aragua", "color": "#f4a261",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Tesla Model 3 2022 — eléctrico",
        "brand": "Otro", "model": "Model 3", "year": 2022, "price": 31900,
        "mileage": 22000, "transmission": "Automática", "fuel_type": "Eléctrico",
        "condition": "Usado - excelente",
        "description": "Model 3 con autopilot, batería con gran autonomía.",
        "city": "Maracay", "state": "Aragua", "color": "#6d597a",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Volkswagen Jetta 2016",
        "brand": "Volkswagen", "model": "Jetta", "year": 2016, "price": 8900,
        "mileage": 95000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - regular",
        "description": "Jetta 2016 funcional, algunos detalles estéticos. Precio negociable.",
        "city": "Maracaibo", "state": "Zulia", "color": "#3a5a40",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Jeep Wrangler 2019 Sahara",
        "brand": "Jeep", "model": "Wrangler", "year": 2019, "price": 29900,
        "mileage": 37000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Wrangler Sahara 4x4, techo removible, perfecto para playa y aventura.",
        "city": "Valencia", "state": "Carabobo", "color": "#606c38",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Toyota Fortuner 2018 4x4",
        "brand": "Toyota", "model": "Fortuner", "year": 2018, "price": 28500,
        "mileage": 64000, "transmission": "Automática", "fuel_type": "Diésel",
        "condition": "Usado - excelente",
        "description": "Fortuner 4x4 diésel, tercera fila, aire dual. Ideal familia y viaje.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#111827",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Toyota Hilux 2020 doble cabina",
        "brand": "Toyota", "model": "Hilux", "year": 2020, "price": 32000,
        "mileage": 48000, "transmission": "Manual", "fuel_type": "Diésel",
        "condition": "Usado - excelente",
        "description": "Hilux 2020, 4x4, para trabajo pesado. Mantenimiento Toyota al día.",
        "city": "Valencia", "state": "Carabobo", "color": "#9a3412",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Chevrolet Aveo 2014",
        "brand": "Chevrolet", "model": "Aveo", "year": 2014, "price": 4500,
        "mileage": 118000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Aveo económico, aire, papeles en regla. Buen primer carro.",
        "city": "Maracaibo", "state": "Zulia", "color": "#0369a1",
    },
    {
        "owner": "ana@demo.motorcriollo",
        "title": "Chevrolet Spark 2016",
        "brand": "Chevrolet", "model": "Spark", "year": 2016, "price": 5200,
        "mileage": 76000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Spark 2016, bajo consumo, ideal ciudad. Un dueño.",
        "city": "Barquisimeto", "state": "Lara", "color": "#7c3aed",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Ford Explorer 2017 Limited",
        "brand": "Ford", "model": "Explorer", "year": 2017, "price": 21000,
        "mileage": 72000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Explorer Limited, piel, techo, 7 puestos. Lista para viajar.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#1e3a8a",
    },
    {
        "owner": "diego@demo.motorcriollo",
        "title": "Ford Ranger 2019 4x4",
        "brand": "Ford", "model": "Ranger", "year": 2019, "price": 24500,
        "mileage": 54000, "transmission": "Automática", "fuel_type": "Diésel",
        "condition": "Usado - excelente",
        "description": "Ranger 4x4, pick-up para obra o campo. Caucho nuevo.",
        "city": "Puerto Ordaz", "state": "Bolívar", "color": "#44403c",
    },
    {
        "owner": "pedro@demo.motorcriollo",
        "title": "Honda Civic 2018 EX",
        "brand": "Honda", "model": "Civic", "year": 2018, "price": 15500,
        "mileage": 61000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Civic 2018, pantalla, cámara, excelente para carretera.",
        "city": "Mérida", "state": "Mérida", "color": "#0f766e",
    },
    {
        "owner": "carmen@demo.motorcriollo",
        "title": "Honda Fit 2015",
        "brand": "Honda", "model": "Fit", "year": 2015, "price": 7800,
        "mileage": 99000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Fit espacioso, económico. Perfecto para ciudad.",
        "city": "San Cristóbal", "state": "Táchira", "color": "#be123c",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Hyundai Tucson 2019",
        "brand": "Hyundai", "model": "Tucson", "year": 2019, "price": 19800,
        "mileage": 43000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Tucson 2019, full equipo, un solo dueño.",
        "city": "Maracay", "state": "Aragua", "color": "#155e75",
    },
    {
        "owner": "rosa@demo.motorcriollo",
        "title": "Hyundai Accent 2016",
        "brand": "Hyundai", "model": "Accent", "year": 2016, "price": 7200,
        "mileage": 87000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Accent 2016, motor sano, aire frío. Negociable.",
        "city": "Barcelona", "state": "Anzoátegui", "color": "#a16207",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Kia Rio 2018",
        "brand": "Kia", "model": "Rio", "year": 2018, "price": 10500,
        "mileage": 58000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Rio 2018, garantía de fábrica vencida hace poco, impecable.",
        "city": "Valencia", "state": "Carabobo", "color": "#7f1d1d",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Kia Sorento 2017 7 puestos",
        "brand": "Kia", "model": "Sorento", "year": 2017, "price": 17500,
        "mileage": 79000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Sorento 7 puestos, familia grande. Cauchos 80%.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#365314",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Mazda 3 2019 Grand Touring",
        "brand": "Mazda", "model": "3", "year": 2019, "price": 14900,
        "mileage": 47000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Mazda 3 GT, Bose, techo. Se ve y maneja como nuevo.",
        "city": "Maracaibo", "state": "Zulia", "color": "#1e293b",
    },
    {
        "owner": "rosa@demo.motorcriollo",
        "title": "Mazda CX-5 2021",
        "brand": "Mazda", "model": "CX-5", "year": 2021, "price": 22900,
        "mileage": 28000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "CX-5 2021, poco uso, AWD. Perfecta para la costa.",
        "city": "Lechería", "state": "Anzoátegui", "color": "#334155",
    },
    {
        "owner": "carmen@demo.motorcriollo",
        "title": "Mitsubishi L200 2018 4x4",
        "brand": "Mitsubishi", "model": "L200", "year": 2018, "price": 19500,
        "mileage": 67000, "transmission": "Manual", "fuel_type": "Diésel",
        "condition": "Usado - bueno",
        "description": "L200 4x4 diésel, para carga y montaña.",
        "city": "San Cristóbal", "state": "Táchira", "color": "#44403c",
    },
    {
        "owner": "diego@demo.motorcriollo",
        "title": "Mitsubishi Lancer 2014",
        "brand": "Mitsubishi", "model": "Lancer", "year": 2014, "price": 6800,
        "mileage": 112000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - regular",
        "description": "Lancer 2014, motor y caja bien. Detalles de pintura.",
        "city": "Puerto Ordaz", "state": "Bolívar", "color": "#0e7490",
    },
    {
        "owner": "pedro@demo.motorcriollo",
        "title": "Nissan Frontier 2020",
        "brand": "Nissan", "model": "Frontier", "year": 2020, "price": 23900,
        "mileage": 41000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Frontier 2020, poco kilometraje, 4x2. Lista para trabajar.",
        "city": "Mérida", "state": "Mérida", "color": "#854d0e",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Nissan Tiida 2013",
        "brand": "Nissan", "model": "Tiida", "year": 2013, "price": 4900,
        "mileage": 131000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Tiida 2013, aire, dirección. Carro de diario confiable.",
        "city": "Cabimas", "state": "Zulia", "color": "#57534e",
    },
    {
        "owner": "pedro@demo.motorcriollo",
        "title": "Renault Duster 2018",
        "brand": "Renault", "model": "Duster", "year": 2018, "price": 12500,
        "mileage": 69000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Duster 2018, alta, para carretera andina. Un dueño.",
        "city": "Mérida", "state": "Mérida", "color": "#166534",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Renault Logan 2017",
        "brand": "Renault", "model": "Logan", "year": 2017, "price": 7500,
        "mileage": 91000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Logan 2017, baúl grande, económico. Papeles al día.",
        "city": "Valencia", "state": "Carabobo", "color": "#1d4ed8",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Suzuki Swift 2019",
        "brand": "Suzuki", "model": "Swift", "year": 2019, "price": 11200,
        "mileage": 44000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Swift 2019, ágil y ahorrador. Como nuevo por dentro.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#b91c1c",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Suzuki Vitara 2020",
        "brand": "Suzuki", "model": "Vitara", "year": 2020, "price": 16800,
        "mileage": 36000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Vitara 2020, SUV compacta, cámara y sensores.",
        "city": "Maracay", "state": "Aragua", "color": "#0f766e",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Volkswagen Golf 2015",
        "brand": "Volkswagen", "model": "Golf", "year": 2015, "price": 9800,
        "mileage": 102000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Golf 2015, maneja firme. Servicio reciente.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#1e40af",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Dodge Journey 2016",
        "brand": "Dodge", "model": "Journey", "year": 2016, "price": 11900,
        "mileage": 88000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Journey 2016, 7 puestos, aire dual. Familia.",
        "city": "Maracaibo", "state": "Zulia", "color": "#7c2d12",
    },
    {
        "owner": "rosa@demo.motorcriollo",
        "title": "Ram 1500 2019",
        "brand": "Ram", "model": "1500", "year": 2019, "price": 33500,
        "mileage": 52000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Ram 1500, hemi, cabina crew. Para trabajo serio.",
        "city": "Puerto La Cruz", "state": "Anzoátegui", "color": "#171717",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Jeep Grand Cherokee 2017 Laredo",
        "brand": "Jeep", "model": "Grand Cherokee", "year": 2017, "price": 24500,
        "mileage": 71000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Grand Cherokee Laredo, 4x4, piel. Lista para carretera.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#14532d",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "BMW 320i 2016",
        "brand": "BMW", "model": "320i", "year": 2016, "price": 18900,
        "mileage": 74000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "320i 2016, techo, xenón. Servicio en agencia.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#1e3a8a",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Mercedes-Benz C200 2015",
        "brand": "Mercedes-Benz", "model": "C200", "year": 2015, "price": 17500,
        "mileage": 86000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "C200 2015, interior impecable. Precio a conversar.",
        "city": "Valencia", "state": "Carabobo", "color": "#111827",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Audi A4 2017",
        "brand": "Audi", "model": "A4", "year": 2017, "price": 20500,
        "mileage": 63000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "A4 2017, quattro, virtual cockpit. Un dueño.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#0c4a6e",
    },
    {
        "owner": "ana@demo.motorcriollo",
        "title": "Toyota Yaris 2018",
        "brand": "Toyota", "model": "Yaris", "year": 2018, "price": 10800,
        "mileage": 55000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Yaris 2018, Toyota puro. Ahorrador y sano.",
        "city": "Barquisimeto", "state": "Lara", "color": "#b45309",
    },
    {
        "owner": "carmen@demo.motorcriollo",
        "title": "Toyota 4Runner 2016",
        "brand": "Toyota", "model": "4Runner", "year": 2016, "price": 26500,
        "mileage": 82000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "4Runner 2016, 4x4, para Táchira y más. Muy cuidada.",
        "city": "San Cristóbal", "state": "Táchira", "color": "#365314",
    },
    {
        "owner": "lucia@demo.motorcriollo",
        "title": "Chevrolet Cruze 2015",
        "brand": "Chevrolet", "model": "Cruze", "year": 2015, "price": 8200,
        "mileage": 97000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Cruze 2015, cómodo para carretera. Aire dual.",
        "city": "Maracay", "state": "Aragua", "color": "#9f1239",
    },
    {
        "owner": "ana@demo.motorcriollo",
        "title": "Ford Fiesta 2014",
        "brand": "Ford", "model": "Fiesta", "year": 2014, "price": 5800,
        "mileage": 108000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - regular",
        "description": "Fiesta 2014, motor bien. Detalles de uso. Barato.",
        "city": "Punto Fijo", "state": "Falcón", "color": "#0369a1",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Honda Accord 2017 EX-L",
        "brand": "Honda", "model": "Accord", "year": 2017, "price": 16500,
        "mileage": 70000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Accord EX-L, piel, techo. Sedán grande y cómodo.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#1e293b",
    },
    {
        "owner": "maria@demo.motorcriollo",
        "title": "Hyundai Santa Fe 2018",
        "brand": "Hyundai", "model": "Santa Fe", "year": 2018, "price": 21500,
        "mileage": 59000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Santa Fe 2018, 7 puestos, full. Una dueña.",
        "city": "Maracaibo", "state": "Zulia", "color": "#115e59",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Nissan Versa 2019",
        "brand": "Nissan", "model": "Versa", "year": 2019, "price": 9900,
        "mileage": 51000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Versa 2019, amplio y económico. Ideal primer carro.",
        "city": "Valencia", "state": "Carabobo", "color": "#4c1d95",
    },
    {
        "owner": "carmen@demo.motorcriollo",
        "title": "Kia Picanto 2020",
        "brand": "Kia", "model": "Picanto", "year": 2020, "price": 8900,
        "mileage": 32000, "transmission": "Manual", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "Picanto 2020, poquito uso, para ciudad.",
        "city": "San Cristóbal", "state": "Táchira", "color": "#9d174d",
    },
    {
        "owner": "carlos@demo.motorcriollo",
        "title": "Toyota Camry 2016 XLE",
        "brand": "Toyota", "model": "Camry", "year": 2016, "price": 15200,
        "mileage": 78000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Camry XLE, cómodo, Toyota de verdad.",
        "city": "Caracas", "state": "Distrito Capital", "color": "#7f1d1d",
    },
    {
        "owner": "jose@demo.motorcriollo",
        "title": "Chevrolet Tahoe 2015",
        "brand": "Chevrolet", "model": "Tahoe", "year": 2015, "price": 22800,
        "mileage": 94000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - bueno",
        "description": "Tahoe 2015, 8 puestos, 4x4. Camioneta grande.",
        "city": "Valencia", "state": "Carabobo", "color": "#1e3a8a",
    },
    {
        "owner": "diego@demo.motorcriollo",
        "title": "Ford F-150 2018 XLT",
        "brand": "Ford", "model": "F-150", "year": 2018, "price": 28900,
        "mileage": 61000, "transmission": "Automática", "fuel_type": "Gasolina",
        "condition": "Usado - excelente",
        "description": "F-150 XLT, para minería o obra. Muy cuidada.",
        "city": "Ciudad Guayana", "state": "Bolívar", "color": "#292524",
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
<text x="320" y="90" font-family="Arial, sans-serif" font-size="28" fill="rgba(255,255,255,0.85)" text-anchor="middle" font-weight="bold">{label}</text>
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
        person = get_user(uid)
        if person and person.get("kyc_status") != "approved":
            approve_kyc(uid, note="Cuenta demo verificada")

    have = {l.get("title") for l in browse_listings(limit=500)}
    created = 0
    phones = {u["email"]: u["phone"] for u in DEMO_USERS}
    for item in LISTINGS:
        if item["title"] in have:
            continue
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
            phone=phones[item["owner"]],
            is_demo=True,
        )
        slug = f"{item['brand']}-{item['model']}-{item['year']}".lower().replace(" ", "-")
        label = f"{item['brand']} {item['model']} {item['year']}"
        photo = _ensure_photo(slug, item["color"], label)
        add_listing_photo(listing["id"], photo, 0)
        created += 1
        have.add(item["title"])

    return created


if __name__ == "__main__":
    n = seed()
    print(f"Publicaciones demo creadas: {n}")
