import requests
import logging
from django.conf import settings
from taiga.base.connectors.exceptions import ConnectorBaseException

logger = logging.getLogger(__name__)

def get_user_info(code, state):
    """
    Получает информацию о пользователе от OIDC-провайдера.

    :param code: Код авторизации.
    :param state: Состояние.
    :returns: Информация о пользователе.
    """
    # Шаг 1: Получение токена доступа
    token_url = settings.OIDC_OP_TOKEN_ENDPOINT
    client_id = settings.OIDC_RP_CLIENT_ID
    client_secret = settings.OIDC_RP_CLIENT_SECRET
    redirect_uri = settings.OIDC_REDIRECT_URI

    token_response = requests.post(
        token_url,
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        },
        headers={'Accept': 'application/json'}
    )

    if token_response.status_code != 200:
        logger.error(f"Failed to obtain access token: {token_response.text}")
        raise ConnectorBaseException({
            "error_message": "Failed to obtain access token",
            "status_code": token_response.status_code,
            "response_text": token_response.text
        })

    token_data = token_response.json()
    access_token = token_data.get('access_token')

    # Шаг 2: Получение информации о пользователе
    userinfo_url = settings.OIDC_OP_USER_ENDPOINT

    userinfo_response = requests.get(
        userinfo_url,
        headers={'Authorization': f'Bearer {access_token}'}
    )

    if userinfo_response.status_code != 200:
        logger.error(f"Failed to obtain user info: {userinfo_response.text}")
        raise ConnectorBaseException({
            "error_message": "Failed to obtain user info",
            "status_code": userinfo_response.status_code,
            "response_text": userinfo_response.text
        })

    user_info = userinfo_response.json()

    # Возвращаем информацию о пользователе
    return {
        'guid': user_info.get('sub', None),
        'username': user_info.get('preferred_username', None),
        'email': user_info.get('email', None),
        'full_name': user_info.get('name', None),
        'groups': user_info.get('groups', []),
    }
