"""Integration tests for Jira tools."""

import logging
import os
import unittest
import uuid
from typing import override

from dotenv import load_dotenv

from adk_jsm_agent.agent.jira_issues import (
    add_comment_to_jira_issue,
    create_jira_issue,
    delete_jira_issue,
    get_jira_issue,
    get_jira_issue_transitions,
    get_jira_server_info,
    list_jira_issues,
    list_jsm_service_projects,
    perform_jira_issue_transition,
    update_jira_issue,
)

log = logging.getLogger(__name__)

# pyright: reportUninitializedInstanceVariable=false


class TestJiraAPI(unittest.IsolatedAsyncioTestCase):
    """Tests for the Jira API."""

    @override
    def setUp(self) -> None:
        """Construct stuff."""
        _ = load_dotenv()

        # This is complex..
        jira_instance: str | None = os.getenv("JIRA_INSTANCE")
        assert jira_instance is not None
        self.jira_instance: str = jira_instance

        assert os.getenv("JIRA_USERNAME") is not None
        assert os.getenv("JIRA_API_TOKEN") is not None

    async def test_get_jira_server_info_no_error(self) -> None:
        """Tests that get_jira_server_info returns server info without errors."""
        server_info = await get_jira_server_info(None, self.jira_instance)
        assert "status" in server_info
        assert server_info["status"] == "success", f"API returned an error: {server_info.get('error')}"
        assert "data" in server_info
        assert "baseUrl" in server_info["data"]

    async def test_list_jira_issues_no_error(self) -> None:
        """Tests that list_jira_issues returns issues without errors."""
        issues_data = await list_jira_issues(None, self.jira_instance, jql='CreatedDate<"2000-01-01"')
        assert "status" in issues_data
        assert issues_data["status"] == "success", f"API returned an error: {issues_data.get('error')}"
        assert "data" in issues_data

    async def test_list_jsm_service_projects_no_error(self) -> None:
        """Tests that list_jsm_service_projects returns projects without errors."""
        projects_data = await list_jsm_service_projects(None, self.jira_instance)
        assert "status" in projects_data
        assert projects_data["status"] == "success", f"API returned an error: {projects_data.get('error')}"
        assert "data" in projects_data

    async def test_get_jira_issue_not_found(self) -> None:
        """Tests that get_jira_issue returns an error for a non-existent issue."""
        issue_data = await get_jira_issue(None, self.jira_instance, "NONEXISTENT-12345")
        assert "status" in issue_data
        assert issue_data["status"] == "error"

    async def test_update_jira_issue_no_fields(self) -> None:
        """Tests that update_jira_issue returns an error if no fields are provided."""
        result = await update_jira_issue(None, self.jira_instance, "some-key")  # key doesn't matter
        assert "status" in result
        assert result["status"] == "error"
        assert result["message"] == "No fields to update were provided."

    async def test_issue_lifecycle(self) -> None:
        """Tests the full lifecycle of a Jira issue."""
        # 1. Find a project to create an issue in
        projects_data = await list_jsm_service_projects(None, self.jira_instance)
        assert "status" in projects_data
        assert projects_data["status"] == "success", f"API returned an error: {projects_data.get('error')}"
        if not projects_data.get("data"):
            self.skipTest("No JSM projects found to test issue lifecycle.")
        project_key = projects_data["data"][0]["projectKey"]
        log.info("Creating project for %s", project_key)

        # 2. Create an issue
        unique_id = uuid.uuid4()
        summary = f"Test issue from integration tests {unique_id}"
        description = "This is a test issue created by automated tests."
        created_issue = await create_jira_issue(
            None,
            self.jira_instance,
            project_key,
            summary,
            description,
            "Task",
        )
        assert "status" in created_issue
        assert created_issue["status"] == "success", f"API returned an error on create: {created_issue.get('error')}"
        issue_key = created_issue["data"]["key"]

        # Ensure the issue is deleted at the end of the test
        self.addAsyncCleanup(lambda: delete_jira_issue(None, self.jira_instance, issue_key))

        # 3. Get the issue
        retrieved_issue = await get_jira_issue(None, self.jira_instance, issue_key)
        assert "status" in retrieved_issue
        assert retrieved_issue["status"] == "success", f"API returned an error on get: {retrieved_issue.get('error')}"
        assert retrieved_issue["data"]["key"] == issue_key
        assert retrieved_issue["data"]["fields"]["summary"] == summary

        # 4. Update the issue
        new_summary = f"Updated test issue summary {unique_id}"
        update_result = await update_jira_issue(None, self.jira_instance, issue_key, summary=new_summary)
        assert "status" in update_result
        assert update_result["status"] == "success", f"API returned an error on update: {update_result.get('error')}"

        # 5. Add a comment
        comment_text = "This is a test comment."
        comment_result = await add_comment_to_jira_issue(None, self.jira_instance, issue_key, comment_text)
        assert "status" in comment_result
        assert comment_result["status"] == "success", f"API returned an error on comment: {comment_result.get('error')}"
        assert "data" in comment_result
        assert "body" in comment_result["data"]

        # 6. Transition the issue
        transitions_data = await get_jira_issue_transitions(None, self.jira_instance, issue_key)
        assert "status" in transitions_data
        assert transitions_data["status"] == "success", (
            f"API returned an error on get_transitions: {transitions_data.get('error')}"
        )

        assert "data" in transitions_data
        if transitions_data["data"].get("transitions"):
            transition_id = transitions_data["data"]["transitions"][0]["id"]
            transition_result = await perform_jira_issue_transition(
                None,
                self.jira_instance,
                issue_key,
                transition_id,
            )
            assert "status" in transition_result
            assert transition_result["status"] == "success", (
                f"API returned an error on transition: {transition_result.get('error')}"
            )


if __name__ == "__main__":
    _ = unittest.main()
