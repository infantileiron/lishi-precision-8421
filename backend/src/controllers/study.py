from src.services import study as service
def list_items(): return service.list_studies()
def list_revisions(id): return service.list_revisions(id)
def create(data,user): return service.create(data,user)
def revise(id,data,user): return service.revise(id,data,user)
