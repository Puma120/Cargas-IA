import re
import unicodedata
from typing import Any

def normalize_header(header: Any) -> str:
    """
    Normalizes headers: removes accents, converts to snake_case, 
    removes special characters, and cleans whitespace.
    Example: "Cod. Activo (Interno)" -> "cod_activo_interno"
    """
    if header is None:
        return "unnamed_column"
    
    # Convert to string
    text = str(header).strip()
    
    # Remove accents (Normalization Form D separates characters from accents)
    text = unicodedata.normalize('NFD', text)
    text = "".join([c for c in text if unicodedata.category(c) != 'Mn'])
    
    # Replace non-alphanumeric characters with underscores
    text = re.sub(r'[^a-zA-Z0-9]+', '_', text)
    
    # Remove leading/trailing underscores and convert to lowercase
    text = text.strip('_').lower()
    
    return text if text else "unnamed_column"
