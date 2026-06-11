# Folk CRM MCP Server

MCP server for interacting with [Folk CRM](https://folk.app) API. Provides 16 tools for managing people, companies, groups, and notes through any MCP-compatible client.

## Installation

1. **Clone and install dependencies:**
```bash
git clone https://github.com/fuego-wtf/folk-mcp.git
cd folk-mcp
pip install -r requirements.txt
```

2. **Create .env file with your API key:**
```bash
cp .env.example .env
# Edit .env and add your Folk API key
```

Get your API key from: https://folk.app/settings/developers

## Configuration

### Claude Code

Add to your Claude Code MCP settings (`~/.claude/settings.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "folk-crm": {
      "command": "python",
      "args": ["/path/to/folk-mcp/server.py"]
    }
  }
}
```

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "folk-crm": {
      "command": "python",
      "args": ["/path/to/folk-mcp/server.py"],
      "env": {
        "FOLK_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

If using .env file, you can omit the `env` block.

## Available Tools (16 total)

### People
| Tool | Description |
|------|-------------|
| `folk_search_people` | Search for people by name, email, company |
| `folk_get_person` | Get full person details |
| `folk_create_person` | Create person with emails, companies, groups |
| `folk_update_person` | Update person fields, companies, groups, and custom fields (e.g. Status) |
| `folk_delete_person` | Delete a person |

### Companies
| Tool | Description |
|------|-------------|
| `folk_search_companies` | Search companies by name |
| `folk_get_company` | Get full company details |
| `folk_create_company` | Create company with groups |
| `folk_update_company` | Update company fields, groups |

### Groups
| Tool | Description |
|------|-------------|
| `folk_list_groups` | List all groups/lists |
| `folk_get_group_members` | Get members of a group |
| `folk_add_to_group` | Add person to a group |
| `folk_remove_from_group` | Remove person from a group |
| `folk_export_group` | Export group as CSV or JSON |

### Notes
| Tool | Description |
|------|-------------|
| `folk_add_note` | Create a note on a person, company, or deal (markdown, public/private) |

## Key Features

- **Company linking** — Associate people with companies on create or update
- **Custom field updates** — Update group-scoped fields like Status via `customFieldValues` on `folk_update_person`
- **Group management** — Add people/companies to groups with object-format IDs
- **Retry logic** — Automatic retry with exponential backoff for transient failures
- **Rate limit handling** — Respects `Retry-After` header on 429 responses
- **Input validation** — All IDs validated before API calls
- **Pagination** — Cursor-based pagination for large result sets
- **CSV export** — Proper escaping via Python csv module

## Usage Examples

### Link a person to a company
```
Update person per_xxx in Folk — set their company to Graphyn (com_yyy)
```

### Create a contact with company
```
Create a new person in Folk: Jane Doe, jane@example.com, linked to company "Acme Corp"
```

### Search and export
```
Export the "Potential Investors" group from Folk as CSV
```

### Add to a group
```
Add person per_xxx to the "Komunite" group in Folk
```

### Update a person's status
```
Update John Doe's status to "Active" in Folk (group grp_xxx)
```

Custom fields are scoped to a group. Pass them as `customFieldValues` keyed by group ID, e.g. `{"grp_xxx": {"Status": "Active"}}`.

### Add a note to a lead
```
Add a note to John Doe in Folk: TIER 1 — Qualified. COO at Digital Pay...
```

Notes support markdown, public/private visibility, and can be linked to people (`per_xxx`), companies (`com_xxx`), or deals. Use `visibility: "private"` for notes only you can see.

## Security

- API keys loaded from `.env` file (never committed)
- All IDs validated with regex patterns before API calls
- Rate limiting respected with automatic backoff

## Folk API Documentation

For more details on the Folk API: https://developers.folk.app/

## License

MIT
