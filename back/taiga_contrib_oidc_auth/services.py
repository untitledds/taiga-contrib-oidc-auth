import logging
from django.db import transaction as tx
from django.apps import apps
from django.conf import settings
from taiga.base.utils.slug import slugify
from taiga.auth.services import send_register_email, make_auth_response_data, get_membership_by_token
from taiga.auth.signals import user_registered as user_registered_signal
from taiga.base.connectors.exceptions import ConnectorBaseException
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from .connector import get_user_info

logger = logging.getLogger(__name__)

USER_KEY = getattr(settings, "OIDC_USER_KEY", "oidc_auth")

class TaigaOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def create_user(self, claims):
        email = claims.get('email')
        if not email:
            return None

        username = claims.get('preferred_username')
        full_name = claims.get('name')
        oidc_guid = claims.get('sub')

        auth_data_model = apps.get_model("users", "AuthData")
        user_model = apps.get_model("users", "User")

        try:
            # OIDC user association exist?
            auth_data = auth_data_model.objects.get(
                key=USER_KEY,
                value=oidc_guid,
            )
            user = auth_data.user
        except auth_data_model.DoesNotExist:
            try:
                # Is a user with the same email as the OIDC user?
                user = user_model.objects.get(email=email)
                auth_data_model.objects.create(
                    user=user,
                    key=USER_KEY,
                    value=oidc_guid,
                    extra={}
                )
            except user_model.DoesNotExist:
                # Create a new user
                username_unique = slugify(username)
                user = user_model.objects.create(
                    email=email,
                    username=username_unique,
                    full_name=full_name,
                )
                auth_data_model.objects.create(
                    user=user,
                    key=USER_KEY,
                    value=oidc_guid,
                    extra={}
                )

                send_register_email(user)
                user_registered_signal.send(
                    sender=user.__class__,
                    user=user
                )

        return user

    def update_user(self, user, claims):
        user.full_name = claims.get('name', user.full_name)
        user.save()
        return user

@tx.atomic
def oidc_register(
        username: str,
        email: str,
        full_name: str,
        oidc_guid: str,
        groups: list = None,
        token: str=None,
):
    """
    Register a new user from OIDC.

    This can raise `exc.IntegrityError` exceptions in
    case of conflicts found.

    :returns: User
    """
    auth_data_model = apps.get_model("users", "AuthData")
    user_model = apps.get_model("users", "User")

    try:
        # OIDC user association exist?
        auth_data = auth_data_model.objects.get(
            key=USER_KEY,
            value=oidc_guid,
        )
        user = auth_data.user
    except auth_data_model.DoesNotExist:
        try:
            # Is a user with the same email as the OIDC user?
            user = user_model.objects.get(email=email)
            auth_data_model.objects.create(
                user=user,
                key=USER_KEY,
                value=oidc_guid,
                extra={}
            )
        except user_model.DoesNotExist:
            # Create a new user
            username_unique = slugify(username)
            user = user_model.objects.create(
                email=email,
                username=username_unique,
                full_name=full_name,
            )
            auth_data_model.objects.create(
                user=user,
                key=USER_KEY,
                value=oidc_guid,
                extra={}
            )

            send_register_email(user)
            user_registered_signal.send(
                sender=user.__class__,
                user=user
            )

    if token:
        membership = get_membership_by_token(token)
        membership.user = user
        membership.save(update_fields=["user"])

    # Update user groups if provided
    if groups:
        user.groups.set(groups)

    return user

def oidc_login_func(request):
    try:
        code = request.DATA['code']
        state = request.DATA['state']

        user_info = get_user_info(code, state)

        user = oidc_register(
            username=user_info['username'],
            email=user_info['email'],
            full_name=user_info['full_name'],
            oidc_guid=user_info['guid'],
            groups=user_info.get('groups', []),
        )
        data = make_auth_response_data(user)
        return data
    except KeyError as e:
        logger.error(f"Missing required parameter: {e}")
        raise ConnectorBaseException({
            "error_message": "Missing required parameter",
            "details": str(e)
        })
    except ConnectorBaseException as e:
        logger.error(f"OIDC authentication failed: {e.detail}")
        raise e
