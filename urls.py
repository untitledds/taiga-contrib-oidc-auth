from taiga.urls import *
urlpatterns += [
    re_path(r"^api/oidc/", include("mozilla_django_oidc.urls")),
]
