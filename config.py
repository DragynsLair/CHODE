import json

def load_server_config(server_id):
    """
    Loads the server configuration from a JSON file named 'config_<server_id>.json'.
    If the file doesn't exist, returns an empty dictionary.
    """
    try:
        with open(f"config_{server_id}.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_server_config(server_id, config):
    """
    Saves the server configuration to a JSON file named 'config_<server_id>.json'.
    """
    with open(f"config_{server_id}.json", "w") as f:
        json.dump(config, f, indent=4)
