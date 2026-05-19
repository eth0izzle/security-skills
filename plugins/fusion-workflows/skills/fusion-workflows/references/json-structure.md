# Fusion SOAR Workflow JSON Structure

This document describes the JSON structure used to define Falcon Fusion SOAR workflows. The workflow definition serves as both the rendering model for the workflow graph and the instruction set used by the execution engine at runtime.

The structure closely follows the **BPMN specification** but uses JSON as the serialization format.

---

## Table of Contents

1. [Top-Level Structure](#top-level-structure)
2. [Trigger](#trigger)
3. [Activities (Actions)](#activities-actions)
4. [Flows (Sequence Flows)](#flows-sequence-flows)
5. [Gateways (Decision/Parallel Logic)](#gateways-decisionparallel-logic)
6. [End Event](#end-event)
7. [SubModels (Loops)](#submodels-loops)
8. [CEL Expressions](#cel-expressions)
9. [Data References](#data-references)
10. [Custom Variables](#custom-variables)
11. [Placeholders](#placeholders)
12. [Complete Examples](#complete-examples)

---

## Top-Level Structure

A workflow is a directed graph expressed as JSON with the following top-level properties:

```json
{
  "model": {
    "trigger": { ... },
    "activities": { ... },
    "flows": { ... },
    "gateways": { ... },
    "end": { ... },
    "sub_models": { ... }
  }
}
```

| Property | Type | Description |
|----------|------|-------------|
| `trigger` | object | The entry point that invokes the workflow |
| `activities` | object | Map of activity node IDs to activity definitions |
| `flows` | object | Map of flow node IDs to sequence flow definitions |
| `gateways` | object | Map of gateway node IDs to gateway definitions |
| `end` | object | The terminal node with references to all inbound flows |
| `sub_models` | object | Map of sub-model node IDs to loop/subprocess definitions |

Each map key is a unique **node ID** set by the caller (e.g., `"activity_1"`, `"flow_1"`, `"gateway_decision_1"`, `"sub_model_1"`).

---

## Trigger

The trigger defines what event starts the workflow.

```json
{
  "trigger": {
    "id": "<trigger-catalog-id>",
    "name": "Alert > EPP Detection",
    "outgoing_flow": "flow_1",
    "trigger_type": "Signal",
    "version_constraint": "~1"
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | string | Yes | Unique identifier from the triggers catalog |
| `name` | string | Yes | Display name of the trigger |
| `outgoing_flow` | string | Yes | Reference to the first flow node ID |
| `trigger_type` | string | Yes | Type: `"Signal"`, `"On demand"`, `"Scheduled"`, `"SubModel"` |
| `version_constraint` | string | Yes | Semantic version constraint (e.g., `"~1"`) |
| `parameters` | object | No | JSON Schema for on-demand trigger parameters |
| `timer_event_definition` | object | No | Schedule configuration for scheduled triggers |

### Trigger Types

- **Signal** - Event-driven (e.g., new detection, new alert)
- **On demand** - Manual execution with optional parameters
- **Scheduled** - Cron-based recurring execution
- **SubModel** - Internal trigger for loop iterations

### Scheduled Trigger (timer_event_definition)

```json
{
  "trigger": {
    "id": "<trigger-id>",
    "name": "Scheduled",
    "outgoing_flow": "flow_1",
    "trigger_type": "Scheduled",
    "timer_event_definition": {
      "time_cycle": "0 0/1 * * *",
      "start_date": "01-01-2024",
      "end_date": "12-31-2024",
      "tz": "America/New_York",
      "skip_concurrent": false
    }
  }
}
```

### On Demand Trigger (with parameters)

```json
{
  "trigger": {
    "id": "<trigger-id>",
    "name": "On demand",
    "outgoing_flow": "flow_1",
    "trigger_type": "On demand",
    "parameters": {
      "type": "object",
      "properties": {
        "device_id": { "type": "string" },
        "severity": { "type": "integer" }
      },
      "required": ["device_id"]
    }
  }
}
```

---

## Activities (Actions)

Activities are the executable actions in a workflow (e.g., send email, contain device, query hosts).

```json
{
  "activities": {
    "activity_1": {
      "id": "<action-catalog-id>",
      "name": "Send email",
      "class": "Default",
      "version_constraint": "~2",
      "flows": {
        "incoming": "flow_1",
        "outgoing": "flow_2"
      },
      "properties": {
        "to": ["admin@example.com"],
        "subject": "Alert: ${data['Trigger.Category.Investigatable.Severity']}",
        "msg": "A new detection was found."
      }
    }
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | string | Yes | Catalog ID of the action |
| `name` | string | Yes | Display name (append index for duplicates: "Send email 2") |
| `class` | string | Yes | Activity class (typically `"Default"`, `"CreateVariable"`, `"UpdateVariable"`) |
| `version_constraint` | string | Yes | Semantic version constraint |
| `flows.incoming` | string | Yes | ID of the inbound flow |
| `flows.outgoing` | string | Yes | ID of the outbound flow |
| `properties` | object | Yes | Input parameters as defined by the action's JSON schema |

### Multiple Instances of Same Action

When using the same action type multiple times, reuse the same `id` but differentiate by `name`:

```json
{
  "activity_1": { "id": "abc123", "name": "Send Email", ... },
  "activity_2": { "id": "abc123", "name": "Send Email 2", ... }
}
```

---

## Flows (Sequence Flows)

Flows connect nodes in the graph and optionally carry conditions.

```json
{
  "flows": {
    "flow_1": {
      "source": "trigger",
      "target": "gateway_decision_1",
      "condition": {}
    },
    "flow_2": {
      "source": "gateway_decision_1",
      "target": "activity_1",
      "condition": {
        "display": ["Severity is equal to Critical"],
        "cel_expression": "data['Trigger.Category.Investigatable.Severity'] == 'Critical'"
      }
    }
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `source` | string | Yes | Node ID of the source (trigger, activity, gateway, sub_model) |
| `target` | string | Yes | Node ID of the target (activity, gateway, end, sub_model) |
| `condition` | object | No | Conditional expression for the flow |
| `condition.display` | string[] | No | Human-readable description of the condition |
| `condition.cel_expression` | string | No | CEL expression that evaluates to boolean |

### Rules
- Flows from a gateway source MUST NOT target "end" directly
- Unconditional flows use an empty condition object: `"condition": {}`

---

## Gateways (Decision/Parallel Logic)

Gateways implement branching and parallel execution.

```json
{
  "gateways": {
    "gateway_decision_1": {
      "type": "exclusive",
      "flows": {
        "incoming": ["flow_1"],
        "outgoing": ["flow_2", "flow_3"],
        "default": "flow_3"
      }
    },
    "gateway_parallel_1": {
      "type": "parallel",
      "flows": {
        "incoming": ["flow_4"],
        "outgoing": ["flow_5", "flow_6", "flow_7"]
      }
    }
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `type` | string | Yes | `"exclusive"`, `"inclusive"`, or `"parallel"` |
| `flows.incoming` | string[] | Yes | IDs of inbound flows |
| `flows.outgoing` | string[] | Yes | IDs of outbound flows |
| `flows.default` | string | No | ID of the default (else) flow for exclusive gateways |

### Gateway Types

- **exclusive** - Only one outgoing path is taken (if/else if/else)
- **parallel** - All outgoing paths execute concurrently
- **inclusive** - One or more outgoing paths may be taken

### Exclusive Gateway Rules

1. Only include branches explicitly needed
2. Conditional flows must have a `cel_expression` in their condition
3. The "else" (default) branch has an empty condition and its flow ID is set as `"default"`
4. Do NOT create empty else paths that go directly to end

---

## End Event

The terminal node that all execution paths must reach.

```json
{
  "end": {
    "incoming_flows": ["flow_3", "flow_7", "flow_9"],
    "output_fields": ["activity_1.Namespace.field_name"],
    "summary": "Workflow completed: ${data['activity_1.Namespace.result']}"
  }
}
```

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `incoming_flows` | string[] | Yes | IDs of all flows that terminate at this node |
| `output_fields` | string[] | No | Field references to expose as workflow output |
| `summary` | string | No | Free-form summary text (can embed variable references) |

---

## SubModels (Loops)

SubModels implement loop constructs: **ForEach** (iterate over arrays) and **While** (condition-based).

### ForEach Loop

```json
{
  "sub_models": {
    "sub_model_1": {
      "name": "For each Device",
      "flows": {
        "incoming": "flow_2",
        "outgoing": "flow_3"
      },
      "multi": {
        "array_field": "activity_1.Device.query.devices",
        "array_field_display_name": "Devices",
        "sequential": true,
        "continue_on_partial_execution": false,
        "max_execution_seconds": 0,
        "max_iteration_count": 0,
        "condition": {}
      },
      "model": {
        "trigger": {
          "id": "sub_model_1",
          "name": "",
          "outgoing_flow": "flow_4",
          "trigger_type": "SubModel"
        },
        "activities": { ... },
        "flows": { ... },
        "gateways": { ... },
        "end": { ... }
      }
    }
  }
}
```

### While Loop

```json
{
  "sub_models": {
    "sub_model_1": {
      "name": "While condition is met",
      "flows": {
        "incoming": "flow_2",
        "outgoing": "flow_3"
      },
      "multi": {
        "array_field": "",
        "array_field_display_name": "",
        "sequential": true,
        "condition": {
          "cel_expression": "data['WorkflowCustomVariable.counter'] < 10",
          "display": ["Counter is less than 10"]
        },
        "max_execution_seconds": 300,
        "max_iteration_count": 100
      },
      "model": { ... }
    }
  }
}
```

### Multi Configuration

| Property | Type | Description |
|----------|------|-------------|
| `array_field` | string | Fully qualified field name of the array to iterate (ForEach only) |
| `array_field_display_name` | string | Human-readable name for the array |
| `sequential` | boolean | `true` for sequential execution (required for While) |
| `continue_on_partial_execution` | boolean | Continue if some iterations fail |
| `condition` | object | Loop continuation condition (While loops only) |
| `max_execution_seconds` | integer | Timeout for the loop (0 = default) |
| `max_iteration_count` | integer | Max iterations (0 = default) |

### ForEach Array Indexing

Inside a ForEach loop, reference the current element using `#` as a dynamic index:

```
${data['activity_1.Device.query.devices.#']}
${data['activity_1.Device.query.devices.#.hostname']}
```

### SubModel Internal Structure

Each sub_model contains a full `model` definition with its own trigger (type `"SubModel"`), activities, flows, gateways, and end. The trigger `id` must match the sub_model's node ID.

---

## CEL Expressions

Conditions and data transformations use [Google Common Expression Language (CEL)](https://github.com/google/cel-spec) with CrowdStrike extensions.

### Basic Operations

```cel
// Equality
data['Trigger.Category.Investigatable.Severity'] == 'Critical'

// Comparison
data['activity_1.Namespace.count'] > 5

// Boolean logic
data['field1'] == 'value' && data['field2'] != 'other'

// String operations
data['Trigger.Hostname'].contains('prod')
data['Trigger.URL'].startsWith('https://')

// List operations
size(data['activity_1.results']) > 0
data['list'].filter(i, i > 10)
data['array'].exists(item, item == 'target')
```

### CrowdStrike Extensions (cs.* functions)

```cel
// IP operations
cs.ip.inCIDR(data['Trigger.IP'], '10.0.0.0/24')
cs.ip.isPrivate(data['Trigger.IP'])

// Timestamp operations
cs.timestamp.now() - data['Trigger.Timestamp'] > duration('24h')
cs.timestamp.format(data['Trigger.LastUpdated'], 'RFC3339')

// String manipulation
cs.string.findAll(data['Trigger.CommandLine'], '[A-Za-z0-9]+')
cs.string.replaceRegex(data['Trigger.URL'], 'https?://', '')

// JSON operations
cs.json.decode(data['Trigger.JSONData'])

// Network functions
cs.net.parseURL(data['Trigger.URL']).host

// Math, Lists, Maps
cs.math.average(data['activity_1.Scores'])
cs.list.chunk(data['activity_1.Devices'], 5)
cs.map.mergeDeep([data['Map1'], data['Map2']])
```

---

## Data References

### Trigger Output Fields

Reference trigger data using the trigger's field path:

```
${data['Trigger.Category.Investigatable.InvestigatableID']}
${data['Trigger.Category.Investigatable.Severity']}
${data['Trigger.Category.Investigatable.Product.EPP.Sensor.Hostname']}
```

### Activity Output Fields

Reference activity outputs with: `${data['<node_id>.<namespace>.<field_name>']}`

```
${data['activity_1.FaaS.nlpassistantapi.llminvocator_handler.completion']}
${data['activity_2.Device.GetDetails.Platform']}
```

If no namespace exists: `${data['<node_id>.<field_name>']}`

### On Demand Parameters

Reference on-demand trigger parameters using: `${data['parameter_name']}`

```
${data['device_id']}
${data['severity']}
```

---

## Custom Variables

Custom variables provide persistent mutable storage throughout workflow execution.

### Create Variable

```json
{
  "name": "Create variable",
  "class": "CreateVariable",
  "id": "702d15788dbbffdf0b68d8e2f3599aa4",
  "flows": { "incoming": "flow_1", "outgoing": "flow_2" },
  "properties": {
    "variable_schema": {
      "type": "object",
      "properties": {
        "counter": { "type": "integer" },
        "results": { "items": { "type": "string" }, "type": "array" }
      }
    }
  }
}
```

### Update Variable

```json
{
  "name": "Update variable",
  "class": "UpdateVariable",
  "id": "6c6eab39063fa3b72d98c82af60deb8a",
  "flows": { "incoming": "flow_3", "outgoing": "flow_4" },
  "properties": {
    "WorkflowCustomVariable": {
      "counter": "${data['WorkflowCustomVariable.counter'] + 1}",
      "results": "${data['WorkflowCustomVariable.results'] + [data['activity_1.Namespace.output']]}"
    }
  }
}
```

### Reference Custom Variables

```
${data['WorkflowCustomVariable.counter']}
${data['WorkflowCustomVariable.results']}
```

---

## Placeholders

When requirements are ambiguous, use placeholder constructs.

### Placeholder Activity

Used when it's unclear which action should be used:

```json
{
  "activity_3": {
    "id": "placeholder",
    "name": "Placeholder",
    "class": "Default",
    "flows": { "incoming": "flow_5", "outgoing": "flow_6" },
    "properties": {
      "task_name": "Notify the user",
      "reason": "Multiple notification actions available: Slack, Email, Teams."
    }
  }
}
```

### Placeholder CEL Function

Used when a condition is ambiguous:

```cel
cs.placeholder.new("Is the alert serious?", "The meaning of 'serious' needs to be defined.")
```

---

## Complete Examples

### Example 1: Detection Response Workflow

**Scenario:** When a new EPP detection appears, if the tactic is Falcon Overwatch: set alert status to in-progress, contain the device, send an email notification. After containment, add a comment to the alert.

```json
{
  "model": {
    "trigger": {
      "id": "<trigger-id>",
      "name": "Alert > EPP Detection",
      "outgoing_flow": "flow_1",
      "trigger_type": "Signal",
      "version_constraint": "~1"
    },
    "activities": {
      "activity_1": {
        "id": "<action-id>",
        "name": "Set alert status",
        "class": "Default",
        "flows": { "incoming": "flow_2", "outgoing": "flow_9" },
        "properties": {
          "investigatable_id": "${data['Trigger.Category.Investigatable.InvestigatableID']}",
          "status": "in_progress"
        }
      },
      "activity_2": {
        "id": "<action-id>",
        "name": "Send email",
        "class": "Default",
        "flows": { "incoming": "flow_5", "outgoing": "flow_3" },
        "properties": {
          "to": [],
          "subject": "[URGENT] - Falcon Overwatch Detection",
          "msg": "The Falcon Overwatch team has detected activity in your environment.",
          "_fields": [
            "${data['Trigger.Category.Investigatable.Severity']}",
            "${data['Trigger.Category.Investigatable.Product.EPP.Sensor.Hostname']}"
          ]
        }
      },
      "activity_3": {
        "id": "<action-id>",
        "name": "Contain device",
        "class": "Default",
        "flows": { "incoming": "flow_4", "outgoing": "flow_8" },
        "properties": {
          "device_id": "${data['Trigger.Category.Investigatable.Product.EPP.Sensor.SensorID']}",
          "note": "Contained due to Overwatch based detection"
        }
      },
      "activity_4": {
        "id": "<action-id>",
        "name": "Add comment to alert",
        "class": "Default",
        "flows": { "incoming": "flow_8", "outgoing": "flow_7" },
        "properties": {
          "comment": "System has been automatically contained via a Workflow",
          "investigatable_id": "${data['Trigger.Category.Investigatable.InvestigatableID']}"
        }
      }
    },
    "flows": {
      "flow_1": { "source": "trigger", "target": "gateway_decision_1", "condition": {} },
      "flow_2": { "source": "gateway_parallel_2", "target": "activity_1", "condition": {} },
      "flow_3": { "source": "activity_2", "target": "end", "condition": {} },
      "flow_4": { "source": "gateway_parallel_2", "target": "activity_3", "condition": {} },
      "flow_5": { "source": "gateway_parallel_2", "target": "activity_2", "condition": {} },
      "flow_6": {
        "source": "gateway_decision_1",
        "target": "gateway_parallel_2",
        "condition": {
          "display": ["Tactic is equal to Falcon Overwatch"],
          "cel_expression": "data['Trigger.Category.Investigatable.Product.EPP.Behavior.TacticName'] == 'Falcon Overwatch'"
        }
      },
      "flow_7": { "source": "activity_4", "target": "end", "condition": {} },
      "flow_8": { "source": "activity_3", "target": "activity_4", "condition": {} },
      "flow_9": { "source": "activity_1", "target": "end", "condition": {} }
    },
    "gateways": {
      "gateway_decision_1": {
        "type": "exclusive",
        "flows": { "incoming": ["flow_1"], "outgoing": ["flow_6"] }
      },
      "gateway_parallel_2": {
        "type": "parallel",
        "flows": { "incoming": ["flow_6"], "outgoing": ["flow_2", "flow_4", "flow_5"] }
      }
    },
    "end": {
      "incoming_flows": ["flow_3", "flow_9", "flow_7"]
    }
  }
}
```

### Example 2: ForEach Loop with Conditional Logic

**Scenario:** When a new unsupported asset appears, if entity type is unmanaged and confidence is high and IP matches 10.0.0.*, query devices matching hostname "CM1". For each device, get details. If platform is Windows, run a remediation action.

```json
{
  "model": {
    "trigger": {
      "id": "<trigger-id>",
      "name": "Asset management > New unmanaged / unsupported asset",
      "outgoing_flow": "flow_8",
      "trigger_type": "Signal",
      "version_constraint": "~1"
    },
    "activities": {
      "activity_1": {
        "id": "<action-id>",
        "name": "Device Query",
        "class": "Default",
        "flows": { "incoming": "flow_9", "outgoing": "flow_2" },
        "properties": { "hostnames": ["CM1"] }
      }
    },
    "flows": {
      "flow_2": { "source": "activity_1", "target": "sub_model_1", "condition": {} },
      "flow_3": { "source": "sub_model_1", "target": "end", "condition": {} },
      "flow_8": { "source": "trigger", "target": "gateway_decision_2", "condition": {} },
      "flow_9": {
        "source": "gateway_decision_2",
        "target": "activity_1",
        "condition": {
          "display": ["Entity type is Unmanaged AND Confidence is High AND IP matches 10.0.0.*"],
          "cel_expression": "data['Trigger.Category.AssetManagement.Change.NewUnmanagedUnsupportedAsset.EntityType'] == 'EntityTypeUnmanaged' && data['Trigger.Category.AssetManagement.Change.NewUnmanagedUnsupportedAsset.Confidence'] == 'ConfidenceHigh' && data['Trigger.Category.AssetManagement.Change.NewUnmanagedUnsupportedAsset.IPAddress'].matches('^10.0.0.*')"
        }
      }
    },
    "gateways": {
      "gateway_decision_2": {
        "type": "exclusive",
        "flows": { "incoming": ["flow_8"], "outgoing": ["flow_9"] }
      }
    },
    "sub_models": {
      "sub_model_1": {
        "name": "For each Sensor IDs",
        "flows": { "incoming": "flow_2", "outgoing": "flow_3" },
        "multi": {
          "array_field": "activity_1.Device.query.devices",
          "array_field_display_name": "Sensor IDs",
          "sequential": true,
          "continue_on_partial_execution": false,
          "max_execution_seconds": 0,
          "max_iteration_count": 0,
          "condition": {}
        },
        "model": {
          "trigger": {
            "id": "sub_model_1",
            "name": "",
            "outgoing_flow": "flow_4",
            "trigger_type": "SubModel"
          },
          "activities": {
            "activity_2": {
              "id": "<action-id>",
              "name": "Get device details",
              "class": "Default",
              "flows": { "incoming": "flow_4", "outgoing": "flow_7" },
              "properties": {
                "device_id": "${data['activity_1.Device.query.devices.#']}"
              }
            },
            "activity_3": {
              "id": "<action-id>",
              "name": "Remediation Action",
              "class": "Default",
              "flows": { "incoming": "flow_6", "outgoing": "flow_5" },
              "properties": {
                "Device": "${data['Trigger.Category.AssetManagement.Change.NewUnmanagedUnsupportedAsset.IPAddress']}",
                "device_id": "${data['activity_1.Device.query.devices.#']}"
              }
            }
          },
          "flows": {
            "flow_4": { "source": "trigger", "target": "activity_2", "condition": {} },
            "flow_5": { "source": "activity_3", "target": "end", "condition": {} },
            "flow_6": {
              "source": "gateway_decision_1",
              "target": "activity_3",
              "condition": {
                "display": ["Platform is equal to Windows"],
                "cel_expression": "data['activity_2.Device.GetDetails.Platform'] == 'Windows'"
              }
            },
            "flow_7": { "source": "activity_2", "target": "gateway_decision_1", "condition": {} }
          },
          "gateways": {
            "gateway_decision_1": {
              "type": "exclusive",
              "flows": { "incoming": ["flow_7"], "outgoing": ["flow_6"] }
            }
          },
          "end": { "incoming_flows": ["flow_5"] }
        }
      }
    },
    "end": { "incoming_flows": ["flow_3"] }
  }
}
```

### Example 3: Minimal Scheduled Workflow

```json
{
  "model": {
    "trigger": {
      "id": "<trigger-id>",
      "name": "Scheduled",
      "outgoing_flow": "flow_1",
      "trigger_type": "Scheduled",
      "timer_event_definition": {
        "time_cycle": "0 0/1 * * *",
        "tz": "America/New_York",
        "skip_concurrent": false
      }
    },
    "activities": {
      "activity_1": {
        "id": "<action-id>",
        "name": "Run daily check",
        "class": "Default",
        "flows": { "incoming": "flow_1", "outgoing": "flow_2" },
        "properties": { }
      }
    },
    "flows": {
      "flow_1": { "source": "trigger", "target": "activity_1", "condition": {} },
      "flow_2": { "source": "activity_1", "target": "end", "condition": {} }
    },
    "gateways": {},
    "end": { "incoming_flows": ["flow_2"] },
    "sub_models": {}
  }
}
```

---

## Key Constraints & Rules

1. **No gateway-to-end flows** - Flows from a gateway source must not target "end" directly
2. **SubModel triggers** - Must use `trigger_type: "SubModel"` and be referenced as `"trigger"` in the flow source
3. **Unique node IDs** - Every node (activity, flow, gateway, sub_model) must have a globally unique ID across the entire workflow including sub_models
4. **Activity scoping** - Activities defined in a sub_model cannot be referenced in flows of the parent model, and vice versa
5. **Version constraints** - Must be included for both triggers and activities
6. **ForEach indexing** - Use `#` symbol for array element references inside loops
7. **While loops** - Must be sequential, must have empty `array_field`, must have a condition

---

## JSON Schema Reference

### GraphConfiguredActivity
```json
{
  "id": "string - catalog action ID",
  "name": "string - display name",
  "class": "string - activity class",
  "version_constraint": "string - semver constraint",
  "flows": {
    "incoming": "string - inbound flow ID",
    "outgoing": "string - outbound flow ID"
  },
  "properties": "object - action-specific input parameters"
}
```

### GraphFlow
```json
{
  "source": "string - source node ID",
  "target": "string - target node ID",
  "condition": {
    "display": ["string - human-readable condition"],
    "cel_expression": "string - CEL boolean expression"
  }
}
```

### GraphGateway
```json
{
  "type": "string - exclusive|inclusive|parallel",
  "flows": {
    "incoming": ["string - inbound flow IDs"],
    "outgoing": ["string - outbound flow IDs"],
    "default": "string - optional default flow ID for else branch"
  }
}
```

### GraphSubModel
```json
{
  "name": "string - display name",
  "flows": {
    "incoming": "string - inbound flow ID",
    "outgoing": "string - outbound flow ID"
  },
  "multi": {
    "array_field": "string - field to iterate (ForEach) or empty (While)",
    "array_field_display_name": "string",
    "sequential": "boolean",
    "continue_on_partial_execution": "boolean",
    "condition": "object - loop condition (While only)",
    "max_execution_seconds": "integer",
    "max_iteration_count": "integer"
  },
  "model": "GraphDefinitionModel - nested workflow graph"
}
```

---

## Validation

Workflows are validated against the Fusion API endpoint (`/workflows/graph/validation/v1`) before delivery. The validation checks:

- Graph structure (no cycles, no disjoint nodes)
- Required fields for each action
- CEL expression syntax
- Trigger/activity version compatibility
- Flow connectivity (all paths reach end)
- Activity scoping within models/sub_models