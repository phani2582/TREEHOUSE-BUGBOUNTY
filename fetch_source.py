import os
import json
import requests
import sys

API_KEY = "XKF2VG9FAP1EM72YYEUGGW997H5QDU8545"

if len(sys.argv) != 2:
    print("Usage: python fetch_source.py <contract_address>")
    sys.exit(1)

address = sys.argv[1]

url = (
    f"https://api.etherscan.io/v2/api"
    f"?chainid=1"
    f"&module=contract"
    f"&action=getsourcecode"
    f"&address={address}"
    f"&apikey={API_KEY}"
)

resp = requests.get(url)
resp.raise_for_status()

data = resp.json()

if data["status"] != "1":
    print(data)
    sys.exit(1)

result = data["result"][0]

print("Contract:", result["ContractName"])
print("Compiler:", result["CompilerVersion"])

source = result["SourceCode"]

# Remove Etherscan's outer braces if present
if source.startswith("{{") and source.endswith("}}"):
    source = source[1:-1]

# Multi-file Standard JSON
if source.strip().startswith("{"):
    source_json = json.loads(source)

    sources = source_json["sources"]

    for path, info in sources.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(info["content"])

    print(f"\nExtracted {len(sources)} source files.")

# Single-file verification
else:
    filename = result["ContractName"] + ".sol"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(source)

    print("Downloaded:", filename)