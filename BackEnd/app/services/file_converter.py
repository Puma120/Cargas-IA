import pandas as pd
import numpy as np
import openpyxl
from io import BytesIO
from typing import List, Dict, Any
import logging
from app.utils.header_utils import normalize_header

logger = logging.getLogger(__name__)

class FileConverterService:
    @staticmethod
    def _get_merged_cell_value(ws, row, col):
        """
        Checks if a cell is part of a merged range and returns the
        value of the top-left cell of that range.
        """
        for merged_range in ws.merged_cells.ranges:
            min_col, min_row, max_col, max_row = merged_range.bounds
            if min_row <= row <= max_row and min_col <= col <= max_col:
                return ws.cell(row=min_row, column=min_col).value
        return ws.cell(row=row, column=col).value

    @staticmethod
    def _detect_header_row(ws):
        """
        Detects the header row dynamically by finding the row with
        the highest density of non-null values among the first 100 rows.
        """
        max_non_nulls = -1
        header_row_idx = 1

        for row_idx in range(1, min(101, ws.max_row + 1)):
            row_values = [FileConverterService._get_merged_cell_value(ws, row_idx, col) for col in range(1, ws.max_column + 1)]
            non_null_count = sum(1 for v in row_values if v is not None)

            if non_null_count > max_non_nulls:
                max_non_nulls = non_null_count
                header_row_idx = row_idx

        return header_row_idx

    @staticmethod
    async def convert_to_json(file_content: bytes, filename: str) -> List[Dict[str, Any]]:
        """
        Converts CSV or Excel file content to a segmented JSON structure.
        Segments data into: document_metadata_raw, table_rows_raw, summary_rows_raw, and footer_metadata_raw.
        """
        try:
            all_sheets_processed = []
            if filename.endswith('.csv'):
                df = pd.read_csv(BytesIO(file_content))
                cleaned_df = df.where(pd.notnull(df), None)
                all_sheets_processed.append({
                    "sheet_name": "default",
                    "document_metadata_raw": [],
                    "table_rows_raw": cleaned_df.to_dict(orient='records'),
                    "summary_rows_raw": [],
                    "footer_metadata_raw": [],
                    "form_selections_raw": []
                })
            
            elif filename.endswith(('.xlsx', '.xls')):
                wb = openpyxl.load_workbook(BytesIO(file_content), data_only=True)
                
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    
                    # 1. Detect Header Row
                    header_row_idx = FileConverterService._detect_header_row(ws)
                    
                    # 2. Extract Document Metadata (Rows before header)
                    metadata_raw = []
                    for row_idx in range(1, header_row_idx):
                        row_data = {f"col_{col}": FileConverterService._get_merged_cell_value(ws, row_idx, col) 
                                    for col in range(1, ws.max_column + 1)}
                        if any(v is not None for v in row_data.values()):
                            metadata_raw.append({"_row_index": row_idx, "data": row_data})
                    
                    # 3. Extract Headers for the table
                    raw_headers = [FileConverterService._get_merged_cell_value(ws, header_row_idx, col) 
                                   for col in range(1, ws.max_column + 1)]
                    
                    # 4. Extract Rows and Classify (Table vs Summary vs Footer)
                    table_rows = []
                    summary_rows = []
                    footer_rows = []
                    
                    for row_idx in range(header_row_idx + 1, ws.max_row + 1):
                        row_dict = {}
                        row_values = []
                        
                        for col_idx, header_val in enumerate(raw_headers, start=1):
                            val = FileConverterService._get_merged_cell_value(ws, row_idx, col_idx)
                            row_values.append(val)
                            norm_header = normalize_header(header_val)
                            
                            row_dict[norm_header] = {
                                "value": val,
                                "original_header": str(header_val) if header_val else "unnamed"
                            }
                        
                        # Exhaustive Classification Logic
                        # a) Summary Row
                        if any(val and any(keyword in str(val).upper() for keyword in ["TOTAL", "SUBTOTAL", "SUMA"]) for val in row_values):
                            summary_rows.append({"_row_index": row_idx, "data": row_dict})
                        
                        # b) Table Record: Any row with at least one value is a potential record
                        elif any(v is not None for v in row_values):
                            # If it's a table record, add it to table_rows
                            if any(v['value'] is not None for v in row_dict.values()):
                                table_rows.append(row_dict)
                            
                            # Additionally, if the row is sparse (looks like a footer/comment), 
                            # capture it as raw footer data too for AI safety
                            non_null_count = sum(1 for v in row_values if v is not None)
                            if non_null_count < (len(raw_headers) // 2):
                                footer_data = {f"col_{col}": FileConverterService._get_merged_cell_value(ws, row_idx, col) 
                                              for col in range(1, ws.max_column + 1)}
                                footer_rows.append({"_row_index": row_idx, "data": footer_data})
                        
                        # c) Fallback: Row exists but didn't fit table/summary logic
                        else:
                            footer_data = {f"col_{col}": FileConverterService._get_merged_cell_value(ws, row_idx, col) 
                                          for col in range(1, ws.max_column + 1)}
                            if any(v is not None for v in footer_data.values()):
                                footer_rows.append({"_row_index": row_idx, "data": footer_data})
                    
                    all_sheets_processed.append({
                        "sheet_name": sheet_name,
                        "document_metadata_raw": metadata_raw,
                        "table_rows_raw": table_rows,
                        "summary_rows_raw": summary_rows,
                        "footer_metadata_raw": footer_rows,
                        "form_selections_raw": []
                    })
            else:
                raise ValueError("Unsupported file format. Please provide a .csv, .xlsx, or .xls file.")

            return all_sheets_processed
