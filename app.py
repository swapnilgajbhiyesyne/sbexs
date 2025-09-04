from flask import Flask, request, jsonify
import subprocess

app = Flask(__name__)

@app.route("/")
def home():
    return {"message": "BTC POP Scanner API running on Render"}

@app.route("/scan")
def scan():
    # Example: /scan?dte_max=7&prem_min=50&prem_max=100&side=puts
    args = ["python", "btc_pop_scanner.py"]

    if "dte_max" in request.args:
        args += ["--dte-max", request.args["dte_max"]]
    if "expiry" in request.args:
        args += ["--expiry", request.args["expiry"]]
    if "side" in request.args:
        args += ["--side", request.args["side"]]
    if "prem_min" in request.args:
        args += ["--prem-min", request.args["prem_min"]]
    if "prem_max" in request.args:
        args += ["--prem-max", request.args["prem_max"]]
    if "premium_in_btc" in request.args:
        args += ["--premium-in-btc"]

    result = subprocess.run(args, capture_output=True, text=True)
    return jsonify({"output": result.stdout, "errors": result.stderr})
from flask import Flask, request, jsonify
import subprocess

app = Flask(__name__)

@app.route("/")
def home():
    return {"message": "BTC POP Scanner API running on Render"}

@app.route("/scan")
def scan():
    # Example: /scan?dte_max=7&prem_min=50&prem_max=100&side=puts
    args = ["python", "btc_pop_scanner.py"]

    if "dte_max" in request.args:
        args += ["--dte-max", request.args["dte_max"]]
    if "expiry" in request.args:
        args += ["--expiry", request.args["expiry"]]
    if "side" in request.args:
        args += ["--side", request.args["side"]]
    if "prem_min" in request.args:
        args += ["--prem-min", request.args["prem_min"]]
    if "prem_max" in request.args:
        args += ["--prem-max", request.args["prem_max"]]
    if "premium_in_btc" in request.args:
        args += ["--premium-in-btc"]

    result = subprocess.run(args, capture_output=True, text=True)
    return jsonify({"output": result.stdout, "errors": result.stderr})
