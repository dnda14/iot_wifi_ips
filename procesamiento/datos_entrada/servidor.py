from flask import Flask, request, jsonify

from procesamiento_escaneos import procesar_escaneo
from validacion_escaneos import EscaneoInvalido, validar_escaneo

app = Flask(__name__)


@app.route("/api/v1/scans", methods=["POST"])
def recibir_escaneo():
    datos = request.get_json(silent=True)
    try:
        validar_escaneo(datos)
    except EscaneoInvalido as error:
        return jsonify({"error": str(error)}), 400

    predictor = app.config.get("PREDICTOR")
    repositorio = app.config.get("REPOSITORIO_ESCANEOS")
    if predictor is None or repositorio is None:
        return jsonify({"error": "Procesamiento de escaneos no disponible"}), 503

    try:
        prediccion = procesar_escaneo(datos, predictor, repositorio)
    except Exception:
        app.logger.exception("Error al procesar o guardar el escaneo")
        return jsonify({"error": "Procesamiento de escaneos no disponible"}), 503

    return jsonify({
        "scan_id": datos["scan_id"],
        "status": "processed",
        "prediction": prediccion,
    }), 201


@app.route("/api/mediciones", methods=["POST"])
def recibir_mediciones():
    datos = request.get_json(silent=True)

    if not isinstance(datos, dict):
        return jsonify({"error": "JSON invalido"}), 400

    mediciones = datos.get("mediciones")

    if not isinstance(mediciones, list):
        return jsonify({"error": "Faltan mediciones"}), 400

    print("Datos recibidos:", datos)

    # Aqui conectaremos tu algoritmo k-NN.
    return jsonify({
        "estado": "recibido",
        "cantidad": len(mediciones)
    }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)