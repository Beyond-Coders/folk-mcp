#!/usr/bin/env python3
"""
Folk CRM MCP Server
Provides tools to interact with Folk CRM API
"""

import os
import re
import csv
import io
import json
import logging
import urllib.parse
from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
import httpx
from dotenv import load_dotenv

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Load .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Folk API configuration
FOLK_API_KEY = os.getenv("FOLK_API_KEY")
if not FOLK_API_KEY:
    raise ValueError("FOLK_API_KEY environment variable is required. Set it in .env file or environment.")
FOLK_API_BASE_URL = "https://api.folk.app/v1"

# Validation patterns
ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
GROUP_ID_PATTERN = re.compile(r'^grp_[a-f0-9-]+$')


def validate_id(id_value: str, id_type: str = "ID") -> bool:
    """Validate ID format to prevent injection attacks."""
    if not id_value or not isinstance(id_value, str):
        return False
    if len(id_value) > 100:  # Reasonable max length
        return False
    return bool(ID_PATTERN.match(id_value))


def validate_group_id(group_id: str) -> bool:
    """Validate Folk group ID format (grp_uuid)."""
    if not group_id or not isinstance(group_id, str):
        return False
    return bool(GROUP_ID_PATTERN.match(group_id))


async def retry_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    max_retries: int = 3,
    **kwargs
) -> httpx.Response:
    """Execute HTTP request with retry logic and rate limit handling."""
    last_exception = None

    for attempt in range(max_retries):
        try:
            response = await getattr(client, method)(url, **kwargs)

            # Handle rate limiting (429)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 2 ** attempt))
                logger.warning(f"Rate limited. Waiting {retry_after}s before retry...")
                await asyncio.sleep(retry_after)
                continue

            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", 2 ** attempt))
                logger.warning(f"Rate limited. Waiting {retry_after}s before retry...")
                await asyncio.sleep(retry_after)
                last_exception = e
                continue
            raise
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            last_exception = e
            wait_time = 2 ** attempt
            logger.warning(f"Connection error. Retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)

    if last_exception:
        raise last_exception
    raise httpx.HTTPError(f"Failed after {max_retries} retries")

class FolkMCPServer:
    def __init__(self):
        self.server = Server("folk-crm")
        self.setup_handlers()
        
    def setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name="folk_search_people",
                    description="Search for people in Folk CRM",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for people (searches in names, emails, companies)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of results to return (default: 20, max: 100)",
                                "default": 20
                            },
                            "cursor": {
                                "type": "string",
                                "description": "Pagination cursor for next page of results"
                            }
                        }
                    }
                ),
                types.Tool(
                    name="folk_get_person",
                    description="Get detailed information about a specific person",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person to retrieve"
                            }
                        },
                        "required": ["person_id"]
                    }
                ),
                types.Tool(
                    name="folk_list_groups",
                    description="List all groups/lists in Folk CRM",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of results to return (default: 20)",
                                "default": 20
                            }
                        }
                    }
                ),
                types.Tool(
                    name="folk_get_group_members",
                    description="Get members of a specific group/list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "group_id": {
                                "type": "string",
                                "description": "The ID of the group"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of results to return (default: 20)",
                                "default": 20
                            }
                        },
                        "required": ["group_id"]
                    }
                ),
                types.Tool(
                    name="folk_create_person",
                    description="Create a new person in Folk CRM with correct API format",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "firstName": {
                                "type": "string",
                                "description": "First name"
                            },
                            "lastName": {
                                "type": "string",
                                "description": "Last name"
                            },
                            "emails": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Email addresses (array)"
                            },
                            "jobTitle": {
                                "type": "string",
                                "description": "Job title"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description/notes about the person"
                            },
                            "groups": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {
                                            "type": "string",
                                            "description": "Group ID to add person to"
                                        }
                                    }
                                },
                                "description": "Groups to add the person to"
                            },
                            "companies": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": "Company ID"},
                                        "name": {"type": "string", "description": "Company name (alternative to ID)"}
                                    }
                                },
                                "description": "Companies to associate (first = primary). Use id or name."
                            }
                        },
                        "required": ["emails"]
                    }
                ),
                types.Tool(
                    name="folk_update_person",
                    description="Update an existing person's information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person to update"
                            },
                            "firstName": {
                                "type": "string",
                                "description": "First name"
                            },
                            "lastName": {
                                "type": "string",
                                "description": "Last name"
                            },
                            "emails": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Email addresses"
                            },
                            "jobTitle": {
                                "type": "string",
                                "description": "Job title"
                            },
                            "description": {
                                "type": "string",
                                "description": "Description/notes about the person"
                            },
                            "companies": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": "Company ID"},
                                        "name": {"type": "string", "description": "Company name (alternative to ID)"}
                                    }
                                },
                                "description": "Companies to associate (replaces all existing). First = primary."
                            },
                            "groups": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": "Group ID"}
                                    }
                                },
                                "description": "Groups to set (replaces all existing)."
                            }
                        },
                        "required": ["person_id"]
                    }
                ),
                types.Tool(
                    name="folk_add_to_group",
                    description="Add a person to a group/list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person"
                            },
                            "group_id": {
                                "type": "string",
                                "description": "The ID of the group (e.g., grp_79b6ed73-9939-4118-ba65-7f8cdf401052)"
                            }
                        },
                        "required": ["person_id", "group_id"]
                    }
                ),
                types.Tool(
                    name="folk_search_companies",
                    description="Search for companies in Folk CRM",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for companies"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of results to return (default: 20)",
                                "default": 20
                            }
                        }
                    }
                ),
                types.Tool(
                    name="folk_add_note",
                    description="Add a note to a person",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person"
                            },
                            "note": {
                                "type": "string",
                                "description": "The note content"
                            }
                        },
                        "required": ["person_id", "note"]
                    }
                ),
                types.Tool(
                    name="folk_export_group",
                    description="Export members of a group as CSV or JSON",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "group_id": {
                                "type": "string",
                                "description": "The ID of the group to export"
                            },
                            "format": {
                                "type": "string",
                                "enum": ["json", "csv"],
                                "description": "Export format (json or csv)",
                                "default": "json"
                            }
                        },
                        "required": ["group_id"]
                    }
                ),
                # Phase 2: Companies CRUD
                types.Tool(
                    name="folk_get_company",
                    description="Get detailed information about a specific company",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_id": {
                                "type": "string",
                                "description": "The ID of the company to retrieve"
                            }
                        },
                        "required": ["company_id"]
                    }
                ),
                types.Tool(
                    name="folk_create_company",
                    description="Create a new company in Folk CRM. Note: Company names are unique - if you try to create a company with an existing name, the existing company will be returned.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Company name (required, must be unique)"
                            },
                            "description": {
                                "type": "string",
                                "description": "Company description"
                            },
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of URLs (e.g., website, LinkedIn)"
                            },
                            "groups": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": "Group ID"}
                                    }
                                },
                                "description": "Groups to add the company to"
                            }
                        },
                        "required": ["name"]
                    }
                ),
                types.Tool(
                    name="folk_update_company",
                    description="Update an existing company's information",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "company_id": {
                                "type": "string",
                                "description": "The ID of the company to update"
                            },
                            "name": {
                                "type": "string",
                                "description": "Company name"
                            },
                            "description": {
                                "type": "string",
                                "description": "Company description"
                            },
                            "urls": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of URLs (e.g., website, LinkedIn)"
                            },
                            "groups": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string", "description": "Group ID"}
                                    }
                                },
                                "description": "Groups to set (replaces all existing)."
                            }
                        },
                        "required": ["company_id"]
                    }
                ),
                # Phase 2: People delete & remove
                types.Tool(
                    name="folk_delete_person",
                    description="Delete a person from Folk CRM",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person to delete"
                            }
                        },
                        "required": ["person_id"]
                    }
                ),
                types.Tool(
                    name="folk_remove_from_group",
                    description="Remove a person from a group/list",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "person_id": {
                                "type": "string",
                                "description": "The ID of the person"
                            },
                            "group_id": {
                                "type": "string",
                                "description": "The ID of the group"
                            }
                        },
                        "required": ["person_id", "group_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, 
            arguments: dict | None
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            if arguments is None:
                arguments = {}
            
            try:
                async with httpx.AsyncClient() as client:
                    headers = {
                        "Authorization": f"Bearer {FOLK_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    
                    if name == "folk_search_people":
                        query = arguments.get("query", "")
                        limit = arguments.get("limit", 20)
                        cursor = arguments.get("cursor")

                        params = {
                            "limit": limit
                        }
                        # Folk API uses filter[fullName][like] for name search, not "q"
                        if query:
                            params["filter[fullName][like]"] = query
                        # Pagination cursor (separate from search query)
                        if cursor:
                            params["cursor"] = cursor

                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/people",
                            headers=headers,
                            params=params
                        )
                        data = response.json()
                        
                        # Format the response nicely
                        if "people" in data:
                            result = f"Found {len(data.get('people', []))} people:\n\n"
                            for person in data.get("people", []):
                                result += f"• {person.get('firstName', '')} {person.get('lastName', '')}\n"
                                if person.get('emails'):
                                    result += f"  Email: {person['emails'][0]}\n"
                                if person.get('company'):
                                    result += f"  Company: {person['company']}\n"
                                if person.get('title'):
                                    result += f"  Title: {person['title']}\n"
                                result += f"  ID: {person.get('id', '')}\n\n"
                        else:
                            result = json.dumps(data, indent=2)
                        
                        return [types.TextContent(
                            type="text",
                            text=result
                        )]
                    
                    elif name == "folk_get_person":
                        person_id = arguments["person_id"]

                        # Validate person_id format
                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]

                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/people/{person_id}",
                            headers=headers
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=json.dumps(data, indent=2)
                        )]
                    
                    elif name == "folk_list_groups":
                        limit = arguments.get("limit", 20)
                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/groups",
                            headers=headers,
                            params={"limit": limit}
                        )
                        data = response.json()
                        
                        # Format groups nicely
                        if "groups" in data:
                            result = f"Found {len(data.get('groups', []))} groups:\n\n"
                            for group in data.get("groups", []):
                                result += f"• {group.get('name', 'Unnamed')}\n"
                                result += f"  ID: {group.get('id', '')}\n"
                                result += f"  Members: {group.get('memberCount', 0)}\n\n"
                        else:
                            result = json.dumps(data, indent=2)
                        
                        return [types.TextContent(
                            type="text",
                            text=result
                        )]
                    
                    elif name == "folk_get_group_members":
                        group_id = arguments["group_id"]
                        limit = arguments.get("limit", 20)

                        # Validate group_id format
                        if not validate_group_id(group_id):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid group_id format. Expected format: grp_<uuid>"
                            )]

                        # Folk API doesn't have a dedicated group members endpoint
                        # Instead, filter people by group using filter[groups][in][id]
                        params = {
                            "limit": limit,
                            "filter[groups][in][id]": group_id
                        }

                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/people",
                            headers=headers,
                            params=params
                        )
                        data = response.json()

                        # Format the response nicely
                        if "people" in data:
                            result = f"Found {len(data.get('people', []))} members in group:\n\n"
                            for person in data.get("people", []):
                                result += f"• {person.get('firstName', '')} {person.get('lastName', '')}\n"
                                if person.get('emails'):
                                    result += f"  Email: {person['emails'][0]}\n"
                                if person.get('company'):
                                    result += f"  Company: {person['company']}\n"
                                if person.get('title'):
                                    result += f"  Title: {person['title']}\n"
                                result += f"  ID: {person.get('id', '')}\n\n"

                            # Include pagination info
                            if data.get('pagination', {}).get('nextLink'):
                                result += f"\n[More results available - use cursor for pagination]"
                        else:
                            result = json.dumps(data, indent=2)

                        return [types.TextContent(
                            type="text",
                            text=result
                        )]
                    
                    elif name == "folk_create_person":
                        # Use Folk's correct API format
                        payload = {}

                        # Required field
                        if "emails" in arguments:
                            payload["emails"] = arguments["emails"]

                        # Optional fields with correct Folk API field names
                        if "firstName" in arguments:
                            payload["firstName"] = arguments["firstName"]
                        if "lastName" in arguments:
                            payload["lastName"] = arguments["lastName"]
                        if "jobTitle" in arguments:
                            payload["jobTitle"] = arguments["jobTitle"]
                        if "description" in arguments:
                            payload["description"] = arguments["description"]
                        if "groups" in arguments:
                            # Validate group IDs
                            for group in arguments["groups"]:
                                if "id" in group and not validate_group_id(group["id"]):
                                    return [types.TextContent(
                                        type="text",
                                        text=f"Error: Invalid group_id format: {group.get('id')}"
                                    )]
                            payload["groups"] = arguments["groups"]
                        if "companies" in arguments:
                            payload["companies"] = arguments["companies"]

                        response = await retry_request(
                            client, "post",
                            f"{FOLK_API_BASE_URL}/people",
                            headers=headers,
                            json=payload
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=f"Person created successfully:\n{json.dumps(data, indent=2)}"
                        )]

                    elif name == "folk_update_person":
                        person_id = arguments["person_id"]

                        # Validate person_id format
                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]

                        payload = {}

                        # Add fields to update with correct Folk API field names
                        for field in ["firstName", "lastName", "emails", "jobTitle", "description", "companies", "groups"]:
                            if field in arguments:
                                payload[field] = arguments[field]

                        response = await retry_request(
                            client, "patch",
                            f"{FOLK_API_BASE_URL}/people/{person_id}",
                            headers=headers,
                            json=payload
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=f"Person updated successfully:\n{json.dumps(data, indent=2)}"
                        )]
                    
                    elif name == "folk_add_to_group":
                        person_id = arguments["person_id"]
                        group_id = arguments["group_id"]

                        # Validate IDs
                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]
                        if not validate_group_id(group_id):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid group_id format. Expected format: grp_<uuid>"
                            )]

                        # First, get the person's current groups
                        get_response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/people/{person_id}",
                            headers=headers
                        )
                        person_data = get_response.json()
                        current_groups = person_data.get("data", {}).get("groups", [])

                        # Check if person is already in the group
                        group_ids = [g["id"] for g in current_groups]
                        if group_id in group_ids:
                            return [types.TextContent(
                                type="text",
                                text=f"Person {person_id} is already in group {group_id}"
                            )]

                        # Add the new group to the list
                        new_groups = current_groups + [{"id": group_id}]

                        # Update the person with the new groups list
                        response = await retry_request(
                            client, "patch",
                            f"{FOLK_API_BASE_URL}/people/{person_id}",
                            headers=headers,
                            json={"groups": new_groups}
                        )

                        return [types.TextContent(
                            type="text",
                            text=f"Person {person_id} added to group {group_id} successfully"
                        )]
                    
                    elif name == "folk_search_companies":
                        query = arguments.get("query", "")
                        limit = arguments.get("limit", 20)

                        # Folk API uses filter[name][like] for name search, not "q"
                        params = {"limit": limit}
                        if query:
                            params["filter[name][like]"] = query

                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/companies",
                            headers=headers,
                            params=params
                        )
                        data = response.json()

                        # Format the response nicely
                        if "companies" in data:
                            result = f"Found {len(data.get('companies', []))} companies:\n\n"
                            for company in data.get("companies", []):
                                result += f"• {company.get('name', 'Unnamed')}\n"
                                if company.get('domain'):
                                    result += f"  Domain: {company['domain']}\n"
                                if company.get('industry'):
                                    result += f"  Industry: {company['industry']}\n"
                                result += f"  ID: {company.get('id', '')}\n\n"
                        else:
                            result = json.dumps(data, indent=2)

                        return [types.TextContent(
                            type="text",
                            text=result
                        )]
                    
                    elif name == "folk_add_note":
                        person_id = arguments["person_id"]
                        note = arguments["note"]

                        # Validate person_id format
                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]

                        response = await retry_request(
                            client, "post",
                            f"{FOLK_API_BASE_URL}/people/{person_id}/notes",
                            headers=headers,
                            json={"content": note}
                        )

                        return [types.TextContent(
                            type="text",
                            text=f"Note added to person {person_id} successfully"
                        )]
                    
                    elif name == "folk_export_group":
                        group_id = arguments["group_id"]
                        format_type = arguments.get("format", "json")

                        # Validate group_id format
                        if not validate_group_id(group_id):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid group_id format. Expected format: grp_<uuid>"
                            )]

                        # Folk API doesn't have a dedicated group members endpoint
                        # Instead, filter people by group using filter[groups][in][id]
                        # Use pagination to get all members
                        all_people = []
                        cursor = None
                        max_pages = 100

                        while max_pages > 0:
                            max_pages -= 1
                            params = {
                                "limit": 100,  # Max per page
                                "filter[groups][in][id]": group_id
                            }
                            if cursor:
                                params["cursor"] = cursor

                            response = await retry_request(
                                client, "get",
                                f"{FOLK_API_BASE_URL}/people",
                                headers=headers,
                                params=params
                            )
                            page_data = response.json()

                            all_people.extend(page_data.get("people", []))

                            # Check for next page
                            next_link = page_data.get("pagination", {}).get("nextLink")
                            if not next_link:
                                break
                            # Extract cursor from next_link URL
                            parsed = urllib.parse.urlparse(next_link)
                            query_params = urllib.parse.parse_qs(parsed.query)
                            cursor = query_params.get("cursor", [None])[0]
                            if not cursor:
                                break

                        data = {"people": all_people}

                        if format_type == "csv":
                            # Create properly escaped CSV format using Python csv module
                            output = io.StringIO()
                            writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
                            writer.writerow(["First Name", "Last Name", "Email", "Company", "Title"])
                            for person in data.get("people", []):
                                emails = person.get('emails', [])
                                email = emails[0] if emails else ''
                                writer.writerow([
                                    person.get('firstName', ''),
                                    person.get('lastName', ''),
                                    email,
                                    person.get('company', ''),
                                    person.get('title', '')
                                ])
                            result = output.getvalue()
                        else:
                            result = json.dumps(data, indent=2)

                        return [types.TextContent(
                            type="text",
                            text=result
                        )]

                    # Phase 2: Companies CRUD
                    elif name == "folk_get_company":
                        company_id = arguments["company_id"]

                        if not validate_id(company_id, "company_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid company_id format"
                            )]

                        response = await retry_request(
                            client, "get",
                            f"{FOLK_API_BASE_URL}/companies/{company_id}",
                            headers=headers
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=json.dumps(data, indent=2)
                        )]

                    elif name == "folk_create_company":
                        payload = {"name": arguments["name"]}

                        if "description" in arguments:
                            payload["description"] = arguments["description"]
                        if "urls" in arguments:
                            payload["urls"] = arguments["urls"]
                        if "groups" in arguments:
                            payload["groups"] = arguments["groups"]

                        response = await retry_request(
                            client, "post",
                            f"{FOLK_API_BASE_URL}/companies",
                            headers=headers,
                            json=payload
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=f"Company created successfully:\n{json.dumps(data, indent=2)}"
                        )]

                    elif name == "folk_update_company":
                        company_id = arguments["company_id"]

                        if not validate_id(company_id, "company_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid company_id format"
                            )]

                        payload = {}
                        for field in ["name", "description", "urls", "groups"]:
                            if field in arguments:
                                payload[field] = arguments[field]

                        response = await retry_request(
                            client, "patch",
                            f"{FOLK_API_BASE_URL}/companies/{company_id}",
                            headers=headers,
                            json=payload
                        )
                        data = response.json()

                        return [types.TextContent(
                            type="text",
                            text=f"Company updated successfully:\n{json.dumps(data, indent=2)}"
                        )]

                    # Phase 2: People delete & remove
                    elif name == "folk_delete_person":
                        person_id = arguments["person_id"]

                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]

                        response = await retry_request(
                            client, "delete",
                            f"{FOLK_API_BASE_URL}/people/{person_id}",
                            headers=headers
                        )

                        return [types.TextContent(
                            type="text",
                            text=f"Person {person_id} deleted successfully"
                        )]

                    elif name == "folk_remove_from_group":
                        person_id = arguments["person_id"]
                        group_id = arguments["group_id"]

                        if not validate_id(person_id, "person_id"):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid person_id format"
                            )]
                        if not validate_group_id(group_id):
                            return [types.TextContent(
                                type="text",
                                text="Error: Invalid group_id format. Expected format: grp_<uuid>"
                            )]

                        response = await retry_request(
                            client, "delete",
                            f"{FOLK_API_BASE_URL}/groups/{group_id}/members/{person_id}",
                            headers=headers
                        )

                        return [types.TextContent(
                            type="text",
                            text=f"Person {person_id} removed from group {group_id} successfully"
                        )]

                    else:
                        return [types.TextContent(
                            type="text",
                            text=f"Unknown tool: {name}"
                        )]
                        
            except httpx.HTTPStatusError as e:
                error_msg = f"Folk API error: {e.response.status_code} - {e.response.text}"
                logger.error(error_msg)
                return [types.TextContent(
                    type="text",
                    text=f"Error: {error_msg}"
                )]
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(error_msg)
                return [types.TextContent(
                    type="text",
                    text=f"Error: {error_msg}"
                )]
    
    async def run(self):
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="folk-crm",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

async def main():
    server = FolkMCPServer()
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())