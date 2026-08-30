import os
from langchain_openai import ChatOpenAI

def get_llm():
    """
    Returns the LLM instance. 
    By default, it uses standard OpenAI config.
    """
    # Allow overriding for local proxies during development
    base_url = os.getenv("OPENAI_BASE_URL", None)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini") # Default to a fast/cheap model
    api_key = os.getenv("OPENAI_API_KEY", "dummy-key-not-needed")
    
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0, # Determinism is required
    )
