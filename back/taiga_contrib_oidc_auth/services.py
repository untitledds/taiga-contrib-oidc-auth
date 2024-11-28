# back/taiga_contrib_oidc_auth/services.py

import os
import unicodedata
from django.apps import apps
from django.db import transaction as tx
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from taiga.auth.services import send_register_email, make_auth_response_data
from taiga.auth.signals import user_registered as user_registered_signal
from taiga.base.utils.slug import slugify
from .connector import get_user_info

# TODO: check groups? https://mozilla-django-oidc.readthedocs.io/en/stable/installation.html#advanced-user-verification-based-on-their-claims

USER_KEY = "oidc_auth"

class TaigaOIDCAuthenticationBackend(OIDCAuthenticationBackend):

    AUTHDATA_KEY = os.getenv("OIDC_AUTHDATA_KEY", "oidc")
    AUTHDATA_CLAIM = os.getenv("OIDC_CLAIM_AUTHDATA", "sub")
    EMAIL_CLAIM = os.getenv("OIDC_CLAIM_EMAIL", "email")
    FULLNAME_CLAIM = os.getenv("OIDC_CLAIM_FULLNAME", "name")
    USERNAME_CLAIM = os.getenv("OIDC_CLAIM_USERNAME", "nickname")

    def filter_users_by_claims(self, claims):
        auth_id = claims.get(self.AUTHDATA_CLAIM, self.get_username(claims))

        AuthData = apps.get_model("users", "AuthData")
        try:
            auth_data = AuthData.objects.filter(
                key=self.AUTHDATA_KEY, value=auth_id
            )
            return [ad.user for ad in auth_data]

        except AuthData.DoesNotExist:
            return self.UserModel.objects.none()

    def get_username(self, claims):
        username = claims.get(self.USERNAME_CLAIM)
        if not username:
            return super(TaigaOIDCAuthenticationBackend, self).get_username(claims)

        if os.getenv("OIDC_SLUGGIFY_USERNAME", "False") == "True":
            username = slugify(username)

        return unicodedata.normalize("NFKC", username)[:150]

    def create_user(self, claims):
        email = claims.get(self.EMAIL_CLAIM)
        if not email:
            return None

        username = self.get_username(claims)
        full_name = claims.get(self.FULLNAME_CLAIM, username)
        auth_id = claims.get(self.AUTHDATA_CLAIM, username)

        AuthData = apps.get_model("users", "AuthData")
        try:
            # User association exist?
            auth_data = AuthData.objects.get(key=self.AUTHDATA_KEY, value=auth_id)
            user = auth_data.user
        except AuthData.DoesNotExist:
            try:
                # Is a user with the same email?
                user = self.UserModel.objects.get(email=email)
                AuthData.objects.create(
                    user=user, key=self.AUTHDATA_KEY, value=auth_id, extra={}
                )
            except self.UserModel.DoesNotExist:
                # Create a new user
                user = self.UserModel.objects.create(
                    email=email, username=username, full_name=full_name
                )
                AuthData.objects.create(
                    user=user, key=self.AUTHDATA_KEY, value=auth_id, extra={}
                )

                send_register_email(user)
                user_registered_signal.send(sender=self.UserModel, user=user)

        return user

    def update_user(self, user, claims):
        try:
            user.full_name = claims[self.FULLNAME_CLAIM]
        except KeyError:
            pass
        else:
            user.save()
        return user

@tx.atomic
def oidc_register(
        username: str,
        email: str,
        full_name: str,
        oidc_guid: str,
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

    return user

def oidc_login_func(request):
    code = request.DATA['code']
    state = request.DATA['state']

    user_info = get_user_info(code, state)

    user = oidc_register(
        username=user_info['username'],
        email=user_info['email'],
        full_name=user_info['full_name'],
        oidc_guid=user_info['guid'],
    )
    data = make_auth_response_data(user)
    return data
