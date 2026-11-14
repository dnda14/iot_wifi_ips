
import csv
import math
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
BASE = Path(__file__).resolve().parent
ARCHIVO_FP = BASE / "fingerprint.csv"

RSSI_AUSENTE = -100
ultima_posicion = None

# Distribucion esquematica de cada salon
PUNTOS = {
    1: (0, 2), 2: (1, 2), 3: (2, 2),
    4: (0, 1), 5: (1, 1), 6: (2, 1),
    7: (0, 0), 8: (1, 0), 9: (2, 0),
    10: (2, -1), 11: (1, -1), 12: (0, -1)
}

# Desplazamiento horizontal para evitar que los
# salones se superpongan en el mapa.
DESPLAZAMIENTO = {
    "301": 0,
    "Lab 3": 4,
    "Lab 4": 8
}

def cargar_fingerprints():
    if not ARCHIVO_FP.exists():
        raise FileNotFoundError(
            f"No existe {ARCHIVO_FP}"
        )

    with ARCHIVO_FP.open(
        encoding="utf-8-sig", newline=""
    ) as archivo:
        lector = csv.DictReader(archivo)
        columnas = lector.fieldnames or []

        bssids = [
            c for c in columnas
            if c.count(":") == 5
        ]

        referencias = []
        for fila in lector:
            try:
                punto = int(fila["punto"])
                salon = fila["salon"].strip()

                senales = {
                    b: float(fila[b])
                    for b in bssids
                    if fila.get(b)
                }

                referencias.append({
                    "salon": salon,
                    "punto": punto,
                    "senales": senales
                })
            except (ValueError, KeyError):
                continue

    return referencias, bssids


def estimar_ubicacion(mediciones):
    referencias, bssids = cargar_fingerprints()

    actuales = {}
    for m in mediciones:
        try:
            bssid = m["bssid"].strip().lower()
            actuales[bssid] = float(m["rssi_dbm"])
        except (KeyError, ValueError, AttributeError, TypeError):
            continue

    vecinos = []

    for ref in referencias:
        diferencias = []

        for bssid in bssids:
            actual = actuales.get(bssid, RSSI_AUSENTE)
            referencia = ref["senales"].get(
                bssid, RSSI_AUSENTE
            )

            if (actual != RSSI_AUSENTE and
                    referencia != RSSI_AUSENTE):
                diferencias.append(
                    (actual - referencia) ** 2
                )

        if diferencias:
            distancia = math.sqrt(
                sum(diferencias) / len(diferencias)
            )
            vecinos.append((distancia, ref))

    if not vecinos:
        return None

    vecinos.sort(key=lambda v: v[0])

    votos = {}
    for distancia, ref in vecinos[:3]:
        clave = (ref["salon"], ref["punto"])
        votos[clave] = votos.get(clave, 0) + (
            1 / (distancia + 0.001)
        )

    salon, punto = max(votos, key=votos.get)

    if salon not in DESPLAZAMIENTO or punto not in PUNTOS:
        return None

    x_local, y = PUNTOS[punto]
    x = x_local + DESPLAZAMIENTO[salon]

    return {
        "salon": salon,
        "punto": punto,
        "x": x,
        "y": y,
        "zona": "pasillo" if punto >= 10 else "interior"
    }


@app.route("/api/mediciones", methods=["POST"])
def recibir():
    global ultima_posicion

    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"error": "JSON invalido"}), 400

    mediciones = datos.get("mediciones")
    if not isinstance(mediciones, list):
        return jsonify({"error": "Faltan mediciones"}), 400

    try:
        posicion = estimar_ubicacion(mediciones)
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 500

    if posicion is None:
        return jsonify({
            "error": "No hay senales suficientes"
        }), 422

    ultima_posicion = posicion
    print("Ubicacion estimada:", posicion)

    return jsonify({
        "estado": "localizado",
        "ubicacion": posicion
    })


@app.route("/api/ubicacion")
def ubicacion():
    return jsonify(ultima_posicion or {})


HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPS Hospitalario</title>
<style>
body {
  font-family: Arial, sans-serif;
  background: #f3f6fb;
  margin: 0;
  padding: 24px;
  text-align: center;
}
h1 { color: #172d4d; }
.panel {
  max-width: 850px;
  margin: auto;
  padding: 20px;
  background: white;
  border-radius: 16px;
}
svg { width: 100%; height: auto; }
.room {
  fill: #e8f0fb;
  stroke: #5073a3;
  stroke-width: 2;
}
.corridor { fill: #e4f5ed; }
.point { fill: #7890ad; }
.marker {
  fill: #e63946;
  stroke: white;
  stroke-width: 3;
}
</style>
</head>
<body>
<div class="panel">
<h1>IPS Hospitalario - UNSA</h1>
<p id="estado">Esperando mediciones del celular...</p>

<svg viewBox="0 0 850 360">
  <rect x="25" y="40" width="250" height="230"
        class="room"/>
  <rect x="300" y="40" width="250" height="230"
        class="room"/>
  <rect x="575" y="40" width="250" height="230"
        class="room"/>

  <text x="150" y="65" text-anchor="middle">301</text>
  <text x="425" y="65" text-anchor="middle">Lab 3</text>
  <text x="700" y="65" text-anchor="middle">Lab 4</text>

  <rect x="25" y="275" width="800" height="70"
        class="corridor"/>
  <text x="425" y="337" text-anchor="middle">
    PASILLO
  </text>

  <g id="puntos"></g>
  <circle id="persona" class="marker"
          r="12" cx="-50" cy="-50"/>
</svg>

<h2 id="ubicacion">Sin ubicación disponible</h2>
</div>

<script>
const centros = [150, 425, 700];
const nombres = ["301", "Lab 3", "Lab 4"];
const posiciones = {
  1:[-75,0], 2:[0,0], 3:[75,0],
  4:[-75,70], 5:[0,70], 6:[75,70],
  7:[-75,140], 8:[0,140], 9:[75,140],
  12:[-75,210], 11:[0,210], 10:[75,210]
};

const grupo = document.getElementById("puntos");
for (let i = 0; i < 3; i++) {
  for (const [numero, pos] of Object.entries(posiciones)) {
    const x = centros[i] + pos[0];
    const y = 105 + pos[1];

    const circulo = document.createElementNS(
      "http://www.w3.org/2000/svg", "circle"
    );
    circulo.setAttribute("cx", x);
    circulo.setAttribute("cy", y);
    circulo.setAttribute("r", 5);
    circulo.setAttribute("class", "point");
    grupo.appendChild(circulo);
  }
}

async function actualizar() {
  try {
    const respuesta = await fetch("/api/ubicacion");
    const p = await respuesta.json();

    if (!p.salon || !posiciones[p.punto]) {
      return;
    }

    const indice = nombres.indexOf(p.salon);
    if (indice < 0) return;

    const pos = posiciones[p.punto];
    const x = centros[indice] + pos[0];
    const y = 105 + pos[1];

    document.getElementById("persona")
      .setAttribute("cx", x);
    document.getElementById("persona")
      .setAttribute("cy", y);

    document.getElementById("ubicacion").textContent =
      p.salon + " - Punto " + p.punto;

    document.getElementById("estado").textContent =
      "Última posición estimada recibida";
  } catch (error) {
    document.getElementById("estado").textContent =
      "Sin conexión con el servidor";
  }
}

setInterval(actualizar, 1500);
actualizar();
</script>
</body>
</html>
"""


@app.route("/")
def mapa():
    return render_template_string(HTML)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
