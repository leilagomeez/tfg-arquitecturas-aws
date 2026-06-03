import json
import boto3

dynamodb     = boto3.resource("dynamodb")
tareas_table = dynamodb.Table("tareas")

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    # ── Trigger desde SQS RespuestaPedidos ──────────────────────────────────
    if "Records" in event and event["Records"][0].get("eventSource") == "aws:sqs":
        for record in event["Records"]:
            procesar_respuesta(record)
        return {"statusCode": 200}

    # ── Trigger desde API Gateway ────────────────────────────────────────────
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    if method == "GET" and "/tareas/" in path:
        id_tarea = event["pathParameters"]["IdTarea"]
        return get_tarea(id_tarea)

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
    return respuesta(400, {"error": "Ruta no reconocida"})


def procesar_respuesta(record):
    """Recibe un mensaje de RespuestaPedidos y guarda el estado en DynamoDB."""
    attrs               = record.get("messageAttributes", {})
    correlation_id_attr = attrs.get("CorrelationId", {})
    id_tarea = (
        correlation_id_attr.get("stringValue") or
        correlation_id_attr.get("StringValue")
    )
    body = json.loads(record["body"])

    if not id_tarea:
        print("WARN: mensaje sin CorrelationId, ignorado")
        return

    if body.get("ok"):
        item = {
            "id":       id_tarea,
            "estado":   "terminada",
            "idPedido": body["idPedido"],
            "error":    None
        }
        print(f"Tarea {id_tarea} terminada → pedido {body['idPedido']}")
    else:
        item = {
            "id":       id_tarea,
            "estado":   "terminada_con_error",
            "idPedido": None,
            "error":    body.get("error", "Error desconocido")
        }
        print(f"Tarea {id_tarea} terminada con error: {body.get('error')}")

    try:
        tareas_table.put_item(Item=item)
        print(f"Tarea {id_tarea} guardada en DynamoDB")
    except Exception as e:
        print(f"ERROR al guardar tarea en DynamoDB: {str(e)}")


def get_tarea(id_tarea):
    """Busca la tarea en DynamoDB y devuelve su estado."""
    try:
        resultado = tareas_table.get_item(Key={"id": id_tarea})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    tarea = resultado.get("Item")

    # Si no está en DynamoDB todavía, el pedido sigue en proceso
    if not tarea:
        return respuesta(200, {
            "idTarea": id_tarea,
            "estado":  "en_proceso"
        })

    if tarea["estado"] == "terminada":
        return respuesta(200, {
            "idTarea":   id_tarea,
            "estado":    "terminada",
            "urlPedido": f"/pedidos/{tarea['idPedido']}"
        })

    return respuesta(200, {
        "idTarea": id_tarea,
        "estado":  "terminada_con_error",
        "error":   tarea["error"]
    })


def respuesta(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
        },
        "body": json.dumps(body)
    }