import os
import sys
from pathlib import Path

# ANSI escape codes for modern, colorized Windows Terminal styling
CLR_SUCCESS = "\033[1;92m"  # Bold Light Green
CLR_ERROR = "\033[1;91m"    # Bold Light Red
CLR_WARNING = "\033[93m"    # Yellow
CLR_INFO = "\033[94m"       # Light Blue
CLR_MUTED = "\033[90m"      # Grey
CLR_RESET = "\033[0m"       # Reset color
CLR_BOLD = "\033[1m"        # Bold text

# Enable ANSI escape processing on Windows Command Prompt / Powershell natively
if os.name == 'nt':
    os.system('')

def register_repi_extension():
    """Natively associates .repi files with this runner in the Windows Registry (Current User).
    This forces them to execute inline inside your active terminal window rather than spawning new popups.
    """
    if os.name != 'nt':
        print(f"{CLR_ERROR}Native system terminal association is only supported on Windows.{CLR_RESET}")
        return False
    
    import winreg
    try:
        # Get active python execution path
        python_exe = sys.executable
        if python_exe.endswith("pythonw.exe"):
            python_exe = python_exe.replace("pythonw.exe", "python.exe")
            
        script_path = os.path.abspath(__file__)
        
        # 1. Create .repi extension mapping to repi_file using robust SetValueEx
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.repi") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "repi_file")
            
        # 2. Define action to run with powershell.exe -NoExit so it stays open in the shell
        command_path = r"Software\Classes\repi_file\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_path) as key:
            # We wrap the python execution in powershell -NoExit.
            # This ensures double-clicking opens a native PowerShell window, runs the script,
            # prints the success banner, and stays open in the active shell without exiting or needing prompts!
            command_string = f'powershell.exe -NoExit -Command "& \\"{python_exe}\\" \\"{script_path}\\" \\"%1\\""'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command_string)
            
        print(f"\n{CLR_SUCCESS}NATIVE TERMINAL REGISTRATION SUCCESSFUL!{CLR_RESET}")
        print(f"{CLR_INFO}Engine Associated To:{CLR_RESET} {python_exe}")
        print(f"You can now double-click any `.repi` file in Windows Explorer to open it in a PowerShell terminal!")
        return True
    except Exception as e:
        print(f"\n{CLR_ERROR}REGISTRATION ERROR:{CLR_RESET} Could not write registry keys.\n{str(e)}\n")
        return False

def unregister_repi_extension():
    """Removes the .repi file extension associations cleanly from the Windows Registry."""
    if os.name != 'nt':
        print(f"{CLR_ERROR}Native system terminal association is only supported on Windows.{CLR_RESET}")
        return False
    
    import winreg
    
    # We must delete keys from the most nested/deepest level upward (bottom-up)
    keys_to_delete = [
        r"Software\Classes\repi_file\shell\open\command",
        r"Software\Classes\repi_file\shell\open",
        r"Software\Classes\repi_file\shell",
        r"Software\Classes\repi_file",
        r"Software\Classes\.repi"
    ]
    
    print(f"\n{CLR_INFO}Removing registry associations...{CLR_RESET}")
    success = True
    for key_path in keys_to_delete:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            # Already deleted or didn't exist, which is fine
            pass
        except Exception as e:
            print(f"{CLR_WARNING}Could not delete registry key '{key_path}': {str(e)}{CLR_RESET}")
            success = False
            
    if success:
        print(f"\n{CLR_SUCCESS}NATIVE TERMINAL REGISTRATION SUCCESSFULLY REMOVED!{CLR_RESET}")
        print("Your system will no longer open `.repi` files with this environment script.")
        return True
    else:
        print(f"\n{CLR_WARNING}Cleanup finished with potential warnings.{CLR_RESET}\n")
        return False

def load_repi_file(filepath):
    """Validates the file extension, cleans potential path wrapper quotes, and streams content."""
    # Strip double and single quotes that Windows or PowerShell wraps around paths
    filepath = filepath.strip('"\'')
    filename = os.path.basename(filepath)
    
    # Strict validation: ONLY .repi extension allowed
    if not filepath.lower().endswith(".repi"):
        print(f"\n{CLR_ERROR}CRITICAL VALIDATION ERROR{CLR_RESET}")
        print(f"{CLR_WARNING}Rejected File: '{filename}'{CLR_RESET}")
        print(f"The system was instructed to ONLY open files containing the official '.repi' file extension.\n")
        return False

    if not os.path.exists(filepath):
        print(f"\n{CLR_ERROR}FILE NOT FOUND ERROR:{CLR_RESET} The file '{filepath}' does not exist.\n")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Print the success banner directly to the Windows Terminal
        print(f"\n{CLR_SUCCESS}.repi FILE SUCCESSFULLY OPENED{CLR_RESET}")
        print(f"{CLR_INFO}Loaded Path:{CLR_RESET} {os.path.abspath(filepath)}")
        print(f"{CLR_MUTED}" + "=" * 60 + f"{CLR_RESET}")
        
        if content.strip() == "":
            print(f"{CLR_WARNING}[Notice] The target script is currently empty.{CLR_RESET}")
        else:
            # Output raw contents
            print(content)
            
        print(f"{CLR_MUTED}" + "=" * 60 + f"{CLR_RESET}\n")
        return True

    except Exception as e:
        print(f"\n{CLR_ERROR}FILE READ ERROR:{CLR_RESET} Unable to parse file contents.\n{str(e)}\n")
        return False

def main():
    try:
        # 1. Check for command-line setup registration argument
        if len(sys.argv) > 1 and sys.argv[1] == "--register":
            register_repi_extension()
            return
            
        # 1b. Check for command-line unregistration argument
        if len(sys.argv) > 1 and sys.argv[1] == "--unregister":
            unregister_repi_extension()
            return

        # 2. Check if a script path was passed directly via command-line argument
        if len(sys.argv) > 1:
            target_file = sys.argv[1]
            load_repi_file(target_file)
            # Clean exit to immediately release terminal session back to user (No prompts!)
            return
                
        # 3. Print utility help information and exit immediately (NO interactive fallback input)
        else:
            print(f"{CLR_BOLD}[REPI RUNTIME TERMINAL]{CLR_RESET} Engine environment active.")
            print(f"{CLR_INFO}Ready to stream a file...{CLR_RESET}")
            print(f"\n{CLR_BOLD}How to integrate with your active console window:{CLR_RESET}")
            print(f"  1. Register the native file extension:")
            print(f"     {CLR_BOLD}python repi_ide.py --register{CLR_RESET}")
            print(f"  2. Remove/Unregister the file extension:")
            print(f"     {CLR_BOLD}python repi_ide.py --unregister{CLR_RESET}")
            print(f"  3. Run any file inline in your current terminal session:")
            print(f"     {CLR_BOLD}.\\your_script.repi{CLR_RESET}")
            print(f"  4. Alternatively, pass the path directly to Python:")
            print(f"     {CLR_BOLD}python repi_ide.py your_script.repi{CLR_RESET}\n")
                
    except Exception as e:
        print(f"\n{CLR_ERROR}FATAL ERROR IN RUNNER WORKSPACE:{CLR_RESET} {str(e)}\n")

if __name__ == "__main__":
    main()
