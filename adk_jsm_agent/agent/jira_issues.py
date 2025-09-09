"""Example Jira agent."""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.adk.tools.tool_context import ToolContext  # noqa: TC002

from .auth import auth_list_jira_instances, is_success, jira_api_call

# pyright: reportDeprecated=false


log = logging.getLogger(__name__)


async def list_jira_instances(tool_context: ToolContext | None) -> dict[str, Any]:
    """Retrieve list of available Jira instances.

    This function connects to the Jira API to fetch available Jira instances with the
    current credentials.

    Args:
        tool_context: The tool context from the agent.

        Example of a successful response:
        {
          "status": "success",
          "data": [
              {"https://your-domain.atlassianet.com": { "id": "1234832433", "name": "My instance name"}},
          ],
        }


    Returns:
        dict: A dictionary containing Jira instances.

    """
    return await auth_list_jira_instances(tool_context)


async def get_jira_server_info(tool_context: ToolContext | None, jira_instance: str) -> dict[str, Any]:
    """Retrieve server information from the Jira instance.

    This function connects to the Jira API to fetch server metadata, which
    also serves as a way to check if authentication credentials are valid.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance (e.g. https://your-domain.atlassian.net).

    Returns:
        dict: A dictionary containing Jira server information.
              Returns a dictionary with an 'error' key if an error occurs or if environment variables are not set.
              Example of a successful response:
              {
                "status": "success",
                {
                  "baseUrl": "https://your-domain.atlassian.net",
                  "version": "1001.0.0-SNAPSHOT",
                  "versionNumbers": [1001, 0, 0],
                  "deploymentType": "Cloud",
                  "buildNumber": 100213,
                  "buildDate": "2024-01-01T12:00:00.000+0000",
                  "serverTime": "2024-01-01T12:00:01.000+0000",
                  "scmInfo": "some-git-hash",
                  "serverTitle": "JIRA"
                }
              }

    """
    return await jira_api_call(
        tool_context,
        jira_instance,
        "GET",
        "/rest/api/3/serverInfo",
    )


async def list_jira_issues(
    tool_context: ToolContext | None,
    jira_instance: str,
    jql: str = "",
) -> dict[str, Any]:
    """List all issues from a Jira instance using JQL, handling pagination.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance (e.g. https://your-domain.atlassian.net).
        jql (str): The Jira Query Language (JQL) string to filter issues.
                   If empty, it will return all issues up to the API's limit.


    Returns:
        dict: A dictionary containing a list of issues under the 'issues' key,
              or an 'error' key if an error occurs.

    """
    all_issues: list[dict[str, Any]] = []
    start_at = 0
    max_results = 100  # Max per page allowed by Jira Cloud

    while True:
        params = {"jql": jql, "startAt": start_at, "maxResults": max_results}
        data = await jira_api_call(
            tool_context,
            jira_instance,
            "GET",
            "/rest/api/3/search",
            params=params,
        )

        if not is_success(data):
            return data

        issues: list[dict[str, Any]] = data["data"].get("issues", [])
        all_issues.extend(issues)

        if start_at + len(issues) >= data["data"].get("total", 0):
            break  # We've fetched all issues

        start_at += len(issues)

    return {
        "status": "success",
        "data": all_issues,
    }


async def create_jira_issue(  # noqa: PLR0913
    tool_context: ToolContext | None,
    jira_instance: str,
    project_key: str,
    summary: str,
    description: str,
    issue_type: str = "Task",
) -> dict[str, Any]:
    """Create a new issue in a Jira project.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the jira instance
        project_key: The key of the project where the issue will be created.
        summary: The summary or title of the issue.
        description: The detailed description of the issue in Atlassian Document Format.
        issue_type: The type of the issue (e.g., 'Bug', 'Task', 'Story').

    Returns:
        A dictionary containing the created issue's data, or an 'error' key.
        Example of a successful response:
        {
            "status": "success",
            "data": {
                "id": "10000",
                "key": "PROJ-24",
                "self": "https://your-domain.atlassian.net/rest/api/3/issue/10000"
            }
        }

    """
    json_data = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    },
                ],
            },
            "issuetype": {"name": issue_type},
        },
    }
    return await jira_api_call(
        tool_context,
        jira_instance,
        "POST",
        "/rest/api/3/issue",
        json_data=json_data,
    )


async def get_jira_issue(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
) -> dict[str, Any]:
    """Get details of a specific Jira issue.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to retrieve.

    Returns:
        dict: A dictionary containing the issue's data, or an 'error' key.

    """
    return await jira_api_call(tool_context, jira_instance, "GET", f"/rest/api/3/issue/{issue_id_or_key}")


async def update_jira_issue(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
    summary: Optional[str] = None,  # noqa: UP045
    description: Optional[str] = None,  # noqa: UP045
) -> dict[str, Any]:
    """Update an existing Jira issue.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to update.
        summary: The new summary for the issue.
        description: The new description for the issue.

    Returns:
        dict: An empty dictionary indicating success or a dictionary with an 'error' key.

    """
    fields = {}
    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description}],
                },
            ],
        }

    if not fields:
        return {"status": "error", "message": "No fields to update were provided."}

    return await jira_api_call(
        tool_context,
        jira_instance,
        "PUT",
        f"/rest/api/3/issue/{issue_id_or_key}",
        json_data={"fields": fields},
    )


async def delete_jira_issue(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
) -> dict[str, Any]:
    """Delete a Jira issue.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to delete.

    Returns:
        dict: An empty dictionary indicating success or a dictionary with an 'error' key.

    """
    return await jira_api_call(tool_context, jira_instance, "DELETE", f"/rest/api/3/issue/{issue_id_or_key}")


async def add_comment_to_jira_issue(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
    comment_body: str,
) -> dict[str, Any]:
    """Add a comment to a Jira issue.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to comment on.
        comment_body: The text of the comment to add.

    Returns:
        dict: A dictionary containing the created comment's data, or an 'error' key.

    """
    json_data = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_body}]}],
        },
    }
    return await jira_api_call(
        tool_context,
        jira_instance,
        "POST",
        f"/rest/api/3/issue/{issue_id_or_key}/comment",
        json_data=json_data,
    )


async def get_jira_issue_transitions(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
) -> dict[str, Any]:
    """Get available transitions for a Jira issue.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to get transitions for.

    Returns:
        dict: A dictionary containing a list of available transitions, or an 'error' key.

    """
    return await jira_api_call(
        tool_context,
        jira_instance,
        "GET",
        f"/rest/api/3/issue/{issue_id_or_key}/transitions",
    )


async def perform_jira_issue_transition(
    tool_context: ToolContext | None,
    jira_instance: str,
    issue_id_or_key: str,
    transition_id: str,
) -> dict[str, Any]:
    """Transition a Jira issue to a new status.

    To get available transitions, you can use the `get_jira_issue_transitions` function.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.
        issue_id_or_key: The ID or key of the issue to transition.
        transition_id: The ID of the transition to perform.

    Returns:
        dict: An empty dictionary indicating success, or an 'error' key.

    """
    json_data = {"transition": {"id": transition_id}}
    return await jira_api_call(
        tool_context,
        jira_instance,
        "POST",
        f"/rest/api/3/issue/{issue_id_or_key}/transitions",
        json_data=json_data,
    )


async def list_jsm_service_projects(tool_context: ToolContext | None, jira_instance: str) -> dict[str, Any]:
    """List all Service Management (JSM) service projects.

    This is a common next step after confirming authentication, as it provides
    the necessary `projectKey` or `projectId` for other JSM operations.

    Args:
        tool_context: The tool context from the agent.
        jira_instance: The URL of the Jira instance.

    Returns:
        dict: A dictionary containing a 'values' key with a list of service
              project dictionaries, or an 'error' key if an error occurs.
              Example of a successful response:
              {
                "status": "success",
                "data": [
                    {
                        "id": "1",
                        "projectId": "10000",
                        "projectName": "Service Desk",
                        "projectKey": "SD",
                        "_links": {
                          "self": "https://your-domain.atlassian.net/rest/servicedeskapi/servicedesk/1"
                        }
                    }
                ]
              }

    """
    all_projects: list[dict[str, Any]] = []
    start = 0
    limit = 50  # Default and max limit for this endpoint

    while True:
        params = {"start": start, "limit": limit}
        data = await jira_api_call(
            tool_context,
            jira_instance,
            "GET",
            "/rest/servicedeskapi/servicedesk",
            params=params,
        )

        if not is_success(data):
            return data

        projects_data = data["data"].get("values", [])
        all_projects.extend(projects_data)

        if data.get("isLastPage", True):
            break

        start += len(projects_data)

    return {
        "status": "success",
        "data": all_projects,
    }
