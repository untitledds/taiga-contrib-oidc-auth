# OIDC Auth
if [[ -z "${ENABLE_OIDC_AUTH}" ]]; then
    export ENABLE_OIDC_AUTH="false"
fi

if [ ${ENABLE_OIDC_AUTH} == "true" ]; then
    contribs+=('"plugins/oidc-auth/oidc-auth.json"')
fi
