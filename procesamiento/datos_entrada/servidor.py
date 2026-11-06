from flask import Flask, request, jsonify

app = Flask(__name__)

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