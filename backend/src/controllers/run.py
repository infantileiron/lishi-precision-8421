from src.services import run as service
from src.utils import repository as repo
def list_items(): return service.list_runs()
def detail(id): return service.detail(id)
def create(data,user): return service.create(data)
