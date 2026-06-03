import json
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("games")

def lambda_handler(event, context):
    print("Evento recibido:", event)

    game_id = event.get("game_id")

    if not game_id:
        return {
            "disponible": False,
            "error": "No se proporcionó game_id"
        }

    # Buscar el juego en DynamoDB
    try:
        resultado = table.get_item(Key={"id": game_id})
    except Exception as e:
        return {
            "disponible": False,
            "error": f"Error al consultar DynamoDB: {str(e)}"
        }

    juego = resultado.get("Item")

    if not juego:
        return {
            "disponible": False,
            "error": f"Juego {game_id} no encontrado"
        }

    cantidad = int(juego.get("available_quantity", 0))
    disponible = cantidad > 0

    respuesta = {
        "game_id": game_id,
        "name": juego.get("name"),
        "available_quantity": cantidad,
        "disponible": disponible
    }

    print("Resultado disponibilidad:", respuesta)
    return respuesta