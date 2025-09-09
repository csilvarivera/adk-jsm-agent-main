# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Jira agent."""

import logging

import google.cloud.logging
from google.adk.agents.llm_agent import Agent

from .jira_issues import (
    add_comment_to_jira_issue,
    create_jira_issue,
    delete_jira_issue,
    get_jira_issue,
    get_jira_issue_transitions,
    get_jira_server_info,
    list_jira_instances,
    list_jira_issues,
    list_jsm_service_projects,
    perform_jira_issue_transition,
    update_jira_issue,
)

logger = logging.getLogger(__name__)


client = google.cloud.logging.Client()
client.setup_logging()  # pyright: ignore[reportUnknownMemberType]


SCOPES = ["offline_access", "read:jira-user", "read:jira-work"]  # Define required scopes


root_agent = Agent(
    name="jira_agent",
    model="gemini-2.0-flash",
    description=("Agent to interact with Jira Service Management."),
    instruction=("I can interact with Jira Service Managment."),
    tools=[
        list_jira_instances,
        get_jira_server_info,
        list_jira_issues,
        add_comment_to_jira_issue,
        create_jira_issue,
        delete_jira_issue,
        get_jira_issue,
        get_jira_issue_transitions,
        list_jsm_service_projects,
        perform_jira_issue_transition,
        update_jira_issue,
    ],
)
