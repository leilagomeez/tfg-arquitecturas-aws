import json
import os
import boto3

sqs          = boto3.client("sqs")
dynamodb     = boto3.resource("dynamodb")
orders_table = dynamodb.Table("orders")

CREACION_QUEUE_URL = os.environ["CREACION_QUEUE_URL"]

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    path        = event.get("path", "")
    method      = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    # GET /pedidos
    if method == "GET" and path == "/pedidos":
        return get_pedidos()

    # POST /pedidos
    if method == "POST" and path == "/pedidos":
        return post_pedido(event)

    # GET /pedidos/{IdPedido}
    if method == "GET" and "/pedidos/" in path:
        id_pedido = path_params.get("IdPedido") or path.split("/pedidos/")[-1]
        return get_pedido(id_pedido)

    # PUT /pedidos/{IdPedido}
    if method == "PUT" and "/pedidos/" in path:
        id_pedido = path_params.get("IdPedido") or path.split("/pedidos/")[-1]
        return put_pedido(id_pedido, event)

    # DELETE /pedidos/{IdPedido}
    if method == "DELETE" and "/pedidos/" in path:
        id_pedido = path_params.get("IdPedido") or path.split("/pedidos/")[-1]
        return delete_pedido(id_pedido)

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


def get_pedidos():
    """Devuelve todos los pedidos de DynamoDB."""
    try:
        resultado = orders_table.scan()
        pedidos   = resultado.get("Items", [])
        return respuesta(200, {"pedidos": [ordenar_pedido(p) for p in pedidos]})
    except Exception as e:
        return respuesta(500, {"error": f"Error al leer pedidos: {str(e)}"})


def post_pedido(event):
    """Valida el body y encola el pedido en SQS."""
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    for campo in ["games", "user", "address"]:
        if campo not in body:
            return respuesta(400, {"error": f"Campo obligatorio ausente: '{campo}'"})

    if not isinstance(body["games"], list) or len(body["games"]) == 0:
        return respuesta(400, {"error": "El campo 'games' debe ser una lista no vacía"})

    body.setdefault("status", "pending")

    try:
        r = sqs.send_message(
            QueueUrl=CREACION_QUEUE_URL,
            MessageBody=json.dumps(body)
        )
    except Exception as e:
        return respuesta(500, {"error": f"Error al encolar el pedido: {str(e)}"})

    id_tarea = r["MessageId"]
    print(f"Pedido encolado. IdTarea: {id_tarea}")

    return respuesta(202, {
        "tarea": {
            "idTarea": id_tarea,
            "estado":  "en_proceso",
            "link":    f"/tareas/{id_tarea}"
        }
    })


def get_pedido(id_pedido):
    """Devuelve un pedido por su id o 404 si no existe."""
    try:
        resultado = orders_table.get_item(Key={"id": id_pedido})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    pedido = resultado.get("Item")
    if not pedido:
        return respuesta(404, {"error": f"Pedido '{id_pedido}' no encontrado"})

    return respuesta(200, ordenar_pedido(pedido))


def put_pedido(id_pedido, event):
    """Actualiza status y address de un pedido existente."""
    # Verificar que existe
    try:
        resultado = orders_table.get_item(Key={"id": id_pedido})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Pedido '{id_pedido}' no encontrado"})

    # Parsear body
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    # Validar que venga al menos uno de los campos actualizables
    if "status" not in body and "address" not in body:
        return respuesta(400, {"error": "Se requiere al menos 'status' o 'address' para actualizar"})

    # Construir expresión de actualización dinámicamente
    update_expr   = "SET "
    expr_names    = {}
    expr_values   = {}
    parts         = []

    if "status" in body:
        parts.append("#st = :st")
        expr_names["#st"]  = "status"
        expr_values[":st"] = body["status"]

    if "address" in body:
        parts.append("#ad = :ad")
        expr_names["#ad"]  = "address"
        expr_values[":ad"] = body["address"]

    update_expr += ", ".join(parts)

    try:
        resultado = orders_table.update_item(
            Key={"id": id_pedido},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
            ReturnValues="ALL_NEW"
        )
    except Exception as e:
        return respuesta(500, {"error": f"Error al actualizar en DynamoDB: {str(e)}"})

    return respuesta(200, ordenar_pedido(resultado["Attributes"]))


def delete_pedido(id_pedido):
    """Elimina un pedido por su id."""
    # Verificar que existe
    try:
        resultado = orders_table.get_item(Key={"id": id_pedido})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Pedido '{id_pedido}' no encontrado"})

    try:
        orders_table.delete_item(Key={"id": id_pedido})
    except Exception as e:
        return respuesta(500, {"error": f"Error al eliminar en DynamoDB: {str(e)}"})

    return respuesta(204, {})

def ordenar_pedido(pedido):
    return {
        "id":      pedido.get("id"),
        "games":   pedido.get("games"),
        "user":    pedido.get("user"),
        "address": pedido.get("address"),
        "status":  pedido.get("status")
    }

def respuesta(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        },
        "body": json.dumps(body)
    }