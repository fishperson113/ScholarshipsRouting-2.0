# dtos/search_dtos.py

from pydantic import BaseModel, Field
from typing import List, Union, Literal

class FilterItem(BaseModel):
    """Định nghĩa cấu trúc cho một tiêu chí lọc."""
    field: str = Field(..., description="Tên trường cần lọc trong document, ví dụ: 'Country'")
    values: List[Union[str, int, float, bool]] = Field(..., description="Danh sách các giá trị cần lọc")
    operator: Literal["AND", "OR"] = Field("OR", description="Toán tử áp dụng cho các giá trị trong list `values`")
