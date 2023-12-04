from fastapi import FastAPI, Request, Depends
from fastapi.exceptions import HTTPException
from fastapi import status
from tortoise.contrib.fastapi import register_tortoise

from models import *

# Authentication
from authentication import *
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from SendEmail import *

from dotenv import load_dotenv
import os

# signals
from tortoise.signals import post_save
from typing import List, Optional, Type
from tortoise import BaseDBAsyncClient
from fastapi.responses import HTMLResponse

# templates
from fastapi.templating import Jinja2Templates

# image upload
from fastapi import File, UploadFile
import secrets
from fastapi.staticfiles import StaticFiles
from PIL import Image

app = FastAPI(title="ECOM API")
load_dotenv()

oauth2_schema = OAuth2PasswordBearer(tokenUrl="token")

# static file setup
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post('/token')
async def generate_token(request_form: OAuth2PasswordRequestForm = Depends()):
    token = await token_generator(request_form.username, request_form.password)
    return {"access_token": token, 'token_type': 'bearer'}


async def get_current_user(token: str = Depends(oauth2_schema)):
    try:
        payload = jwt.decode(token, os.getenv('SECRET'), algorithms=['HS256'])
        user = await User.get(id=payload.get("id"))
    except:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return user


@app.post('/user/me')
async def user_login(user: user_pydanticIn = Depends(get_current_user)):
    business = await Business.get(owner=user)
    return {
        'status': "ok",
        'data': {
            'username': user.username,
            'email': user.email,
            'verified': user.is_verified,
            'joined_date': user.join_date
        }
    }


@post_save(User)
async def create_business(
        sender: "Type[User]",
        instance: User,
        created: bool,
        using_db: "Optional[BaseDBAsyncClient]",
        updated_fields: list[str]
) -> None:
    if created:
        business_obj = await Business.create(
            business_name=instance.username, owner=instance
        )

        await business_pydantic.from_tortoise_orm(business_obj)
        # await send_email([instance.email], instance)


@app.get("/")
def index():
    return {"Message": "Hello World"}


@app.post("/registration")
async def user_registration(user: user_pydanticIn):
    user_info = user.dict(exclude_unset=True)
    user_info["password"] = get_hashed_password(user_info["password"])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)
    return {
        "status": "ok",
        "data": f"Hello {new_user.username}, thanks for choosing our services."
                f" Please check your email and click the link for confirm your account."
    }


templates = Jinja2Templates(directory="templates")


@app.get("/verification", response_class=HTMLResponse)
async def email_verification(request: Request, token: str):
    user = await verify_token(token)
    if user and not user.is_verified:
        user.is_verified = True
        await user.save()
        return templates.TemplateResponse("Verification.html", {"request": request, "username": user.username})

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token or expired token",
        headers={"WWW-Authenticate": "Bearer"}
    )


@app.post("/upload/profile")
async def create_upload_file(file: UploadFile = File(...), user: user_pydanticIn = Depends(get_current_user)):
    FILEPATH = "./static/images"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ['png', 'jpg']:
        return {'status': "error", 'details': "file extension not allowed"}

    token_name = secrets.token_hex(10) + "." + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, 'wb') as file:
        file.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()

    business = await Business.get(owner=user)
    owner = await business.owner

    if owner == user:
        business.logo = token_name
        await business.save()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}


@app.post("/uploadfile/product/{id}")
async def create_upload_file(id: int, file: UploadFile = File(...), user: user_pydanticIn = Depends(get_current_user)):
    FILEPATH = "./static/images"
    filename = file.filename
    extension = filename.split(".")[1]

    if extension not in ['png', 'jpg']:
        return {'status': "error", 'details': "file extension not allowed"}

    token_name = secrets.token_hex(10) + "." + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, 'wb') as file:
        file.write(file_content)

    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()

    product = await Product.get(id=id)
    business = await product.business
    owner = business.owner

    if owner == user:
        product.product_image = token_name
        await product.save()
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    file_url = "localhost:8000" + generated_name[1:]
    return {"status": "ok", "filename": file_url}


TORTOISE_ORM = {
    'connections': {
        # Dict format for connection
        'default': {
            'engine': 'tortoise.backends.asyncpg',
            'credentials': {
                'host': os.getenv('DB_HOST'),
                'port': os.getenv('DB_PORT'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASS'),
                'database': os.getenv('DB_NAME'),
            }
        },

    },
    'apps': {
        'models': {
            'models': ['models'],
            # If no default_connection specified, defaults to 'default'
            'default_connection': 'default',
        }
    }
}

register_tortoise(
    app,
    config=TORTOISE_ORM,
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)

# register_tortoise(
#     app,
#     db_url="sqlite://db.sqlite3",
#     modules={"models": ["models"]},
#     generate_schemas=True,
#     add_exception_handlers=True
# )
