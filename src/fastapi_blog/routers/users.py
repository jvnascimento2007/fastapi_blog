from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import OAuth2PasswordRequestForm

from datetime import timedelta

import fastapi_blog.models as models
from fastapi_blog.config import settings
from fastapi_blog.database import get_db
from fastapi_blog.schemas import (
    UserCreate,
    UserPublic,
    UserPrivate,
    UserUpdate,
    Token
)

from fastapi_blog.auth import (
    CurrentUser,
    create_access_token,
    verify_access_token,
    hash_password,
    verify_password,
    oauth2_scheme
)

router = APIRouter()

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Look up user by email (case-insensitive)
    # Note: OAuth2PasswordRequestForm uses "username" field, but we treat it as email
    result = await db.execute(
        select(models.User).where(
            func.lower(models.User.email) == form_data.username.lower(),
        ),
    )
    user = result.scalars().first()

    # Verify user exists and password is correct
    # Don't reveal which one failed (security best practice)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token with user id as subject
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token, token_type="bearer")

@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user

@router.get('', response_model=list[UserPublic])
async def get_users(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User))
    users = result.scalars().all()
    return users

@router.post(
    '',
    response_model=UserPrivate,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.User).where(func.lower(models.User.username) == user.username.lower())
    )

    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Username already exists'
        )

    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )

    existing_user = result.scalars().all()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Email already registered'
        )

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user

@router.get('/{user_id}', response_model=UserPublic)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    return user

@router.patch('/{user_id}', response_model=UserPrivate)
async def update_user(user_id: int, user_data: UserUpdate, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Not authorized to patch this user')

    if user_data.username is not None and user_data.username != current_user.username:
        result = await db.execute(
            select(models.User).where(func.lower(models.User.username) == user_data.username.lower())
        )

        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already registered')

    if user_data.email is not None and user_data.email != current_user.email:
        result = await db.execute(select(models.User).where(func.lower(models.User.email) == user_data.email.lower()))

        existing_email = result.scalars().first()

        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Email already registered')

        user_data.email = user_data.email.lower()

    update_data = user_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user

@router.delete('/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, current_user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]):
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Not authorized to delete this user')

    await db.delete(current_user)
    await db.commit()