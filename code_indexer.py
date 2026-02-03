import os
import sys
from tree_sitter import Parser, Language
import tree_sitter_python
import pathspec


class CodeIndexer:
    def __init__(self, repo_id: str, root_path: str):
        self.repo_id = repo_id
        self.root_path = root_path

        self.parser = Parser()
        self.parser.language = Language(tree_sitter_python.language())

        # ---------------- Raw stores ----------------
        self.files_source = {}          # file_path -> source
        self.imports = {}               # file_path -> {internal, external}

        self.symbol_defs = {}           # qualified_name -> meta
        self.calls = {}                 # caller -> set(callees)
        self.called_by = {}             # callee -> set(callers)
        self.callback_used_by = {}      # function -> set(functions)
        
        self.gitignore = self._load_gitignore()

        # ---------------- Final JSON ----------------
        self.json = {
            "repo_id": repo_id,
            "root_path": root_path,
            "metadata": {
                "language": "python",
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
                "external_dependencies": [],
                "app_type": None,
                "entrypoint_style": [],
                "frameworks": [],
                "secondary_frameworks": [],
                "summary": None
            },
            "codebase": {
                "folders": [],
                "files": []
            }
        }

    # =========================================================
    # PUBLIC API
    # =========================================================

    def index(self):
        self._walk_repo()
        self._build_folder_index()
        self._build_file_objects()
        return self.json

    # =========================================================
    # REPO WALK
    # =========================================================

    def _walk_repo(self):
        for root, dirs, files in os.walk(self.root_path):
            rel_root = os.path.relpath(root, self.root_path)

            # Skip ignored directories
            dirs[:] = [
                d for d in dirs
                if not self._is_ignored(os.path.join(rel_root, d))
            ]

            for file in files:
                rel_path = os.path.join(rel_root, file)

                if self._is_ignored(rel_path):
                    continue

                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    self._index_file(full_path)

    def _index_file(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        rel_path = os.path.relpath(file_path, self.root_path)
        self.files_source[rel_path] = source
        self.imports[rel_path] = {"internal": [], "external": []}

        tree = self.parser.parse(source.encode())
        self._walk_ast(tree.root_node, rel_path, None, None)

    # =========================================================
    # AST WALK
    # =========================================================

    def _walk_ast(self, node, file_path, current_class, current_function):
        # ---------- Class ----------
        if node.type == "class_definition":
            name = node.child_by_field_name("name").text.decode()
            qname = f"{file_path.replace('/', '.')[:-3]}.{name}"

            self.symbol_defs[qname] = {
                "type": "class",
                "name": name,
                "qualified_name": qname,
                "file": file_path,
                "methods": [],
                "inherits_from": [],
                "code_range": self._range(node)
            }
            current_class = qname

        # ---------- Function ----------
        if node.type == "function_definition":
            name = node.child_by_field_name("name").text.decode()
            qname = (
                f"{current_class}.{name}" if current_class else
                f"{file_path.replace('/', '.')[:-3]}.{name}"
            )

            self.symbol_defs[qname] = {
                "type": "function",
                "name": name,
                "qualified_name": qname,
                "file": file_path,
                "calls": set(),
                "called_by": set(),
                "callbacks": set(),
                "control_flow": [],
                "code_range": self._range(node)
            }

            if current_class:
                self.symbol_defs[current_class]["methods"].append(name)

            current_function = qname

        # ---------- Imports ----------
        if node.type == "import_statement":
            for c in node.children:
                if c.type == "dotted_name":
                    name = c.text.decode()
                    self.imports[file_path]["external"].append(name)

        if node.type == "import_from_statement":
            module = node.child_by_field_name("module")
            if module:
                self.imports[file_path]["internal"].append(module.text.decode())

        # ---------- Calls ----------
        if node.type == "call" and current_function:
            fn = node.child_by_field_name("function")
            if fn and fn.type == "identifier":
                callee = fn.text.decode()
                self.symbol_defs[current_function]["calls"].add(callee)
                self.called_by.setdefault(callee, set()).add(current_function)

            # callback usage (static only)
            args = node.child_by_field_name("arguments")
            if args:
                for arg in args.children:
                    if arg.type == "identifier":
                        self.symbol_defs[current_function]["callbacks"].add(
                            arg.text.decode()
                        )

        # ---------- Control Flow ----------
        if node.type in ("if_statement", "try_statement") and current_function:
            self.symbol_defs[current_function]["control_flow"].append({
                "type": "if" if node.type == "if_statement" else "try",
                "code_range": self._range(node),
                "purpose": None
            })

        for child in node.children:
            self._walk_ast(child, file_path, current_class, current_function)

    # =========================================================
    # BUILD FINAL JSON
    # =========================================================

    def _build_folder_index(self):
        folders = {}
        for path in self.files_source:
            folder = os.path.dirname(path)
            folders.setdefault(folder, []).append(os.path.basename(path))

        for folder, files in folders.items():
            self.json["codebase"]["folders"].append({
                "path": folder + "/" if folder else "./",
                "files": files,
                "summary": None,
                "responsibilities": []
            })

    def _build_file_objects(self):
        files = {}

        for sym in self.symbol_defs.values():
            files.setdefault(sym["file"], {"classes": [], "functions": []})

        for sym in self.symbol_defs.values():
            if sym["type"] == "class":
                files[sym["file"]]["classes"].append({
                    "name": sym["name"],
                    "qualified_name": sym["qualified_name"],
                    "symbol_type": "class",
                    "class_type": None,
                    "class_inherits_from": sym["inherits_from"],
                    "class_methods": sym["methods"],
                    "code_range": sym["code_range"],
                    "summary": None
                })

            if sym["type"] == "function":
                files[sym["file"]]["functions"].append({
                    "name": sym["name"],
                    "qualified_name": sym["qualified_name"],
                    "symbol_type": "function",
                    "async": False,
                    "calls": list(sym["calls"]),
                    "called_by": list(sym["called_by"]),
                    "used_as_callback_by": [
                        {
                            "used_by": cb,
                            "confidence": "static",
                            "reason": "Passed as identifier"
                        }
                        for cb in sym["callbacks"]
                    ],
                    "control_flow": sym["control_flow"],
                    "code_range": sym["code_range"],
                    "summary": None
                })

        for file_path, data in files.items():
            self.json["codebase"]["files"].append({
                "path": file_path,
                "imports": self.imports[file_path],
                "entry_points": [],
                "classes": data["classes"],
                "functions": data["functions"],
                "summary": None
            })

    # =========================================================
    # UTIL
    # =========================================================

    def _range(self, node):
        return {
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1
        }
    
    def _load_gitignore(self):
        gitignore_path = os.path.join(self.root_path, ".gitignore")
        if not os.path.exists(gitignore_path):
            return None

        with open(gitignore_path, "r", encoding="utf-8") as f:
            patterns = f.read().splitlines()

        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            patterns
        )
        
    def _is_ignored(self, relative_path: str) -> bool:
        if not self.gitignore:
            return False
        return self.gitignore.match_file(relative_path)




# import os
# from tree_sitter import Parser, Language
# import tree_sitter_python


# class CodeIndexer:
#     def __init__(self):
#         self.parser = Parser()
#         self.parser.language = Language(tree_sitter_python.language())

#         # ---------- Core stores ----------
#         self.files = {}                 # file_path -> source
#         self.module_map = {}            # module_name -> file_path

#         self.symbols = {}               # qualified_name -> metadata
#         self.calls = {}                 # caller -> set(callees)
#         self.called_by = {}             # callee -> set(callers)
#         self.references = {}            # symbol -> set(referrers)
#         self.callback_used_by = {}      # callback -> set(functions)

#         self.import_bindings = {}        # file -> local_name -> qualified_name
#         self.type_bindings = {}          # function -> var_name -> class_name

#         self.entry_points = []           # detected entry points

#     # =========================================================
#     # INDEXING
#     # =========================================================

#     def index_folder(self, folder_path: str):
#         self._build_module_map(folder_path)

#         for root, _, files in os.walk(folder_path):
#             for file in files:
#                 if file.endswith(".py"):
#                     self._index_file(os.path.join(root, file))

#     def _build_module_map(self, folder_path: str):
#         for root, _, files in os.walk(folder_path):
#             for file in files:
#                 if file.endswith(".py"):
#                     full_path = os.path.join(root, file)
#                     rel = os.path.relpath(full_path, folder_path)
#                     module = rel[:-3].replace(os.sep, ".")
#                     if module.endswith(".__init__"):
#                         module = module.replace(".__init__", "")
#                     self.module_map[module] = full_path

#     def _index_file(self, file_path: str):
#         with open(file_path, "r", encoding="utf-8") as f:
#             source = f.read()

#         tree = self.parser.parse(source.encode("utf8"))
#         self.files[file_path] = source
#         self.import_bindings[file_path] = {}

#         self._walk(
#             tree.root_node,
#             file_path,
#             current_class=None,
#             current_function=None
#         )

#     # =========================================================
#     # AST WALK
#     # =========================================================

#     def _walk(self, node, file_path, current_class, current_function):
#         # ---------- Class ----------
#         if node.type == "class_definition":
#             name_node = node.child_by_field_name("name")
#             if name_node:
#                 class_name = name_node.text.decode()
#                 self._store_symbol(class_name, "class", node, file_path)
#                 current_class = class_name

#         # ---------- Function / Method ----------
#         if node.type == "function_definition":
#             name_node = node.child_by_field_name("name")
#             if name_node:
#                 fn = name_node.text.decode()
#                 qname = f"{current_class}.{fn}" if current_class else fn

#                 self._store_symbol(
#                     qname,
#                     "method" if current_class else "function",
#                     node,
#                     file_path
#                 )

#                 self.calls.setdefault(qname, set())
#                 self.called_by.setdefault(qname, set())
#                 self.type_bindings[qname] = {}

#                 self._extract_type_hints(node, qname)
#                 current_function = qname

#         # ---------- Imports ----------
#         if node.type in ("import_statement", "import_from_statement"):
#             self._extract_imports(node, file_path)

#         # ---------- Direct calls ----------
#         if node.type == "call" and current_function:
#             callee = self._resolve_call(node, file_path, current_function)
#             if callee:
#                 self.calls[current_function].add(callee)
#                 self.called_by.setdefault(callee, set()).add(current_function)

#             # ALSO inspect arguments for callbacks
#             self._extract_callbacks_from_call(node, current_function, file_path)

#         # ---------- Assignment-based callbacks ----------
#         if node.type == "assignment" and current_function:
#             self._extract_callbacks_from_assignment(node, current_function, file_path)

#         # ---------- Decorators ----------
#         if node.type == "decorator" and current_function:
#             self._extract_callbacks_from_decorator(node, current_function, file_path)

#         # ---------- Entry points ----------
#         self._detect_entry_points(node, file_path)

#         for child in node.children:
#             self._walk(child, file_path, current_class, current_function)

#     # =========================================================
#     # HELPERS
#     # =========================================================

#     def _store_symbol(self, name, kind, node, file_path):
#         self.symbols[name] = {
#             "type": kind,
#             "file": file_path,
#             "start_line": node.start_point[0],
#             "end_line": node.end_point[0]
#         }

#     def _extract_imports(self, node, file_path):
#         if node.type == "import_statement":
#             for child in node.children:
#                 if child.type == "dotted_name":
#                     mod = child.text.decode()
#                     self.import_bindings[file_path][mod.split(".")[-1]] = mod

#         if node.type == "import_from_statement":
#             module_node = node.child_by_field_name("module")
#             if not module_node:
#                 return

#             module = module_node.text.decode()
#             for child in node.children:
#                 if child.type == "import_list":
#                     for item in child.children:
#                         if item.type == "identifier":
#                             name = item.text.decode()
#                             self.import_bindings[file_path][name] = f"{module}.{name}"

#     def _extract_type_hints(self, fn_node, fn_name):
#         params = fn_node.child_by_field_name("parameters")
#         if not params:
#             return

#         for child in params.children:
#             if child.type == "typed_parameter":
#                 name = child.child_by_field_name("name")
#                 type_node = child.child_by_field_name("type")
#                 if name and type_node:
#                     self.type_bindings[fn_name][
#                         name.text.decode()
#                     ] = type_node.text.decode()

#     def _resolve_call(self, call_node, file_path, current_function):
#         fn_node = call_node.child_by_field_name("function")
#         if not fn_node:
#             return None

#         # foo()
#         if fn_node.type == "identifier":
#             name = fn_node.text.decode()
#             return self._resolve_import(name, file_path)

#         # obj.method()
#         if fn_node.type == "attribute":
#             obj = fn_node.child_by_field_name("object")
#             attr = fn_node.child_by_field_name("attribute")
#             if not obj or not attr:
#                 return None

#             var = obj.text.decode()
#             method = attr.text.decode()

#             var_type = self.type_bindings.get(current_function, {}).get(var)
#             if var_type:
#                 return f"{var_type}.{method}"

#             return method

#         return None

#     def _resolve_import(self, name, file_path):
#         if name in self.import_bindings[file_path]:
#             return self.import_bindings[file_path][name]
#         return name

#     def _detect_entry_points(self, node, file_path):
#         # FastAPI decorators
#         if node.type == "decorator":
#             text = node.text.decode()
#             if ".get(" in text or ".post(" in text or ".put(" in text or ".delete(" in text:
#                 self.entry_points.append({
#                     "type": "http",
#                     "decorator": text,
#                     "file": file_path
#                 })

#         # CLI decorators
#         if node.type == "decorator" and ".command(" in node.text.decode():
#             self.entry_points.append({
#                 "type": "cli",
#                 "file": file_path
#             })

#         # __main__
#         if node.type == "if_statement":
#             cond = node.child_by_field_name("condition")
#             if cond and "__name__" in cond.text.decode():
#                 self.entry_points.append({
#                     "type": "main",
#                     "file": file_path
#                 })

#     def _extract_callbacks_from_call(self, call_node, current_function, file_path):
#         args = call_node.child_by_field_name("arguments")
#         if not args:
#             return

#         for arg in args.children:
#             if arg.type == "identifier":
#                 cb = arg.text.decode()
#                 cb = self._resolve_import(cb, file_path)
#                 self.callback_used_by.setdefault(cb, set()).add(current_function)


#     def _extract_callbacks_from_assignment(self, assign_node, current_function, file_path):
#         right = assign_node.child_by_field_name("right")
#         if right and right.type == "identifier":
#             cb = right.text.decode()
#             cb = self._resolve_import(cb, file_path)
#             self.callback_used_by.setdefault(cb, set()).add(current_function)


#     def _extract_callbacks_from_decorator(self, decorator_node, current_function, file_path):
#         call = decorator_node.child_by_field_name("call")
#         if not call:
#             return

#         args = call.child_by_field_name("arguments")
#         if not args:
#             return

#         for arg in args.children:
#             if arg.type == "identifier":
#                 cb = arg.text.decode()
#                 cb = self._resolve_import(cb, file_path)
#                 self.callback_used_by.setdefault(cb, set()).add(current_function)
#     # =========================================================
#     # TRACE GRAPH
#     # =========================================================

#     def trace(self, start_symbol: str, depth: int = 3):
#         visited = set()
#         result = {}

#         def dfs(symbol, d):
#             if d == 0 or symbol in visited:
#                 return

#             visited.add(symbol)
#             result[symbol] = list(self.calls.get(symbol, []))

#             for callee in self.calls.get(symbol, []):
#                 dfs(callee, d - 1)

#         dfs(start_symbol, depth)
#         return result

#     # =========================================================
#     # RETRIEVAL
#     # =========================================================

#     def get_symbol_code(self, symbol: str):
#         meta = self.symbols.get(symbol)
#         if not meta:
#             return None

#         lines = self.files[meta["file"]].splitlines()
#         return {
#             "file": meta["file"],
#             "code": "\n".join(lines[meta["start_line"]: meta["end_line"] + 1])
#         }
