import os
import sys
import re
import math
import random
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

COLOR_BG_DARK = "#0F172A"       # Pure slate dark canvas background
COLOR_ACCENT = "#6366F1"        # Highlight colors
COLOR_TEXT_PRIMARY = "#F8FAFC"  # Crisp reading labels
COLOR_BORDER = "#1E293B"        # Clean visual separations

def evaluate_math_expression(expr, env_vars):
    """Evaluates algebraic and string concatenation expressions safely."""
    expr = str(expr).strip()
    if not expr:
        return 0

    # If it is a hex color code, preserve it and bypass evaluation
    if expr.startswith('#'):
        return expr

    # Replace declared variables in expression
    for var_name, var_val in sorted(env_vars.items(), key=lambda x: len(x[0]), reverse=True):
        if var_name in expr:
            expr = expr.replace(var_name, str(var_val))

    # Parse random ranges: random 10 50
    random_matches = re.findall(r'random\s+(\d+|any)\s+(\d+|any)', expr)
    for r_min, r_max in random_matches:
        val_min = 0 if r_min == 'any' else int(r_min)
        val_max = 100 if r_max == 'any' else int(r_max)
        if val_min > val_max:
            val_min, val_max = val_max, val_min
        expr = re.sub(rf'random\s+{r_min}\s+{r_max}', str(random.randint(val_min, val_max)), expr, count=1)

    # Convert custom math multiplication
    expr_normalized = expr.replace('x', '*').replace('X', '*')

    try:
        sanitized = re.sub(r'[^0-9\+\-\*\/\(\)\s\.]', '', expr_normalized)
        if sanitized.strip():
            return int(eval(sanitized))
    except Exception:
        pass
    
    return expr.strip('"\'')

def parse_repi_script(lines, env_vars):
    """
    Parses both nested tree structures and flat sequential lists (like 'test5673.repi').
    Supports both 'create' and 'build' start commands.
    """
    compiled_objects = []
    current_obj = None
    current_prop = None
    current_sub_context = None

    for raw_line in lines:
        cleaned = raw_line.strip()
        if not cleaned or cleaned.startswith("#"):
            continue

        # Check action roots
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
        elif "=" in cleaned and not cleaned.startswith("-") and not "[" in cleaned:
            # Handle variable allocations
            parts = cleaned.split("=", 1)
            var_name = parts[0].replace("LET", "").strip()
            var_val = evaluate_math_expression(parts[1], env_vars)
            env_vars[var_name] = var_val
            continue

        # Clean off any leading tree structure hyphens dynamically
        hyphen_stripped = re.sub(r'^-+', '', raw_line).strip()

        # Match active structural block types
        match_type = re.match(r'^\[([a-zA-Z_]+)\]', hyphen_stripped)
        match_prop = re.match(r'^\{([a-zA-Z_]+)\}', hyphen_stripped)
        match_context = re.match(r'^\(([a-zA-Z_]+)\)', hyphen_stripped)

        if match_type:
            obj_type = match_type.group(1).lower()
            if current_obj is not None:
                current_obj["type"] = obj_type
            current_prop = None
            current_sub_context = None
        elif match_prop:
            current_prop = match_prop.group(1).lower()
            current_sub_context = None
        elif match_context:
            current_sub_context = match_context.group(1).lower()
        else:
            # We have a value parameter line
            if current_obj is not None and current_prop is not None:
                props = current_obj["properties"]
                
                # Setup structure map if missing
                if current_prop not in props:
                    props[current_prop] = {}

                # Parse coordinates arrays: [{id:"1", x:10, y:20}]
                if hyphen_stripped.startswith("[{") and hyphen_stripped.endswith("}]"):
                    coords_list = []
                    item_blocks = re.findall(r'\{(.*?)\}', hyphen_stripped)
                    for block in item_blocks:
                        coordinate = {}
                        pairs = re.findall(r'([a-zA-Z0-9_]+)\s*:\s*([^,]+)', block)
                        for k, v in pairs:
                            cleaned_v = v.strip().strip('"\'')
                            coordinate[k] = evaluate_math_expression(cleaned_v, env_vars)
                        coords_list.append(coordinate)
                    props[current_prop]["_value"] = coords_list

                # Parse list arrays: ["FAMILY", "GROUPS"]
                elif hyphen_stripped.startswith("[") and hyphen_stripped.endswith("]"):
                    items = [i.strip().strip('"\'') for i in hyphen_stripped[1:-1].split(",")]
                    props[current_prop]["_value"] = items

                # Parse key-value attributes inside blocks
                elif "=" in hyphen_stripped:
                    parts = hyphen_stripped.split("=", 1)
                    sub_k = parts[0].strip().lower()
                    sub_v = parts[1].strip()
                    # Resolve boolean status flags
                    if sub_v.upper() in ("T", "TRUE", "Y", "YES"):
                        resolved_v = True
                    elif sub_v.upper() in ("F", "FALSE", "N", "NO"):
                        resolved_v = False
                    else:
                        resolved_v = evaluate_math_expression(sub_v, env_vars)

                    if current_sub_context:
                        if current_sub_context not in props[current_prop]:
                            props[current_prop][current_sub_context] = {}
                        props[current_prop][current_sub_context][sub_k] = resolved_v
                    else:
                        props[current_prop][sub_k] = resolved_v

                # Parse single sequential leaf values (like HEX, opacities, or simple text bounds)
                else:
                    resolved_leaf = evaluate_math_expression(hyphen_stripped, env_vars)
                    if current_sub_context:
                        if current_sub_context not in props[current_prop]:
                            props[current_prop][current_sub_context] = {}
                        # Keep a sequence listing inside the subcontext
                        if "_values" not in props[current_prop][current_sub_context]:
                            props[current_prop][current_sub_context]["_values"] = []
                        props[current_prop][current_sub_context]["_values"].append(resolved_leaf)
                    else:
                        if "_values" not in props[current_prop]:
                            props[current_prop]["_values"] = []
                        props[current_prop]["_values"].append(resolved_leaf)

    return compiled_objects

def flatten_repi_object(parsed_struct):
    """Flattens a dynamic properties dictionary into standard coordinate & styling primitives."""
    flat = {
        "id": "unnamed",
        "type": parsed_struct.get("type", "ui"),
        "familys": [],
        "groups": [],
        "color_bg": "#4F46E5",  # Default nice indigo fallback
        "color_fg": "#FFFFFF",
        "color_hl": "#818CF8",
        "opacity_bg": 1.0,
        "opacity_fg": 1.0,
        "opacity_hl": 1.0,
        "points": [],
        "location": [],
        "text": "",
        "font": "Segoe UI",
        "style_bold": False,
        "style_italic": False,
        "style_underline": False,
        "style_strikethrough": False,
        "source": ""
    }

    props = parsed_struct.get("properties", {})

    # Extract identification parameters
    if "all_objects" in props:
        meta = props["all_objects"]
        if "id" in meta and "_values" in meta["id"]:
            flat["id"] = str(meta["id"]["_values"][0])
        if "familys" in meta and "_value" in meta["familys"]:
            flat["familys"] = meta["familys"]["_value"]
        if "groups" in meta and "_value" in meta["groups"]:
            flat["groups"] = meta["groups"]["_value"]

    # Extract coordinates points
    if "points" in props and "_value" in props["points"]:
        flat["points"] = props["points"]["_value"]
    if "location" in props and "_value" in props["location"]:
        flat["location"] = props["location"]["_value"]

    # Extract literal values
    if "text" in props:
        text_prop = props["text"]
        if "_values" in text_prop:
            flat["text"] = str(text_prop["_values"][0])
    if "font" in props:
        font_prop = props["font"]
        if "_values" in font_prop:
            flat["font"] = str(font_prop["_values"][0])
    if "source" in props:
        src_prop = props["source"]
        if "_values" in src_prop:
            flat["source"] = str(src_prop["_values"][0])

    # Extract styling parameters
    if "style" in props:
        style_prop = props["style"]
        flat["style_bold"] = style_prop.get("bold", False)
        flat["style_italic"] = style_prop.get("italic", False)
        flat["style_underline"] = style_prop.get("underline", False)
        flat["style_strikethrough"] = style_prop.get("strikethrough", False)

    # Extract layer color values safely
    if "color" in props:
        col_prop = props["color"]
        
        # Check explicit layer definitions (e.g. (backround) -> HEX, OPACITY)
        for layer in ["backround", "text", "highlight"]:
            if layer in col_prop:
                layer_data = col_prop[layer]
                values = layer_data.get("_values", [])
                
                hex_color = None
                opacity_val = 1.0
                for v in values:
                    if str(v).startswith("#"):
                        hex_color = v
                    else:
                        try:
                            raw_f = float(v)
                            opacity_val = raw_f / 100.0 if raw_f > 1.0 else raw_f
                        except ValueError:
                            pass
                
                if layer == "backround" and hex_color:
                    flat["color_bg"] = hex_color
                    flat["opacity_bg"] = opacity_val
                elif layer == "text" and hex_color:
                    flat["color_fg"] = hex_color
                    flat["opacity_fg"] = opacity_val
                elif layer == "highlight" and hex_color:
                    flat["color_hl"] = hex_color
                    flat["opacity_hl"] = opacity_val

        # Check for sequential flat lists of color values (e.g. HEX on line 1, Opacity on line 2)
        if "_values" in col_prop:
            flat_vals = col_prop["_values"]
            for fv in flat_vals:
                if str(fv).startswith("#"):
                    flat["color_bg"] = fv
                else:
                    try:
                        raw_f = float(fv)
                        flat["opacity_bg"] = raw_f / 100.0 if raw_f > 1.0 else raw_f
                    except ValueError:
                        pass

    return flat

class REPIDesignerWindow(tk.Tk):
    """A premium, minimal vector window showing ONLY the compiled layout canvas."""
    def __init__(self, script_path, code_string, objects_list):
        super().__init__()
        self.script_path = script_path
        self.code_string = code_string
        self.objects_list = objects_list
        
        # Pure workspace title
        self.title(f"REPI Workspace - {os.path.basename(script_path)}")
        self.geometry("600x600")
        self.minsize(300, 300)
        self.configure(bg=COLOR_BG_DARK)

        # Designer settings (Default grid off for clean rendering)
        self.show_grid = False

        self.build_ui()
        self.draw_workspace()

    def build_ui(self):
        """Constructs a pure canvas-only viewport."""
        # 100% window filled canvas
        self.canvas = tk.Canvas(self, bg=COLOR_BG_DARK, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind window resize action to trigger redraw
        self.canvas.bind("<Configure>", lambda event: self.draw_workspace())

        # Bind hotkeys for quick, seamless workspace syncing
        self.bind("<F5>", lambda event: self.reload_file_contents())
        self.bind("<Control-r>", lambda event: self.reload_file_contents())
        self.bind("<Control-R>", lambda event: self.reload_file_contents())

    def draw_workspace(self, highlight_id=None):
        """Renders vector elements with precision on designer canvas."""
        self.canvas.delete("all")

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width <= 1 or height <= 1:
            return

        # Render subtle coordinates grid matrix (only if toggled)
        if self.show_grid:
            grid_interval = 40
            for x in range(0, width, grid_interval):
                self.canvas.create_line(x, 0, x, height, fill="#2D3748", width=1)
            for y in range(0, height, grid_interval):
                self.canvas.create_line(0, y, width, y, fill="#2D3748", width=1)

        # Draw vector layout elements sequentially
        for obj in self.objects_list:
            obj_type = obj.get("type", "unknown").lower()
            is_highlighted = (obj.get("id") == highlight_id)

            outline_color = COLOR_ACCENT if is_highlighted else ""
            outline_width = 3 if is_highlighted else 0

            # Handle Polygon/Vector UI element shape drawing
            if obj_type == "ui":
                pts = obj.get("points", [])
                if len(pts) >= 2:
                    coords = []
                    for p in pts:
                        try:
                            coords.append(float(p.get("x", 0)))
                            coords.append(float(p.get("y", 0)))
                        except (ValueError, TypeError):
                            pass
                    
                    if len(coords) >= 4:
                        if len(coords) == 4:
                            self.canvas.create_line(
                                coords[0], coords[1], coords[2], coords[3],
                                fill=obj.get("color_bg", "#FFFFFF"),
                                width=2,
                                tags=obj.get("id")
                            )
                        else:
                            self.canvas.create_polygon(
                                coords,
                                fill=obj.get("color_bg", "#4F46E5"),
                                outline=outline_color,
                                width=outline_width,
                                tags=obj.get("id")
                            )
                elif len(pts) == 1:
                    # Single point coordinate layout mark
                    try:
                        px = float(pts[0].get("x", 0))
                        py = float(pts[0].get("y", 0))
                        r = 6
                        self.canvas.create_oval(
                            px - r, py - r, px + r, py + r,
                            fill=obj.get("color_bg", COLOR_ACCENT),
                            outline=outline_color if outline_color else obj.get("color_bg", COLOR_ACCENT),
                            width=outline_width if outline_width else 1,
                            tags=obj.get("id")
                        )
                    except (ValueError, TypeError):
                        pass

            # Handle Text Element drawing
            elif obj_type == "text":
                loc = obj.get("location", [])
                if loc:
                    try:
                        tx = float(loc[0].get("x", 0))
                        ty = float(loc[0].get("y", 0))
                        
                        # Apply custom text modifications
                        font_style = []
                        if obj.get("style_bold"): font_style.append("bold")
                        if obj.get("style_italic"): font_style.append("italic")
                        if obj.get("style_underline"): font_style.append("underline")
                        
                        font_spec = (obj.get("font", "Segoe UI"), 10, " ".join(font_style))
                        
                        # Text background boundary box rendering
                        t_id = self.canvas.create_text(
                            tx, ty,
                            text=obj.get("text", ""),
                            font=font_spec,
                            fill=obj.get("color_fg", COLOR_TEXT_PRIMARY),
                            anchor="nw",
                            tags=obj.get("id")
                        )
                        
                        bbox = self.canvas.bbox(t_id)
                        if bbox:
                            bg_rect = self.canvas.create_rectangle(
                                bbox[0] - 4, bbox[1] - 4, bbox[2] + 4, bbox[3] + 4,
                                fill=obj.get("color_bg", COLOR_BG_DARK),
                                outline=outline_color if is_highlighted else "",
                                width=outline_width,
                                tags=obj.get("id")
                            )
                            self.canvas.tag_lower(bg_rect, t_id)
                    except (ValueError, TypeError, IndexError):
                        pass

            # Handle Button Component drawing
            elif obj_type == "button":
                loc = obj.get("location", [])
                if loc:
                    try:
                        bx = float(loc[0].get("x", 0))
                        by = float(loc[0].get("y", 0))
                        
                        label_text = obj.get("text", "Button")
                        font_spec = (obj.get("font", "Segoe UI"), 9, "bold" if obj.get("style_bold") else "normal")
                        
                        pad_x, pad_y = 16, 8
                        t_id = self.canvas.create_text(
                            bx, by,
                            text=label_text,
                            font=font_spec,
                            fill=obj.get("color_fg", COLOR_TEXT_PRIMARY),
                            anchor="center",
                            tags=obj.get("id")
                        )
                        
                        bbox = self.canvas.bbox(t_id)
                        if bbox:
                            btn_card = self.canvas.create_rectangle(
                                bbox[0] - pad_x, bbox[1] - pad_y, bbox[2] + pad_x, bbox[3] + pad_y,
                                fill=obj.get("color_bg", "#4F46E5"),
                                outline=outline_color if outline_color else "#4F46E5",
                                width=outline_width if outline_width else 1,
                                tags=obj.get("id")
                            )
                            self.canvas.tag_lower(btn_card, t_id)
                    except (ValueError, TypeError, IndexError):
                        pass

            # Handle Image Block Placeholder drawing
            elif obj_type == "image":
                loc = obj.get("location", [])
                if loc:
                    try:
                        ix = float(loc[0].get("x", 0))
                        iy = float(loc[0].get("y", 0))
                        iw, ih = 140, 90
                        
                        img_card = self.canvas.create_rectangle(
                            ix, iy, ix + iw, iy + ih,
                            fill=obj.get("color_bg", "#1E293B"),
                            outline=outline_color if outline_color else "#1E293B",
                            width=outline_width if outline_width else 1,
                            tags=obj.get("id")
                        )
                        
                        # Draw visual center icon placeholder
                        self.canvas.create_line(ix, iy, ix + iw, iy + ih, fill="#334155", width=1)
                        self.canvas.create_line(ix, iy + ih, ix + iw, iy, fill="#334155", width=1)
                        
                        self.canvas.create_text(
                            ix + iw/2, iy + ih/2,
                            text="[IMAGE]",
                            font=("Segoe UI", 9, "bold"),
                            fill="#94A3B8",
                            anchor="center",
                            tags=obj.get("id")
                        )
                    except (ValueError, TypeError, IndexError):
                        pass

    def reload_file_contents(self):
        """Reloads and recompiles active script lines from local file system storage."""
        if not os.path.exists(self.script_path):
            messagebox.showerror("Error", f"Failed to sync. File not found:\n{self.script_path}")
            return

        try:
            with open(self.script_path, "r", encoding="utf-8") as f:
                new_content = f.read()

            env_vars = {"VERSION": "1.1.0", "OBJECT_COUNT": 0}
            lines = new_content.splitlines()
            parsed_ops = parse_repi_script(lines, env_vars)

            new_objects_map = {}
            for action, data in parsed_ops:
                if action == "create":
                    flat = flatten_repi_object(data)
                    new_objects_map[flat["id"]] = flat
                elif action == "edit":
                    obj_id = data.get("properties", {}).get("all_objects", {}).get("id", {}).get("_values", ["unnamed"])[0]
                    if obj_id in new_objects_map:
                        flat_edit = flatten_repi_object(data)
                        orig = new_objects_map[obj_id]
                        for k, v in flat_edit.items():
                            if k == "id": continue
                            if v not in (None, [], "", False) or k.startswith("style_"):
                                orig[k] = v
                elif action == "delete":
                    obj_id = data.get("id")
                    if obj_id in new_objects_map:
                        del new_objects_map[obj_id]

            self.objects_list = list(new_objects_map.values())
            self.draw_workspace()
            
        except Exception as e:
            messagebox.showerror("Parser Error", f"Failed parsing the updated schema script:\n{str(e)}")

def register_repi_extension():
    """Associates file format .repi with our execution tool inside Windows system registries."""
    if os.name != 'nt':
        print("[ERROR] Registrations can only run inside a Windows workspace.")
        return False
    
    import winreg
    try:
        python_exe = sys.executable
        if python_exe.endswith("pythonw.exe"):
            python_exe = python_exe.replace("pythonw.exe", "python.exe")
            
        script_path = os.path.abspath(__file__)
        
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.repi") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "repi_file")
            
        command_path = r"Software\Classes\repi_file\shell\open\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_path) as key:
            cmd_line = f'"{python_exe}" "{script_path}" "%1"'
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, cmd_line)
            
        print("\n[SUCCESS] NATIVE REPI SYSTEM PREVIEW WINDOW REGISTRATION COMPLETED!")
        print(f"Associated To Command Line:\n  {cmd_line}\n")
        return True
    except Exception as e:
        print(f"\n[ERROR] Registry registration failed: {str(e)}\n")
        return False

def unregister_repi_extension():
    """Removes all .repi system registry values safely."""
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
    
    print("\n[INFO] Starting registry cleaning...")
    success = True
    for p in keys_to_delete:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, p)
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[WARNING] Could not delete node key '{p}': {str(e)}")
            success = False
            
    if success:
        print("\n[SUCCESS] SYSTEM FILE REGISTRY BINDINGS CLEARED!")
        return True
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
            
            # Treat argument as active script file
            file_path = os.path.abspath(arg.strip('"\''))
            if not file_path.lower().endswith(".repi"):
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "Format Validation Failure",
                    f"Rejected file execution. Target files must strictly carry the official '.repi' extension."
                )
                return
                
            if not os.path.exists(file_path):
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "Source Missing",
                    f"Target file path is offline or inaccessible:\n{file_path}"
                )
                return

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            env_vars = {"VERSION": "1.1.0", "OBJECT_COUNT": 0}
            lines = content.splitlines()
            parsed_ops = parse_repi_script(lines, env_vars)

            # Compile parsed visual elements list sequentially
            objects_map = {}
            for action, data in parsed_ops:
                if action == "create":
                    flat = flatten_repi_object(data)
                    objects_map[flat["id"]] = flat
                elif action == "edit":
                    obj_id = data.get("properties", {}).get("all_objects", {}).get("id", {}).get("_values", ["unnamed"])[0]
                    if obj_id in objects_map:
                        flat_edit = flatten_repi_object(data)
                        orig = objects_map[obj_id]
                        for k, v in flat_edit.items():
                            if k == "id": continue
                            if v not in (None, [], "", False) or k.startswith("style_"):
                                orig[k] = v
                elif action == "delete":
                    obj_id = data.get("id")
                    if obj_id in objects_map:
                        del objects_map[obj_id]

            # Trigger live designer GUI workspace window directly!
            app = REPIDesignerWindow(file_path, content, list(objects_map.values()))
            app.mainloop()
            return
                
        else:
            # Fallback console run instructions if loaded empty
            print("[REPI DESIGN SYSTEM ENGINE ACTIVE]")
            print("To run visual previews directly in separate workspace windows, register the file associations:")
            print("  python repi.py --register")
            print("\nRun any explicit file script with:")
            print("  python repi.py your_script.repi\n")
                
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Fatal Workspace System Crash", f"An unexpected error occurred:\n{str(e)}")

if __name__ == "__main__":
    main()
