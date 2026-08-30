import logging
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from src.config import get_llm

logger = logging.getLogger(__name__)

class BrandName(BaseModel):
    formatted_name: str = Field(description="The correctly formatted, official, human-readable brand name.")

async def normalize_brand_name(raw_name: str) -> str:
    """Takes a raw string like '1800contacts' and returns '1-800 Contacts' using the LLM."""
    # Fast path: If it already looks formatted (has spaces or hyphens), just capitalize it
    if " " in raw_name or "-" in raw_name:
        return raw_name.title()
        
    llm = get_llm()
    parser = PydanticOutputParser(pydantic_object=BrandName)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a precise brand name formatter. Your job is to take a compressed string and return the proper, official, human-readable brand name used in commerce.\n\nExamples:\n- '1800contacts' -> '1-800 Contacts'\n- '1password' -> '1Password'\n- 'bedbathandbeyond' -> 'Bed Bath & Beyond'\n- 'nike' -> 'Nike'\n\nOutput only the formatted name in JSON according to the exact schema."),
        ("user", "Format this brand string: {raw_name}\n\n{format_instructions}")
    ])
    
    try:
        chain = prompt | llm | parser
        result = await chain.ainvoke({
            "raw_name": raw_name,
            "format_instructions": parser.get_format_instructions()
        })
        return result.formatted_name
    except Exception as e:
        logger.warning(f"Failed to normalize brand {raw_name}: {e}")
        return raw_name # Fallback to original if LLM fails
