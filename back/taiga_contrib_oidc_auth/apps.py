# back/taiga_contrib_oidc_auth/apps.py
from django.apps import AppConfig

class TaigaContribOIDCAuthAppConfig(AppConfig):
    name = "taiga_contrib_oidc_auth"
    verbose_name = "Taiga contrib OIDC auth App Config"

    def ready(self):
        from taiga.auth.services import register_auth_plugin
        from . import services
        register_auth_plugin(
            "oidc_auth",
            services.oidc_login_func,
        )
