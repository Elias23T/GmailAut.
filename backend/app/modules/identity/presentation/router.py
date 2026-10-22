from fastapi import APIRouter, Request
from app.core.dependencies import UowDependency, CurrentUser
from app.modules.identity.application.service import IdentityService
from .schemas import LoginInput, UserOutput, TokenOutput

router = APIRouter(prefix='/auth', tags=['Identidad'])


def service(request: Request, uow):
    return IdentityService(uow, request.app.state.passwords, request.app.state.tokens)


@router.post('/login', response_model=TokenOutput)
def login(body: LoginInput, request: Request, uow: UowDependency):
    user, token = service(request, uow).login(body.username if body.username is not None else str(body.email), body.password.get_secret_value(), request.state.request_id)
    return {'user': user, 'access_token': token, 'expires_in': request.app.state.settings.jwt_minutes * 60}


@router.get('/me', response_model=UserOutput)
def me(user: CurrentUser):
    return user
