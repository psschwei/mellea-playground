## 6. Orchestration / Visual Builder

The visual builder enables users to compose mellea programs, models, and primitives into executable workflows through a drag-and-drop canvas interface. This section covers the architecture, node system, and execution model.

### 6.1 Technology Stack
- **Canvas Library**: ReactFlow (v11+) for graph-based visual editing—provides drag-and-drop, zoom/pan, minimap, edge routing, and node selection out of the box.
- **UI Framework**: Consistent with playground UI (React + Chakra UI per Section 10); node configuration panels use same component library.
- **State Management**: ReactFlow's `useNodesState` and `useEdgesState` hooks for graph state; lift shared state (selected node, execution status) to composition context.

### 6.2 Node Architecture

#### 6.2.1 Node Data Interface
All nodes conform to a common data shape enabling consistent handling:
```typescript
interface MelleaNodeData {
  // Display
  label: string
  category: MelleaNodeCategory  // "program" | "model" | "primitive" | "utility"
  icon?: string                 // Icon identifier or path

  // Mellea-specific
  slotSignature?: SlotSignature      // For @generative nodes: typed args/returns
  requirements?: string[]            // Dependency libraries
  pythonCode?: string                // Generated or custom code snippet

  // Configuration
  parameters: Record<string, ParameterValue>
  samplingStrategy?: SamplingConfig  // loop_budget, repair_template, etc.
  modelOverride?: string             // Per-node model selection

  // Callbacks (injected by canvas)
  onParameterChange?: (nodeId: string, param: string, value: any) => void
  onSlotWire?: (nodeId: string, slotName: string, sourceNodeId: string) => void

  // Runtime state
  isUpdating?: boolean
  lastRunStatus?: "pending" | "running" | "succeeded" | "failed"
  lastRunArtifacts?: ArtifactRef[]
}

interface SlotSignature {
  name: string
  docstring: string
  args: Array<{ name: string; type: string; description?: string }>
  returns: { type: string; description?: string }
}
```

#### 6.2.2 Node Types
Implement each node type as an isolated React component with consistent structure:

| Category | Node Type | Purpose | Key Configuration |
|----------|-----------|---------|-------------------|
| **Program** | `programNode` | Imported mellea program | Entrypoint, env vars, resource profile |
| **Model** | `modelNode` | LLM backend configuration | Provider, model ID, credentials ref, temperature |
| **Primitive** | `generativeSlotNode` | `@generative` function | Slot signature, prompt template, output binding |
| **Primitive** | `verifierNode` | Validation/guardian check | Verification logic, pass/fail threshold |
| **Primitive** | `samplerNode` | Sampling strategy (rejection, repair, IVR) | `loop_budget`, `repair_template`, retry policy |
| **Primitive** | `ivrNode` | Iterative verification-refinement | Max iterations, verifier refs, refinement prompt |
| **Utility** | `branchNode` | Conditional routing | Condition expression, true/false outputs |
| **Utility** | `aggregatorNode` | Fan-in merge | Merge policy (first-success, vote, reduce) |
| **Utility** | `contextNode` | Session context read/write | Key path, read vs. write mode |
| **Utility** | `inputNode` | Composition input parameter | Name, type, default value |
| **Utility** | `outputNode` | Composition output | Name, source binding |

#### 6.2.3 Node Component Structure
Each node component follows a consistent layout pattern:
```
┌─────────────────────────────────┐
│ [Icon] Category Label    [Menu] │  ← Header (color-coded by category)
├─────────────────────────────────┤
│ ○ Input Handle(s)               │  ← ReactFlow handles (typed)
├─────────────────────────────────┤
│                                 │
│   Configuration Controls        │  ← Dropdowns, sliders, text inputs
│   (collapsible advanced section)│
│                                 │
├─────────────────────────────────┤
│ ○ Output Handle(s)              │  ← ReactFlow handles (typed)
└─────────────────────────────────┘
```

### 6.3 Node Palette & Sidebar

#### 6.3.1 Palette Organization
Sidebar presents nodes in collapsible category sections:
```typescript
const paletteCategories = [
  {
    id: "programs",
    label: "Programs",
    icon: "folder-code",
    color: "#8B5CF6",  // Purple
    nodes: []  // Dynamically populated from catalog
  },
  {
    id: "models",
    label: "Models",
    icon: "brain",
    color: "#EC4899",  // Pink
    nodes: []  // Dynamically populated from catalog
  },
  {
    id: "primitives",
    label: "Mellea Primitives",
    icon: "puzzle",
    color: "#3B82F6",  // Blue
    nodes: [
      { type: "generativeSlotNode", label: "@generative Slot" },
      { type: "verifierNode", label: "Verifier" },
      { type: "samplerNode", label: "Sampler" },
      { type: "ivrNode", label: "IVR Loop" },
    ]
  },
  {
    id: "utilities",
    label: "Utilities",
    icon: "settings",
    color: "#10B981",  // Green
    nodes: [
      { type: "branchNode", label: "Branch" },
      { type: "aggregatorNode", label: "Aggregator" },
      { type: "contextNode", label: "Context" },
      { type: "inputNode", label: "Input" },
      { type: "outputNode", label: "Output" },
    ]
  }
]
```

#### 6.3.2 Node Addition Flow
1. User drags node from palette onto canvas (or clicks to add at default position)
2. Canvas assigns unique ID: `{nodeType}-{timestamp}`
3. Node receives injected callbacks (`onParameterChange`, etc.)
4. For Program/Model nodes: open catalog picker modal to select asset
5. For `@generative` slots: if program selected, show slot picker from program's exported slots

### 6.4 Connections & Edge Styling

#### 6.4.1 Edge Data Model
```typescript
interface MelleaEdge {
  id: string
  source: string        // Source node ID
  sourceHandle?: string // Named output handle (for multi-output nodes)
  target: string        // Target node ID
  targetHandle?: string // Named input handle (for multi-input nodes)

  // Display
  animated: boolean     // Flow animation during execution
  style: { stroke: string }
  label?: string        // Data flow description

  // Typing
  dataType?: string     // Expected data type for validation
}
```

#### 6.4.2 Color-Coded Edges
Edges inherit color from source node category for visual flow tracking:

| Source Category | Edge Color | Hex |
|-----------------|------------|-----|
| Program | Purple | `#8B5CF6` |
| Model | Pink | `#EC4899` |
| Primitive | Blue | `#3B82F6` |
| Utility | Green | `#10B981` |
| Error/Invalid | Red | `#EF4444` |

#### 6.4.3 Connection Validation
On connect attempt, validate compatibility:
- **Type Check**: Source output type must match or be assignable to target input type
- **Cycle Detection**: Prevent cycles that would cause infinite loops (except within IVR nodes)
- **Slot Compatibility**: For `@generative` slots, verify argument types match upstream outputs
- **Visual Feedback**: Invalid connections show red dashed preview; valid show category color

Define data/control edges representing `MelleaSession` calls (e.g., pass `summary` output into downstream verifiers). Support fan-out (one output to multiple consumers) and fan-in with merge policies (first-success, map/reduce, voting).

### 6.5 Compositional Contracts
The builder understands the mellea contract model—slot signatures (typed args/returns) and docstrings—so wiring nodes enforces type compatibility and highlights missing context. When a `@generative` slot is placed on the canvas:
- Its signature is parsed to determine required inputs and output type
- Input handles are created for each typed argument
- Output handle reflects the return type
- Docstrings appear as tooltips and in the configuration panel
- Incompatible wirings are blocked with explanatory error messages

### 6.6 Session Context & Execution

#### 6.6.1 Session Context
Each composition run instantiates a `MelleaSession`; nodes can read/write shared context objects (memory, cached sub-results) and configure backend/model options at session start or per node. The builder exposes which nodes mutate session state to avoid unintended coupling:
- **Context Reader Nodes**: Display a "reads context" badge; show which keys they depend on
- **Context Writer Nodes**: Display a "writes context" badge with warning color; show which keys they modify
- **Dependency Visualization**: Optional overlay mode highlights context dependencies between nodes

#### 6.6.2 Execution Semantics
Run each composition inside a single shared container hosting one `MelleaSession` runtime. All nodes execute within this container, sharing session context (memory, cached sub-results) without cross-container serialization. The orchestrator schedules nodes sequentially or in parallel within that environment while capturing intermediate artifacts per node.

#### 6.6.3 Shared Container Considerations
- *Image Composition*: When a composition references multiple programs, build a unified container image that unions their dependencies. Fail at build time with clear diagnostics if dependency versions conflict; prompt users to resolve or pin versions.
- *Resource Sizing*: Container resource limits (CPU/memory) apply to the composition as a whole. Default to the maximum resource profile across constituent programs; allow users to override at composition level.
- *Failure Handling*: Distinguish node-level failures (exception in user code) from container-level failures (OOM, crash). Node failures mark that node as failed and allow downstream error handling or retry. Container crashes fail the entire composition with a clear infrastructure error message and remediation hints.
- *Parallel Execution*: When nodes execute in parallel (fan-out), they share container resources. Log output is tagged by node ID to prevent interleaving confusion. Resource contention may cause slowdowns; document this tradeoff for users designing parallel workflows.

### 6.7 Code Generation Pipeline

#### 6.7.1 Graph-to-Code Translation
The builder generates executable Python code from the visual graph:

```python
# Generated composition code structure
from mellea import MelleaSession
from mellea.stdlib.sampling import RejectionSampler, RepairSampler

def run_composition(inputs: dict) -> dict:
    session = MelleaSession(
        backend="openai",
        model="gpt-4",
        # ... model config from modelNode
    )

    # Node execution in topological order
    # node-1: @generative slot
    result_1 = session.call(
        slot=summarize,  # from programNode reference
        prompt="...",    # from generativeSlotNode config
        # ... parameters
    )

    # node-2: verifier
    is_valid = verify_summary(result_1)  # from verifierNode

    # node-3: branch
    if is_valid:
        # ... true branch
    else:
        # ... false branch (repair path)

    return {"output": final_result}
```

#### 6.7.2 Code Panel Integration
- **Split View**: Canvas on left, generated code on right (resizable divider)
- **Live Updates**: Code regenerates as nodes/edges change
- **Section Highlighting**: Clicking a node highlights its corresponding code section
- **Manual Edits**: Allow code overrides with warning about sync loss; track divergence state
- **Syntax Highlighting**: Python syntax coloring with line numbers
- **Copy/Export**: One-click copy to clipboard or download as `.py` file

### 6.8 Pattern Library & Templates

#### 6.8.1 Template Definition Format
```typescript
interface CompositionTemplate {
  id: string
  name: string
  description: string
  category: "sampling" | "verification" | "orchestration" | "custom"

  // Graph structure
  nodes: Array<{
    id: string
    type: string
    position: { x: number; y: number }
    data: Partial<MelleaNodeData>
  }>
  edges: Array<{
    id: string
    source: string
    target: string
    sourceHandle?: string
    targetHandle?: string
  }>

  // Customization points
  parameters: Array<{
    nodeId: string
    paramPath: string
    label: string
    description: string
    required: boolean
  }>

  // Documentation
  useCases: string[]
  prerequisites: string[]  // Required program slots, etc.
}
```

#### 6.8.2 Built-in Templates
Ship pre-built templates grounded in mellea stdlib strategies (Rejection/Repair sampling, Guardian checks) so users can instantiate best-practice workflows with minimal wiring. Template nodes expose sampling strategy knobs (`loop_budget`, repair templates) aligned with `mellea.stdlib.sampling`, and can emit instrumentation hooks for comparing attempts.

| Template | Nodes | Description |
|----------|-------|-------------|
| **Rejection Sampling** | Input → @generative → Verifier → Branch → Output/Retry | Basic retry-until-valid pattern |
| **Repair Sampling** | Input → @generative → Verifier → Branch → Repair → Output | Fix invalid outputs before retry |
| **IVR Standard** | Input → IVR(Generate, Verify, Refine) → Output | Iterative verification-refinement loop |
| **Guardian Check** | Input → @generative → Guardian → Branch → Output/Fallback | Safety/policy verification |
| **Ensemble Vote** | Input → Fan-out(3x @generative) → Aggregator(vote) → Output | Multi-generation with voting |
| **Summarize-Verify-Decide** | Doc → Summarize → Verify → Decide → Output | Common document processing pattern |

### 6.9 Reusable Subflows
Allow grouping nodes into reusable "modules" (e.g., "Summarize → Verify → Decide" pattern) that can be published back into the catalog as composition assets:
- **Selection**: Multi-select nodes on canvas, right-click → "Create Module"
- **Encapsulation**: Grouped nodes collapse into a single "module node" with aggregated inputs/outputs
- **Editing**: Double-click module node to expand and edit internal graph
- **Publishing**: Save module to catalog with metadata; appears in sidebar for reuse
- **Versioning**: Module updates can be propagated to compositions that reference them (with user approval)

### 6.10 Run Visualization

#### 6.10.1 Node Execution States
During execution, animate node states and show model selections and sampling loops (e.g., IVR attempts):

```typescript
type NodeExecutionState =
  | "idle"      // Not yet reached
  | "queued"    // Waiting for upstream
  | "running"   // Currently executing
  | "succeeded" // Completed successfully
  | "failed"    // Threw exception
  | "skipped"   // Branch not taken
  | "cancelled" // User cancelled run

// Visual indicators per state
const stateStyles = {
  idle:      { border: "gray",   animation: null,    icon: null },
  queued:    { border: "yellow", animation: "pulse", icon: "clock" },
  running:   { border: "blue",   animation: "spin",  icon: "loader" },
  succeeded: { border: "green",  animation: null,    icon: "check" },
  failed:    { border: "red",    animation: null,    icon: "x" },
  skipped:   { border: "gray",   animation: null,    icon: "skip", opacity: 0.5 },
  cancelled: { border: "orange", animation: null,    icon: "stop" },
}
```

#### 6.10.2 Per-Node Side Drawer
Expose per-node logs/artifacts via side drawer. Clicking a node during/after execution opens detail drawer showing:
- **Status**: Current state with timing (queued duration, execution duration)
- **Inputs**: Values received from upstream nodes (truncated with expand option)
- **Outputs**: Values produced (truncated with expand option)
- **Logs**: Stdout/stderr captured during node execution
- **Artifacts**: Files produced, downloadable
- **Retry Button**: Re-run this node with same inputs (for failed nodes)
- **Sampling Attempts**: For sampler/IVR nodes, show each attempt with verifier results

#### 6.10.3 Edge Animation
During execution:
- Edges animate flow direction (moving dashes) when data is being passed
- Completed edges show static solid line in category color
- Failed edges transition to red color
- Edge labels can show data preview on hover

#### 6.10.4 Controls
- **Cancel**: Stop active runs (graceful SIGTERM then SIGKILL); capture who initiated cancel
- **Retry**: Single-click retry from failed nodes or full composition restart
- **Pause/Resume**: For long-running compositions, allow pausing between nodes (future enhancement)

### 6.11 Persistence & Sharing

#### 6.11.1 Composition Storage Format
Treat compositions as first-class assets with versioning, diff view (graph + JSON spec), and sharing settings. Persist both the visual layout metadata and executable graph definition:

```typescript
interface CompositionAsset {
  // Asset metadata (shared with Programs/Models)
  id: string
  name: string
  description: string
  version: string
  owner: string
  sharing: SharingMode
  tags: string[]
  created: timestamp
  updated: timestamp

  // Graph definition
  graph: {
    nodes: MelleaNode[]
    edges: MelleaEdge[]
    viewport: { x: number; y: number; zoom: number }
  }

  // Executable spec (for headless runs)
  spec: {
    inputs: Array<{ name: string; type: string; required: boolean }>
    outputs: Array<{ name: string; type: string }>
    nodeExecutionOrder: string[]  // Topologically sorted
    generatedCode?: string        // Cached Python code
  }

  // References
  programRefs: string[]  // IDs of referenced program assets
  modelRefs: string[]    // IDs of referenced model assets
}
```

#### 6.11.2 URL Sharing
Enable shareable links for compositions:
```typescript
// Encode composition for URL sharing
function generateShareableUrl(composition: CompositionAsset): string {
  const minimalGraph = {
    nodes: composition.graph.nodes.map(n => ({
      id: n.id, type: n.type, position: n.position,
      data: pickEssentialData(n.data)
    })),
    edges: composition.graph.edges
  }
  const compressed = lzString.compressToEncodedURIComponent(
    JSON.stringify(minimalGraph)
  )
  return `${baseUrl}/composer?c=${compressed}`
}
```

#### 6.11.3 Version Diff View
- **Graph Diff**: Side-by-side canvas views highlighting added (green), removed (red), and modified (yellow) nodes
- **JSON Diff**: Structured diff of composition spec for detailed comparison
- **History Timeline**: List of versions with author, timestamp, and change summary
- **Restore**: One-click restore to any previous version

