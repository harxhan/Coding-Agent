class SummaryBuilder:
    def __init__(self, index_json: dict, file_sources: dict, ollama_client):
        """
        index_json   -> output from CodeIndexer.index()
        file_sources -> CodeIndexer.files_source
        """
        self.index = index_json
        self.sources = file_sources
        self.ollama = ollama_client

    # =========================================================
    # PUBLIC API
    # =========================================================

    def build_all_summaries(self):
        self._build_function_summaries()
        self._build_class_summaries()
        self._build_file_summaries()

    # =========================================================
    # FUNCTION SUMMARIES
    # =========================================================

    def _build_function_summaries(self):
        for file in self.index["codebase"]["files"]:
            path = file["path"]
            source = self.sources.get(path)

            if not source:
                continue

            lines = source.splitlines()

            for fn in file["functions"]:
                if fn["summary"]:
                    continue

                code = self._slice_code(lines, fn["code_range"])
                prompt = self._function_prompt(code)

                fn["summary"] = self.ollama.generate(prompt)

    # =========================================================
    # CLASS SUMMARIES
    # =========================================================

    def _build_class_summaries(self):
        for file in self.index["codebase"]["files"]:
            path = file["path"]
            source = self.sources.get(path)

            if not source:
                continue

            lines = source.splitlines()

            for cls in file["classes"]:
                if cls["summary"]:
                    continue

                code = self._slice_code(lines, cls["code_range"])
                prompt = self._class_prompt(code)

                cls["summary"] = self.ollama.generate(prompt)

    # =========================================================
    # FILE SUMMARIES
    # =========================================================

    def _build_file_summaries(self):
        for file in self.index["codebase"]["files"]:
            if file["summary"]:
                continue

            imports = "\n".join(file["imports"])
            symbols = []

            for fn in file["functions"]:
                symbols.append(f"function: {fn['name']}")

            for cls in file["classes"]:
                symbols.append(f"class: {cls['name']}")

            prompt = self._file_prompt(imports, symbols)
            file["summary"] = self.ollama.generate(prompt)

    # =========================================================
    # PROMPTS
    # =========================================================

    def _function_prompt(self, code: str) -> str:
        return f"""
            You are a senior Python engineer.

            Summarize the purpose of the following function in 1–2 sentences.
            Do not speculate. Be precise.

            FUNCTION CODE:
            {code}
        """

    def _class_prompt(self, code: str) -> str:
        return f"""
            You are a senior Python engineer.

            Summarize the responsibility of the following class.
            Mention the type of class if obvious (e.g. data model, utility).

            CLASS CODE:
            {code}
        """

    def _file_prompt(self, imports: str, symbols: list) -> str:
        symbols_text = "\n".join(symbols)

        return f"""
            You are a senior Python engineer.

            Given the following information about a file, summarize its responsibility.

            IMPORTS:
            {imports}

            DEFINED SYMBOLS:
            {symbols_text}

            Do not speculate beyond what is shown.
        """

    # =========================================================
    # UTIL
    # =========================================================

    def _slice_code(self, lines: list, code_range: dict) -> str:
        start = code_range["start_line"] - 1
        end = code_range["end_line"]
        return "\n".join(lines[start:end])
