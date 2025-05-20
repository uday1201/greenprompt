import os
from greenprompt.sysUsage import get_system_info
from greenprompt.dbconn import init_db

def sanitize_key(key):
    """
    Sanitize keys to make them valid Python variable names.
    Replaces spaces and special characters with underscores.
    """
    return key.upper().replace(" ", "_").replace("(", "").replace(")", "")

def main():
    # Get system information
    system_info = get_system_info()

    # Initialize the database and create tables
    init_db()

    # Save system information to constants.py
    constants_py_path = os.path.join(os.getcwd(), "constants.py")
    with open(constants_py_path, "w") as py_file:
        py_file.write("# Auto-generated constants file\n")
        for key, value in system_info.items():
            sanitized_key = sanitize_key(key)
            py_file.write(f"{sanitized_key} = {repr(value)}\n")
    print(f"✅ System information saved to {constants_py_path}")

if __name__ == "__main__":
    main()