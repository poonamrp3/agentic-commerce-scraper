from langchain_openai import ChatOpenAI

def get_llm():
    """
    Returns the LLM instance pointing to the local proxy.
    """
    return ChatOpenAI(
        model="gemini-advanced", # Adjust if your local proxy uses a different model name mapping
        base_url="http://localhost:4981/openai/v1",
        api_key="dummy-key-not-needed",
        temperature=0, # We want deterministic JSON output for our planning
    )
