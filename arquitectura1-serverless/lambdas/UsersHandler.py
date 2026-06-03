import json
import boto3

dynamodb    = boto3.resource("dynamodb")
users_table = dynamodb.Table("users")

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    path        = event.get("path", "")
    method      = event.get("httpMethod", "")
    path_params = event.get("pathParameters") or {}

    # GET /users
    if method == "GET" and path == "/users":
        return get_users()

    # POST /users
    if method == "POST" and path == "/users":
        return post_user(event)

    # GET /users/{username}
    if method == "GET" and "/users/" in path:
        username = path_params.get("username") or path.split("/users/")[-1]
        return get_user(username)

    # PUT /users/{username}
    if method == "PUT" and "/users/" in path:
        username = path_params.get("username") or path.split("/users/")[-1]
        return put_user(username, event)

    # DELETE /users/{username}
    if method == "DELETE" and "/users/" in path:
        username = path_params.get("username") or path.split("/users/")[-1]
        return delete_user(username)

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


def get_users():
    """Devuelve todos los usuarios de DynamoDB."""
    try:
        resultado = users_table.scan()
        users     = resultado.get("Items", [])
        # No devolvemos el campo password por seguridad
        for u in users:
            u.pop("password", None)
        return respuesta(200, [ordenar_usuario(u) for u in users])
    except Exception as e:
        return respuesta(500, {"error": f"Error al leer usuarios: {str(e)}"})


def post_user(event):
    """Crea un nuevo usuario en DynamoDB."""
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    # Validar campos obligatorios
    for campo in ["username", "first_name", "last_name", "email", "password", "phone"]:
        if campo not in body:
            return respuesta(400, {"error": f"Campo obligatorio ausente: '{campo}'"})

    username = body["username"].strip().lower()

    # Verificar que no existe ya
    try:
        resultado = users_table.get_item(Key={"username": username})
        if resultado.get("Item"):
            return respuesta(400, {"error": f"El usuario '{username}' ya existe"})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    # Crear el item
    item = {
        "username":  username,
        "first_name": body["first_name"].strip(),
        "last_name":  body["last_name"].strip(),
        "email":     body["email"].strip(),
        "password":  body["password"].strip(),
        "phone":     body["phone"].strip()
    }

    try:
        users_table.put_item(Item=item)
    except Exception as e:
        return respuesta(500, {"error": f"Error al crear usuario en DynamoDB: {str(e)}"})

    item.pop("password")
    print(f"Usuario {username} creado")
    return respuesta(200, item)


def get_user(username):
    """Devuelve un usuario por su username o 404 si no existe."""
    try:
        resultado = users_table.get_item(Key={"username": username})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    user = resultado.get("Item")
    if not user:
        return respuesta(404, {"error": f"Usuario '{username}' no encontrado"})

    user.pop("password", None)
    return respuesta(200, ordenar_usuario(user))


def put_user(username, event):
    """Actualiza los datos de un usuario existente."""
    # Verificar que existe
    try:
        resultado = users_table.get_item(Key={"username": username})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Usuario '{username}' no encontrado"})

    # Parsear body
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        return respuesta(400, {"error": "JSON inválido"})

    campos_actualizables = ["first_name", "last_name", "email", "phone"]
    parts      = []
    expr_names = {}
    expr_vals  = {}

    for campo in campos_actualizables:
        if campo in body:
            placeholder = f"#{campo}"
            value_key   = f":{campo}"
            parts.append(f"{placeholder} = {value_key}")
            expr_names[placeholder] = campo
            expr_vals[value_key]    = body[campo].strip()

    if not parts:
        return respuesta(400, {"error": "Se requiere al menos uno de: first_name, last_name, email, phone"})

    try:
        resultado = users_table.update_item(
            Key={"username": username},
            UpdateExpression="SET " + ", ".join(parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_vals,
            ReturnValues="ALL_NEW"
        )
    except Exception as e:
        return respuesta(500, {"error": f"Error al actualizar en DynamoDB: {str(e)}"})

    user = resultado["Attributes"]
    user.pop("password", None)
    return respuesta(200, ordenar_usuario(user))


def delete_user(username):
    """Elimina un usuario por su username."""
    # Verificar que existe
    try:
        resultado = users_table.get_item(Key={"username": username})
    except Exception as e:
        return respuesta(500, {"error": f"Error al consultar DynamoDB: {str(e)}"})

    if not resultado.get("Item"):
        return respuesta(404, {"error": f"Usuario '{username}' no encontrado"})

    try:
        users_table.delete_item(Key={"username": username})
    except Exception as e:
        return respuesta(500, {"error": f"Error al eliminar en DynamoDB: {str(e)}"})

    return respuesta(204, {})


def ordenar_usuario(user):
    return {
        "username":   user.get("username"),
        "first_name": user.get("first_name"),
        "last_name":  user.get("last_name"),
        "email":      user.get("email"),
        "phone":      user.get("phone")
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