from fastapi import APIRouter,Depends
from src.controllers import study as controller
from src.schemas.entities import ControlStudyInput,StudyRevisionInput
from src.services.auth import current,editor,admin
router=APIRouter(prefix="/studies",tags=["studies"])
@router.get("")
def list_items(user=Depends(current)): return controller.list_items()
@router.post("",status_code=201)
def create(data:ControlStudyInput,user=Depends(editor)): return controller.create(data,user)
@router.get("/{id}/revisions")
def list_revisions(id:str,user=Depends(current)): return controller.list_revisions(id)
@router.post("/{id}/revisions",status_code=201)
def revise(id:str,data:StudyRevisionInput,user=Depends(editor)): return controller.revise(id,data,user)
