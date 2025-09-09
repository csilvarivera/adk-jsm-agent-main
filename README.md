
# Jira sample Agent

## Quickstart

 * Choose a project and Agentspace instance and Agentengine. Note that Agentspace cannot be in the global region, and the region must correspond to each other. The provided example uses 'us' Agentspace and 'us-central1' for Agentengine.
 * Copy .env.example to .env and edit the project id, project number, Agentspace ID, and GCS bucket (temporary, for staging)
 * Go to https://developer.atlassian.com/ and create two OAuth clients. Add them as ADK and Agentspace OAuth credentials. Configure each OAuth client with the respect redirect URLs (one with vertex and one localhost).
 * make deploy (for deploy into AgentEngine and Agentspace), make adk (for local running), make adk-agentengine (for local running against AgentEngine).

## Notes

For enhancing the scope the AUTH URL for Agentspace needs updating as well as the list of SCOPES for ADK.
