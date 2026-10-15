from fastapi import FastAPI, Request, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from typing import Annotated

from sqlalchemy import select
from sqlalchemy.orm import Session

import fastapi_blog.models

from fastapi_blog.database import engine, Base, get_db

from fastapi_blog.schemas import PostResponse, PostCreate, PostUpdate, UserResponse, UserCreate, UserUpdate

Base.metadata.create_all(engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

app.mount('/media', StaticFiles(directory='media'), name='media')

templates = Jinja2Templates(directory='templates')

@app.get('/', include_in_schema=False, name='home')
@app.get('/posts', include_in_schema=False, name='posts')
def home(request: Request, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post))

    posts = result.scalars().all()

    return templates.TemplateResponse(request, 'home.html', {'title': 'Home', 'posts': posts})

@app.get('/posts/{post_id}', include_in_schema=False)
def post_page(request: Request, post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')

    return templates.TemplateResponse(request, 'post.html', {'title': post.title, 'post': post})

@app.get('/users/{user_id}/posts', include_in_schema=False, name='user_posts')
def user_posts(request: Request, user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(
        select(models.User).where(models.User.id == user_id)
    )

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found'
        )

    result = db.execute(
        select(models.Post).where(models.Post.user_id == user_id)
    )

    posts = result.scalars().all()

    return templates.TemplateResponse(
        request,
        'user_posts.html',
        {'title': f'{user.username}\'s posts', 'user': user, 'posts': posts}
    )

@app.get('/api/posts', response_model=list[PostResponse])
def get_posts(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post))

    posts = result.scalars().all()

    return posts

@app.get('/api/posts/{post_id}', response_model=PostResponse)
def get_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if post:
        return post

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')

@app.post(
    "/api/posts",
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_post(post: PostCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(
        select(models.User).where(models.User.id == post.user_id)
    )

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='User not found'
        )

    new_post = models.Post(
        title=post.title,
        content=post.content,
        user_id=post.user_id
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return new_post

@app.put('/api/posts/{post_id}', response_model=PostResponse)
def update_post_all(post_id: int, post_data: PostCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')

    if post_data.user_id != post.user_id:
        result = db.execute(select(models.User).where(models.User.id == post.user_id))

        user = result.scalars().first()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    post.title = post_data.title
    post.content = post_data.content
    post.user_id = post_data.user_id

    db.commit()
    db.refresh(post)

    return post

@app.patch('/api/posts/{post_id}', response_model=PostResponse)
def update_post_partial(post_id: int, post_data: PostUpdate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')

    update_data = post_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)

    return post

@app.delete('/api/posts/{post_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.Post).where(models.Post.id == post_id))

    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Post not found')

    db.delete(post)
    db.commit()

@app.get('/api/users', response_model=list[UserResponse])
def get_users(db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User))
    users = result.scalars().all()
    return users

@app.get('/api/users/{user_id}', response_model=UserResponse)
def get_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    return user

@app.post(
    '/api/users',
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(user: UserCreate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(
        select(models.User).where(models.User.username == user.username)
    )

    existing_user = result.scalars().first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Username already exists'
        )

    result = db.execute(
        select(models.User).where(models.User.email == user.email)
    )

    existing_user = result.scalars().all()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='Email already registered'
        )

    new_user = models.User(
        username=user.username,
        email=user.email,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user

@app.patch('/api/users/{user_id}', response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    if user_data.username is not None and user_data.username != user.username:
        result = db.execute(
            select(models.User).where(models.User.username == user_data.username)
        )

        existing_user = result.scalars().first()

        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already registered')

    if user_data.email is not None and user_data.email != user.email:
        result = db.execute(select(models.User).where(models.User.email == user_data.email))

        existing_email = result.scalars().first()

        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Email already registered')

    update_data = user_data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user

@app.delete('/api/users/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Annotated[Session, Depends(get_db)]):
    result = db.execute(select(models.User).where(models.User.id == user_id))

    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    db.delete(user)
    db.commit()

@app.exception_handler(StarletteHTTPException)
def general_http_exception_handler(request: Request, exception: StarletteHTTPException):
    message = (
        exception.detail
        if exception.detail
        else "An error occurred. Please check your request and try again."
    )

    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=exception.status_code,
            content={"detail": message},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": exception.status_code,
            "title": exception.status_code,
            "message": message,
        },
        status_code=exception.status_code,
    )

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )