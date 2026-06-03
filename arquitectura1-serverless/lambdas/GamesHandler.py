import json
import uuid
import boto3
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)

dynamodb         = boto3.resource("dynamodb")
games_table      = dynamodb.Table("games")
categories_table = dynamodb.Table("categories")
tags_table       = dynamodb.Table("tags")

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    path        = event.get("path", "")
    method      = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    # GET /games
    if method == "GET" and path == "/games":
        return get_games()

    # POST /games
    if method == "POST" and path == "/games":
        return post_game(event)

    # GET /games/{IdGame}
    if method == "GET" and "/games/" in path:
        id_game = path_params.get("IdGame") or path.split("/games/")[-1]
        return get_game(id_game)

    # PUT /games/{IdGame}
    if method == "PUT" and "/games/" in path:
        id_game = path_params.get("IdGame") or path.split("/games/")[-1]
        return put_game(id_game, event)

    # DELETE /games/{IdGame}
    if method == "DELETE" and "/games/" in path:
        id_game = path_params.get("IdGame") or path.split("/games/")[-1]
        return delete_game(id_game)

    # OPTIONS (CORS preflight)
    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
            },
            "body": ""
        }
    return respuesta(404, {"error": "Ruta no encontrada"})


def resolver_categoria(category_name):
    """Busca una categoría por nombre y devuelve el item completo."""
    resultado = categories_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("name").eq(category_name)
    )
    items = resultado.get("Items", [])
    if not items:
        return None
    return items[0]


def resolver_tag(tag_name):
    """Busca un tag por nombre y devuelve el item completo."""
    resultado = tags_table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("name").eq(tag_name)
    )
    items = resultado.get("Items", [])
    if not items:
        return None
    return items[0]


def enriquecer_game(game):
    """Dado un item de DynamoDB, resuelve category_id y tag_ids a objetos completos."""
    # Resolver categoría
    if "category_id" in game:
        cat = categories_table.get_item(Key={"id": game["category_id"]}).get("Item")
        game["category"] = cat if cat else {"id": game["category_id"]}
        del game["category_id"]

    # Resolver tags
    if "tag_ids" in game:
        tags = []
        for tag_id in game["tag_ids"]:
            tag = tags_table.get_item(Key={"id": tag_id}).get("Item")
            if tag:
                tags.append(tag)
        game["tags"] = tags
        del game["tag_ids"]

    return {
        "id":                 game.get("id"),
        "name":               game.get("name"),
        "available_quantity": game.get("available_quantity"),
        "category":           game.get("category"),
        "photo_url":          game.get("photo_url"),
        "tags":               game.get("tags")
    }


def get_games():
    """Devuelve todos los juegos con categoría y tags resueltos."""
    try:
        resultado = games_table.scan()
        games     = resultado.get("Items", [])
        games     = [enriquecer_game(g) for g in games]
        return respuesta(200, games)
    except Exception as e:
        return respuesta(500, {"error": f"Error al leer juegos: {str(e)}"})


def post_game(event):
    """Crea un nuevo juego en DynamoDB."""
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    # Validar campos obligatorios
    for campo in ["name", "availableQuantity", "category", "photoUrl", "tags"]:
        if campo not in body:
            return respuesta(400, {"error": f"Campo obligatorio ausente: '{campo}'"})

    # Resolver categoría por nombre
    cat = resolver_categoria(body["category"]["name"])
    if not cat:
        return respuesta(404, {"error": f"Categoría '{body['category']['name']}' no encontrada"})

    # Resolver tags por nombre
    tag_ids = []
    for tag_data in body["tags"]:
        tag = resolver_tag(tag_data["name"])
        if not tag:
            return respuesta(404, {"error": f"Tag '{tag_data['name']}' no encontrado"})
        tag_ids.append(tag["id"])

    item = {
        "id":                 str(uuid.uuid4()),
        "name":               body["name"].strip(),
        "available_quantity": int(body["availableQuantity"]),
        "category_id":        cat["id"],
        "photo_url":          body["photoUrl"].strip(),
        "tag_ids":            tag_ids
    }

    try:
        games_table.put_item(Item=item)
    except Exception as e:
        return respuesta(500, {"error": f"Error al crear juego en DynamoDB: {str(e)}"})

    print(f"Juego {item['name']} creado con id {item['id']}")
    return respuesta(200, enriquecer_game(item))


def get_game(id_game):
    """Devuelve un juego por su id o 404 si no existe."""
    try:
        resultado = games_table.get_item(Key={"id": id_game})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    game = resultado.get("Item")
    if not game:
        return respuesta(404, {"error": f"Juego '{id_game}' no encontrado"})

    return respuesta(200, enriquecer_game(game))


def put_game(id_game, event):
    """Actualiza un juego existente."""
    # Verificar que existe
    try:
        resultado = games_table.get_item(Key={"id": id_game})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Juego '{id_game}' no encontrado"})

    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    parts      = []
    expr_names = {}
    expr_vals  = {}

    if "name" in body:
        parts.append("#nm = :nm")
        expr_names["#nm"] = "name"
        expr_vals[":nm"]  = body["name"].strip()

    if "availableQuantity" in body:
        parts.append("#aq = :aq")
        expr_names["#aq"] = "available_quantity"
        expr_vals[":aq"]  = int(body["availableQuantity"])

    if "photoUrl" in body:
        parts.append("#pu = :pu")
        expr_names["#pu"] = "photo_url"
        expr_vals[":pu"]  = body["photoUrl"].strip()

    if "category" in body:
        cat = resolver_categoria(body["category"]["name"])
        if not cat:
            return respuesta(404, {"error": f"Categoría '{body['category']['name']}' no encontrada"})
        parts.append("#ci = :ci")
        expr_names["#ci"] = "category_id"
        expr_vals[":ci"]  = cat["id"]

    if "tags" in body:
        tag_ids = []
        for tag_data in body["tags"]:
            tag = resolver_tag(tag_data["name"])
            if not tag:
                return respuesta(404, {"error": f"Tag '{tag_data['name']}' no encontrado"})
            tag_ids.append(tag["id"])
        parts.append("#ti = :ti")
        expr_names["#ti"] = "tag_ids"
        expr_vals[":ti"]  = tag_ids

    if not parts:
        return respuesta(400, {"error": "Se requiere al menos un campo para actualizar"})

    try:
        resultado = games_table.update_item(
            Key={"id": id_game},
            UpdateExpression="SET " + ", ".join(parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_vals,
            ReturnValues="ALL_NEW"
        )
    except Exception as e:
        return respuesta(500, {"error": f"Error al actualizar en DynamoDB: {str(e)}"})

    return respuesta(200, enriquecer_game(resultado["Attributes"]))


def delete_game(id_game):
    """Elimina un juego por su id."""
    try:
        resultado = games_table.get_item(Key={"id": id_game})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Juego '{id_game}' no encontrado"})

    try:
        games_table.delete_item(Key={"id": id_game})
    except Exception as e:
        return respuesta(500, {"error": f"Error al eliminar en DynamoDB: {str(e)}"})

    return respuesta(204, {})


def respuesta(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }
