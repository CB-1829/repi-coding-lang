import os
import sys
import re
import math
import random
from pathlib import Path

# ANSI escape codes for modern, colorized Windows Terminal styling
CLR_SUCCESS = "\033[1;92m"   # Bold Light Green
CLR_ERROR = "\033[1;91m"     # Bold Light Red
CLR_WARNING = "\033[93m"     # Yellow
CLR_INFO = "\033[94m"        # Light Blue
CLR_MUTED = "\033[90m"       # Grey
CLR_RESET = "\033[0m"        # Reset color
CLR_BOLD = "\033[1m"         # Bold text
CLR_CANVAS_BG = "\033[48;5;234m" # Dark grey block background for preview canvas

# Enable ANSI escape processing on Windows Command Prompt / Powershell natively
if os.name == 'nt':
    os.system('')

def evaluate_math_expression(expr, env_vars):
    """
    Evaluates algebraic and string concat expressions.
    Supports standard operations: +, -, /, and 'x' for multiplication.
    """
    expr = expr.strip()
    if not expr:
        return 0

    # Replace variables in the expression with their literal values
    for var_name, var_val in sorted(env_vars.items(), key=lambda x: len(x[0]), reverse=True):
        if var_name in expr:
            expr = expr.replace(var_name, str(var_val))

    # Evaluate dynamic 'random min max' statements if present
    # Format: random 10 50 -> yields value in range [10, 50]
    random_matches = re.findall(r'random\s+(\d+|any)\s+(\d+|any)', expr)
    for r_min, r_max in random_matches:
        val_min = 0 if r_min == 'any' else int(r_min)
        val_max = 100 if r_max == 'any' else int(r_max)
        if val_min > val_max:
            val_min, val_max = val_max, val_min
        expr = re.sub(rf'random\s+{r_min}\s+{r_max}', str(random.randint(val_min, val_max)), expr, count=1)

    # Normalize custom REPI math operators to Python format
    # Supports 'x' for multiplication and '/' for division
    expr_normalized = expr.replace('x', '*').replace('X', '*')

    try:
        # Evaluate cleanly while ignoring arbitrary unsafe strings
        sanitized = re.sub(r'[^0-9\+\-\*\/\(\)\s\.]', '', expr_normalized)
        if sanitized.strip():
            return int(eval(sanitized))
    except Exception:
        pass
    
    return expr.strip('"\'') # Fallback as standard literal string

def parse_repi_lines(lines, env_vars):
    """
    Parses hierarchical layout structures from text lines based on leading hyphen depth.
    Builds nested dictionaries representing object creations and mutations.
    """
    parsed_objects = []
    current_action = None  # 'create', 'edit', 'delete'
    current_obj = None
    stack = [] # Tracking parent structures during indentation shifts

    # Utility regex captures
    re_array_dicts = re.compile(r'\[\s*\{(.*?)\}\s*\]') # Coordinates matching [{id:"p1", x:10, y:2}]
    re_array_strs = re.compile(r'\[\s*"(.*?)"\s*\]')   # Lists matching ["item1", "item2"]

    for raw_line in lines:
        cleaned = raw_line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue

        # Check top-level root operation controls
        if cleaned == "create":
            current_action = "create"
            current_obj = {}
            stack = [(0, current_obj)]
            parsed_objects.append(("create", current_obj))
            continue
        elif cleaned == "edit":
            current_action = "edit"
            current_obj = {}
            stack = [(0, current_obj)]
            parsed_objects.append(("edit", current_obj))
            continue
        elif cleaned.startswith("delete"):
            target_id = cleaned.replace("delete", "").strip().strip("#").strip()
            parsed_objects.append(("delete", {"id": target_id}))
            continue
        elif "=" in cleaned and not cleaned.startswith("-"):
            # Variable assignments: e.g., LET x = 10 x 5
            parts = cleaned.split("=", 1)
            var_name = parts[0].replace("LET", "").strip()
            var_val = evaluate_math_expression(parts[1], env_vars)
            env_vars[var_name] = var_val
            continue

        # Determine structural depth via leading hyphens
        hyphen_match = re.match(r'^(-+)(.*)', raw_line)
        if not hyphen_match:
            continue

        depth = len(hyphen_match.group(1))
        content = hyphen_match.group(2).strip()

        # Extract values or nested structural components
        is_type = re.match(r'^\[([a-zA-Z_]+)\]', content)
        is_key = re.match(r'^\{([a-zA-Z_]+)\}', content)
        is_context = re.match(r'^\(([a-zA-Z_]+)\)', content)

        # Unwind stack hierarchy for shallower indentation lines
        while stack and stack[-1][0] >= depth:
            stack.pop()

        current_node = stack[-1][1] if stack else None

        if is_type:
            obj_type = is_type.group(1)
            if current_node is not None:
                current_node["type"] = obj_type
                stack.append((depth, current_node))
        elif is_key:
            key_name = is_key.group(1)
            if current_node is not None:
                current_node[key_name] = {}
                stack.append((depth, current_node[key_name]))
        elif is_context:
            context_name = is_context.group(1)
            if current_node is not None:
                current_node[context_name] = {}
                stack.append((depth, current_node[context_name]))
        else:
            # Parse actual values or value mappings
            value_str = content
            # Parse list of coordinate dict objects: e.g. [{id:"p1", x:10, y:20}]
            if value_str.startswith("[{") and value_str.endswith("}]"):
                parsed_list = []
                inner_items = re.findall(r'\{(.*?)\}', value_str)
                for item in inner_items:
                    item_dict = {}
                    # Split keys and values
                    pairs = re.findall(r'([a-zA-Z0-9_]+)\s*:\s*([^,]+)', item)
                    for k, v in pairs:
                        v_eval = evaluate_math_expression(v, env_vars)
                        item_dict[k] = v_eval
                    parsed_list.append(item_dict)
                if current_node is not None:
                    # Merge or assign parsed list
                    current_node["_value"] = parsed_list
            # Parse standard lists of strings: e.g. ["FAMILY", "GROUPS"]
            elif value_str.startswith("[") and value_str.endswith("]"):
                items = [i.strip().strip('"\'') for i in value_str[1:-1].split(",")]
                if current_node is not None:
                    current_node["_value"] = items
            # Parse style indicators like bold=T/F
            elif "=" in value_str and current_node is not None:
                parts = value_str.split("=", 1)
                flag_name = parts[0].strip()
                flag_val = parts[1].strip().upper() in ("T", "TRUE", "Y", "YES")
                current_node[flag_name] = flag_val
            # Standard leaf string or numerical value
            else:
                evaluated_val = evaluate_math_expression(value_str, env_vars)
                if current_node is not None:
                    current_node["_value"] = evaluated_val

    return parsed_objects

def flatten_repi_object(parsed_dict):
    """
    Helper that structures raw parsed dictionary trees into standard UI elements.
    Example: extracts deep HEX and OPACITIES into easily renderable attributes.
    """
    flat = {
        "id": "unnamed",
        "type": parsed_dict.get("type", "unknown"),
        "familys": [],
        "groups": [],
        "color_bg": "#FFFFFF",
        "color_fg": "#000000",
        "color_hl": None,
        "opacity_bg": 1.0,
        "opacity_fg": 1.0,
        "opacity_hl": 1.0,
        "points": [],
        "location": [],
        "text": "",
        "font": "Consolas",
        "style_bold": False,
        "style_italic": False,
        "style_underline": False,
        "style_strikethrough": False,
        "source": ""
    }

    # Extract metadata properties from [ALL_OBJECTS] block
    all_objs = parsed_dict.get("ALL_OBJECTS", {})
    if all_objs:
        if "id" in all_objs and isinstance(all_objs["id"], dict):
            flat["id"] = all_objs["id"].get("_value", "unnamed")
        if "familys" in all_objs and isinstance(all_objs["familys"], dict):
            flat["familys"] = all_objs["familys"].get("_value", [])
        if "groups" in all_objs and isinstance(all_objs["groups"], dict):
            flat["groups"] = all_objs["groups"].get("_value", [])

    # Extract dynamic custom attributes based on design tokens
    for key, val in parsed_dict.items():
        if key == "ALL_OBJECTS" or key == "type":
            continue
        if not isinstance(val, dict):
            continue

        if key == "color":
            # Check nested colors: background, text, highlight
            for layer in ["backround", "text", "highlight"]:
                if layer in val and isinstance(val[layer], dict):
                    # Gather nested leaf values
                    hex_val = "#FFFFFF"
                    opacity_val = 1.0
                    for sub_k, sub_v in val[layer].items():
                        if isinstance(sub_v, dict):
                            val_to_check = sub_v.get("_value", "")
                            if str(val_to_check).startswith("#"):
                                hex_val = val_to_check
                            else:
                                try:
                                    opacity_val = float(val_to_check)
                                except ValueError:
                                    pass
                    if layer == "backround":
                        flat["color_bg"] = hex_val
                        flat["opacity_bg"] = opacity_val
                    elif layer == "text":
                        flat["color_fg"] = hex_val
                        flat["opacity_fg"] = opacity_val
                    elif layer == "highlight":
                        flat["color_hl"] = hex_val
                        flat["opacity_hl"] = opacity_val
            # Fallback flat color definition
            if "_value" in val:
                flat["color_bg"] = val["_value"]

        elif key == "points":
            flat["points"] = val.get("_value", [])
        elif key == "location":
            flat["location"] = val.get("_value", [])
        elif key == "text":
            flat["text"] = val.get("_value", "")
        elif key == "font":
            flat["font"] = val.get("_value", "")
        elif key == "source":
            flat["source"] = val.get("_value", "")
        elif key == "style":
            flat["style_bold"] = val.get("bold", False)
            flat["style_italic"] = val.get("italic", False)
            flat["style_underline"] = val.get("underline", False)
            flat["style_strikethrough"] = val.get("strikethrough", False)

    return flat

def draw_line(x0, y0, x1, y1, char, canvas, width, height):
    """Rasterizes vector line coordinates using a basic Bresenham algorithm."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        if 0 <= x0 < width and 0 <= y0 < height:
            canvas[y0][x0] = char

        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

def render_ascii_canvas(objects):
    """
    Renders compiled UI component objects inside a beautiful terminal ASCII mock-up.
    Generates a 80x22 layout preview directly inside PowerShell / command shells.
    """
    width = 80
    height = 22
    
    # Initialize workspace with quiet dot canvas pattern
    canvas = [["·" for _ in range(width)] for _ in range(height)]

    for obj in objects:
        obj_type = obj.get("type", "unknown").lower()
        
        if obj_type == "ui":
            # Render a custom shape / polygon from designated points array
            pts = obj.get("points", [])
            if len(pts) >= 2:
                # Render lines between consecutive vertices
                for i in range(len(pts)):
                    p_start = pts[i]
                    p_end = pts[(i + 1) % len(pts)]
                    try:
                        x0, y0 = int(p_start.get("x", 0)), int(p_start.get("y", 0))
                        x1, y1 = int(p_end.get("x", 0)), int(p_end.get("y", 0))
                        draw_line(x0, y0, x1, y1, "*", canvas, width, height)
                    except ValueError:
                        continue
            elif len(pts) == 1:
                # Single point plot
                try:
                    px = int(pts[0].get("x", 0))
                    py = int(pts[0].get("y", 0))
                    if 0 <= px < width and 0 <= py < height:
                        canvas[py][px] = "✦"
                except ValueError:
                    pass

        elif obj_type == "text":
            # Render descriptive text nodes onto layout grid
            loc = obj.get("location", [])
            if loc:
                try:
                    tx = int(loc[0].get("x", 0))
                    ty = int(loc[0].get("y", 0))
                    text_str = str(obj.get("text", ""))
                    for offset, char in enumerate(text_str):
                        cx = tx + offset
                        if 0 <= cx < width and 0 <= ty < height:
                            canvas[ty][cx] = char
                except ValueError:
                    pass

        elif obj_type == "button":
            # Render stylized buttons surrounded by structural borders
            loc = obj.get("location", [])
            if loc:
                try:
                    bx = int(loc[0].get("x", 0))
                    by = int(loc[0].get("y", 0))
                    label = f" [ {str(obj.get('text', 'Button'))} ] "
                    for offset, char in enumerate(label):
                        cx = bx + offset
                        if 0 <= cx < width and 0 <= by < height:
                            canvas[by][cx] = char
                except ValueError:
                    pass

        elif obj_type == "image":
            # Render a visual image block layout
            loc = obj.get("location", [])
            if loc:
                try:
                    ix = int(loc[0].get("x", 0))
                    iy = int(loc[0].get("y", 0))
                    # Default image dimensions (bounding box block)
                    img_w, img_h = 12, 4
                    for dy in range(img_h):
                        for dx in range(img_w):
                            cx, cy = ix + dx, iy + dy
                            if 0 <= cx < width and 0 <= cy < height:
                                if dy == 0 or dy == img_h - 1 or dx == 0 or dx == img_w - 1:
                                    canvas[cy][cx] = "▩"
                                elif dy == img_h // 2 and 1 <= dx <= len("IMG"):
                                    canvas[cy][cx] = "IMG"[dx-1]
                                else:
                                    canvas[cy][cx] = " "
                except ValueError:
                    pass

    # Print fully compiled visual layout to PowerShell terminal
    print(f"\n{CLR_INFO}┌───────────────────────────────── {CLR_BOLD}LIVE TERMINAL PREVIEW WORKSPACE{CLR_RESET}{CLR_INFO} ─────────────────────────────────┐{CLR_RESET}")
    for row in canvas:
        row_str = "".join(row)
        # Apply slight background shading to preview canvas frame
        print(f"{CLR_INFO}│{CLR_RESET}{CLR_CANVAS_BG}{row_str}{CLR_RESET}{CLR_INFO}│{CLR_RESET}")
    print(f"{CLR_INFO}└──────────────────────────────────────────────────────────────────────────────────────────────────┘{CLR_RESET}\n")

def execute_repi_code(code_string):
    """Compiles and executes parsed REPI directives step-by-step."""
    env_vars = {
        "VERSION": "1.1.0",
        "OBJECT_COUNT": 0
    }
    
    compiled_objects = {} # ID mapping of compiled elements

    lines = code_string.splitlines()
    parsed_operations = parse_repi_lines(lines, env_vars)

    # Process operations
    for action, data in parsed_operations:
        if action == "create":
            flat_obj = flatten_repi_object(data)
            obj_id = flat_obj["id"]
            compiled_objects[obj_id] = flat_obj
            print(f"  {CLR_SUCCESS}[CREATED]{CLR_RESET} Element type '{flat_obj['type']}' with ID '{obj_id}'")
        elif action == "edit":
            obj_id = data.get("ALL_OBJECTS", {}).get("id", {}).get("_value")
            if not obj_id:
                # Find by nested structure or use fallback
                obj_id = data.get("id", {}).get("_value")
            
            if obj_id in compiled_objects:
                flat_edit = flatten_repi_object(data)
                # Merge edit parameters onto original element structure safely
                orig = compiled_objects[obj_id]
                for k, v in flat_edit.items():
                    # Keep ID unchanged
                    if k == "id":
                        continue
                    # Overwrite default parameters if values exist
                    if v not in (None, [], "", False) or k.startswith("style_"):
                        orig[k] = v
                print(f"  {CLR_INFO}[UPDATED]{CLR_RESET} Modified parameters for ID '{obj_id}'")
            else:
                print(f"  {CLR_WARNING}[NOTICE]{CLR_RESET} Attempted to edit non-existent ID '{obj_id}'")
        elif action == "delete":
            obj_id = data.get("id")
            if obj_id in compiled_objects:
                del compiled_objects[obj_id]
                print(f"  {CLR_ERROR}[DELETED]{CLR_RESET} Removed ID '{obj_id}' from preview list")
            else:
                print(f"  {CLR_WARNING}[NOTICE]{CLR_RESET} ID '{obj_id}' not found for removal")

    # Render layout workspace to active PowerShell session
    if compiled_objects:
        render_ascii_canvas(compiled_objects.values())
    else:
        print(f"\n{CLR_WARNING}[Notice] No visual elements queued inside active environment.{CLR_RESET}\n")

def register_repi_extension():
    """Associates .repi file types with the global python runner inside Windows Registry."""
    if os.name != 'nt':
        print(f"{CLR_ERROR}File associations are only supported on Windows operating systems.{CLR_RESET}")
        return False
    
    import winreg
    try:
        # Determine execution path
        python_exe = sys.executable
        if python_exe.endswith("pythonw.exe"):
            python_exe = python_exe.replace("pythonw.exe", "python.exe")
            
        script_path = os.path.abspath(__file__)
        
        # 1. Map extension tag to system file class
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.repi") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "repi_file")
            
        # 2. Instruct file system to route through active PowerShell session
        command_path = r"Software\Classes\repi_file\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_path) as key:
            # -NoExit parameter ensures PowerShell tab stays active for user inputs
            command_string = f'powershell.exe -NoExit -Command "& \\"{python_exe}\\" \\"{script_path}\\" \\"%1\\""'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command_string)
            
        print(f"\n{CLR_SUCCESS}SYSTEM FILE ASSOCIATION REGISTERED SUCCESSFULLY!{CLR_RESET}")
        print(f"{CLR_INFO}Target Path:{CLR_RESET} {script_path}")
        print(f"You can now double-click any `.repi` file in Explorer to run it inside PowerShell!\n")
        return True
    except Exception as e:
        print(f"\n{CLR_ERROR}Registry Write Failure:{CLR_RESET} Confirm administrator privileges.\n{str(e)}\n")
        return False

def unregister_repi_extension():
    """Clears and removes .repi registry configurations safely."""
    if os.name != 'nt':
        return False
    
    import winreg
    keys_to_delete = [
        r"Software\Classes\repi_file\shell\open\command",
        r"Software\Classes\repi_file\shell\open",
        r"Software\Classes\repi_file\shell",
        r"Software\Classes\repi_file",
        r"Software\Classes\.repi"
    ]
    
    print(f"\n{CLR_INFO}Starting registry clean...{CLR_RESET}")
    success = True
    for path in keys_to_delete:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"{CLR_WARNING}Key removal warning '{path}': {str(e)}{CLR_RESET}")
            success = False
            
    if success:
        print(f"\n{CLR_SUCCESS}REPI SYSTEM FILE ASSOCIATION UNINSTALLED CLEANLY!{CLR_RESET}")
        return True
    return False

def load_repi_file(filepath):
    """Sanitizes arguments, inspects extensions, reads files, and runs them."""
    filepath = filepath.strip('"\'')
    filename = os.path.basename(filepath)
    
    if not filepath.lower().endswith(".repi"):
        print(f"\n{CLR_ERROR}Strict Extension Error:{CLR_RESET}")
        print(f"Cannot compile '{filename}'. Only '.repi' scripts are allowed by the compiler.\n")
        return False

    if not os.path.exists(filepath):
        print(f"\n{CLR_ERROR}File Retrieval Failure:{CLR_RESET} '{filepath}' is missing or offline.\n")
        return False

    try:
        with open(filepath, "r", encoding="utf-8") as file_stream:
            content = file_stream.read()

        print(f"\n{CLR_SUCCESS}.repi FILE SUCCESSFULLY OPENED{CLR_RESET}")
        print(f"{CLR_INFO}Absolute Path:{CLR_RESET} {os.path.abspath(filepath)}")
        print(f"{CLR_MUTED}" + "=" * 100 + f"{CLR_RESET}")
        
        # Compile and execute the parsed operations
        execute_repi_code(content)
            
        print(f"{CLR_MUTED}" + "=" * 100 + f"{CLR_RESET}\n")
        return True

    except Exception as e:
        print(f"\n{CLR_ERROR}Compiler Execution Interrupted:{CLR_RESET}\n{str(e)}\n")
        return False

def main():
    try:
        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if arg == "--register":
                register_repi_extension()
                return
            if arg == "--unregister":
                unregister_repi_extension()
                return
            
            # Execute file path
            load_repi_file(arg)
            return
                
        else:
            print(f"{CLR_BOLD}[REPI COMPILER & INTERP]{CLR_RESET} System active.")
            print(f"Use the command: {CLR_BOLD}python repi.py --register{CLR_RESET} to integrate double-click execution.")
            print(f"Direct terminal run command: {CLR_BOLD}python repi.py your_script.repi{CLR_RESET}\n")
                
    except Exception as e:
        print(f"\n{CLR_ERROR}System Fault:{CLR_RESET} {str(e)}\n")

if __name__ == "__main__":
    main()
