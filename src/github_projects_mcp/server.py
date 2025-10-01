#!/usr/bin/env python3
"""
GitHub Projects V2 MCP Server

A Model Context Protocol server that provides tools for managing GitHub Projects V2.
"""


import json
import logging
import os
from typing import Any, List, Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

from .github_client import GitHubClient, GitHubClientError

# Load environment variables from .env file if present
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize the MCP server
mcp = FastMCP(
    name="GitHub Projects V2",
    instructions="This server provides tools for managing GitHub Projects V2.",
)

# GitHub client for GraphQL API interactions
github_client = GitHubClient(
    token=os.environ.get("GITHUB_TOKEN"),
)

# --- Tool definitions ---


@mcp.tool()
async def list_projects(owner: str) -> str:
    """List GitHub Projects V2 for a given organization or user.

    Args:
        owner: The GitHub organization or user name

    Returns:
        A formatted string with project details
    """
    try:
        projects = await github_client.get_projects(owner)

        if not projects:
            return f"No projects found for {owner}"

        result = f"Projects for {owner}:\n\n"
        for project in projects:
            result += f"- ID: {project['id']}\n"
            result += f"  Number: {project['number']}\n"
            result += f"  Title: {project['title']}\n"
            result += f"  URL: {project['url']}\n"
            result += "\n"

        return result
    except GitHubClientError as e:
        logger.error(f"Error listing projects for {owner}: {e}")
        return f"Error: Could not list projects for {owner}. Details: {e}"


@mcp.tool()
async def get_project_fields(owner: str, project_number: int) -> str:
    """Get fields available in a GitHub Project V2, including options for SingleSelect fields.

    Args:
        owner: The GitHub organization or user name
        project_number: The project number

    Returns:
        A formatted string with field details.
    """
    try:
        # Use the new method that returns structured data
        fields_details = await github_client.get_project_fields_details(
            owner, project_number
        )

        if not fields_details:
            return f"No fields found for project #{project_number} in {owner}"

        result = f"Fields for project #{project_number} in {owner}:\n\n"
        for field_name, details in fields_details.items():
            result += f"- Name: {field_name}\n"
            result += f"  ID: {details['id']}\n"
            result += f"  Type: {details['type']}\n"

            # Show options if it's a SingleSelect field
            if details["type"] == "ProjectV2SingleSelectField" and details.get(
                "options"
            ):
                result += "  Options (Name: ID):\n"
                for opt_name, opt_id in details["options"].items():
                    result += f"    - {opt_name}: {opt_id}\n"

            # TODO: Add similar display for Iteration fields if needed

            result += "\n"

        return result
    except GitHubClientError as e:
        logger.error(f"Error getting fields for project {owner}/{project_number}: {e}")
        return f"Error: Could not get fields for project {owner}/{project_number}. Details: {e}"


@mcp.tool()
async def get_project_items(
    owner: str,
    project_number: int,
    limit: int = 50,
    state: Optional[str] = None,
    filter_field_name: Optional[str] = None,
    filter_field_value: Optional[str] = None,
    cursor: Optional[str] = None,
) -> str:
    """Get items in a GitHub Project V2. Can filter by state OR a single custom field=value.

    Args:
        owner: The GitHub organization or user name
        project_number: The project number
        limit: Maximum number of items to return (default: 50). When filtering, the system automatically fetches more items to improve efficiency.
        state: Optional state filter (e.g., "OPEN", "CLOSED"). Applies to Issues/PRs.
        filter_field_name: Optional custom field name to filter by (e.g., "Status"). Currently supports SingleSelect and Iteration fields.
        filter_field_value: Optional custom field value to filter by (e.g., "In Development"). Uses case-insensitive matching.
        cursor: Optional cursor for pagination. Use value from previous results to get next page.

    Returns:
        A formatted string with item details.
    """
    if state and filter_field_name:
        return "Error: Cannot filter by both 'state' and a custom field ('filter_field_name') simultaneously."

    try:
        result = await github_client.get_project_items(
            owner,
            project_number,
            limit,
            state,
            filter_field_name,
            filter_field_value,
            cursor,
        )

        items = result["items"]
        page_info = result["pageInfo"]
        has_next_page = page_info.get("hasNextPage", False)
        end_cursor = page_info.get("endCursor")

        filter_desc = ""
        if state:
            filter_desc = f" (State: {state.upper()})"
        elif filter_field_name and filter_field_value:
            filter_desc = f" (Filter: {filter_field_name} = '{filter_field_value}')"

        pagination_desc = ""
        if cursor:
            pagination_desc = " (continued)"

        if not items:
            if cursor:
                return f"No more items found in project #{project_number} for {owner}{filter_desc}"
            else:
                # Add more context for debugging purposes when filtering returns no items
                if filter_field_name and filter_field_value:
                    # Get available fields and options to help debug
                    try:
                        fields_details = await github_client.get_project_fields_details(
                            owner, project_number
                        )
                        field_info = None

                        # Try to find the field case-insensitively
                        for fname, finfo in fields_details.items():
                            if fname.lower() == filter_field_name.lower():
                                field_info = finfo
                                break

                        if field_info:
                            field_type = field_info.get("type", "Unknown")
                            if field_type == "ProjectV2SingleSelectField":
                                available_options = list(
                                    field_info.get("options", {}).keys()
                                )
                                return (
                                    f"No items found in project #{project_number} for {owner}{filter_desc}\n\n"
                                    f"Debug info:\n"
                                    f"- Found field '{filter_field_name}' with type '{field_type}'\n"
                                    f"- Available options: {available_options}\n"
                                    f"- Note: Searched up to {limit} items. If the project has many items, some '{filter_field_value}' items might be beyond this scope.\n"
                                    f"- Tip: Try increasing the limit parameter or check if the field value spelling is correct."
                                )
                            elif field_type == "ProjectV2IterationField":
                                available_iterations = list(
                                    field_info.get("iterations", {}).keys()
                                )
                                return (
                                    f"No items found in project #{project_number} for {owner}{filter_desc}\n\n"
                                    f"Debug info:\n"
                                    f"- Found field '{filter_field_name}' with type '{field_type}'\n"
                                    f"- Available iterations: {available_iterations}\n"
                                    f"- Note: Searched up to {limit} items. If the project has many items, some '{filter_field_value}' items might be beyond this scope.\n"
                                    f"- Tip: Try increasing the limit parameter or check if the field value spelling is correct."
                                )
                    except Exception as e:
                        logger.warning(
                            f"Could not get additional field details for debug info: {e}"
                        )

                return f"No items found in project #{project_number} for {owner}{filter_desc}\n\nNote: If the project has many items, try increasing the limit parameter to search more thoroughly."

        # Format results
        result = f"Items in project #{project_number} for {owner}{filter_desc}{pagination_desc}:\n\n"
        for item in items:
            content = item.get("content", {})
            result += f"- Item ID: {item['id']}\n"
            item_type = content.get("__typename")
            repo_info = content.get("repository", {})
            repo_str = (
                f"{repo_info.get('owner', {}).get('login')}/{repo_info.get('name')}"
                if repo_info
                else "N/A"
            )

            if item_type == "Issue":
                result += f"  Type: Issue #{content.get('number')} ({repo_str})\n"
                result += f"  Title: {content.get('title')}\n"
                result += f"  State: {content.get('state')}\n"
                result += f"  URL: {content.get('url')}\n"
            elif item_type == "PullRequest":
                result += f"  Type: PR #{content.get('number')} ({repo_str})\n"
                result += f"  Title: {content.get('title')}\n"
                result += f"  State: {content.get('state')}\n"
                result += f"  URL: {content.get('url')}\n"
            elif item_type == "DraftIssue":
                # Include body for draft issues if available (check if client fetches it)
                body = content.get("body", "")  # Assuming client might fetch body
                result += f"  Type: Draft Issue ID: {content.get('id')}\n"
                result += f"  Title: {content.get('title')}\n"
                if body:
                    result += f"  Body: {body[:100]}...\n"  # Show preview
            else:
                result += f"  Type: {item_type or 'Unknown'}\n"
                result += f"  Content: {json.dumps(content)}\n"

            # Show processed field values
            if item.get("fieldValues"):
                result += "  Field Values:\n"
                for field_name, value in item["fieldValues"].items():
                    result += f"    - {field_name}: {value}\n"
            result += "\n"

        # Add pagination info
        if has_next_page and end_cursor:
            result += "\n--- Pagination ---\n"
            result += "More items available: Yes\n"
            result += f"Next page cursor: {end_cursor}\n"
            result += "To get the next page, use the cursor parameter:\n"
            result += f"cursor: {end_cursor}\n"

        return result
    except (
        GitHubClientError,
        ValueError,
    ) as e:  # Catch client errors and validation errors
        logger.error(
            f"Error getting items for project {owner}/{project_number} with filter: {e}"
        )
        return f"Error: Could not get items for project {owner}/{project_number}. Details: {e}"


@mcp.tool()
async def create_issue(owner: str, repo: str, title: str, body: str = "", assignees: Optional[List[str]] = None) -> str:
    """Create a new GitHub issue.

    Args:
        owner: The GitHub organization or user name
        repo: The repository name
        title: The issue title
        body: The issue body (optional)
        assignees: List of GitHub usernames to assign to the issue (optional)

    Returns:
        A formatted string with the created issue details
    """
    try:
        issue = await github_client.create_issue(owner, repo, title, body, assignees)
        assignees_info = ""
        if assignees and issue.get('assignees', {}).get('nodes'):
            assigned_users = [user['login'] for user in issue['assignees']['nodes']]
            assignees_info = f"Assignees: {', '.join(assigned_users)}\n"
        
        return (
            f"Issue created successfully!\n\n"
            f"Repository: {owner}/{repo}\n"
            f"Issue Number: #{issue['number']}\n"
            f"Title: {issue['title']}\n"
            f"{assignees_info}"
            f"URL: {issue['url']}\n"
        )
    except GitHubClientError as e:
        logger.error(f"Error creating issue in {owner}/{repo}: {e}")
        return f"Error: Could not create issue in {owner}/{repo}. Details: {e}"


@mcp.tool()
async def add_issue_to_project(
    owner: str,
    project_number: int,
    issue_owner: str,
    issue_repo: str,
    issue_number: int,
) -> str:
    """Add an existing GitHub issue to a Project V2.

    Args:
        owner: The GitHub organization or user name that owns the project
        project_number: The project number
        issue_owner: The owner of the repository containing the issue
        issue_repo: The repository name containing the issue
        issue_number: The issue number

    Returns:
        A formatted string confirming the addition
    """
    try:
        result = await github_client.add_issue_to_project(
            owner, project_number, issue_owner, issue_repo, issue_number
        )
        return (
            f"Successfully added issue {issue_owner}/{issue_repo}#{issue_number} to project #{project_number}!\n"
            f"Item ID: {result['id']}"
        )
    except GitHubClientError as e:
        logger.error(
            f"Error adding issue {issue_owner}/{issue_repo}#{issue_number} to project {owner}/{project_number}: {e}"
        )
        return f"Error: Could not add issue to project. Details: {e}"


@mcp.tool()
async def set_project_item_dates(
    owner: str,
    project_number: int,
    item_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_field_name: str = "Start Date",
    end_field_name: str = "End Date",
) -> str:
    """Set Start / End date fields for a given project item by field names.

    Args:
        owner: Project owner (user or org)
        project_number: Project number
        item_id: Project item ID
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        start_field_name: Name of the start date field (default: "Start Date")
        end_field_name: Name of the end date field (default: "End Date")

    Returns:
        A formatted confirmation message with updated fields.
    """
    if not (start_date or end_date):
        return "Error: Provide at least one of start_date or end_date"
    try:
        updates = await github_client.set_project_item_dates(
            owner,
            project_number,
            item_id,
            start_date=start_date,
            end_date=end_date,
            start_field_name=start_field_name,
            end_field_name=end_field_name,
        )
        if not updates:
            return "No date fields were updated (fields may be missing)."
        updated_str = "\n".join(f"  - {k}: {v}" for k, v in updates.items())
        return (
            f"Successfully updated date fields for item {item_id} in project #{project_number}:\n{updated_str}"
        )
    except (GitHubClientError, ValueError) as e:
        logger.error(
            f"Error setting dates on item {item_id} in project {owner}/{project_number}: {e}"
        )
        return f"Error: Could not set dates. Details: {e}"


@mcp.tool()
async def add_issue_to_project_with_dates(
    owner: str,
    project_number: int,
    issue_owner: str,
    issue_repo: str,
    issue_number: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_field_name: str = "Start Date",
    end_field_name: str = "End Date",
) -> str:
    """Add an existing issue to a project and optionally set Start / End dates in one step.

    Args:
        owner: Project owner (user/org)
        project_number: Project number
        issue_owner: Owner (user/org) of the issue's repository
        issue_repo: Repository name of the issue
        issue_number: Issue number
        start_date: Optional YYYY-MM-DD start date
        end_date: Optional YYYY-MM-DD end date
        start_field_name: Start date field name in project
        end_field_name: End date field name in project
    """
    try:
        item = await github_client.add_issue_to_project(
            owner, project_number, issue_owner, issue_repo, issue_number
        )
        item_id = item.get("id")
        date_msg = ""
        if item_id and (start_date or end_date):
            try:
                updates = await github_client.set_project_item_dates(
                    owner,
                    project_number,
                    item_id,
                    start_date=start_date,
                    end_date=end_date,
                    start_field_name=start_field_name,
                    end_field_name=end_field_name,
                )
                if updates:
                    date_lines = "\n".join(f"  - {k}: {v}" for k, v in updates.items())
                    date_msg = f"\nDates set:\n{date_lines}"
                else:
                    date_msg = "\nWarning: No date fields updated (fields may not exist)."
            except (GitHubClientError, ValueError) as e:
                date_msg = f"\nWarning: Issue added but failed to set dates: {e}"
        return (
            f"Successfully added issue {issue_owner}/{issue_repo}#{issue_number} to project #{project_number}!\n"
            f"Item ID: {item_id}{date_msg}"
        )
    except GitHubClientError as e:
        logger.error(
            f"Error adding issue {issue_owner}/{issue_repo}#{issue_number} with dates to project {owner}/{project_number}: {e}"
        )
        return f"Error: Could not add issue or set dates. Details: {e}"


@mcp.tool()
async def create_issue_and_add_to_project(
    owner: str,
    repo: str,
    project_number: int,
    title: str,
    body: str = "",
    assignees: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    start_field_name: str = "Start Date",
    end_field_name: str = "End Date",
) -> str:
    """Create an issue, add it to a project, and optionally set Start / End dates.

    Args:
        owner: Repository owner (also project owner if same)
        repo: Repository name
        project_number: Project number
        title: Issue title
        body: Issue body
        assignees: Optional list of assignee usernames
        start_date: Optional start date YYYY-MM-DD
        end_date: Optional end date YYYY-MM-DD
        start_field_name: Start date field name
        end_field_name: End date field name
    """
    try:
        issue = await github_client.create_issue(owner, repo, title, body, assignees)
        issue_number = issue.get("number")
        # Add to project
        item = await github_client.add_issue_to_project(
            owner, project_number, owner, repo, issue_number
        )
        item_id = item.get("id")
        date_msg = ""
        if item_id and (start_date or end_date):
            try:
                updates = await github_client.set_project_item_dates(
                    owner,
                    project_number,
                    item_id,
                    start_date=start_date,
                    end_date=end_date,
                    start_field_name=start_field_name,
                    end_field_name=end_field_name,
                )
                if updates:
                    date_lines = "\n".join(f"  - {k}: {v}" for k, v in updates.items())
                    date_msg = f"\nDates set:\n{date_lines}"
                else:
                    date_msg = "\nWarning: No date fields updated (fields may not exist)."
            except (GitHubClientError, ValueError) as e:
                date_msg = f"\nWarning: Issue created and added but failed to set dates: {e}"
        assignees_info = ""
        if assignees and issue.get('assignees', {}).get('nodes'):
            assigned_users = [u['login'] for u in issue['assignees']['nodes']]
            assignees_info = f"Assignees: {', '.join(assigned_users)}\n"
        return (
            f"Issue created and added to project successfully!\n\n"
            f"Repository: {owner}/{repo}\n"
            f"Issue Number: #{issue_number}\n"
            f"Title: {issue.get('title')}\n"
            f"URL: {issue.get('url')}\n"
            f"Project Item ID: {item_id}{date_msg}\n"
            f"{assignees_info}"
        )
    except GitHubClientError as e:
        logger.error(
            f"Error creating issue and adding to project {owner}/{project_number}: {e}"
        )
        return f"Error: Could not create/add issue or set dates. Details: {e}"


@mcp.tool()
async def update_project_item_field(
    owner: str, project_number: int, item_id: str, field_id: str, field_value: str
) -> str:
    """Update a field value for a project item.

    Args:
        owner: The GitHub organization or user name
        project_number: The project number
        item_id: The ID of the item to update
        field_id: The ID of the field to update
        field_value: The new value for the field (text, date, or option ID for single select)

    Returns:
        A confirmation message
    """
    try:
        # The GitHub client's update method expects the raw value, not just string
        # We might need a way to parse field_value based on field_id or context
        # For now, we pass the string directly, but this might fail for non-text fields.
        # A better implementation would fetch field info first to determine expected type.
        logger.warning(
            f"Attempting to update field {field_id} with value '{field_value}'. Type conversion might be needed."
        )

        # Attempt basic type inference (example - needs improvement)
        parsed_value: Any = field_value
        try:
            parsed_value = float(field_value)
            if parsed_value.is_integer():
                parsed_value = int(parsed_value)
        except ValueError:
            # Check if looks like a date?
            pass  # Keep as string if not obviously numeric

        result = await github_client.update_project_item_field(
            owner,
            project_number,
            item_id,
            field_id,
            parsed_value,  # Pass potentially parsed value
        )
        return (
            f"Successfully updated field for item in project #{project_number}!\n"
            f"Item ID: {item_id}\n"
            f"Field ID: {field_id}\n"
            f"Value Set: {field_value}"  # Report the value as passed to the tool
        )
    except GitHubClientError as e:
        logger.error(f"Error updating field {field_id} for item {item_id}: {e}")
        return f"Error: Could not update field value. Details: {e}"


@mcp.tool()
async def create_draft_issue(
    owner: str, project_number: int, title: str, body: str = "", assignees: Optional[List[str]] = None
) -> str:
    """Create a draft issue directly in a GitHub Project V2.

    Args:
        owner: The GitHub organization or user name
        project_number: The project number
        title: The draft issue title
        body: The draft issue body (optional)
        assignees: List of GitHub usernames to assign to the draft issue (optional)
                  Note: For draft issues, assignees must be set separately via field updates

    Returns:
        A confirmation message with the new draft issue details
    """
    try:
        result = await github_client.add_draft_issue_to_project(
            owner, project_number, title, body, assignees
        )
        return (
            f"Successfully created draft issue in project #{project_number}!\n"
            f"Item ID: {result['id']}\n"
            f"Title: {title}"
        )
    except GitHubClientError as e:
        logger.error(f"Error creating draft issue in project {project_number}: {e}")
        return f"Error: Could not create draft issue. Details: {e}"


@mcp.tool()
async def delete_project_item(owner: str, project_number: int, item_id: str) -> str:
    """Delete an item from a GitHub Project V2.

    Args:
        owner: The GitHub organization or user name
        project_number: The project number
        item_id: The ID of the item to delete

    Returns:
        A confirmation message
    """
    try:
        deleted_item_id = await github_client.delete_project_item(
            owner, project_number, item_id
        )
        return (
            f"Successfully deleted item from project #{project_number}!\n"
            f"Deleted Item ID: {deleted_item_id}"
        )
    except GitHubClientError as e:
        logger.error(
            f"Error deleting item {item_id} from project {project_number}: {e}"
        )
        return f"Error: Could not delete item. Details: {e}"


# --- Helper for updating project item field ---
# TODO: Add a helper tool to get field details (ID, name, type) to allow
#       users/LLM to specify fields by name and provide correct value types.
# Example:
# @mcp.tool()
# async def get_project_field_details(owner: str, project_number: int, field_name: str) -> str:
#    ...


# Main entry point function that can be imported
def main():
    """Main entry point for the GitHub Projects MCP server.

    Checks for required environment variables and starts the MCP server.
    """
    # Check for GitHub token
    if not os.environ.get("GITHUB_TOKEN"):
        logger.error("GITHUB_TOKEN environment variable is required")
        print("Error: GITHUB_TOKEN environment variable is required")
        exit(1)

    # Run the MCP server
    mcp.run(transport="stdio")


# Run the main function if executed directly
if __name__ == "__main__":
    main()
