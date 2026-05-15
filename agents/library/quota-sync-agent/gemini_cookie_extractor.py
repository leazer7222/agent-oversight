import os
import json
import base64
import sqlite3
import shutil
from datetime import datetime, timedelta
import win32crypt
from Crypto.Cipher import AES

def get_encryption_key():
    local_state_path = os.path.join(os.environ["USERPROFILE"],
                                    "AppData", "Local", "Google", "Chrome",
                                    "User Data", "Local State")
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = f.read()
        local_state = json.loads(local_state)

    # Decode the encryption key from Base64
    key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    # Remove 'DPAPI' prefix
    key = key[5:]
    # Decrypt the key using Windows Data Protection API
    return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]

def decrypt_data(data, key):
    try:
        # Get the initialization vector
        iv = data[3:15]
        data = data[15:]
        # Generate cipher
        cipher = AES.new(key, AES.MODE_GCM, iv)
        # Decrypt and decode object
        return cipher.decrypt(data)[:-16].decode()
    except Exception as e:
        print(f"Decryption failed: {e}")
        return ""

def get_cookies(host_search="aistudio.google.com"):
    # Path to the Cookies database
    db_path = os.path.join(os.environ["USERPROFILE"], "AppData", "Local",
                           "Google", "Chrome", "User Data", "Default", "Network", "Cookies")
    
    # Copy the database to a temporary file (Chrome locks it)
    temp_db = "temp_cookies.db"
    # Use cmd /c copy to bypass some locking issues
    os.system(f'cmd /c copy "{db_path}" "{temp_db}" > nul')
    
    if not os.path.exists(temp_db):
        # Fallback to shutil if cmd fails
        shutil.copyfile(db_path, temp_db)
    
    key = get_encryption_key()
    db = sqlite3.connect(temp_db)
    cursor = db.cursor()
    
    # Query for cookies
    cursor.execute(f"SELECT host_key, name, value, encrypted_value FROM cookies WHERE host_key LIKE '%{host_search}%'")
    
    cookies = {}
    for host_key, name, value, encrypted_value in cursor.fetchall():
        if not value:
            decrypted_value = decrypt_data(encrypted_value, key)
        else:
            decrypted_value = value
        cookies[name] = decrypted_value
        
    db.close()
    os.remove(temp_db)
    return cookies

if __name__ == "__main__":
    try:
        cookies = get_cookies()
        print(json.dumps(cookies, indent=2))
    except Exception as e:
        print(f"Error: {e}")
