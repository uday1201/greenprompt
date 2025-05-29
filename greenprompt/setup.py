import os
from greenprompt.sysUsage import get_system_info
from greenprompt.dbconn import init_db
import subprocess

# Ollama URL for local server
OLLAMA_URL = "http://127.0.0.1:11434"
monitor = None


def sanitize_key(key):
    """
    Sanitize keys to make them valid Python variable names.
    Replaces spaces and special characters with underscores.
    """
    return key.upper().replace(" ", "_").replace("(", "").replace(")", "")


def check_ollama():
    """
    Check if Ollama is installed. If not, install it and return the port.
    """
    print("Checking if Ollama is installed...")
    try:
        result = subprocess.run(["ollama", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Ollama is installed: {result.stdout.strip()}")
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        print("Ollama is not installed. Installing...")
        subprocess.run(["brew", "install", "ollama"], check=True)

    # Check the port Ollama is running on
    try:
        result = subprocess.run(
            ["lsof", "-i", ":11434"], capture_output=True, text=True
        )
        if result.returncode == 0:
            print("Ollama is running on port 11434.")
        else:
            print("Ollama is not running on port 11434. Starting it...")
            subprocess.run(["ollama", "serve"], check=True)
    except Exception as e:
        print(f"Error checking or starting Ollama: {e}")


def main():
    print("Setting up GreenPrompt...")

    # Get system information
    system_info = get_system_info()

    # Run git update-index to hide constants.py
    try:
        subprocess.run(
            [
                "git",
                "update-index",
                "--no-assume-unchanged",
                "greenprompt/constants.py",
            ],
            check=True,
        )
        print("Updated git index to track changes to constants.py.")
    except Exception as e:
        print(f"Could not update git index: {e}")

    # Save system information to constants.py
    constants_py_path = os.path.join(os.getcwd(), "constants.py")
    with open(constants_py_path, "w") as py_file:
        py_file.write("# Auto-generated constants file\n")
        for key, value in system_info.items():
            sanitized_key = sanitize_key(key)
            py_file.write(f"{sanitized_key} = {repr(value)}\n")
        # Add ollama URL
        py_file.write(f"OLLAMA_URL = {repr(OLLAMA_URL)}\n")
    print(f"✅ System information saved to {constants_py_path}")

    # Check if Ollama is installed
    check_ollama()

    # Initialize the database and create tables
    init_db()


if __name__ == "__main__":
    main()
