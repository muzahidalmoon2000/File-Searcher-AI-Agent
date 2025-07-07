import msal
import os

def build_msal_app(cache=None):
    return msal.ConfidentialClientApplication(
        os.getenv("CLIENT_ID"),
        authority=os.getenv("AUTHORITY"),
        client_credential=os.getenv("CLIENT_SECRET"),
        token_cache=cache
    )

def get_token_from_cache(scope=None):
    scope = scope or [os.getenv("SCOPE")]
    msal_app = build_msal_app()
    accounts = msal_app.get_accounts()
    if accounts:
        result = msal_app.acquire_token_silent(scope, account=accounts[0])
        return result["access_token"] if result and "access_token" in result else None
    return None
