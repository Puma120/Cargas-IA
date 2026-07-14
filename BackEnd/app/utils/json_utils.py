import json
from datetime import datetime, date
import pandas as pd
import numpy as np

def safe_json_dumps(obj, **kwargs):
    """
    Serializador robusto que convierte datetimes, timestamps y tipos de numpy
    a strings para evitar errores de 'not JSON serializable'.
    """
    def default_serializer(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, (pd.Timestamp, pd.NaT)):
            return str(o)
        if isinstance(o, (np.integer, np.floating)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        return str(o)
    
    return json.dumps(obj, default=default_serializer, **kwargs)
