import json

def load_server_config(server_id):
    try:
        with open(f"config_{server_id}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_server_config(server_id, config):
    with open(f"config_{server_id}.json", "w") as f:
        json.dump(config, f, indent=4)
