# Folk MCP Server — Roadmap

## Current State (v0.4)

```
IMPLEMENTED (16 tools):
├── People
│   ├── folk_search_people      ✓
│   ├── folk_get_person         ✓
│   ├── folk_create_person      ✓  (+ companies field)
│   ├── folk_update_person      ✓  (+ companies, groups fields)
│   └── folk_delete_person      ✓
├── Companies
│   ├── folk_search_companies   ✓
│   ├── folk_get_company        ✓
│   ├── folk_create_company     ✓  (fixed groups format)
│   └── folk_update_company     ✓  (+ groups field)
├── Groups
│   ├── folk_list_groups        ✓
│   ├── folk_get_group_members  ✓
│   ├── folk_add_to_group       ✓
│   ├── folk_remove_from_group  ✓
│   └── folk_export_group       ✓
└── Notes
    └── folk_add_note           ✓

FEATURES:
├── Secure API key (.env)   ✓
├── Input validation        ✓
├── Retry logic             ✓
├── Rate limit handling     ✓
├── CSV escaping            ✓
└── Company-person linking  ✓  (v0.4)
```

---

## Folk API — Full Capabilities

Based on developer.folk.app/llms.txt:

```
AVAILABLE ENDPOINTS:
├── Companies (CRUD + list)        ← PARTIAL
├── People (CRUD + list)           ← IMPLEMENTED
├── Deals (CRUD + list)            ← MISSING
├── Notes (CRUD + list)            ← PARTIAL (create only)
├── Interactions (log)             ← MISSING
├── Reminders (CRUD + list)        ← MISSING
├── Users (get, list)              ← MISSING
├── Groups (list, custom fields)   ← PARTIAL
└── Webhooks (CRUD + list)         ← MISSING
```

---

## Phase 1: Security & Stability ✅ COMPLETE

**Priority: HIGH | Effort: LOW**

```
[x] Move API key to .env file
[x] Add input validation for IDs
[x] Fix query/cursor parameter bug
[x] Add proper CSV escaping
[x] Add rate limiting handling
[x] Add retry logic for transient failures
```

---

## Phase 2: Complete Core CRUD ✅ PARTIAL

**Priority: HIGH | Effort: MEDIUM**

### Companies ✅ DONE
```python
folk_get_company         # GET /companies/{id}        ✓
folk_create_company      # POST /companies            ✓
folk_update_company      # PATCH /companies/{id}      ✓
folk_delete_company      # DELETE /companies/{id}     (skipped - rarely needed)
```

### Notes (expand) - DEFERRED
```python
folk_list_notes          # GET /notes
folk_get_note            # GET /notes/{id}
folk_update_note         # PATCH /notes/{id}
folk_delete_note         # DELETE /notes/{id}
```

### People ✅ DONE
```python
folk_delete_person       # DELETE /people/{id}                    ✓
folk_remove_from_group   # DELETE /groups/{id}/members/{person_id} ✓
```

---

## Phase 3: Deals Pipeline

**Priority: HIGH | Effort: MEDIUM**

For Graphyn investor pipeline tracking:

```python
folk_list_deals          # GET /deals
folk_get_deal            # GET /deals/{id}
folk_create_deal         # POST /deals
folk_update_deal         # PATCH /deals/{id}
folk_delete_deal         # DELETE /deals/{id}

# Deal stages for investor pipeline:
# Identified → Contacted → Meeting → Diligence → Committed → Closed
```

---

## Phase 4: Activity & Reminders

**Priority: MEDIUM | Effort: MEDIUM**

### Interactions
```python
folk_log_interaction     # POST /interactions
# Types: email, call, meeting, note
# Links to person or company
```

### Reminders
```python
folk_list_reminders      # GET /reminders
folk_get_reminder        # GET /reminders/{id}
folk_create_reminder     # POST /reminders
folk_update_reminder     # PATCH /reminders/{id}
folk_delete_reminder     # DELETE /reminders/{id}
folk_complete_reminder   # Mark as done
```

---

## Phase 5: Workspace & Users

**Priority: LOW | Effort: LOW**

```python
folk_get_current_user    # GET /users/me
folk_list_users          # GET /users
folk_get_user            # GET /users/{id}
```

---

## Phase 6: Webhooks & Real-time

**Priority: LOW | Effort: HIGH**

```python
folk_list_webhooks       # GET /webhooks
folk_create_webhook      # POST /webhooks
folk_update_webhook      # PATCH /webhooks/{id}
folk_delete_webhook      # DELETE /webhooks/{id}

# Events to subscribe:
# person.created, person.updated
# company.created, company.updated
# deal.created, deal.updated, deal.stage_changed
# note.created
# interaction.logged
```

---

## Implementation Plan

### Week 1: Security & Stability
```
DAY 1-2:
├── Move API key to .env
├── Add python-dotenv loading
└── Update README

DAY 3-4:
├── Fix query/cursor bug
├── Add input validation
└── Add CSV escaping

DAY 5:
├── Add retry logic
├── Add rate limit handling
└── Test all existing tools
```

### Week 2: Core CRUD Expansion
```
DAY 1-2:
├── folk_create_company
├── folk_update_company
├── folk_get_company
└── folk_delete_company

DAY 3-4:
├── folk_delete_person
├── folk_remove_from_group
└── Expand notes tools

DAY 5:
└── Test & document
```

### Week 3: Deals Pipeline
```
DAY 1-3:
├── All deal CRUD tools
├── Deal stage management
└── Pipeline queries

DAY 4-5:
├── Integration with graphyn-pitch
├── Investor pipeline automation
└── Test end-to-end
```

---

## Tool Schema Template

```python
@self.server.list_tools()
async def handle_list_tools():
    return [
        types.Tool(
            name="folk_create_deal",
            description="Create a new deal in Folk CRM pipeline",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Deal name (e.g., 'Graphyn - Seed Round')"
                    },
                    "value": {
                        "type": "number",
                        "description": "Deal value in cents"
                    },
                    "stage": {
                        "type": "string",
                        "description": "Pipeline stage",
                        "enum": ["identified", "contacted", "meeting",
                                 "diligence", "committed", "closed", "lost"]
                    },
                    "person_id": {
                        "type": "string",
                        "description": "Associated person ID"
                    },
                    "company_id": {
                        "type": "string",
                        "description": "Associated company ID"
                    }
                },
                "required": ["name"]
            }
        ),
        # ... more tools
    ]
```

---

## Integration with graphyn-pitch

Once Deals are implemented, update `/commands/investor-intro.md`:

```markdown
# After sending intro, create deal:
1. Create person: mcp__folk-crm__folk_create_person
2. Add to group: mcp__folk-crm__folk_add_to_group
3. Create deal: mcp__folk-crm__folk_create_deal
4. Log interaction: mcp__folk-crm__folk_log_interaction
5. Set reminder: mcp__folk-crm__folk_create_reminder
```

This creates a full CRM workflow:
- Contact created
- Added to investor group
- Deal in pipeline
- Interaction logged
- Follow-up reminder set

---

## Target State (v1.0)

```
TOOLS (25+):
├── People (6)     → search, get, create, update, delete, remove_from_group
├── Companies (5)  → search, get, create, update, delete
├── Groups (3)     → list, get_members, add_to_group
├── Deals (5)      → list, get, create, update, delete
├── Notes (5)      → list, get, create, update, delete
├── Interactions (1) → log
├── Reminders (5)  → list, get, create, update, delete
├── Users (3)      → me, list, get
└── Export (1)     → export_group

FEATURES:
├── Secure API key handling
├── Input validation
├── Rate limiting
├── Retry logic
├── Error normalization
└── Full API coverage
```
