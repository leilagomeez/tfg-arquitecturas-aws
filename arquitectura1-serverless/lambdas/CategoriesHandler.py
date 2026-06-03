import json
import boto3

dynamodb         = boto3.resource("dynamodb")
categories_table = dynamodb.Table("categories")

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    path        = event.get("path", "")
    method      = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    # GET /categories
    if method == "GET" and path == "/categories":
        return get_categories()

    # GET /categories/{IdCategory}
    if method == "GET" and "/categories/" in path:
        id_category = path_params.get("IdCategory") or path.split("/categories/")[-1]
        return get_category(id_category)

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


def get_categories():
    """Devuelve todas las categorías de DynamoDB."""
    try:
        resultado   = categories_table.scan()
        categories  = resultado.get("Items", [])
        return respuesta(200, categories)
    except Exception as e:
        return respuesta(500, {"error": f"Error al leer categorías: {str(e)}"})


def get_category(id_category):
    """Devuelve una categoría por su id o 404 si no existe."""
    try:
        resultado = categories_table.get_item(Key={"id": id_category})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    category = resultado.get("Item")
    if not category:
        return respuesta(404, {"error": f"Categoría '{id_category}' no encontrada"})

    return respuesta(200, category)


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