"""CodeGenerator - Generates executable Python code from composition graphs.

This is the Python backend equivalent of the frontend CodeGenerator.ts,
used for server-side code generation during composition execution.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CompositionInput:
    """Detected composition input."""

    name: str
    type: str = "any"
    required: bool = True
    description: str = ""


@dataclass
class CompositionOutput:
    """Detected composition output."""

    name: str
    type: str = "any"
    description: str = ""


@dataclass
class GeneratedCode:
    """Result of code generation."""

    code: str
    execution_order: list[str]
    inputs: list[CompositionInput]
    outputs: list[CompositionOutput]
    warnings: list[str] = field(default_factory=list)


@dataclass
class CodeGeneratorOptions:
    """Options for code generation."""

    include_comments: bool = True
    async_code: bool = True
    indent: str = "    "
    type_hints: bool = True
    include_node_logging: bool = True  # Whether to include per-node logging calls


def to_variable_name(node_id: str) -> str:
    """Convert node ID to valid Python variable name."""
    # Replace non-alphanumeric with underscore
    name = re.sub(r"[^a-zA-Z0-9]", "_", node_id)
    # Ensure starts with letter
    if name and name[0].isdigit():
        name = "node_" + name
    return name


def build_adjacency_list(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Build adjacency list from edges (source -> targets)."""
    adjacency: dict[str, list[str]] = {node["id"]: [] for node in nodes}

    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source in adjacency and target not in adjacency[source]:
            adjacency[source].append(target)

    return adjacency


def build_incoming_edges(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> dict[str, list[dict[str, str | None]]]:
    """Build reverse adjacency (incoming edges) for dependency tracking."""
    incoming: dict[str, list[dict[str, str | None]]] = {node["id"]: [] for node in nodes}

    for edge in edges:
        target = edge.get("target", "")
        if target in incoming:
            incoming[target].append(
                {
                    "source": edge.get("source", ""),
                    "sourceHandle": edge.get("sourceHandle"),
                    "targetHandle": edge.get("targetHandle"),
                }
            )

    return incoming


def topological_sort(
    nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> tuple[list[str], bool]:
    """Compute topological sort using Kahn's algorithm.

    Args:
        nodes: List of node dictionaries with 'id' field
        edges: List of edge dictionaries with 'source' and 'target' fields

    Returns:
        Tuple of (ordered node IDs, has_cycle flag)
    """
    node_ids = {node["id"] for node in nodes}
    adjacency = build_adjacency_list(nodes, edges)

    # Calculate in-degrees
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for edge in edges:
        target = edge.get("target", "")
        if target in in_degree:
            in_degree[target] += 1

    # Initialize queue with nodes having no incoming edges
    queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
    order: list[str] = []

    while queue:
        node_id = queue.pop(0)
        order.append(node_id)

        # Reduce in-degree of neighbors
        for neighbor in adjacency.get(node_id, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Check for cycle
    has_cycle = len(order) != len(node_ids)

    return order, has_cycle


def get_node_data(node: dict[str, Any]) -> dict[str, Any]:
    """Extract node data from a node dictionary."""
    data: dict[str, Any] = node.get("data") or {}
    return data


def detect_inputs(nodes: list[dict[str, Any]]) -> list[CompositionInput]:
    """Detect composition inputs (utility nodes with utilityType='input')."""
    inputs: list[CompositionInput] = []

    for node in nodes:
        data = get_node_data(node)
        if data.get("category") == "utility" and data.get("utilityType") == "input":
            inputs.append(
                CompositionInput(
                    name=data.get("label", node["id"]),
                    type=data.get("dataType", "any"),
                    required=True,
                    description=f"Input from node {node['id']}",
                )
            )

    return inputs


def detect_outputs(nodes: list[dict[str, Any]]) -> list[CompositionOutput]:
    """Detect composition outputs (utility nodes with utilityType='output')."""
    outputs: list[CompositionOutput] = []

    for node in nodes:
        data = get_node_data(node)
        if data.get("category") == "utility" and data.get("utilityType") == "output":
            outputs.append(
                CompositionOutput(
                    name=data.get("label", node["id"]),
                    type=data.get("dataType", "any"),
                    description=f"Output from node {node['id']}",
                )
            )

    return outputs


def generate_program_node_code(
    node: dict[str, Any],
    incoming: dict[str, list[dict[str, str | None]]],
    options: CodeGeneratorOptions,
) -> list[str]:
    """Generate code for a program node."""
    data = get_node_data(node)
    var_name = to_variable_name(node["id"])
    node_id = node["id"]
    lines: list[str] = []
    indent = options.indent

    # Get inputs from connected nodes
    inputs = incoming.get(node_id, [])
    input_args: list[str] = []

    for inp in inputs:
        source = inp.get("source") or ""
        source_var = to_variable_name(source)
        handle = inp.get("targetHandle") or "input"
        input_args.append(f"{handle}={source_var}_output")

    if options.include_comments:
        lines.append(f"{indent}# Program: {data.get('label', node_id)}")
        if data.get("programId"):
            lines.append(f"{indent}# Program ID: {data['programId']}")

    # Add logging for node start
    if options.include_node_logging:
        label = data.get("label", node_id)
        lines.append(f'{indent}log_node("{node_id}", "Starting program: {label}")')

    async_prefix = "await " if options.async_code else ""
    args_str = ", ".join(input_args)
    program_id = data.get("programId") or data.get("label") or node_id

    if args_str:
        lines.append(
            f'{indent}{var_name}_output = {async_prefix}run_program("{program_id}", {args_str})'
        )
    else:
        lines.append(
            f'{indent}{var_name}_output = {async_prefix}run_program("{program_id}")'
        )

    # Add logging for node completion
    if options.include_node_logging:
        lines.append(f'{indent}log_node("{node_id}", f"Program completed. Output: {{{var_name}_output}}")')

    return lines


def generate_model_node_code(
    node: dict[str, Any],
    incoming: dict[str, list[dict[str, str | None]]],
    options: CodeGeneratorOptions,
) -> list[str]:
    """Generate code for a model node."""
    data = get_node_data(node)
    var_name = to_variable_name(node["id"])
    node_id = node["id"]
    lines: list[str] = []
    indent = options.indent

    # Get input from connected node
    inputs = incoming.get(node_id, [])
    input_expr = '""'

    if inputs:
        source = inputs[0].get("source") or ""
        input_expr = f"{to_variable_name(source)}_output"

    if options.include_comments:
        lines.append(f"{indent}# Model: {data.get('label', node_id)}")

    # Add logging for node start
    if options.include_node_logging:
        label = data.get("label", node_id)
        lines.append(f'{indent}log_node("{node_id}", f"Invoking model: {label} with input: {{{input_expr}[:100]}}")')

    async_prefix = "await " if options.async_code else ""
    model_id = data.get("modelId") or data.get("label") or node_id
    lines.append(
        f'{indent}{var_name}_output = {async_prefix}invoke_model("{model_id}", {input_expr})'
    )

    # Add logging for node completion
    if options.include_node_logging:
        lines.append(f'{indent}log_node("{node_id}", f"Model response received. Length: {{len(str({var_name}_output))}}")')

    return lines


def generate_primitive_node_code(
    node: dict[str, Any],
    incoming: dict[str, list[dict[str, str | None]]],
    options: CodeGeneratorOptions,
) -> list[str]:
    """Generate code for a primitive node."""
    data = get_node_data(node)
    var_name = to_variable_name(node["id"])
    lines: list[str] = []
    indent = options.indent
    primitive_type = data.get("primitiveType", "merge")

    if options.include_comments:
        lines.append(f"{indent}# Primitive: {primitive_type}")

    # Get inputs mapped by handle
    inputs = incoming.get(node["id"], [])
    inputs_by_handle: dict[str, str] = {}
    for inp in inputs:
        handle = inp.get("targetHandle") or "input"
        source = inp.get("source") or ""
        inputs_by_handle[handle] = f"{to_variable_name(source)}_output"

    if primitive_type == "loop":
        collection = inputs_by_handle.get("collection", "[]")
        lines.append(f"{indent}{var_name}_results = []")
        lines.append(
            f"{indent}for {var_name}_index, {var_name}_item in enumerate({collection}):"
        )
        lines.append(f"{indent}{indent}{var_name}_results.append({var_name}_item)")
        lines.append(f"{indent}{var_name}_output = {var_name}_results")

    elif primitive_type == "conditional":
        condition = inputs_by_handle.get("condition", "False")
        value = inputs_by_handle.get("value", "None")
        lines.append(f"{indent}if {condition}:")
        lines.append(f"{indent}{indent}{var_name}_output = {value}  # true branch")
        lines.append(f"{indent}else:")
        lines.append(f"{indent}{indent}{var_name}_output = {value}  # false branch")

    elif primitive_type == "merge":
        merge_inputs = [
            inputs_by_handle.get(f"input{i}", "None")
            for i in range(1, 4)
            if inputs_by_handle.get(f"input{i}") not in (None, "None")
        ]
        lines.append(f"{indent}{var_name}_output = [{', '.join(merge_inputs)}]")

    elif primitive_type == "map":
        collection = inputs_by_handle.get("collection", "[]")
        mapper = inputs_by_handle.get("mapper", "lambda x: x")
        lines.append(
            f"{indent}{var_name}_output = [{mapper}(item) for item in {collection}]"
        )

    elif primitive_type == "filter":
        collection = inputs_by_handle.get("collection", "[]")
        predicate = inputs_by_handle.get("predicate", "lambda x: True")
        lines.append(
            f"{indent}{var_name}_output = [item for item in {collection} if {predicate}(item)]"
        )

    else:
        lines.append(
            f"{indent}{var_name}_output = None  # Unknown primitive: {primitive_type}"
        )

    return lines


def generate_utility_node_code(
    node: dict[str, Any],
    incoming: dict[str, list[dict[str, str | None]]],
    options: CodeGeneratorOptions,
    input_params: dict[str, str],
) -> list[str]:
    """Generate code for a utility node."""
    data = get_node_data(node)
    var_name = to_variable_name(node["id"])
    lines: list[str] = []
    indent = options.indent
    utility_type = data.get("utilityType", "input")

    # Get input from connected node
    inputs = incoming.get(node["id"], [])

    if utility_type == "input":
        # Input nodes become function parameters
        param_name = to_variable_name(data.get("label") or node["id"])
        input_params[node["id"]] = param_name
        if options.include_comments:
            lines.append(f"{indent}# Input: {data.get('label', node['id'])}")
        lines.append(f"{indent}{var_name}_output = {param_name}")

    elif utility_type == "output":
        if options.include_comments:
            lines.append(f"{indent}# Output: {data.get('label', node['id'])}")
        if inputs:
            source = inputs[0].get("source") or ""
            source_var = to_variable_name(source)
            lines.append(f"{indent}{var_name}_output = {source_var}_output")
        else:
            lines.append(f"{indent}{var_name}_output = None")

    elif utility_type == "constant":
        if options.include_comments:
            lines.append(f"{indent}# Constant: {data.get('label', node['id'])}")
        value = data.get("value")
        if isinstance(value, str):
            value_str = repr(value)
        elif value is None:
            value_str = "None"
        else:
            value_str = str(value)
        lines.append(f"{indent}{var_name}_output = {value_str}")

    elif utility_type == "debug":
        if options.include_comments:
            lines.append(f"{indent}# Debug: {data.get('label', node['id'])}")
        if inputs:
            source = inputs[0].get("source") or ""
            source_var = to_variable_name(source)
            input_var = f"{source_var}_output"
            label = data.get("label", node["id"])
            lines.append(f'{indent}print(f"[DEBUG {label}]: {{{input_var}}}")')
            lines.append(f"{indent}{var_name}_output = {input_var}")
        else:
            lines.append(f"{indent}{var_name}_output = None")

    elif utility_type == "note":
        # Notes don't generate code, just comments
        if options.include_comments and data.get("label"):
            lines.append(f"{indent}# Note: {data.get('label')}")

    return lines


def generate_code(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    options: CodeGeneratorOptions | None = None,
) -> GeneratedCode:
    """Generate Python code from a composition graph.

    Args:
        nodes: List of node dictionaries from the composition graph
        edges: List of edge dictionaries from the composition graph
        options: Code generation options

    Returns:
        GeneratedCode with the generated Python source and metadata
    """
    warnings: list[str] = []

    # Apply defaults
    opts = options or CodeGeneratorOptions()

    # Compute execution order
    order, has_cycle = topological_sort(nodes, edges)
    if has_cycle:
        warnings.append("Graph contains a cycle - execution order may be incorrect")

    # Build incoming edge map for dependency resolution
    incoming = build_incoming_edges(nodes, edges)

    # Create node lookup
    node_map = {node["id"]: node for node in nodes}

    # Detect inputs and outputs
    inputs = detect_inputs(nodes)
    outputs = detect_outputs(nodes)

    # Track input parameter names
    input_params: dict[str, str] = {}

    # Generate code lines
    code_lines: list[str] = []

    # Header
    code_lines.append('"""')
    code_lines.append("Auto-generated workflow code from Mellea Visual Builder")
    code_lines.append('"""')
    code_lines.append("")

    # Imports
    code_lines.append("from typing import Any, List, Optional")
    if opts.async_code:
        code_lines.append("import asyncio")
    code_lines.append("")
    code_lines.append("# Mellea runtime imports (using mellea 0.3.0 adapter)")
    code_lines.append("from mellea_api.runtime import run_program, invoke_model")
    if opts.include_node_logging:
        code_lines.append("from mellea_api.runtime import log_node, configure_runtime")
    code_lines.append("")

    # Build input parameters for function signature
    input_param_list: list[str] = []
    for node in nodes:
        data = get_node_data(node)
        if data.get("category") == "utility" and data.get("utilityType") == "input":
            param_name = to_variable_name(data.get("label") or node["id"])
            input_params[node["id"]] = param_name
            if opts.type_hints:
                data_type = data.get("dataType", "any")
                py_type = (
                    "str"
                    if data_type == "string"
                    else "float" if data_type == "number" else "Any"
                )
                input_param_list.append(f"{param_name}: {py_type}")
            else:
                input_param_list.append(param_name)

    # Function definition
    func_def = "async def" if opts.async_code else "def"
    return_type = " -> Any" if opts.type_hints else ""
    code_lines.append(
        f"{func_def} run_workflow({', '.join(input_param_list)}){return_type}:"
    )
    code_lines.append(f'{opts.indent}"""Execute the workflow."""')

    # Generate code for each node in execution order
    for node_id in order:
        current_node = node_map.get(node_id)
        if not current_node:
            warnings.append(f"Node {node_id} not found in node map")
            continue
        data = get_node_data(current_node)
        category = data.get("category", "")
        node_lines: list[str] = []

        if category == "program":
            node_lines = generate_program_node_code(current_node, incoming, opts)
        elif category == "model":
            node_lines = generate_model_node_code(current_node, incoming, opts)
        elif category == "primitive":
            node_lines = generate_primitive_node_code(current_node, incoming, opts)
        elif category == "utility":
            node_lines = generate_utility_node_code(current_node, incoming, opts, input_params)
        else:
            warnings.append(f"Unknown node category: {category}")

        if node_lines:
            code_lines.append("")
            code_lines.extend(node_lines)

    # Return statement
    code_lines.append("")
    if outputs:
        # Find output nodes and return their values
        output_vars: list[str] = []
        for node in nodes:
            data = get_node_data(node)
            if data.get("category") == "utility" and data.get("utilityType") == "output":
                output_vars.append(f"{to_variable_name(node['id'])}_output")

        if len(output_vars) == 1:
            code_lines.append(f"{opts.indent}return {output_vars[0]}")
        elif len(output_vars) > 1:
            code_lines.append(f"{opts.indent}return {{")
            for i, output in enumerate(outputs):
                comma = "," if i < len(outputs) - 1 else ""
                code_lines.append(
                    f'{opts.indent}{opts.indent}"{output.name}": {output_vars[i]}{comma}'
                )
            code_lines.append(f"{opts.indent}}}")
        else:
            code_lines.append(f"{opts.indent}return None")
    else:
        code_lines.append(f"{opts.indent}return None")

    # Main block for standalone execution
    code_lines.append("")
    code_lines.append("")
    if opts.async_code:
        code_lines.append('if __name__ == "__main__":')
        if opts.include_node_logging:
            code_lines.append(f"{opts.indent}# Configure runtime for node logging")
            code_lines.append(f"{opts.indent}configure_runtime()")
            code_lines.append("")
        code_lines.append(f"{opts.indent}# Example usage")
        if input_param_list:
            code_lines.append(f"{opts.indent}# result = asyncio.run(run_workflow(...))")
        else:
            code_lines.append(f"{opts.indent}result = asyncio.run(run_workflow())")
            code_lines.append(f'{opts.indent}print(f"Result: {{result}}")')
    else:
        code_lines.append('if __name__ == "__main__":')
        if opts.include_node_logging:
            code_lines.append(f"{opts.indent}# Configure runtime for node logging")
            code_lines.append(f"{opts.indent}configure_runtime()")
            code_lines.append("")
        code_lines.append(f"{opts.indent}# Example usage")
        if input_param_list:
            code_lines.append(f"{opts.indent}# result = run_workflow(...)")
        else:
            code_lines.append(f"{opts.indent}result = run_workflow()")
            code_lines.append(f'{opts.indent}print(f"Result: {{result}}")')

    return GeneratedCode(
        code="\n".join(code_lines),
        execution_order=order,
        inputs=inputs,
        outputs=outputs,
        warnings=warnings,
    )


def generate_standalone_script(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    options: CodeGeneratorOptions | None = None,
) -> str:
    """Generate a fully standalone Python script with runtime stubs.

    This allows the code to be run independently without the Mellea runtime.

    Args:
        nodes: List of node dictionaries from the composition graph
        edges: List of edge dictionaries from the composition graph
        options: Code generation options

    Returns:
        Complete Python script as a string
    """
    from datetime import datetime

    generated = generate_code(nodes, edges, options)
    opts = options or CodeGeneratorOptions()
    indent = opts.indent

    standalone_header = f'''#!/usr/bin/env python3
"""
Standalone workflow script generated from Mellea Visual Builder

This script includes runtime stubs that allow it to run independently.
For production use, replace the stubs with mellea 0.3.0 imports:
  from mellea_api.runtime import run_program, invoke_model

Generated at: {datetime.utcnow().isoformat()}
"""

from typing import Any, List, Optional, Callable
import asyncio
import json

# =============================================================================
# Runtime Stubs (replace with actual Mellea runtime for production)
# =============================================================================

async def run_program(
{indent}program_id: str,
{indent}slot_name: str = "main",
{indent}*,
{indent}module_name: str | None = None,
{indent}backend: str | None = None,
{indent}model_id: str | None = None,
{indent}**kwargs
) -> Any:
{indent}"""
{indent}Stub for running a Mellea program (mellea 0.3.0 API).

{indent}In production, this would:
{indent}- Import the module (module_name or program_id)
{indent}- Execute the @generative slot with given arguments
{indent}- Return the slot output

{indent}Args:
{indent}{indent}program_id: Program identifier (used as module name if module_name not provided)
{indent}{indent}slot_name: Name of the @generative slot to execute (default: "main")
{indent}{indent}module_name: Python module path (defaults to program_id)
{indent}{indent}backend: Backend name ('ollama', 'openai', 'watsonx', etc.)
{indent}{indent}model_id: Model identifier (e.g., 'granite4:micro', 'gpt-4o')
{indent}{indent}**kwargs: Arguments to pass to the slot

{indent}Returns:
{indent}{indent}The slot output
{indent}"""
{indent}print(f"[STUB] Running program: {{program_id}}, slot: {{slot_name}}")
{indent}print(f"[STUB] Backend: {{backend or 'default'}}, Model: {{model_id or 'default'}}")
{indent}print(f"[STUB] Inputs: {{kwargs}}")
{indent}# Simulate slot execution
{indent}await asyncio.sleep(0.1)
{indent}return {{"status": "success", "program_id": program_id, "slot": slot_name, "inputs": kwargs}}


async def invoke_model(
{indent}model_id: str,
{indent}prompt: str,
{indent}*,
{indent}backend: str | None = None,
{indent}**kwargs
) -> str:
{indent}"""
{indent}Stub for invoking an LLM model (mellea 0.3.0 API).

{indent}In production, this would:
{indent}- Initialize a MelleaRuntime with the specified backend/model
{indent}- Send the prompt via session.chat()
{indent}- Return the model response

{indent}Args:
{indent}{indent}model_id: Model identifier (e.g., 'ollama:granite4:micro', 'gpt-4o')
{indent}{indent}prompt: The prompt to send
{indent}{indent}backend: Optional backend override
{indent}{indent}**kwargs: Additional model options

{indent}Returns:
{indent}{indent}Model response text
{indent}"""
{indent}print(f"[STUB] Invoking model: {{model_id}}")
{indent}print(f"[STUB] Backend: {{backend or 'auto'}}")
{indent}print(f"[STUB] Prompt: {{prompt}}")
{indent}# Simulate model invocation
{indent}await asyncio.sleep(0.2)
{indent}return f"[Model {{model_id}} response to: {{prompt}}]"


# =============================================================================
# Workflow Definition
# =============================================================================

'''

    # Extract just the workflow function and main block from generated code
    code_lines = generated.code.split("\n")
    workflow_start = -1
    for i, line in enumerate(code_lines):
        if line.startswith("async def run_workflow") or line.startswith(
            "def run_workflow"
        ):
            workflow_start = i
            break

    if workflow_start >= 0:
        workflow_code = "\n".join(code_lines[workflow_start:])
    else:
        # Fallback: use full generated code without header
        import_end = -1
        for i, line in enumerate(code_lines):
            if line.startswith("async def") or line.startswith("def"):
                import_end = i
                break
        workflow_code = (
            "\n".join(code_lines[import_end:]) if import_end >= 0 else generated.code
        )

    return standalone_header + workflow_code


class CodeGenerator:
    """Code generator for composition workflows.

    Generates executable Python code from composition graph definitions.
    """

    def __init__(self, options: CodeGeneratorOptions | None = None) -> None:
        """Initialize the CodeGenerator.

        Args:
            options: Code generation options
        """
        self.options = options or CodeGeneratorOptions()

    def generate(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> GeneratedCode:
        """Generate code from composition nodes and edges.

        Args:
            nodes: List of node dictionaries from the composition graph
            edges: List of edge dictionaries from the composition graph

        Returns:
            GeneratedCode with the generated Python source and metadata
        """
        return generate_code(nodes, edges, self.options)

    def get_execution_order(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> tuple[list[str], bool]:
        """Get the topological execution order without generating code.

        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries

        Returns:
            Tuple of (ordered node IDs, has_cycle flag)
        """
        return topological_sort(nodes, edges)

    def set_options(self, **kwargs: Any) -> None:
        """Update generator options.

        Args:
            **kwargs: Options to update
        """
        for key, value in kwargs.items():
            if hasattr(self.options, key):
                setattr(self.options, key, value)

    def generate_standalone(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> str:
        """Generate a standalone script with runtime stubs.

        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries

        Returns:
            Complete Python script as a string
        """
        return generate_standalone_script(nodes, edges, self.options)


# Global generator instance
_code_generator: CodeGenerator | None = None


def get_code_generator() -> CodeGenerator:
    """Get the global CodeGenerator instance."""
    global _code_generator
    if _code_generator is None:
        _code_generator = CodeGenerator()
    return _code_generator
