from typing import Dict, Any, List, Union

RowDict          = Dict[str, Any]            # One row: tag → value
ColumnarDict     = Dict[str, List[Any]]      # One column per tag
RowMatrix        = List[List[Any]]           # Matrix of rows (format #3)
FlatRow          = List[Any]                 # One flat row (format #4)

DataInput = Union[
    RowDict,                 # format #1 – single row
    List[RowDict],           # format #1 – many rows
    ColumnarDict,            # format #2 – columnar
    RowMatrix,               # format #3 – list of lists
    FlatRow,                 # format #4 – flat list
]
