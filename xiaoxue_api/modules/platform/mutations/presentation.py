from fastapi import APIRouter, Body, HTTPException

from .service import MutationRejected, apply_business_mutation

router = APIRouter(prefix='/api/business-mutations', tags=['business-mutations'])


@router.post('/apply')
def apply_mutation(payload: dict = Body(...)) -> dict:
    try:
        return apply_business_mutation(
            target_type=payload.get('target_type', ''),
            target=payload.get('target', ''),
            changes=payload.get('changes') or {},
            reason=payload.get('reason', ''),
        )
    except MutationRejected as exc:
        raise HTTPException(422, str(exc)) from exc
