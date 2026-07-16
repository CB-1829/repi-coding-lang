import os
import sys
import re
import tkinter as tk
from tkinter import messagebox, filedialog

# Modern clean theme tokens (Pure white canvas focus)
COLOR_BG_DEFAULT = "#FFFFFF"     # White canvas background
COLOR_PRIMARY = "#0F172A"        # Deep slate text color (used if text is drawn)
COLOR_BORDER = "#E2E8F0"         # Light gray for visual borders/grid
COLOR_FALLBACK_SHAPE = "#000000" # Pure black fallback color for shapes

# Enable ANSI escape processing on Windows Command Prompt / Powershell natively (for logs)
if os.name == 'nt':
    os.system('')

def register_repi_extension():
    """Associates .repi files with this script to open the GUI window directly on double-click."""
    if os.name != 'nt':
        print("[REPI] Native system file association is only supported on Windows.")
        return False
    
    import winreg
    try:
        pythonw_exe = sys.executable
        # Use pythonw.exe to prevent the black command prompt window from flashing/showing!
        if pythonw_exe.endswith("python.exe"):
            pythonw_exe = pythonw_exe.replace("python.exe", "pythonw.exe")
            
        script_path = os.path.abspath(__file__)
        
        # 1. Map .repi extension to repi_file class
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.repi") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "repi_file")
            
        # 2. Map repi_file to launch with pythonw.exe (No console window!)
        command_path = r"Software\Classes\repi_file\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_path) as key:
            command_string = f'"{pythonw_exe}" "{script_path}" "%1"'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command_string)
            
        print("\n[SUCCESS] NATIVE DOUBLE-CLICK ASSOCIATION COMPLETED!")
        print(f"Path: {pythonw_exe}")
        print("You can now double-click any .repi file to open it directly as a GUI window!\n")
        return True
    except Exception as e:
        print(f"\n[ERROR] Could not register file association: {str(e)}\n")
        return False

def unregister_repi_extension():
    """Safely removes the .repi file association from the Windows Registry."""
    if os.name != 'nt':
        print("[REPI] Native system file association is only supported on Windows.")
        return False
    
    import winreg
    keys_to_delete = [
        r"Software\Classes\repi_file\shell\open\command",
        r"Software\Classes\repi_file\shell\open",
        r"Software\Classes\repi_file\shell",
        r"Software\Classes\repi_file",
        r"Software\Classes\.repi"
    ]
    
    print("\n[REPI] Removing file association keys...")
    success = True
    for key_path in keys_to_delete:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[WARNING] Could not delete key '{key_path}': {str(e)}")
            success = False
            
    if success:
        print("[SUCCESS] Registry association completely removed!\n")
    return success

def evaluate_math_expression(expr_str, env_vars):
    """Parses and calculates math commands (+, -, /, x, =) within variable contexts."""
    cleaned = expr_str.strip()
    
    # Do not treat valid hexadecimal colors as math expressions!
    if cleaned.startswith("#"):
        return cleaned
        
    # Replace customized variable symbols with active scope values
    for var_name, var_val in list(env_vars.items()):
        if var_name in cleaned:
            cleaned = cleaned.replace(var_name, str(var_val))
            
    # Swap our syntax 'x' multiplication flag with Python '*' multiply symbol
    cleaned = cleaned.replace('x', '*').replace('X', '*')
    
    try:
        # Calculate resulting operations safely
        result = eval(cleaned, {"__builtins__": None}, {})
        return result
    except Exception:
        return cleaned

def parse_repi_script(lines, env_vars):
    """
    Parses loose flat declarations, nested hierarchies, and lists.
    Strips out comments formatted only as @comment@.
    """
    compiled_objects = []
    current_obj = None
    current_prop = None
    current_sub_context = None

    for raw_line in lines:
        # Strip comments matching the @comment@ pattern exclusively
        line_without_comments = re.sub(r'@.*?@', '', raw_line)
        cleaned = line_without_comments.strip()
        if not cleaned:
            continue

        # Match structural start commands
        if cleaned.lower() in ("create", "build"):
            current_obj = {"type": "ui", "properties": {}}
            compiled_objects.append(("create", current_obj))
            current_prop = None
            current_sub_context = None
            continue
        elif cleaned.lower() == "edit":
            current_obj = {"type": "edit", "properties": {}}
            compiled_objects.append(("edit", current_obj))
            current_prop = None
            current_sub_context = None
            continue
        elif cleaned.lower().startswith("delete"):
            target_id = cleaned.lower().replace("delete", "").strip().strip("#").strip()
            compiled_objects.append(("delete", {"id": target_id}))
            continue
        
        # Handle variable updates
        elif "=" in cleaned and not cleaned.startswith("-") and not "[" in cleaned and not "{" in cleaned:
            parts = cleaned.split("=", 1)
            var_name = parts[0].replace("LET", "").strip()
            var_val = evaluate_math_expression(parts[1], env_vars)
            env_vars[var_name] = var_val
            continue

        # Strip any leading hyphens to parse tree parameters
        hyphen_stripped = re.sub(r'^-+', '', line_without_comments).strip()

        # Check structural layout types
        if hyphen_stripped.startswith("[") and hyphen_stripped.endswith("]"):
            block_type = hyphen_stripped[1:-1].lower()
            if block_type in ("ui", "text", "button", "image", "variable", "all_objects"):
                current_obj = {"type": block_type, "properties": {}}
                compiled_objects.append(("create", current_obj))
                current_prop = None
                current_sub_context = None
            continue

        elif hyphen_stripped.startswith("{") and hyphen_stripped.endswith("}"):
            current_prop = hyphen_stripped[1:-1].lower()
            if current_obj is not None:
                current_obj["properties"][current_prop] = []
            current_sub_context = None
            continue

        elif hyphen_stripped.startswith("(") and hyphen_stripped.endswith(")"):
            current_sub_context = hyphen_stripped[1:-1].lower()
            continue

        # Parse block and property lists (coordinate matrices, style flags, etc.)
        if current_obj is not None and current_prop is not None:
            val = evaluate_math_expression(hyphen_stripped, env_vars)
            
            # Map parameters under sub-contexts (like text color highlights)
            target_store = current_obj["properties"][current_prop]
            if current_sub_context:
                if not isinstance(target_store, dict):
                    current_obj["properties"][current_prop] = {}
                if current_sub_context not in current_obj["properties"][current_prop]:
                    current_obj["properties"][current_prop][current_sub_context] = []
                current_obj["properties"][current_prop][current_sub_context].append(val)
            else:
                if isinstance(target_store, list):
                    target_store.append(val)
                else:
                    current_obj["properties"][current_prop] = [val]

    return compiled_objects

class RepiRendererApp(tk.Tk):
    def __init__(self, script_path):
        super().__init__()
        self.script_path = script_path
        self.title(f"REPI Workspace - {os.path.basename(script_path) if script_path else 'New Script'}")
        self.geometry("800x800")
        self.configure(bg=COLOR_BG_DEFAULT)
        
        # State scopes
        self.env_vars = {}
        self.compiled_objects = []
        
        # Create full window Canvas with absolutely NO headers, sidebars, or frames
        self.canvas = tk.Canvas(
            self, 
            bg=COLOR_BG_DEFAULT, 
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind hotkeys for lightning-fast reloading
        self.bind("<F5>", lambda e: self.reload_and_render())
        self.bind("<Control-r>", lambda e: self.reload_and_render())
        self.bind("<Control-R>", lambda e: self.reload_and_render())
        
        # Initial run
        self.reload_and_render()

    def reload_and_render(self):
        """Re-reads the script file, clears previous layouts, and paints the new interface elements."""
        self.canvas.delete("all")
        self.env_vars.clear()
        
        if not self.script_path or not os.path.exists(self.script_path):
            self.draw_empty_state_message("No script file loaded. Press Ctrl+O to open a file.")
            return

        try:
            with open(self.script_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            self.compiled_objects = parse_repi_script(lines, self.env_vars)
            self.render_objects_to_canvas()
        except Exception as e:
            self.draw_empty_state_message(f"Parser/Render Error:\n{str(e)}")

    def parse_points_property(self, points_raw_list):
        """Converts raw string coordinate lists into structural drawing tuples."""
        if not points_raw_list:
            return []
            
        full_str = "".join(str(x) for x in points_raw_list)
        # Use regex to isolate JSON-like objects: {id:"...", x:..., y:...}
        matches = re.findall(r'\{([^}]+)\}', full_str)
        points = []
        
        for item in matches:
            # Extract x and y coordinates
            x_match = re.search(r'x\s*:\s*(-?\d+)', item)
            y_match = re.search(r'y\s*:\s*(-?\d+)', item)
            if x_match and y_match:
                points.append((int(x_match.group(1)), int(y_match.group(1))))
        return points

    def render_objects_to_canvas(self):
        """Processes elements and draws vector polygons, text, buttons, and rectangles."""
        rendered_count = 0
        
        for op, obj in self.compiled_objects:
            if op != "create":
                continue
                
            obj_type = obj.get("type")
            props = obj.get("properties", {})
            
            # --- Render Vector Shapes / UI Elements ---
            if obj_type == "ui":
                points = self.parse_points_property(props.get("points", []))
                
                # Fetch Hex Color dynamically
                color_list = props.get("color", [])
                hex_color = COLOR_FALLBACK_SHAPE
                if color_list:
                    # Clean color input
                    raw_col = str(color_list[0]).strip()
                    if raw_col.startswith("#") and len(raw_col) in (4, 7, 9):
                        hex_color = raw_col
                
                if len(points) == 1:
                    # Point Coordinate
                    x, y = points[0]
                    self.canvas.create_oval(x-4, y-4, x+4, y+4, fill=hex_color, outline="")
                    rendered_count += 1
                elif len(points) == 2:
                    # Draw Line
                    (x1, y1), (x2, y2) = points
                    self.canvas.create_line(x1, y1, x2, y2, fill=hex_color, width=2)
                    rendered_count += 1
                elif len(points) > 2:
                    # Draw solid Polygon (Like your square!)
                    flat_coords = [coord for pt in points for coord in pt]
                    self.canvas.create_polygon(
                        flat_coords, 
                        fill=hex_color, 
                        outline=hex_color, 
                        width=1
                    )
                    rendered_count += 1

            # --- Render Text Objects ---
            elif obj_type == "text":
                text_val = " ".join(str(x) for x in props.get("text", ["TEXT"]))
                text_val = text_val.replace('"', '').replace("'", "")
                
                loc = self.parse_points_property(props.get("location", []))
                x, y = loc[0] if loc else (100, 100)
                
                # Check for styles and alignments
                self.canvas.create_text(
                    x, y, 
                    text=text_val, 
                    fill=COLOR_PRIMARY, 
                    font=("Segoe UI", 12, "normal"),
                    anchor="nw"
                )
                rendered_count += 1

            # --- Render Button Objects ---
            elif obj_type == "button":
                text_val = " ".join(str(x) for x in props.get("text", ["Button"]))
                text_val = text_val.replace('"', '').replace("'", "")
                
                loc = self.parse_points_property(props.get("location", []))
                x, y = loc[0] if loc else (100, 150)
                
                # Render a neat clean button container
                self.canvas.create_rectangle(
                    x, y, x+120, y+40, 
                    fill="#F1F5F9", 
                    outline=COLOR_BORDER, 
                    width=1
                )
                self.canvas.create_text(
                    x+60, y+20, 
                    text=text_val, 
                    fill=COLOR_PRIMARY, 
                    font=("Segoe UI", 10, "bold"),
                    anchor="center"
                )
                rendered_count += 1

        if rendered_count == 0:
            self.draw_empty_state_message("[Notice] No visual elements parsed inside active environment.")

    def draw_empty_state_message(self, message):
        """Draws clear center-aligned messaging when a script contains no items or displays errors."""
        self.canvas.create_text(
            400, 400,
            text=message,
            fill="#94A3B8",
            font=("Segoe UI", 12, "italic"),
            justify="center",
            anchor="center"
        )

def main():
    # Handle system registration setups
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "--register":
            register_repi_extension()
            return
        elif arg == "--unregister":
            unregister_repi_extension()
            return
            
    # Resolve target file to render
    target_file = None
    if len(sys.argv) > 1:
        potential_path = sys.argv[1]
        if potential_path.lower().endswith(".repi") and os.path.exists(potential_path):
            target_file = potential_path
            
    # Interactive fallbacks if the script is run natively without an argument
    if not target_file:
        root = tk.Tk()
        root.withdraw() # Hide empty main root
        target_file = filedialog.askopenfilename(
            title="Open REPI Design Script",
            filetypes=[("REPI Script Files", "*.repi"), ("All Files", "*.*")]
        )
        if not target_file:
            print("[REPI] No target workspace script was chosen.")
            return

    # Run the Vector render application
    app = RepiRendererApp(target_file)
    app.mainloop()

if __name__ == "__main__":
    main()
