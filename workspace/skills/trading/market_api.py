import requests
import json
import sys

def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,eur"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_fear_greed():
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "price"
    
    if cmd == "price":
        print(json.dumps(get_btc_price()))
    elif cmd == "fng":
        print(json.dumps(get_fear_greed()))
    else:
        print(json.dumps({"error": "Unknown command"}))
