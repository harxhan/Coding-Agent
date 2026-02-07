import ollama
import time


class OllamaClient:
    def __init__(self, model: str = "llama3"):
        self.model = model

    def generate(self, prompt: str) -> str:
        start = time.time()

        response = ollama.generate(
            model=self.model,
            prompt=prompt,
            stream=False
        )

        text = response.get("response", "").strip()
        duration = time.time() - start

        print(f"[Ollama] Generated summary in {duration:.2f}s")

        return text
