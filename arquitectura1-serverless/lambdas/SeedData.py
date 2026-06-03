import json
import boto3
import uuid

dynamodb = boto3.resource("dynamodb")

def lambda_handler(event, context):
    seed_categories()
    seed_tags()
    seed_users()
    seed_games()
    return {"statusCode": 200, "body": "Datos iniciales insertados correctamente"}


def seed_categories():
    table = dynamodb.Table("categories")
    categorias = [
        "PlayStation 4", "PlayStation 5", "XBOX Series",
        "XBOX One", "Nintendo Switch", "PC"
    ]
    for nombre in categorias:
        table.put_item(Item={
            "id": str(uuid.uuid4()),
            "name": nombre
        })
    print("Categorías insertadas")


def seed_tags():
    table = dynamodb.Table("tags")
    tags = ["Action", "RPG", "Simulation", "Fighting", "Shooter", "Visual Novel"]
    for nombre in tags:
        table.put_item(Item={
            "id": str(uuid.uuid4()),
            "name": nombre
        })
    print("Tags insertados")


def seed_users():
    table = dynamodb.Table("users")
    usuarios = [
        {
            "username": "lichking",
            "first_name": "Arthas",
            "last_name": "Menethil",
            "email": "thelichking@warcraft.com",
            "phone": "+34123456789"
        },
        {
            "username": "windrunner",
            "first_name": "Sylvanas",
            "last_name": "Windrunner",
            "email": "thequeen@warcraft.com",
            "phone": "+34123456781"
        }
    ]
    for usuario in usuarios:
        table.put_item(Item=usuario)
    print("Usuarios insertados")


def seed_games():
    # Primero obtenemos los IDs de categorías y tags que acabamos de insertar
    cat_table = dynamodb.Table("categories")
    tag_table = dynamodb.Table("tags")
    game_table = dynamodb.Table("games")

    # Leemos todas las categorías y tags para poder referenciarlos por nombre
    categorias = {item["name"]: item["id"] for item in cat_table.scan()["Items"]}
    tags = {item["name"]: item["id"] for item in tag_table.scan()["Items"]}

    juegos = [
        {
            "name": "Persona 5 Royal",
            "available_quantity": 10,
            "category_id": categorias.get("PlayStation 5"),
            "photo_url": "https://m.media-amazon.com/images/I/71lQbeZ5LFL.__AC_SX300_SY300_QL70_ML2_.jpg",
            "tag_ids": [tags.get("RPG"), tags.get("Visual Novel")]
        },
        {
            "name": "Final Fantasy VII Remake",
            "available_quantity": 10,
            "category_id": categorias.get("PlayStation 5"),
            "photo_url": "https://m.media-amazon.com/images/I/81W8CAno24L.__AC_SX300_SY300_QL70_ML2_.jpg",
            "tag_ids": [tags.get("RPG")]
        },
        {
            "name": "Resident Evil 4 Remake",
            "available_quantity": 10,
            "category_id": categorias.get("PlayStation 5"),
            "photo_url": "https://m.media-amazon.com/images/I/71X0kpkEnML.__AC_SX300_SY300_QL70_ML2_.jpg",
            "tag_ids": [tags.get("Action"), tags.get("Shooter")]
        },
        {
            "name": "Hogwarts Legacy",
            "available_quantity": 34,
            "category_id": categorias.get("PlayStation 5"),
            "photo_url": "https://m.media-amazon.com/images/I/811m+JsGAzL._AC_SX679_.jpg",
            "tag_ids": [tags.get("Action"), tags.get("RPG")]
        },
        {
            "name": "Metaphor ReFantazio",
            "available_quantity": 1,
            "category_id": categorias.get("PlayStation 5"),
            "photo_url": "https://m.media-amazon.com/images/I/71sKdPyDA+L._AC_SL1157_.jpg",
            "tag_ids": [tags.get("RPG"), tags.get("Visual Novel")]
        }
    ]

    for juego in juegos:
        juego["id"] = str(uuid.uuid4())
        game_table.put_item(Item=juego)
    print("Juegos insertados")

if __name__ == "__main__":
    seed_categories()
    seed_tags()
    seed_users()
    seed_games()
    print("Seed completado")