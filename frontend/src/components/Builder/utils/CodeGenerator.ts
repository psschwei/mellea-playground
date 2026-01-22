/**
 * CodeGenerator - Generates executable Python code from composition graphs
 *
 * Takes a visual composition (nodes + edges) and produces:
 * - Topologically sorted execution order
 * - Python code that wires up the workflow
 * - Import statements for dependencies
 */

import type { Node, Edge } from 'reactflow';
import type { MelleaNodeData } from '../CompositionContext';
import type {
  CompositionNode,
  CompositionEdge,
  CompositionInput,
  CompositionOutput,
} from '../../../types';

// ============================================================================
// Types
// ============================================================================

/** Node type identifiers used in the graph */
export type NodeType = 'program' | 'model' | 'primitive' | 'utility';

/** Primitive node subtypes */
export type PrimitiveType = 'loop' | 'conditional' | 'merge' | 'map' | 'filter';

/** Utility node subtypes */
export type UtilityType = 'input' | 'output' | 'note' | 'constant' | 'debug';

/** Extended node data with subtype info */
interface ExtendedNodeData extends MelleaNodeData {
  primitiveType?: PrimitiveType;
  utilityType?: UtilityType;
  programId?: string;
  modelId?: string;
  value?: unknown;
  dataType?: string;
  slots?: {
    inputs: Array<{ id: string; label: string; type?: string }>;
    outputs: Array<{ id: string; label: string; type?: string }>;
  };
}

/** Generated code result */
export interface GeneratedCode {
  /** The generated Python source code */
  code: string;
  /** Ordered list of node IDs for execution */
  executionOrder: string[];
  /** Detected composition inputs */
  inputs: CompositionInput[];
  /** Detected composition outputs */
  outputs: CompositionOutput[];
  /** Any warnings during code generation */
  warnings: string[];
}

/** Options for code generation */
export interface CodeGeneratorOptions {
  /** Include debug comments in generated code */
  includeComments?: boolean;
  /** Generate async code (default: true) */
  async?: boolean;
  /** Indent string (default: 4 spaces) */
  indent?: string;
  /** Include type hints (default: true) */
  typeHints?: boolean;
}

// ============================================================================
// Graph Analysis
// ============================================================================

/**
 * Build adjacency list from edges
 */
function buildAdjacencyList(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
  edges: Array<CompositionEdge | Edge>
): Map<string, string[]> {
  const adjacency = new Map<string, string[]>();

  // Initialize all nodes
  for (const node of nodes) {
    adjacency.set(node.id, []);
  }

  // Add edges (source -> target)
  for (const edge of edges) {
    const targets = adjacency.get(edge.source) || [];
    if (!targets.includes(edge.target)) {
      targets.push(edge.target);
      adjacency.set(edge.source, targets);
    }
  }

  return adjacency;
}

/**
 * Build reverse adjacency (incoming edges) for dependency tracking
 */
function buildIncomingEdges(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
  edges: Array<CompositionEdge | Edge>
): Map<string, Array<{ source: string; sourceHandle?: string; targetHandle?: string }>> {
  const incoming = new Map<
    string,
    Array<{ source: string; sourceHandle?: string; targetHandle?: string }>
  >();

  // Initialize all nodes
  for (const node of nodes) {
    incoming.set(node.id, []);
  }

  // Add edges
  for (const edge of edges) {
    const sources = incoming.get(edge.target) || [];
    sources.push({
      source: edge.source,
      sourceHandle: edge.sourceHandle ?? undefined,
      targetHandle: edge.targetHandle ?? undefined,
    });
    incoming.set(edge.target, sources);
  }

  return incoming;
}

/**
 * Compute topological sort using Kahn's algorithm
 * Returns node IDs in execution order
 */
export function topologicalSort(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
  edges: Array<CompositionEdge | Edge>
): { order: string[]; hasCycle: boolean } {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const inDegree = new Map<string, number>();
  const adjacency = buildAdjacencyList(nodes, edges);

  // Calculate in-degrees
  for (const nodeId of nodeIds) {
    inDegree.set(nodeId, 0);
  }
  for (const edge of edges) {
    if (nodeIds.has(edge.target)) {
      inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
    }
  }

  // Initialize queue with nodes having no incoming edges
  const queue: string[] = [];
  for (const [nodeId, degree] of inDegree) {
    if (degree === 0) {
      queue.push(nodeId);
    }
  }

  const order: string[] = [];

  while (queue.length > 0) {
    const nodeId = queue.shift()!;
    order.push(nodeId);

    // Reduce in-degree of neighbors
    const neighbors = adjacency.get(nodeId) || [];
    for (const neighbor of neighbors) {
      const newDegree = (inDegree.get(neighbor) || 0) - 1;
      inDegree.set(neighbor, newDegree);
      if (newDegree === 0) {
        queue.push(neighbor);
      }
    }
  }

  // Check for cycle
  const hasCycle = order.length !== nodeIds.size;

  return { order, hasCycle };
}

// ============================================================================
// Code Generation Helpers
// ============================================================================

/**
 * Convert node ID to valid Python variable name
 */
function toVariableName(nodeId: string): string {
  // Replace non-alphanumeric with underscore, ensure starts with letter
  let name = nodeId.replace(/[^a-zA-Z0-9]/g, '_');
  if (/^[0-9]/.test(name)) {
    name = 'node_' + name;
  }
  return name;
}

/**
 * Get node data with proper typing
 */
function getNodeData(
  node: CompositionNode | Node<ExtendedNodeData>
): ExtendedNodeData {
  return node.data as ExtendedNodeData;
}

/**
 * Detect composition inputs (utility nodes with utilityType='input')
 */
function detectInputs(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>
): CompositionInput[] {
  const inputs: CompositionInput[] = [];

  for (const node of nodes) {
    const data = getNodeData(node);
    if (data.category === 'utility' && data.utilityType === 'input') {
      inputs.push({
        name: data.label || node.id,
        type: data.dataType || 'any',
        required: true,
        description: `Input from node ${node.id}`,
      });
    }
  }

  return inputs;
}

/**
 * Detect composition outputs (utility nodes with utilityType='output')
 */
function detectOutputs(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>
): CompositionOutput[] {
  const outputs: CompositionOutput[] = [];

  for (const node of nodes) {
    const data = getNodeData(node);
    if (data.category === 'utility' && data.utilityType === 'output') {
      outputs.push({
        name: data.label || node.id,
        type: data.dataType || 'any',
        description: `Output from node ${node.id}`,
      });
    }
  }

  return outputs;
}

// ============================================================================
// Node-specific Code Generation
// ============================================================================

/**
 * Generate code for a program node
 */
function generateProgramNodeCode(
  node: CompositionNode | Node<ExtendedNodeData>,
  incoming: Map<string, Array<{ source: string; sourceHandle?: string; targetHandle?: string }>>,
  options: CodeGeneratorOptions
): string[] {
  const data = getNodeData(node);
  const varName = toVariableName(node.id);
  const lines: string[] = [];
  const indent = options.indent || '    ';

  // Get inputs from connected nodes
  const inputs = incoming.get(node.id) || [];
  const inputArgs: string[] = [];

  for (const input of inputs) {
    const sourceVar = toVariableName(input.source);
    const handle = input.targetHandle || 'input';
    inputArgs.push(`${handle}=${sourceVar}_output`);
  }

  if (options.includeComments) {
    lines.push(`${indent}# Program: ${data.label || node.id}`);
    if (data.programId) {
      lines.push(`${indent}# Program ID: ${data.programId}`);
    }
  }

  const asyncPrefix = options.async ? 'await ' : '';
  const argsStr = inputArgs.length > 0 ? inputArgs.join(', ') : '';

  lines.push(
    `${indent}${varName}_output = ${asyncPrefix}run_program("${data.programId || data.label || node.id}"${argsStr ? ', ' + argsStr : ''})`
  );

  return lines;
}

/**
 * Generate code for a model node
 */
function generateModelNodeCode(
  node: CompositionNode | Node<ExtendedNodeData>,
  incoming: Map<string, Array<{ source: string; sourceHandle?: string; targetHandle?: string }>>,
  options: CodeGeneratorOptions
): string[] {
  const data = getNodeData(node);
  const varName = toVariableName(node.id);
  const lines: string[] = [];
  const indent = options.indent || '    ';

  // Get input from connected node
  const inputs = incoming.get(node.id) || [];
  let inputExpr = '""';

  if (inputs.length > 0) {
    inputExpr = `${toVariableName(inputs[0].source)}_output`;
  }

  if (options.includeComments) {
    lines.push(`${indent}# Model: ${data.label || node.id}`);
  }

  const asyncPrefix = options.async ? 'await ' : '';
  lines.push(
    `${indent}${varName}_output = ${asyncPrefix}invoke_model("${data.label || node.id}", ${inputExpr})`
  );

  return lines;
}

/**
 * Generate code for a primitive node
 */
function generatePrimitiveNodeCode(
  node: CompositionNode | Node<ExtendedNodeData>,
  incoming: Map<string, Array<{ source: string; sourceHandle?: string; targetHandle?: string }>>,
  options: CodeGeneratorOptions
): string[] {
  const data = getNodeData(node);
  const varName = toVariableName(node.id);
  const lines: string[] = [];
  const indent = options.indent || '    ';
  const primitiveType = data.primitiveType || 'merge';

  if (options.includeComments) {
    lines.push(`${indent}# Primitive: ${primitiveType}`);
  }

  // Get inputs mapped by handle
  const inputs = incoming.get(node.id) || [];
  const inputsByHandle: Record<string, string> = {};
  for (const input of inputs) {
    const handle = input.targetHandle || 'input';
    inputsByHandle[handle] = `${toVariableName(input.source)}_output`;
  }

  switch (primitiveType) {
    case 'loop':
      lines.push(`${indent}${varName}_results = []`);
      lines.push(
        `${indent}for ${varName}_index, ${varName}_item in enumerate(${inputsByHandle['collection'] || '[]'}):`
      );
      lines.push(`${indent}${indent}${varName}_results.append(${varName}_item)`);
      lines.push(`${indent}${varName}_output = ${varName}_results`);
      break;

    case 'conditional':
      lines.push(`${indent}if ${inputsByHandle['condition'] || 'False'}:`);
      lines.push(
        `${indent}${indent}${varName}_output = ${inputsByHandle['value'] || 'None'}  # true branch`
      );
      lines.push(`${indent}else:`);
      lines.push(
        `${indent}${indent}${varName}_output = ${inputsByHandle['value'] || 'None'}  # false branch`
      );
      break;

    case 'merge': {
      const mergeInputs = [
        inputsByHandle['input1'] || 'None',
        inputsByHandle['input2'] || 'None',
        inputsByHandle['input3'] || 'None',
      ].filter((v) => v !== 'None');
      lines.push(`${indent}${varName}_output = [${mergeInputs.join(', ')}]`);
      break;
    }

    case 'map':
      lines.push(
        `${indent}${varName}_output = [${inputsByHandle['mapper'] || 'lambda x: x'}(item) for item in ${inputsByHandle['collection'] || '[]'}]`
      );
      break;

    case 'filter':
      lines.push(
        `${indent}${varName}_output = [item for item in ${inputsByHandle['collection'] || '[]'} if ${inputsByHandle['predicate'] || 'lambda x: True'}(item)]`
      );
      break;

    default:
      lines.push(`${indent}${varName}_output = None  # Unknown primitive: ${primitiveType}`);
  }

  return lines;
}

/**
 * Generate code for a utility node
 */
function generateUtilityNodeCode(
  node: CompositionNode | Node<ExtendedNodeData>,
  incoming: Map<string, Array<{ source: string; sourceHandle?: string; targetHandle?: string }>>,
  options: CodeGeneratorOptions,
  inputParams: Map<string, string>
): string[] {
  const data = getNodeData(node);
  const varName = toVariableName(node.id);
  const lines: string[] = [];
  const indent = options.indent || '    ';
  const utilityType = data.utilityType || 'input';

  // Get input from connected node
  const inputs = incoming.get(node.id) || [];

  switch (utilityType) {
    case 'input': {
      // Input nodes become function parameters
      const paramName = toVariableName(data.label || node.id);
      inputParams.set(node.id, paramName);
      if (options.includeComments) {
        lines.push(`${indent}# Input: ${data.label || node.id}`);
      }
      lines.push(`${indent}${varName}_output = ${paramName}`);
      break;
    }

    case 'output':
      if (options.includeComments) {
        lines.push(`${indent}# Output: ${data.label || node.id}`);
      }
      if (inputs.length > 0) {
        lines.push(
          `${indent}${varName}_output = ${toVariableName(inputs[0].source)}_output`
        );
      } else {
        lines.push(`${indent}${varName}_output = None`);
      }
      break;

    case 'constant': {
      if (options.includeComments) {
        lines.push(`${indent}# Constant: ${data.label || node.id}`);
      }
      const value = data.value;
      let valueStr: string;
      if (typeof value === 'string') {
        valueStr = JSON.stringify(value);
      } else if (value === undefined || value === null) {
        valueStr = 'None';
      } else {
        valueStr = String(value);
      }
      lines.push(`${indent}${varName}_output = ${valueStr}`);
      break;
    }

    case 'debug':
      if (options.includeComments) {
        lines.push(`${indent}# Debug: ${data.label || node.id}`);
      }
      if (inputs.length > 0) {
        const inputVar = `${toVariableName(inputs[0].source)}_output`;
        lines.push(`${indent}print(f"[DEBUG ${data.label || node.id}]: {${inputVar}}")`);
        lines.push(`${indent}${varName}_output = ${inputVar}`);
      } else {
        lines.push(`${indent}${varName}_output = None`);
      }
      break;

    case 'note':
      // Notes don't generate code, just comments
      if (options.includeComments && data.label) {
        lines.push(`${indent}# Note: ${data.label}`);
      }
      break;
  }

  return lines;
}

// ============================================================================
// Main Code Generator
// ============================================================================

/**
 * Generate Python code from a composition graph
 */
export function generateCode(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
  edges: Array<CompositionEdge | Edge>,
  options: CodeGeneratorOptions = {}
): GeneratedCode {
  const warnings: string[] = [];

  // Apply defaults
  const opts: CodeGeneratorOptions = {
    includeComments: true,
    async: true,
    indent: '    ',
    typeHints: true,
    ...options,
  };

  // Compute execution order
  const { order, hasCycle } = topologicalSort(nodes, edges);
  if (hasCycle) {
    warnings.push('Graph contains a cycle - execution order may be incorrect');
  }

  // Build incoming edge map for dependency resolution
  const incoming = buildIncomingEdges(nodes, edges);

  // Create node lookup
  const nodeMap = new Map<string, CompositionNode | Node<ExtendedNodeData>>();
  for (const node of nodes) {
    nodeMap.set(node.id, node);
  }

  // Detect inputs and outputs
  const inputs = detectInputs(nodes);
  const outputs = detectOutputs(nodes);

  // Track input parameter names
  const inputParams = new Map<string, string>();

  // Generate code lines
  const codeLines: string[] = [];

  // Header
  codeLines.push('"""');
  codeLines.push('Auto-generated workflow code from Mellea Visual Builder');
  codeLines.push('"""');
  codeLines.push('');

  // Imports
  codeLines.push('from typing import Any, List, Optional');
  if (opts.async) {
    codeLines.push('import asyncio');
  }
  codeLines.push('');
  codeLines.push('# Mellea runtime imports');
  codeLines.push('from mellea.runtime import run_program, invoke_model');
  codeLines.push('');

  // Build input parameters for function signature
  const inputParamList: string[] = [];
  for (const node of nodes) {
    const data = getNodeData(node);
    if (data.category === 'utility' && data.utilityType === 'input') {
      const paramName = toVariableName(data.label || node.id);
      inputParams.set(node.id, paramName);
      if (opts.typeHints) {
        const pyType = data.dataType === 'string' ? 'str' : data.dataType === 'number' ? 'float' : 'Any';
        inputParamList.push(`${paramName}: ${pyType}`);
      } else {
        inputParamList.push(paramName);
      }
    }
  }

  // Function definition
  const funcDef = opts.async ? 'async def' : 'def';
  const returnType = opts.typeHints ? ' -> Any' : '';
  codeLines.push(`${funcDef} run_workflow(${inputParamList.join(', ')})${returnType}:`);
  codeLines.push(`${opts.indent}"""Execute the workflow."""`);

  // Generate code for each node in execution order
  for (const nodeId of order) {
    const node = nodeMap.get(nodeId);
    if (!node) {
      warnings.push(`Node ${nodeId} not found in node map`);
      continue;
    }

    const data = getNodeData(node);
    let nodeLines: string[] = [];

    switch (data.category) {
      case 'program':
        nodeLines = generateProgramNodeCode(node, incoming, opts);
        break;
      case 'model':
        nodeLines = generateModelNodeCode(node, incoming, opts);
        break;
      case 'primitive':
        nodeLines = generatePrimitiveNodeCode(node, incoming, opts);
        break;
      case 'utility':
        nodeLines = generateUtilityNodeCode(node, incoming, opts, inputParams);
        break;
      default:
        warnings.push(`Unknown node category: ${data.category}`);
    }

    if (nodeLines.length > 0) {
      codeLines.push('');
      codeLines.push(...nodeLines);
    }
  }

  // Return statement
  codeLines.push('');
  if (outputs.length > 0) {
    // Find output nodes and return their values
    const outputVars: string[] = [];
    for (const node of nodes) {
      const data = getNodeData(node);
      if (data.category === 'utility' && data.utilityType === 'output') {
        outputVars.push(`${toVariableName(node.id)}_output`);
      }
    }
    if (outputVars.length === 1) {
      codeLines.push(`${opts.indent}return ${outputVars[0]}`);
    } else if (outputVars.length > 1) {
      codeLines.push(`${opts.indent}return {`);
      for (let i = 0; i < outputs.length; i++) {
        const comma = i < outputs.length - 1 ? ',' : '';
        codeLines.push(`${opts.indent}${opts.indent}"${outputs[i].name}": ${outputVars[i]}${comma}`);
      }
      codeLines.push(`${opts.indent}}`);
    } else {
      codeLines.push(`${opts.indent}return None`);
    }
  } else {
    codeLines.push(`${opts.indent}return None`);
  }

  // Main block for standalone execution
  codeLines.push('');
  codeLines.push('');
  if (opts.async) {
    codeLines.push('if __name__ == "__main__":');
    codeLines.push(`${opts.indent}# Example usage`);
    if (inputParamList.length > 0) {
      codeLines.push(`${opts.indent}# result = asyncio.run(run_workflow(...))`);
    } else {
      codeLines.push(`${opts.indent}result = asyncio.run(run_workflow())`);
      codeLines.push(`${opts.indent}print(f"Result: {result}")`);
    }
  } else {
    codeLines.push('if __name__ == "__main__":');
    codeLines.push(`${opts.indent}# Example usage`);
    if (inputParamList.length > 0) {
      codeLines.push(`${opts.indent}# result = run_workflow(...)`);
    } else {
      codeLines.push(`${opts.indent}result = run_workflow()`);
      codeLines.push(`${opts.indent}print(f"Result: {result}")`);
    }
  }

  return {
    code: codeLines.join('\n'),
    executionOrder: order,
    inputs,
    outputs,
    warnings,
  };
}

/**
 * Create a CodeGenerator instance with default options
 */
export class CodeGenerator {
  private options: CodeGeneratorOptions;

  constructor(options: CodeGeneratorOptions = {}) {
    this.options = {
      includeComments: true,
      async: true,
      indent: '    ',
      typeHints: true,
      ...options,
    };
  }

  /**
   * Generate code from composition nodes and edges
   */
  generate(
    nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
    edges: Array<CompositionEdge | Edge>
  ): GeneratedCode {
    return generateCode(nodes, edges, this.options);
  }

  /**
   * Get the topological execution order without generating code
   */
  getExecutionOrder(
    nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
    edges: Array<CompositionEdge | Edge>
  ): { order: string[]; hasCycle: boolean } {
    return topologicalSort(nodes, edges);
  }

  /**
   * Update generator options
   */
  setOptions(options: Partial<CodeGeneratorOptions>): void {
    this.options = { ...this.options, ...options };
  }
}

/**
 * Create a new CodeGenerator instance
 */
export function createCodeGenerator(
  options?: CodeGeneratorOptions
): CodeGenerator {
  return new CodeGenerator(options);
}

// ============================================================================
// Standalone Export
// ============================================================================

/**
 * Generate a fully standalone Python script with runtime stubs
 * This allows the code to be run independently without the Mellea runtime
 */
export function generateStandaloneScript(
  nodes: Array<CompositionNode | Node<ExtendedNodeData>>,
  edges: Array<CompositionEdge | Edge>,
  options: CodeGeneratorOptions = {}
): string {
  const generated = generateCode(nodes, edges, options);
  const indent = options.indent || '    ';

  const standaloneHeader = `#!/usr/bin/env python3
"""
Standalone workflow script generated from Mellea Visual Builder

This script includes runtime stubs that allow it to run independently.
For production use, replace the stubs with actual Mellea runtime imports.

Generated at: ${new Date().toISOString()}
"""

from typing import Any, List, Optional, Callable
import asyncio
import json

# =============================================================================
# Runtime Stubs (replace with actual Mellea runtime for production)
# =============================================================================

async def run_program(program_id: str, **kwargs) -> Any:
${indent}"""
${indent}Stub for running a Mellea program.
${indent}
${indent}In production, this would:
${indent}- Load the program from the asset store
${indent}- Execute it with the provided inputs
${indent}- Return the program output
${indent}
${indent}Args:
${indent}${indent}program_id: The ID of the program to run
${indent}${indent}**kwargs: Input arguments for the program
${indent}
${indent}Returns:
${indent}${indent}The program output
${indent}"""
${indent}print(f"[STUB] Running program: {program_id}")
${indent}print(f"[STUB] Inputs: {kwargs}")
${indent}# Simulate program execution
${indent}await asyncio.sleep(0.1)
${indent}return {"status": "success", "program_id": program_id, "inputs": kwargs}


async def invoke_model(model_id: str, prompt: Any) -> Any:
${indent}"""
${indent}Stub for invoking an LLM model.
${indent}
${indent}In production, this would:
${indent}- Load the model configuration from the asset store
${indent}- Send the prompt to the model API
${indent}- Return the model response
${indent}
${indent}Args:
${indent}${indent}model_id: The ID of the model to invoke
${indent}${indent}prompt: The input prompt or data
${indent}
${indent}Returns:
${indent}${indent}The model response
${indent}"""
${indent}print(f"[STUB] Invoking model: {model_id}")
${indent}print(f"[STUB] Prompt: {prompt}")
${indent}# Simulate model invocation
${indent}await asyncio.sleep(0.2)
${indent}return f"[Model {model_id} response to: {prompt}]"


# =============================================================================
# Workflow Definition
# =============================================================================

`;

  // Extract just the workflow function and main block from generated code
  const codeLines = generated.code.split('\n');
  const workflowStart = codeLines.findIndex(line =>
    line.startsWith('async def run_workflow') || line.startsWith('def run_workflow')
  );

  let workflowCode = '';
  if (workflowStart >= 0) {
    workflowCode = codeLines.slice(workflowStart).join('\n');
  } else {
    // Fallback: use the full generated code without the header
    const importEnd = codeLines.findIndex(line => line.startsWith('async def') || line.startsWith('def'));
    workflowCode = importEnd >= 0 ? codeLines.slice(importEnd).join('\n') : generated.code;
  }

  return standaloneHeader + workflowCode;
}

/**
 * Download text content as a file
 */
export function downloadAsFile(content: string, filename: string, mimeType: string = 'text/plain'): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
