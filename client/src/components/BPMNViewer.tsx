import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  MarkerType,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

interface BPMNViewerProps {
  mermaidCode: string;
  className?: string;
}

function parseMermaidToFlow(mermaidCode: string): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  const nodeMap = new Map<string, { label: string; type: string }>();

  const lines = mermaidCode.split("\n").map((l) => l.trim()).filter((l) => l && !l.startsWith("%%"));

  let yPosition = 0;
  const xPositions = new Map<number, number>();
  const nodeYLevels = new Map<string, number>();
  const processedNodes = new Set<string>();

  for (const line of lines) {
    if (line.startsWith("flowchart") || line.startsWith("graph")) continue;
    if (line.startsWith("subgraph") || line === "end") continue;
    if (line.startsWith("style") || line.startsWith("classDef")) continue;

    // Parse node definitions: A[Label] or A([Label]) or A{Label} or A((Label))
    const nodePatterns = [
      /^([A-Za-z_][A-Za-z0-9_]*)\[\[([^\]]+)\]\]/g, // A[[Label]] - subroutine
      /^([A-Za-z_][A-Za-z0-9_]*)\(\[([^\]]+)\]\)/g, // A([Label]) - stadium
      /^([A-Za-z_][A-Za-z0-9_]*)\[\(([^\)]+)\)\]/g, // A[(Label)] - cylinder
      /^([A-Za-z_][A-Za-z0-9_]*)\(\(([^\)]+)\)\)/g, // A((Label)) - circle
      /^([A-Za-z_][A-Za-z0-9_]*)\{([^\}]+)\}/g,     // A{Label} - diamond
      /^([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]/g,     // A[Label] - rectangle
      /^([A-Za-z_][A-Za-z0-9_]*)\(([^\)]+)\)/g,     // A(Label) - rounded
    ];

    // Parse edges: A --> B or A -->|text| B
    const edgeMatch = line.match(
      /([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?)\s*(-->|--o|--x|---|-.->|==>)\s*(?:\|([^|]*)\|)?\s*([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?)/
    );

    if (edgeMatch) {
      const [, sourceRaw, edgeType, labelText, targetRaw] = edgeMatch;
      
      // Extract node IDs and labels
      const extractNode = (raw: string): { id: string; label: string; shape: string } => {
        const patterns = [
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\[\[([^\]]+)\]\]/, shape: "subroutine" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\(\[([^\]]+)\]\)/, shape: "stadium" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\[\(([^\)]+)\)\]/, shape: "cylinder" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\(\(([^\)]+)\)\)/, shape: "circle" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\{([^\}]+)\}/, shape: "diamond" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\[([^\]]+)\]/, shape: "rectangle" },
          { regex: /^([A-Za-z_][A-Za-z0-9_]*)\(([^\)]+)\)/, shape: "rounded" },
        ];
        
        for (const { regex, shape } of patterns) {
          const match = raw.match(regex);
          if (match) {
            return { id: match[1], label: match[2], shape };
          }
        }
        return { id: raw, label: raw, shape: "rectangle" };
      };

      const source = extractNode(sourceRaw);
      const target = extractNode(targetRaw);

      // Register nodes if not already registered
      if (!nodeMap.has(source.id)) {
        nodeMap.set(source.id, { label: source.label, type: source.shape });
      }
      if (!nodeMap.has(target.id)) {
        nodeMap.set(target.id, { label: target.label, type: target.shape });
      }

      // Add edge
      edges.push({
        id: `e-${source.id}-${target.id}-${edges.length}`,
        source: source.id,
        target: target.id,
        label: labelText || undefined,
        type: "smoothstep",
        animated: edgeType === "-.->" || edgeType === "==>",
        style: {
          stroke: "#3b82f6",
          strokeWidth: 2,
        },
        labelStyle: {
          fill: "#1e293b",
          fontWeight: 500,
          fontSize: 12,
        },
        labelBgStyle: {
          fill: "#ffffff",
          fillOpacity: 0.9,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: "#3b82f6",
        },
      });

      // Track levels for positioning
      if (!nodeYLevels.has(source.id)) {
        nodeYLevels.set(source.id, yPosition);
      }
      const sourceLevel = nodeYLevels.get(source.id)!;
      if (!nodeYLevels.has(target.id)) {
        nodeYLevels.set(target.id, sourceLevel + 1);
        yPosition = Math.max(yPosition, sourceLevel + 1);
      }
    }
  }

  // Calculate positions and create nodes
  const levelNodes = new Map<number, string[]>();
  nodeYLevels.forEach((level, nodeId) => {
    if (!levelNodes.has(level)) {
      levelNodes.set(level, []);
    }
    levelNodes.get(level)!.push(nodeId);
  });

  nodeMap.forEach((nodeData, nodeId) => {
    const level = nodeYLevels.get(nodeId) || 0;
    const nodesAtLevel = levelNodes.get(level) || [nodeId];
    const indexAtLevel = nodesAtLevel.indexOf(nodeId);
    const totalAtLevel = nodesAtLevel.length;

    // Center nodes at each level
    const xSpacing = 280;
    const ySpacing = 120;
    const xOffset = ((totalAtLevel - 1) * xSpacing) / 2;

    const getNodeStyle = (type: string) => {
      const baseStyle = {
        padding: "12px 20px",
        fontSize: "13px",
        fontWeight: 500,
        border: "2px solid #3b82f6",
        color: "#1e293b",
        minWidth: "160px",
        textAlign: "center" as const,
      };

      switch (type) {
        case "circle":
          return { ...baseStyle, borderRadius: "50%", background: "#dbeafe", minWidth: "80px", minHeight: "80px" };
        case "diamond":
          return { ...baseStyle, borderRadius: "4px", background: "#fef3c7", border: "2px solid #f59e0b", transform: "rotate(45deg)" };
        case "stadium":
        case "rounded":
          return { ...baseStyle, borderRadius: "24px", background: "#f0fdf4", border: "2px solid #22c55e" };
        case "subroutine":
          return { ...baseStyle, borderRadius: "4px", background: "#f5f3ff", border: "3px double #8b5cf6" };
        case "cylinder":
          return { ...baseStyle, borderRadius: "8px 8px 0 0", background: "#fef2f2", border: "2px solid #ef4444" };
        default:
          return { ...baseStyle, borderRadius: "8px", background: "#f8fafc" };
      }
    };

    nodes.push({
      id: nodeId,
      type: "default",
      position: {
        x: indexAtLevel * xSpacing - xOffset + 400,
        y: level * ySpacing + 50,
      },
      data: {
        label: nodeData.label,
      },
      style: getNodeStyle(nodeData.type),
    });
  });

  return { nodes, edges };
}

export function BPMNViewer({ mermaidCode, className = "" }: BPMNViewerProps) {
  const { nodes: initialNodes, edges: initialEdges } = useMemo(
    () => parseMermaidToFlow(mermaidCode),
    [mermaidCode]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  const onInit = useCallback((reactFlowInstance: any) => {
    reactFlowInstance.fitView({ padding: 0.2 });
  }, []);

  if (nodes.length === 0) {
    return (
      <div className={`flex items-center justify-center h-[500px] bg-muted/30 rounded-lg border ${className}`}>
        <p className="text-muted-foreground">Unable to parse diagram. Try regenerating.</p>
      </div>
    );
  }

  return (
    <div className={`h-[550px] rounded-lg border-2 border-border overflow-hidden ${className}`} data-testid="bpmn-viewer">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={onInit}
        fitView
        attributionPosition="bottom-left"
        proOptions={{ hideAttribution: true }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: "smoothstep",
        }}
      >
        <Controls 
          showZoom={true}
          showFitView={true}
          showInteractive={false}
          position="top-right"
        />
        <MiniMap 
          nodeColor="#3b82f6"
          maskColor="rgba(0, 0, 0, 0.1)"
          className="!bg-background !border-border"
          position="bottom-right"
        />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}
