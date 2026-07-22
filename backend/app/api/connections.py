from fastapi import APIRouter, Response, status

from backend.app.models.connection import ConnectionInput, ConnectionProfile
from backend.app.services.connections import (
    create_connection,
    delete_connection,
    list_connections,
    update_connection,
)

router = APIRouter(prefix="/api/v1/connections", tags=["connections"])


@router.get("", response_model=list[ConnectionProfile])
def get_connections() -> list[ConnectionProfile]:
    return list_connections()


@router.post("", response_model=ConnectionProfile, status_code=status.HTTP_201_CREATED)
def post_connection(value: ConnectionInput) -> ConnectionProfile:
    return create_connection(value)


@router.put("/{profile_id}", response_model=ConnectionProfile)
def put_connection(profile_id: str, value: ConnectionInput) -> ConnectionProfile:
    return update_connection(profile_id, value)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_connection(profile_id: str) -> Response:
    delete_connection(profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
