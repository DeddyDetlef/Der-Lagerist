from typing import Optional, List
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    code: str = Field(..., min_length=1, description='Eindeutiger QR-/Lagerecode')
    name: Optional[str] = ''
    category: Optional[str] = 'sonstiges'
    description: Optional[str] = ''
    location: Optional[str] = ''
    quantity: Optional[float] = 0
    unit: Optional[str] = ''


class ItemCreate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = ''
    category: Optional[str] = 'sonstiges'
    description: Optional[str] = ''
    location: Optional[str] = ''
    quantity: Optional[float] = 0
    unit: Optional[str] = ''
    t14_gen: Optional[str] = None
    owners: Optional[str] = None
    notes: Optional[str] = None
    sina_token: Optional[str] = None
    rma_date: Optional[str] = None
    rma_description: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    t14_gen: Optional[str] = None
    owners: Optional[str] = None
    notes: Optional[str] = None
    sina_token: Optional[str] = None
    rma_date: Optional[str] = None
    rma_description: Optional[str] = None


class LaptopDetails(BaseModel):
    t14_gen: Optional[str] = ''
    owners: Optional[str] = ''
    notes: Optional[str] = ''


class Rma(BaseModel):
    id: Optional[int] = None
    item_id: Optional[int] = None
    rma_date: str
    description: Optional[str] = ''


class Item(ItemBase):
    id: int
    updated_at: str
    details: Optional[LaptopDetails] = None
    rmas: List[Rma] = []
