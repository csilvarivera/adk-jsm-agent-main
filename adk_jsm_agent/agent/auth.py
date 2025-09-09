"""Example Jira agent."""

from __future__ import annotations

import functools
import logging
import os
from abc import ABC
from typing import Any, override

import httpx
from fastapi.openapi.models import OAuth2, OAuthFlowAuthorizationCode, OAuthFlows
from google.adk.auth.auth_credential import (
    AuthCredential,
    AuthCredentialTypes,
    OAuth2Auth,
)
from google.adk.auth.auth_tool import AuthConfig
from google.adk.auth.refresher.oauth2_credential_refresher import OAuth2CredentialRefresher
from google.adk.tools.tool_context import ToolContext  # noqa: TC002
from httpx import BasicAuth

log = logging.getLogger(__name__)


TOKEN_CACHE = "jra_agent_token"  # Choose a unique key  # noqa: S105
JIRA_INSTANCE_CACHE = "jira_instance_cache"

# NOTE: offline_access is needed in the scope in order to get a refresh token
SCOPES = ["offline_access", "read:jira-user", "read:jira-work"]  # Define required scopes


@functools.cache
def _get_auth_sheme_and_credential() -> tuple[OAuth2, AuthCredential]:
    client_id = os.getenv("ADK_OAUTH_CLIENT_ID")
    client_secret = os.getenv("ADK_OAUTH_CLIENT_SECRET")
    if not client_secret or not client_id:
        msg = "must define environment variables ADK_OAUTH_CLIENT_ID and ADK_OAUTH_CLIENT_SECRET"
        raise ValueError(msg)

    auth_uri = os.getenv("ADK_OAUTH_AUTH_URI")
    token_uri = os.getenv("ADK_OAUTH_TOKEN_URI")
    scopes = os.getenv("ADK_OAUTH_SCOPES")
    if not auth_uri or not token_uri or not scopes:
        msg = "must define environment variables ADK_OAUTH_AUTH_URI, ADK_OAUTH_TOKEN_URI, and ADK_OAUTH_SCOPES"
        raise ValueError(msg)

    auth_scheme = OAuth2(
        flows=OAuthFlows(
            authorizationCode=OAuthFlowAuthorizationCode(
                authorizationUrl=auth_uri,
                tokenUrl=token_uri,
                refreshUrl=token_uri,
                scopes={scope: f"Access to {scope}" for scope in scopes.split(" ")},
            ),
        ),
    )
    auth_credential = AuthCredential(
        auth_type=AuthCredentialTypes.OAUTH2,
        oauth2=OAuth2Auth(
            client_id=client_id,
            client_secret=client_secret,
            audience=os.getenv("ADK_OAUTH_AUDIENCE", None),
        ),
    )

    log.info("Auth schema: %s", auth_scheme)
    log.info("Auth credential: %s", auth_credential)

    return auth_scheme, auth_credential


async def _refresh_credentials(tool_context: ToolContext) -> ResultsDict:
    auth_scheme, auth_credential = _get_auth_sheme_and_credential()

    refresher = OAuth2CredentialRefresher()

    # Extract cached credentials
    auth_cred: str | None = tool_context.state.get(TOKEN_CACHE)
    creds: AuthCredential | None = AuthCredential.model_validate_json(auth_cred) if auth_cred else None
    if creds:
        try:
            if await refresher.is_refresh_needed(creds, auth_scheme):
                log.info("Returned the still current credentials: %s", creds)
                tool_context.state[TOKEN_CACHE] = (await refresher.refresh(creds, auth_scheme)).model_dump_json()

        except Exception as e:
            log.exception("Error refreshing credentials", exc_info=e)
            tool_context.state[TOKEN_CACHE] = None

        return ResultsSuccess()

    creds = tool_context.get_auth_response(
        AuthConfig(
            auth_scheme=auth_scheme,
            raw_auth_credential=auth_credential,
        ),
    )

    if creds:
        log.info(f"Got credentials, now dumping: {creds}")
        tool_context.state[TOKEN_CACHE] = creds.model_dump_json()
        log.info(f"State is now: {tool_context.state[TOKEN_CACHE]}")
        return ResultsSuccess()

    # The type for get_auth_response is wrong (it might return None)
    log.info("Pending, as we tried to exchange.")  # pyright: ignore[reportUnreachable]
    tool_context.request_credential(
        AuthConfig(
            auth_scheme=auth_scheme,
            raw_auth_credential=auth_credential,
        ),
    )
    return ResultsPending()


async def _api_call(  # noqa: PLR0913
    tool_context: ToolContext | None,
    endpoint: str,
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> ResultsDict:
    auth = None
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # Try to extract token from Agentspace AUTH_ID
    auth_id = os.getenv("AGENTSPACE_AUTH_ID")
    token: str | None = None
    if auth_id and tool_context and tool_context.state:
        log.info("Current tool_context state: %s", str(tool_context.state.to_dict()))
        token = tool_context.state.get("temp:" + auth_id)

    # If we got the token from Agentspace - that's good enough
    if token:
        log.info("Token: %s", token)
        headers["Authorization"] = f"Bearer {token}"

    # Otherwise try to use PAT.
    elif os.getenv("JIRA_USERNAME") and os.getenv("JIRA_API_TOKEN"):
        log.info("Running in PAT mode")

        auth = BasicAuth(os.getenv("JIRA_USERNAME", ""), os.getenv("JIRA_API_TOKEN", ""))

    # Otherwise assume it is OAuth in ADK
    else:
        log.info("Running in OAuth mode")

        if not tool_context or not tool_context.state:
            return ResultsError("no tool_context when running in OAuth mode")

        r = await _refresh_credentials(tool_context)
        if not is_success(r):
            return r

        # Get the credentials into the header
        creds = AuthCredential.model_validate_json(tool_context.state.get(TOKEN_CACHE))
        if not creds or not creds.oauth2 or not creds.oauth2.access_token:
            return ResultsError(f"no credentials when running in OAuth mode only {creds}")

        headers["Authorization"] = f"Bearer {creds.oauth2.access_token}"

    try:
        async with httpx.AsyncClient(auth=auth, timeout=30) as client:
            log.info("Request %s against %s", method, endpoint + path)
            response = await client.request(
                method,
                endpoint + path,
                headers=headers,
                params=params,
                json=json_data,
            )
            _ = response.raise_for_status()
            return ResultsSuccess(response.json() if response.text else {})
    except httpx.HTTPStatusError as e:
        log.exception("An error occurred while calling Jira API endpoint %s", endpoint, exc_info=e)
        return ResultsError(f"An error occurred while calling Jira API endpoint {endpoint}: {e!s}")


class ResultsDict(dict[str, Any], ABC):
    """Class for dictionary returned for tool functions."""

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Construct a results dictionary."""
        super().__init__(**kwargs)

    def is_success(self) -> bool:
        """If the results are a success or not."""
        return False


class ResultsPending(ResultsDict):
    """Results when they are pending (OAuth authentication)."""

    def __init__(self) -> None:
        """Construct a results dictionary."""
        super().__init__(pending=True, message="Awaiting user authentication.")


class ResultsError(ResultsDict):
    """Results when there is an error (see message for details)."""

    def __init__(self, message: str) -> None:
        """Construct a results dictionary."""
        super().__init__(status="error", message=message)


class ResultsSuccess(ResultsDict):
    """Results when there is a success (see data for payload)."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        """Construct a results dictionary."""
        super().__init__(status="success", data=data)

    @override
    def is_success(self) -> bool:
        return True


def is_success(d: dict[str, Any]) -> bool:
    """Whether results is successful or not."""
    return "status" in d and d["status"] == "success"


# This lists the available resources. OAuth only.
async def auth_list_jira_instances(tool_context: ToolContext | None) -> ResultsDict:
    """Retrieve list of available Jira instances.

    This function connects to the Jira API to fetch available Jira instances with the
    current credentials.

    Args:
        tool_context: The tool context from the agent.

    Returns:
        dict: A dictionary containing Jira instances.

              Example of a successful response:
              {
                "status": "success",
                "data": [
                    {"https://your-domain.atlassianet.com": { "id": "1234832433", "name": "My instance name"}},
                ],
              }

    """
    jira_instance = os.getenv("JIRA_INSTANCE")
    if jira_instance:
        return ResultsSuccess(
            {
                jira_instance: {
                    "id": None,
                    "name": "",
                },
            },
        )

    if not tool_context or not tool_context.state:
        return ResultsError("no tool_context when running in OAuth mode")

    if not tool_context.state.get(JIRA_INSTANCE_CACHE):
        r = await _api_call(
            tool_context,
            "https://api.atlassian.com",
            "GET",
            "/oauth/token/accessible-resources",
        )
        if not is_success(r):
            log.info("Breaking early -- must be pending: %s", r)
            return r

        # Capture instance cache
        tool_context.state[JIRA_INSTANCE_CACHE] = {
            k["url"]: {
                "id": k["id"],
                "name": k["name"],
            }
            for k in r["data"]
        }

    # Return the list of instances
    return ResultsSuccess(tool_context.state[JIRA_INSTANCE_CACHE])


async def jira_api_call(  # noqa: PLR0913
    tool_context: ToolContext | None,
    jira_instance: str,
    method: str,
    path: str,
    json_data: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> ResultsDict:
    """Execute Jira API call.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        method: The HTTP method.
        path: The path to REST endpoint.
        json_data: The JSON data payload.
        params: Parameters for the GET or POST on URL.

    Returns:
        ResultsDict with success, error, or pending

    """
    # Get the available resources
    r = await auth_list_jira_instances(tool_context)
    if not is_success(r):
        return r

    log.info("Jira instances: %s", r)

    if jira_instance not in r["data"]:
        return ResultsError("Jira instance {jira_instance} not in list {', '.join(r['data'].keys())}")

    # Get the ID (may be None, but should exist)
    instance_id: str | None = r["data"][jira_instance].get("id")

    return await _api_call(
        tool_context,
        f"https://api.atlassian.com/ex/jira/{instance_id}" if instance_id else jira_instance,
        method,
        path,
        json_data,
        params,
    )
