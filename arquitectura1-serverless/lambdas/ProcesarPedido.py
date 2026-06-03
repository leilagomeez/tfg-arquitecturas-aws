import json
import os
import uuid
import boto3

sqs = boto3.client("sqs")
sns = boto3.client("sns")
lambda_client = boto3.client("lambda")
dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table("orders")

RESPUESTA_QUEUE_URL = os.environ["RESPUESTA_QUEUE_URL"]
SNS_TOPIC_ARN       = os.environ["SNS_TOPIC_ARN"]
DISPONIBILIDAD_LAMBDA = os.environ["DISPONIBILIDAD_LAMBDA"]

def lambda_handler(event, context):
    print("Evento SQS recibido:", json.dumps(event))

    for record in event.get("Records", []):
        procesar_record(record)

    return {"statusCode": 200}


def procesar_record(record):
    body_str     = record.get("body", "{}")
    body         = json.loads(body_str)
    correlation_id = record.get("messageId")

    # Campos del pedido (estructura game-store)
    game_ids = body.get("games", [])      # lista de IDs de juegos
    username = body.get("user")
    address  = body.get("address")
    status   = body.get("status", "pending")

    # Validación básica
    if not game_ids or not username or not address:
        enviar_error(correlation_id, "Faltan campos obligatorios: games, user o address")
        return

    # Comprobar disponibilidad de cada juego (invocación directa Lambda)
    juegos_no_disponibles = []
    for game_id in game_ids:
        disponible, motivo = comprobar_disponibilidad(game_id)
        if not disponible:
            juegos_no_disponibles.append({"game_id": game_id, "motivo": motivo})

    if juegos_no_disponibles:
        enviar_error(
            correlation_id,
            f"Juegos sin disponibilidad: {json.dumps(juegos_no_disponibles)}"
        )
        return

    # Crear el pedido en DynamoDB
    id_pedido = str(uuid.uuid4())
    pedido = {
        "id":      id_pedido,
        "games":   game_ids,
        "user":    username,
        "address": address,
        "status":  status
    }

    try:
        orders_table.put_item(Item=pedido)
        print(f"Pedido {id_pedido} guardado en DynamoDB")
    except Exception as e:
        enviar_error(correlation_id, f"Error al guardar en DynamoDB: {str(e)}")
        return

    # Publicar respuesta en RespuestaPedidos
    respuesta = {"ok": True, "idPedido": id_pedido, "error": None}
    sqs.send_message(
        QueueUrl=RESPUESTA_QUEUE_URL,
        MessageBody=json.dumps(respuesta),
        MessageAttributes={
            "CorrelationId": {
                "StringValue": correlation_id,
                "DataType": "String"
            }
        }
    )

    # Publicar evento en SNS topic Pedidos
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps({"idPedido": id_pedido, "pedido": pedido}),
        MessageAttributes={
            "tipoMensaje": {"DataType": "String", "StringValue": "creacion"}
        }
    )

    print(f"Pedido {id_pedido} creado y publicado en SNS")


def comprobar_disponibilidad(game_id):
    """Invoca directamente λ ComprobarDisponibilidad y devuelve (bool, motivo)."""
    try:
        resp = lambda_client.invoke(
            FunctionName=DISPONIBILIDAD_LAMBDA,
            InvocationType="RequestResponse",
            Payload=json.dumps({"game_id": game_id}).encode("utf-8")
        )
        payload = json.loads(resp["Payload"].read().decode("utf-8"))
        print(f"Respuesta ComprobarDisponibilidad para {game_id}:", payload)

        if not payload.get("disponible", False):
            motivo = payload.get("error") or "Sin stock"
            return False, motivo

        return True, None

    except Exception as e:
        return False, f"Error invocando ComprobarDisponibilidad: {str(e)}"


def enviar_error(correlation_id, mensaje_error):
    """Publica un mensaje de error en RespuestaPedidos."""
    print(f"Error en pedido {correlation_id}: {mensaje_error}")
    respuesta = {"ok": False, "idPedido": None, "error": mensaje_error}
    sqs.send_message(
        QueueUrl=RESPUESTA_QUEUE_URL,
        MessageBody=json.dumps(respuesta),
        MessageAttributes={
            "CorrelationId": {
                "StringValue": correlation_id,
                "DataType": "String"
            }
        }
    )