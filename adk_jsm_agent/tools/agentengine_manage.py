"""A CLI for deploying and testing the JSM Agent Engine."""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer
import vertexai
from dotenv import find_dotenv, load_dotenv
from vertexai import agent_engines
from vertexai.preview import reasoning_engines

from adk_jsm_agent.agent import root_agent

if TYPE_CHECKING:
    from google.cloud.aiplatform_v1 import types as aip_types

logger = logging.getLogger(__name__)

# Load environment variables from a .env file if it exists.
# Typer's `envvar` support will then pick them up.
DOTENV_FILE = find_dotenv()
if DOTENV_FILE:
    _ = load_dotenv(dotenv_path=DOTENV_FILE)

    # Load up all other environment files
    agentengine_instance_env = os.getenv("AGENTENGINE_INSTANCE_ENV")
    if agentengine_instance_env:
        _ = load_dotenv(Path(DOTENV_FILE).parent / Path(agentengine_instance_env))


app = typer.Typer(
    help="A command-line tool to manage Google Cloud Agentengine deployments.",
    add_completion=False,
    no_args_is_help=True,
)


# Common options for project and location
project_id_option = typer.Option(
    ...,
    "--project-id",
    envvar="GOOGLE_CLOUD_PROJECT",
    help="Google Cloud Project ID.",
)
location_option = typer.Option(
    ...,
    "--location",
    envvar="AGENT_LOCATION",
    help="Google Cloud Location for the agent engine.",
)


state: dict[str, str] = {}


@app.callback()
def main_callback(
    project_id: Annotated[
        str,
        typer.Option(
            ...,
            "--project-id",
            envvar="AGENTENGINE_PROJECT",
            help="Google Cloud Project ID.",
        ),
    ],
    location: Annotated[
        str,
        typer.Option(
            ...,
            "--location",
            help="The location to use for the AgentEngine instances.",
            envvar="AGENTENGINE_LOCATION",
        ),
    ],
    staging_bucket: Annotated[
        str,
        typer.Option(
            ...,
            "--staging-bucket",
            envvar="AGENTENGINE_STAGING_BUCKET",
            help="GCS bucket for staging the deployment. e.g. my-bucket",
        ),
    ],
) -> None:
    """Manage agents and authorizations."""
    state["location"] = location
    state["project_id"] = project_id

    # Initialize vertex AI
    typer.echo(f"Initializing Vertex AI for project '{project_id}' in '{location}'...")
    vertexai.init(
        project=project_id,
        location=location,
        staging_bucket=f"gs://{staging_bucket}",
    )


@app.command()
def deploy(
    instance_file: Annotated[
        Path,
        typer.Option(
            ...,
            "--instance-env-file",
            envvar="AGENTENGINE_INSTANCE_ENV",
            writable=True,
            dir_okay=False,
            help="File to write the deployed agent engine resource name to as AGENTENGINE_INSTANCE=.",
        ),
    ],
    display_name: Annotated[
        str,
        typer.Option(
            "--display-name",
            envvar="AGENTENGINE_DISPLAY_NAME",
            help="Display name for the agent engine.",
        ),
    ],
    extra_packages: Annotated[
        list[str] | None,
        typer.Option(
            help=(
                "Path to extra python packages to install. "
                "Can be specified multiple times. Defaults to wheels in dist/."
            ),
        ),
    ] = None,
    requirements: Annotated[
        list[str] | None,
        typer.Option(
            help=(
                "Path to extra python packages to install (as requirements)."
                "Can be specified multiple times. Defaults to wheels in dist/."
            ),
        ),
    ] = None,
    env: Annotated[
        list[str] | None,
        typer.Option(
            "--env",
            help="Environment variable to re-export from environment for the agent. (can be set multiple times)",
        ),
    ] = None,
) -> None:
    """Deploys the agent engine to Vertex AI."""
    # For writing out to the instance_file, we need a .env file
    if instance_file and not DOTENV_FILE:
        typer.echo("Cannot use --instance-env-file without a .env file.")
        raise typer.Exit(1)

    # Create the app_to_deploy
    # TODO(scannell): If this has multiple agents, we could make this configurable to a path
    app_to_deploy = reasoning_engines.AdkApp(
        agent=root_agent,
        enable_tracing=True,
    )

    # Parse the environment variable values
    env_vars: dict[str, str | aip_types.SecretRef] = {}
    if env:
        for k in env:
            v = os.getenv(k)
            if not v:
                typer.echo(f"--env {k} is not defined in the environment", err=True)
                raise typer.Exit(1)
            env_vars[k] = v

    # Default requirements from extra_packages if not provided.
    if extra_packages and not requirements:
        requirements = list(extra_packages)

    typer.echo(f"Deploying agent engine with display name: '{display_name}'")
    typer.echo(f"Extra packages: {extra_packages}")
    typer.echo(f"Requirements: {requirements}")
    typer.echo(f"Environment variables: {env_vars}")

    remote_app = agent_engines.create(  # pyright: ignore[reportUnknownMemberType]
        agent_engine=app_to_deploy,
        display_name=display_name,
        extra_packages=extra_packages,
        requirements=requirements,
        env_vars=env_vars,
    )

    resource_name = remote_app.resource_name
    typer.echo(f"✅ Deployed resource {resource_name}")

    if instance_file:
        with (Path(DOTENV_FILE).parent / Path(instance_file).name).open("wt") as w:
            _ = w.write(f"AGENTENGINE_INSTANCE={resource_name}\n")
        typer.echo(f"Wrote out resource name to {instance_file}")


@app.command()
def remote_test(
    resource: Annotated[
        str,
        typer.Option(
            "--resource",
            help="Fully qualified resource path to the AgentEngine. "
            "Suggest use AGENTENGINE_INSTANCE environment variable.",
            envvar="AGENTENGINE_INSTANCE",
        ),
    ],
    message: Annotated[
        str,
        typer.Option(
            "--message",
            "-m",
            help="Message to send to the agent.",
        ),
    ] = "list the tools available for the agent",
    user_id: Annotated[
        str,
        typer.Option("--user-id", help="User ID for the session."),
    ] = "user",
) -> None:
    """Test a deployed agent engine."""
    typer.echo(f"Getting remote app for resource: {resource}")
    try:
        remote_app = agent_engines.get(resource)
    except Exception as e:
        typer.echo(f"❗ error: Could not get remote app for resource: {resource}", err=True)
        raise typer.Exit(code=1) from e

    #
    # This is really ugly from a typing perspective as the Agent Engine API is a bit odd in the
    # Python code.
    #

    session = None
    try:
        typer.echo(f"Creating session for user: {user_id}")
        session: Any = remote_app.create_session(user_id=user_id)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
        typer.echo(f"Session created: {session}")

        typer.echo(f"Streaming query with message: '{message}'")
        events = list(  # pyright: ignore[reportUnknownVariableType]
            remote_app.stream_query(  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType, reportAttributeAccessIssue]
                user_id=user_id,
                session_id=session["id"],
                message=message,
            ),
        )

        # For quick tests, you can extract just the final text response
        final_text_responses = [  # pyright: ignore[reportUnknownVariableType]
            e
            for e in events  # pyright: ignore[reportUnknownVariableType]
            if e.get("content", {}).get("parts", [{}])[0].get("text")  # pyright: ignore[reportUnknownMemberType]
            and not e.get("content", {}).get("parts", [{}])[0].get("function_call")  # pyright: ignore[reportUnknownMemberType]
        ]
        if final_text_responses:
            typer.echo("\n--- Final Response ---")
            typer.echo(final_text_responses[0]["content"]["parts"][0]["text"])  # pyright: ignore[reportUnknownArgumentType]

    except Exception as e:
        typer.echo(f"❗ error: Could not stream query: {e}", err=True)
        raise typer.Exit(code=1) from e

    finally:
        if session:
            typer.echo(f"\nDeleting session: {session['id']}")
            remote_app.delete_session(user_id=user_id, session_id=session["id"])  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]

    typer.echo("✅ Test finished.")


@app.command()
def delete(
    resource: Annotated[
        str,
        typer.Option(
            "--resource",
            help="Fully qualified resource path to the AgentEngine. "
            "Suggest use instance_file or AGENT_INSTANCE environment variable.",
            envvar="AGENTENGINE_INSTANCE",
        ),
    ],
    with_sessions: Annotated[
        bool,
        typer.Option(
            "--with-sessions",
            help="Delete all sessions as well for user 'user'."
        ),
    ] = False,
) -> None:
    """Delete a deployed agent engine."""
    typer.echo(f"Deleting Agentengine: {resource}")
    try:
        if with_sessions:
            remote_app = agent_engines.get(resource)
            result = s.list_sessions(user_id="user")
            for session in result['sessions']:
                typer.echo(f"Deleting session {session['id']}")
                s.delete_session(user_id="user", session_id=session["id"])

        agent_engines.delete(resource)  # pyright: ignore[reportUnknownMemberType]
    except Exception as e:
        typer.echo(f"❗ error: could not delete resource {resource}", err=True)
        print(e)
        raise typer.Exit(code=1) from e
    typer.echo("✅ Deleted.")


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    logger.info("Starting AgentEngine deployment CLI.")
    app()
