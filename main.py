import logging
import time
from fastapi import FastAPI
from pydantic import BaseModel
import ollama

from code_indexer import CodeIndexer

# =========================================================
# LOGGING SETUP
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("DevAgent")

# =========================================================
# FASTAPI APP
# =========================================================
app = FastAPI(title="DevAgent")

# ---------------- CONFIG ----------------
OLLAMA_MODEL = "llama3"
REPO_PATH = "C:\\Harshan's Data\\Projects\\Habit Tracker\\Development\\App-Backend"

# ---------------- INIT ----------------
logger.info("Initializing CodeIndexer...")
start = time.time()

indexer = CodeIndexer()
indexer.index_folder(REPO_PATH)

logger.info(
    "Indexing completed in %.2fs | Symbols=%d | EntryPoints=%d",
    time.time() - start,
    len(indexer.symbols),
    len(indexer.entry_points)
)

# =========================================================
# SCHEMAS
# =========================================================
class ExplainRequest(BaseModel):
    symbol: str
    depth: int = 3


class RefactorRequest(BaseModel):
    symbol: str
    depth: int = 3
    goal: str | None = None  # optional user intent


# =========================================================
# CONTEXT BUILDER
# =========================================================
def build_context(symbol: str, depth: int) -> str:
    logger.info("Building enriched context | symbol=%s depth=%d", symbol, depth)

    sections = []
    seen = set()

    def add_symbol(sym):
        if sym in seen:
            return
        seen.add(sym)

        code = indexer.get_symbol_code(sym)
        if not code:
            return

        sections.append(
            f"\n[file: {code['file']} | symbol: {sym}]\n{code['code']}"
        )

    # --------------------------------------------------
    # 1. ENTRY POINTS THAT REACH THIS SYMBOL
    # --------------------------------------------------
    for ep in indexer.entry_points:
        handler = ep.get("handler")
        if not handler:
            continue

        trace = indexer.trace(handler, depth)
        if symbol in trace:
            logger.info("Entry point '%s' reaches '%s'", handler, symbol)
            add_symbol(handler)

    # --------------------------------------------------
    # 2. PARENTS (CALLERS)
    # --------------------------------------------------
    parents = indexer.called_by.get(symbol, set())
    for parent in parents:
        add_symbol(parent)

    # --------------------------------------------------
    # 3. TARGET SYMBOL
    # --------------------------------------------------
    add_symbol(symbol)

    # --------------------------------------------------
    # 4. CLASS CONTEXT (IF METHOD)
    # --------------------------------------------------
    if "." in symbol:
        class_name = symbol.split(".")[0]
        add_symbol(class_name)

    # --------------------------------------------------
    # 5. CALLEES (CHILD FUNCTIONS)
    # --------------------------------------------------
    trace = indexer.trace(symbol, depth)
    for callee in trace:
        add_symbol(callee)
    
    for user in indexer.callback_used_by.get(symbol, []):
        add_symbol(user)

    logger.info("Context built | symbols=%d", len(sections))
    return "\n".join(sections)


# =========================================================
# OLLAMA HELPERS
# =========================================================
def run_llama(prompt: str) -> str:
    logger.info("Calling Ollama model=%s", OLLAMA_MODEL)
    start = time.time()

    response = ollama.generate(
        model=OLLAMA_MODEL,
        prompt=prompt,
        stream=False
    )

    logger.info("Ollama response received in %.2fs", time.time() - start)
    return response["response"]


# =========================================================
# API ENDPOINTS
# =========================================================

# ---------------- EXPLAIN ----------------
@app.post("/explain")
def explain_code(req: ExplainRequest):
    logger.info("POST /explain | symbol=%s", req.symbol)

    context = build_context(req.symbol, req.depth)
    if not context:
        logger.warning("Symbol not found: %s", req.symbol)
        return {"error": f"Symbol '{req.symbol}' not found"}
    
    print("===============================================================================================================")
    logger.info("Context built: %s", context)
    print("===============================================================================================================")
    
    prompt = f"""
        You are a senior software engineer.

        Understand the following codebase structure and implementation.
        Explain clearly and concisely.

        Focus on:
        - Execution flow
        - Responsibilities of functions/classes
        - Interactions between components

        CODE:
        {context}
    """

    explanation = run_llama(prompt)

    return {
        "symbol": req.symbol,
        "depth": req.depth,
        "explanation": explanation
    }


# ---------------- TRACE (GRAPH ONLY) ----------------
@app.get("/trace/{symbol}")
def trace_symbol(symbol: str, depth: int = 3):
    logger.info("GET /trace | symbol=%s depth=%d", symbol, depth)

    trace = indexer.trace(symbol, depth)
    if not trace:
        logger.warning("Trace not found for symbol=%s", symbol)
        return {"error": f"No trace found for '{symbol}'"}

    return {
        "symbol": symbol,
        "depth": depth,
        "graph": trace
    }


# ---------------- ENTRY POINTS ----------------
@app.get("/entry-points")
def entry_points():
    logger.info("GET /entry-points")

    return {
        "count": len(indexer.entry_points),
        "entry_points": indexer.entry_points
    }


# ---------------- SUGGEST REFACTOR ----------------
@app.post("/suggest-refactor")
def suggest_refactor(req: RefactorRequest):
    logger.info(
        "POST /suggest-refactor | symbol=%s depth=%d",
        req.symbol,
        req.depth
    )

    context = build_context(req.symbol, req.depth)
    if not context:
        logger.warning("Symbol not found: %s", req.symbol)
        return {"error": f"Symbol '{req.symbol}' not found"}

    goal_text = (
        f"Refactor goal: {req.goal}\n"
        if req.goal else
        "Suggest general refactoring improvements.\n"
    )
    
    print("===============================================================================================================")
    logger.info("Context built: %s", context)
    print("===============================================================================================================")

    prompt = f"""
        You are a senior software engineer reviewing code.

        {goal_text}

        Analyze the following code and suggest:
        - Structural refactors
        - Design improvements
        - Simplifications
        - Potential bugs or smells
        - Better abstractions (if any)

        Be practical and specific.
        Do NOT rewrite the entire code unless necessary.

        CODE:
        {context}
    """

    suggestions = run_llama(prompt)

    return {
        "symbol": req.symbol,
        "depth": req.depth,
        "suggestions": suggestions
    }
