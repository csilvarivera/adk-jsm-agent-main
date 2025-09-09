"""A CLI for managing agentengine engines and auths."""

import json
import os
from pathlib import Path
from typing import Annotated, Any

import google.auth
import requests
import typer
from dotenv import find_dotenv, load_dotenv
from google.auth.transport.requests import Request

# Load environment variables from a .env file if it exists.
# Typer's `envvar` support will then pick them up.
DOTENV_FILE = find_dotenv()
if DOTENV_FILE:
    _ = load_dotenv(dotenv_path=DOTENV_FILE)

    # Load up all other environment files
    agentengine_instance_env = os.getenv("AGENTENGINE_INSTANCE_ENV")
    if agentengine_instance_env:
        _ = load_dotenv(Path(DOTENV_FILE).parent / Path(agentengine_instance_env))

    agentspace_agent_env = os.getenv("AGENTSPACE_AGENT_INSTANCE_ENV")
    if agentspace_agent_env:
        _ = load_dotenv(Path(DOTENV_FILE).parent / Path(agentspace_agent_env))


state = {"location": "global", "base_url": "https://discoveryengine.googleapis.com/v1alpha"}

app = typer.Typer(
    help="A command-line tool to manage Google Cloud Agentspace agents and authorizations.",
    add_completion=False,
    no_args_is_help=True,
)
auth_app = typer.Typer(
    help="Manage authorization resources for agents.",
    name="auth",
    no_args_is_help=True,
)
agent_app = typer.Typer(help="Manage agent registrations in Agentspace.", name="agent", no_args_is_help=True)
app.add_typer(auth_app)
app.add_typer(agent_app)


@app.callback()
def main_callback(
    location: str = typer.Option(
        "global",
        "--location",
        help="The location to use for the API.",
        envvar="AGENTSPACE_LOCATION",
    ),
) -> None:
    """Manage agents and authorizations."""
    if location != "global":
        state["base_url"] = f"https://{location}-discoveryengine.googleapis.com/v1alpha"
    else:
        typer.echo(
            "WARNING: The global location will not work with auth. "
            "'It must be the same region as AgentEngine and AgentEngine doe snot support global.",
        )
    state["location"] = location


def get_auth_token() -> str:
    """Authenticate with Google Cloud and returns an access token."""
    try:
        creds, _ = google.auth.default(  # pyright: ignore[reportUnknownMemberType]
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        if not creds.valid:
            creds.refresh(Request())
        return str(creds.token)
    except Exception as e:
        typer.echo(
            "Error: Could not obtain Google Cloud credentials. "
            f"Please run 'gcloud auth application-default login'. Details: {e}",
            err=True,
        )
        raise typer.Exit(code=1) from e


def make_api_request(
    method: str,
    url: str,
    project_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated API request and handles responses."""
    headers = {
        "Authorization": f"Bearer {get_auth_token()}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id,
    }
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            data=json.dumps(payload) if payload else None,
            timeout=60,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        typer.echo(f"Error: API request failed with status {e.response.status_code}:")
        typer.echo(e.response.text, err=True)
        raise typer.Exit(code=1) from e
    except Exception as e:
        typer.echo(f"An unexpected error occurred: {e}", err=True)
        raise typer.Exit(code=1) from e


#
# Authorization Commands
#
# From here:
# https://cloud.google.com/agentspace/docs/reference/rest/v1alpha/projects.locations.authorizations#ServerSideOAuth2
#


@auth_app.command("create")
def create_authorization(  # noqa: PLR0913
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    auth_id: str = typer.Option(..., help="A unique ID for the authorization resource.", envvar="AGENTSPACE_AUTH_ID"),
    client_id: str = typer.Option(..., help="OAuth 2.0 Client ID.", envvar="AGENTSPACE_OAUTH_CLIENT_ID"),
    client_secret: str = typer.Option(..., help="OAuth 2.0 Client Secret.", envvar="AGENTSPACE_OAUTH_CLIENT_SECRET"),
    auth_uri: str = typer.Option(
        ...,
        help="The endpoint for obtaining an OAuth 2.0 authorization code.",
        envvar="AGENTSPACE_OAUTH_AUTH_URI",
    ),
    token_uri: str = typer.Option(
        ...,
        help="The endpoint for exchanging an authorization code for an access token.",
        envvar="AGENTSPACE_OAUTH_TOKEN_URI",
    ),
) -> None:
    """Create an OAuth 2.0 authorization resource in Agentspace."""
    location = state["location"]
    base_url = state["base_url"]
    url = f"{base_url}/projects/{project_id}/locations/{location}/authorizations?authorizationId={auth_id}"
    payload = {
        "name": f"projects/{project_id}/locations/{location}/authorizations/{auth_id}",
        "serverSideOauth2": {
            "clientId": client_id,
            "clientSecret": client_secret,
            "authorizationUri": auth_uri,
            "tokenUri": token_uri,
        },
    }
    result = make_api_request("POST", url, project_id, payload)
    typer.echo(json.dumps(result, indent=2))


@auth_app.command("list")
def list_authorizations(
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
) -> None:
    """List all authorization resources for a project."""
    location = state["location"]
    base_url = state["base_url"]
    url = f"{base_url}/projects/{project_id}/locations/{location}/authorizations"
    result = make_api_request("GET", url, project_id)
    typer.echo(json.dumps(result, indent=2))


@auth_app.command("delete")
def delete_authorization(
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    auth_id: str = typer.Option(
        ...,
        help="The ID of the authorization resource to delete.",
        envvar="AGENTSPACE_AUTH_ID",
    ),
) -> None:
    """Delete an authorization resource from Agentspace."""
    location = state["location"]
    base_url = state["base_url"]
    url = f"{base_url}/projects/{project_id}/locations/{location}/authorizations/{auth_id}"
    result = make_api_request("DELETE", url, project_id)
    typer.echo(f"Successfully deleted authorization resource '{auth_id}'.")
    typer.echo(json.dumps(result, indent=2))


#
# Agentspace Agent commands
#


@agent_app.command("create")
def create_agent(  # noqa: PLR0913
    instance_file: Annotated[
        Path,
        typer.Option(
            ...,
            "--instance-env-file",
            envvar="AGENTSPACE_AGENT_INSTANCE_ENV",
            writable=True,
            dir_okay=False,
            help="File to write the deployed agnetspace agent resource name to as AGENTSPACE_AGENT_INSTANCE=.",
        ),
    ],
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    project_number: int = typer.Option(..., help="Google Cloud project number.", envvar="AGENTSPACE_PROJECT_NUMBER"),
    app_id: str = typer.Option(..., help="The ID of the Agentspace app.", envvar="AGENTSPACE_APP_ID"),
    display_name: str = typer.Option(
        ...,
        help="The display name of the agent.",
        envvar="AGENTSPACE_AGENT_DISPLAY_NAME",
    ),
    description: str = typer.Option(..., help="Description shown to the user.", envvar="AGENTSPACE_AGENT_DESCRIPTION"),
    tool_description: str = typer.Option(
        ...,
        help="Description/prompt for the LLM router.",
        envvar="AGENTSPACE_AGENT_TOOL_DESCRIPTION",
    ),
    agentengine_instance: str = typer.Option(
        ...,
        help="The full path of the Agent Engine instance.",
        envvar="AGENTENGINE_INSTANCE",
    ),
    icon_uri: str | None = typer.Option(None, help="Public URI of the agent's icon.", envvar="AGENT_ICON_URI"),
    auth_id: str | None = typer.Option(
        None,
        "--auth-id",
        help="Authorization resource ID to associate. Can be used multiple times.",
        envvar="AGENTSPACE_AUTH_ID",
    ),
) -> None:
    """Register a new agent with Agentspace."""
    typer.echo(
        f'AgentEngine engine: "{agentengine_instance}"',
    )
    location = state["location"]
    base_url = state["base_url"]
    url = (
        f"{base_url}/projects/{project_id}/locations/{location}/collections/"
        f"default_collection/engines/{app_id}/assistants/default_assistant/agents"
    )
    payload: dict[str, Any] = {
        "displayName": display_name,
        "description": description,
        "adk_agent_definition": {
            "tool_settings": {
                "tool_description": tool_description,
            },
            "provisioned_reasoning_engine": {
                "reasoning_engine": agentengine_instance,
            },
        },
    }
    if icon_uri:
        payload["icon"] = {"uri": icon_uri}
    if auth_id:
        # TODO(scannell): Why do we need the GOOGLE_CLOUD_PROJECT NUMBER? Can we do without this?
        payload["authorization_config"] = {
            "tool_authorizations": [
                f"projects/{project_number}/locations/{location}/authorizations/{auth_id}",
            ],
        }
    typer.echo(f"Creating agent: {payload}")
    result = make_api_request("POST", url, project_id, payload)
    typer.echo("Successfully created agent: {result}")

    if instance_file:
        with (Path(DOTENV_FILE).parent / Path(instance_file).name).open("wt") as w:
            _ = w.write(f"AGENTSPACE_AGENT_INSTANCE={result['name']}\n")
        typer.echo(f"Wrote out resource name to {instance_file}")

    typer.echo(json.dumps(result, indent=2))


@agent_app.command("get")
def get_agent(
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    agent_resource_name: str = typer.Argument(..., help="Full resource name of the agent."),
) -> None:
    """Retrieve the details of a specific agent."""
    base_url = state["base_url"]
    url = f"{base_url}/{agent_resource_name}"
    result = make_api_request("GET", url, project_id)
    typer.echo(json.dumps(result, indent=2))


@agent_app.command("list")
def list_agents(
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    app_id: str = typer.Option(..., help="The ID of the Agentspace app.", envvar="AGENTSPACE_APP_ID"),
) -> None:
    """List all registered agents in an Agentspace app."""
    location = state["location"]
    base_url = state["base_url"]
    url = (
        f"{base_url}/projects/{project_id}/locations/{location}/collections/default_collection"
        f"/engines/{app_id}/assistants/default_assistant/agents"
    )
    result = make_api_request("GET", url, project_id)
    typer.echo(json.dumps(result, indent=2))


@agent_app.command("delete")
def delete_agent(
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    agent_resource_name: str = typer.Argument(
        ...,
        help="Full resource name of the agent to delete.",
        envvar="AGENTSPACE_AGENT_INSTANCE",
    ),
) -> None:
    """Delete an agent registration from Agentspace."""
    base_url = state["base_url"]
    url = f"{base_url}/{agent_resource_name}"
    _ = make_api_request("DELETE", url, project_id)
    typer.echo(f"Successfully deleted agent '{agent_resource_name}'.")


@agent_app.command("update")
def update_agent(  # noqa: PLR0913
    agent_instance: str = typer.Option(
        ...,
        help="The full path of the Agent Engine instance.",
        envvar="AGENTSPACE_AGENT_INSTANCE",
    ),
    project_id: str = typer.Option(..., help="Google Cloud project ID.", envvar="AGENTSPACE_PROJECT"),
    project_number: int = typer.Option(..., help="Google Cloud project number.", envvar="AGENTSPACE_PROJECT_NUMBER"),
    agent_resource_name: str = typer.Argument(..., help="Full resource name of the agent to update."),
    display_name: str = typer.Option(
        ...,
        help="The display name of the agent.",
        envvar="AGENTSPACE_AGENT_DISPLAY_NAME",
    ),
    description: str = typer.Option(..., help="Description shown to the user.", envvar="AGENTSPACE_AGENT_DESCRIPTION"),
    tool_description: str = typer.Option(
        ...,
        help="Description/prompt for the LLM router.",
        envvar="AGENT_TOOL_DESCRIPTION",
    ),
    icon_uri: str | None = typer.Option(
        None,
        help="Public URI of the agent's icon.",
        envvar="AGENTSPACE_AGENT_ICON_URI",
    ),
    auth_id: str | None = typer.Option(
        None,
        "--auth-id",
        help="Authorization resource ID to associate. Can be used multiple times.",
        envvar="AGENTSPACE_AUTH_ID",
    ),
) -> None:
    """Update an existing agent. All fields are required."""
    base_url = state["base_url"]
    location = state["location"]
    url = f"{base_url}/{agent_resource_name}"
    payload: dict[str, Any] = {
        "displayName": display_name,
        "description": description,
        "adk_agent_definition": {
            "tool_settings": {
                "tool_description": tool_description,
            },
            "provisioned_reasoning_engine": {
                "reasoning_engine": agent_instance,
            },
        },
    }
    if icon_uri:
        payload["icon"] = {"uri": icon_uri}
    if auth_id:
        payload["authorization_config"] = {
            "tool_authorizations": [
                f"projects/{project_number}/locations/{location}/authorizations/{auth_id}",
            ],
        }
    result = make_api_request("PATCH", url, project_id, payload)
    typer.echo("Successfully updated agent:")
    typer.echo(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
