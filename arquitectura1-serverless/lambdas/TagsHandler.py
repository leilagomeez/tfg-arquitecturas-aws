import json
import boto3

dynamodb   = boto3.resource("dynamodb")
tags_table = dynamodb.Table("tags")

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    path        = event.get("path", "")
    method      = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    # GET /tags
    if method == "GET" and path == "/tags":
        return get_tags()

    # GET /tags/{IdTag}
    if method == "GET" and "/tags/" in path:
        id_tag = path_params.get("IdTag") or path.split("/tags/")[-1]
        return get_tag(id_tag)

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


def get_tags():
    """Devuelve todos los tags de DynamoDB."""
    try:
        resultado = tags_table.scan()
        tags      = resultado.get("Items", [])
        return respuesta(200, tags)
    except Exception as e:
        return respuesta(500, {"error": f"Error al leer tags: {str(e)}"})


def get_tag(id_tag):
    """Devuelve un tag por su id o 404 si no existe."""
    try:
        resultado = tags_table.get_item(Key={"id": id_tag})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    tag = resultado.get("Item")
    if not tag:
        return respuesta(404, {"error": f"Tag '{id_tag}' no encontrado"})

    return respuesta(200, tag)


def respuesta(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,OPTIONS"
        },
        "body": json.dumps(body)
    }