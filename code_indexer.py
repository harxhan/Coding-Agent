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
        self.files_source = {}
        self.imports = {}

        self.symbol_defs = {}
        self.calls = {}
        self.called_by = {}
        self.callback_used_by = {}

        self.gitignore = self._load_gitignore()

        # ---------------- Final JSON ----------------
        self.json = {
            "repo_id": repo_id,
            "root_path": root_path,
            "metadata": {
                "language": "python",
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
                "external_dependencies": [],
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
        self._populate_external_dependencies()
        self._resolve_calls_and_called_by()
        self._build_folder_index()
        self._build_file_objects()
        return self.json

    # =========================================================
    # REPO WALK
    # =========================================================

    def _walk_repo(self):
        for root, dirs, files in os.walk(self.root_path):
            rel_root = os.path.relpath(root, self.root_path)

            dirs[:] = [
                d for d in dirs
                if not self._is_ignored(os.path.join(rel_root, d))
            ]

            for file in files:
                rel_path = os.path.join(rel_root, file)

                if self._is_ignored(rel_path):
                    continue

                if file.endswith(".py"):
                    self._index_file(os.path.join(root, file))

    def _index_file(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        rel_path = os.path.relpath(file_path, self.root_path)
        self.files_source[rel_path] = source
        self.imports[rel_path] = []

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
        if node.type in ("import_statement", "import_from_statement"):
            import_text = node.text.decode().strip()
            
            # Store full import line
            self.imports[file_path].append(import_text)    
        
        # ---------- Calls ----------
        if node.type == "call" and current_function:
            fn_node = node.child_by_field_name("function")

            if fn_node:
                # Case 1: simple call: foo()
                if fn_node.type == "identifier":
                    callee = fn_node.text.decode()
                    self.symbol_defs[current_function]["calls"].add(callee)
                    self.called_by.setdefault(callee, set()).add(current_function)

                # Case 2: attribute call: obj.method()
                elif fn_node.type == "attribute":
                    attr = fn_node.child_by_field_name("attribute")
                    if attr:
                        callee = attr.text.decode()
                        self.symbol_defs[current_function]["calls"].add(callee)
                        self.called_by.setdefault(callee, set()).add(current_function)     
                        
                                           
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
                "classes": data["classes"],
                "functions": data["functions"],
                "summary": None
            })
    
    def _build_symbol_name_index(self):
        """
        Maps short function names to fully-qualified names.
        Example:
        decode_token -> utils.helpers.decode_token
        """
        name_index = {}

        for qname, meta in self.symbol_defs.items():
            if meta["type"] == "function":
                short = meta["name"]
                name_index.setdefault(short, []).append(qname)

        return name_index
    
    def _resolve_calls_and_called_by(self):
        name_index = self._build_symbol_name_index()

        # Initialize called_by
        for meta in self.symbol_defs.values():
            if meta["type"] == "function":
                meta["called_by"] = set()

        # Resolve calls
        for caller_qname, caller_meta in self.symbol_defs.items():
            if caller_meta["type"] != "function":
                continue

            resolved_calls = set()

            for callee in caller_meta["calls"]:
                candidates = name_index.get(callee, [])

                if len(candidates) == 1:
                    resolved = candidates[0]
                    resolved_calls.add(resolved)

                    # reverse edge
                    self.symbol_defs[resolved]["called_by"].add(caller_qname)
                else:
                    # unresolved or external
                    resolved_calls.add(callee)

            caller_meta["calls"] = resolved_calls

    def _populate_external_dependencies(self):
        stdlib = self._get_stdlib_modules()

        reqs = self._read_requirements_txt()
        if reqs:
            self.json["metadata"]["external_dependencies"] = sorted(
                dep for dep in reqs if dep not in stdlib
            )
            return

        inferred = self._infer_external_dependencies_from_imports()
        self.json["metadata"]["external_dependencies"] = sorted(
            dep for dep in inferred if dep not in stdlib
        )
        
    def _read_requirements_txt(self):
        req_path = os.path.join(self.root_path, "requirements.txt")
        if not os.path.exists(req_path):
            return None

        dependencies = set()

        with open(req_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                # ignore comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # strip version specifiers
                for sep in ("==", ">=", "<=", "~=", ">", "<"):
                    if sep in line:
                        line = line.split(sep)[0]
                        break

                dependencies.add(line)

        return dependencies

    def _infer_external_dependencies_from_imports(self):
        """
        Infer dependencies by:
        - extracting top-level modules from import lines
        - excluding repo-internal folders
        """
        internal_modules = self._get_internal_modules()
        external_deps = set()

        for imports in self.imports.values():
            for import_line in imports:
                # Normalize: remove "import" / "from"
                if import_line.startswith("import "):
                    remainder = import_line[len("import "):]
                    top = remainder.split()[0].split(".")[0]

                elif import_line.startswith("from "):
                    remainder = import_line[len("from "):]
                    top = remainder.split()[0].split(".")[0]

                else:
                    continue

                if top and top not in internal_modules:
                    external_deps.add(top)

        return external_deps

    def _get_internal_modules(self):
        """
        Repo-internal modules are top-level folders in the repo root.
        """
        modules = set()

        for item in os.listdir(self.root_path):
            full = os.path.join(self.root_path, item)
            if os.path.isdir(full) and not item.startswith("."):
                modules.add(item)

        return modules

    def _get_stdlib_modules(self):
        try:
            return set(sys.stdlib_module_names)
        except AttributeError:
            # Fallback (very old Python)
            return set()
    # =========================================================
    # UTIL
    # =========================================================

    def _range(self, node):
        return {
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1
        }

    def _load_gitignore(self):
        path = os.path.join(self.root_path, ".gitignore")
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            patterns = f.read().splitlines()

        return pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            patterns
        )

    def _is_ignored(self, relative_path: str) -> bool:
        if not self.gitignore:
            return False
        return self.gitignore.match_file(relative_path)
