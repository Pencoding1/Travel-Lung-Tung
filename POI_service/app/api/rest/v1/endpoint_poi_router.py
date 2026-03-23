import traceback
import logging

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, status

from app.core.domain.get_payload import POIGetResponse
from app.core.services.management import POIManagementService
from app.core.interfaces.repositories import IDocumentRepository

from app.api.dependencies.services import (
    get_poi_management_service, 
    get_document_repository, 
)
from app.core.security.auth import verify_jwt_token

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/pois", tags=["POI Retrieval"])

@router.get(
    "/{poi_id}", 
    response_model=POIGetResponse,
    summary="Get Agentic POI Payload",
    description="Retrieves POI data. Degrades gracefully if Document RAG is uninitialized.",
    responses={
        200: {"description": "Successful retrieval (Full or Partial)"},
        404: {"description": "POI not found in Knowledge Graph"},
        500: {"description": "Internal server error"}
    }
)
def get_poi(
    poi_id: str,
    current_user: dict = Depends(verify_jwt_token),
    poi_service: POIManagementService = Depends(get_poi_management_service),
    doc_repo: IDocumentRepository = Depends(get_document_repository)
):
    try:
        # The service returns a Pydantic object with success=True
        return poi_service.get_agentic_poi_details(poi_id=poi_id, doc_repo=doc_repo)
        
    except ValueError as e:
        # Explicit 404 Handling: The POI does not exist in Memgraph
        # We return success=False and nullify the result object
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False, 
                "result": None,
                "detail": str(e)
            }
        )
        
    except Exception as e:
        tb_str = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error(f"GLOBAL CRASH in get_poi: {str(e)}\n{tb_str}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False, 
                "result": None,
                "detail": f"Internal Error: {str(e)}",
                "traceback": tb_str # Now a serializable string
            }
        )