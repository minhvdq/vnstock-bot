import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from typing import Annotated
from app.core.config import SECRET_KEY, ALGORITHM
from app.models.user import User
from app.services.user_service import get_by_id

async def authen_restricted(request: Request):
    autho = request.headers.get("authorization")
    if(not autho or not autho.startswith("Bearer ")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You are not authenticated!"
        )

    token = autho.replace("Bearer ", "")
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, ALGORITHM)
        if not decoded_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token invalid!"
            )
        print(f"Decode into {decoded_token}")
        user = get_by_id(decoded_token["id"])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Token invalid!"
            )
        request.state.user = user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error decoding token {e}"
        )