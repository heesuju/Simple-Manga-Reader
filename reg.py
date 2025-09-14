import sys
import os
import winreg

python_exe = sys.executable
script_path = os.path.abspath("main.py")  # adjust if needed
menu_name = "View in Manga Reader"

key_path = r"Directory\shell\{}".format(menu_name)
background_path = r"Directory\Background\shell\{}".format(menu_name)
background_cmd_path = background_path + r"\command"
command_path = key_path + r"\command"
command_value = f'"{python_exe}" "{script_path}" "%V"'

try:
    # Create or open menu key
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_name)

    # Create or open command key
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, command_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command_value)

    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, background_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_name)

    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, background_cmd_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command_value)

    print(f"✅ Right-click menu '{menu_name}' added/updated successfully!")
except PermissionError:
    print("❌ Permission denied! Run this script as Administrator.")