import React, { useState, useRef, useCallback, useEffect, useMemo, createContext, useContext } from 'react';

export interface FlowingerNode<T = any> {
  id: string;
  position: { x: number; y: number };
  data: T;
  type?: string;
  className?: string;
  style?: React.CSSProperties;
}

export interface FlowingerEdge {
  id: string;
  source: string;
  target: string;
  label?: string | number;
  animated?: boolean;
  style?: React.CSSProperties;
  className?: string;
  data?: any;
}

interface ComputedEdge {
  edge: FlowingerEdge;
  pathData: string;
  strokeColor: string;
  isDown: boolean;
  isAlternate: boolean;
  isAnimated: boolean;
  midX: number;
  midY: number;
  labelStr: string;
  badgeWidth: number;
  badgeHalf: number;
  badgeFill: string;
  labelTextColor: string;
}

interface FlowingerContextType {
  zoom: number;
  pan: { x: number; y: number };
  zoomIn: () => void;
  zoomOut: () => void;
  resetView: () => void;
  fitView: () => void;
}

const FlowingerContext = createContext<FlowingerContextType | null>(null);

export interface FlowingerProps {
  nodes: FlowingerNode[];
  edges: FlowingerEdge[];
  onNodeClick?: (event: React.MouseEvent, node: FlowingerNode) => void;
  nodeTypes?: Record<string, React.ComponentType<{ id: string; data: any; selected?: boolean }>>;
  children?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

export const Flowinger: React.FC<FlowingerProps> = ({
  nodes,
  edges,
  onNodeClick,
  nodeTypes,
  children,
  className = '',
  style = {},
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // User-dragged custom node coordinates
  const [draggedPositions, setDraggedPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [activeDragNodeId, setActiveDragNodeId] = useState<string | null>(null);

  const dragNodeRef = useRef<{
    nodeId: string;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    hasMoved: boolean;
  } | null>(null);

  const isPanningRef = useRef<boolean>(false);
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });

  // Node position lookup map (exact and normalized case-insensitive)
  const nodeMap = useMemo(() => {
    const map = new Map<string, FlowingerNode>();
    nodes.forEach((n) => {
      if (n && n.id) {
        map.set(n.id, n);
        map.set(n.id.trim(), n);
        map.set(n.id.trim().toLowerCase(), n);
      }
    });
    return map;
  }, [nodes]);

  const zoomIn = useCallback(() => {
    setZoom((z) => Math.min(z * 1.15, 2.2));
  }, []);

  const zoomOut = useCallback(() => {
    setZoom((z) => Math.max(z / 1.15, 0.4));
  }, []);

  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setDraggedPositions({});
  }, []);

  const fitView = useCallback(() => {
    if (!containerRef.current || nodes.length === 0) return;
    const rect = containerRef.current.getBoundingClientRect();
    const allX = nodes.map((n) => (draggedPositions[n.id]?.x ?? n.position.x));
    const allY = nodes.map((n) => (draggedPositions[n.id]?.y ?? n.position.y));
    const minX = Math.min(...allX);
    const maxX = Math.max(...allX) + 200;
    const minY = Math.min(...allY);
    const maxY = Math.max(...allY) + 100;

    const graphWidth = maxX - minX || 400;
    const graphHeight = maxY - minY || 300;

    const scaleX = (rect.width - 80) / graphWidth;
    const scaleY = (rect.height - 80) / graphHeight;
    const newZoom = Math.min(Math.max(Math.min(scaleX, scaleY), 0.5), 1.3);

    const centerX = (minX + maxX) / 2;
    const centerY = (minY + maxY) / 2;

    setZoom(newZoom);
    setPan({
      x: rect.width / 2 - centerX * newZoom,
      y: rect.height / 2 - centerY * newZoom,
    });
  }, [nodes, draggedPositions]);

  // Canvas background mousedown (pan)
  const handleMouseDown = (e: React.MouseEvent) => {
    if (
      (e.target as HTMLElement).closest('.flowinger-node') ||
      (e.target as HTMLElement).closest('.flowinger-controls')
    ) {
      return;
    }
    isPanningRef.current = true;
    panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    setIsDragging(true);
  };

  // Node mousedown (drag)
  const handleNodeMouseDown = (e: React.MouseEvent, node: FlowingerNode) => {
    if (e.button !== 0) return; // left click only
    e.stopPropagation();
    const currentPos = draggedPositions[node.id] || node.position;
    dragNodeRef.current = {
      nodeId: node.id,
      startX: e.clientX,
      startY: e.clientY,
      origX: currentPos.x,
      origY: currentPos.y,
      hasMoved: false,
    };
    setActiveDragNodeId(node.id);
  };

  // Global mousemove and mouseup listeners attached to window for smooth drag & drop
  useEffect(() => {
    if (!activeDragNodeId && !isDragging) return;

    const onWindowMouseMove = (e: MouseEvent) => {
      // 1. Dragging a node
      if (dragNodeRef.current) {
        const dx = (e.clientX - dragNodeRef.current.startX) / zoom;
        const dy = (e.clientY - dragNodeRef.current.startY) / zoom;
        if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
          dragNodeRef.current.hasMoved = true;
        }
        const newX = Math.round(dragNodeRef.current.origX + dx);
        const newY = Math.round(dragNodeRef.current.origY + dy);
        setDraggedPositions((prev) => ({
          ...prev,
          [dragNodeRef.current!.nodeId]: { x: newX, y: newY },
        }));
        return;
      }

      // 2. Panning canvas
      if (isPanningRef.current) {
        setPan({
          x: e.clientX - panStartRef.current.x,
          y: e.clientY - panStartRef.current.y,
        });
      }
    };

    const onWindowMouseUp = (e: MouseEvent) => {
      if (dragNodeRef.current) {
        const { nodeId, hasMoved } = dragNodeRef.current;
        dragNodeRef.current = null;
        setActiveDragNodeId(null);
        if (!hasMoved) {
          // Pure click, select node
          setSelectedNodeId(nodeId);
          const node = nodeMap.get(nodeId);
          if (node) onNodeClick?.(e as unknown as React.MouseEvent, node);
        }
      }
      isPanningRef.current = false;
      setIsDragging(false);
    };

    window.addEventListener('mousemove', onWindowMouseMove);
    window.addEventListener('mouseup', onWindowMouseUp);
    return () => {
      window.removeEventListener('mousemove', onWindowMouseMove);
      window.removeEventListener('mouseup', onWindowMouseUp);
    };
  }, [activeDragNodeId, isDragging, zoom, nodeMap, onNodeClick]);

  // Smooth, reduced sensitivity zoom (clamped delta + damped exponential response)
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const clampedDelta = Math.max(Math.min(e.deltaY, 40), -40);
    const zoomFactor = Math.exp(-clampedDelta * 0.001);
    setZoom((z) => Math.min(Math.max(z * zoomFactor, 0.4), 2.2));
  };

  // Precompute curved edge geometry and styles
  const computedEdges = useMemo<ComputedEdge[]>(() => {
    const list: ComputedEdge[] = [];
    edges.forEach((edge, edgeIndex) => {
      const srcId = String(edge.source || '').trim();
      const tgtId = String(edge.target || '').trim();
      const srcNode = nodeMap.get(srcId) || nodeMap.get(srcId.toLowerCase());
      const tgtNode = nodeMap.get(tgtId) || nodeMap.get(tgtId.toLowerCase());
      if (!srcNode || !tgtNode) return;

      const srcPos = draggedPositions[srcNode.id] || srcNode.position;
      const tgtPos = draggedPositions[tgtNode.id] || tgtNode.position;

      // Approximate center of node cards (190px width x 80px height)
      const srcX = srcPos.x + 95;
      const srcY = srcPos.y + 40;
      const tgtX = tgtPos.x + 95;
      const tgtY = tgtPos.y + 40;

      const dx = tgtX - srcX;
      const dy = tgtY - srcY;
      const len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len;
      const ny = dx / len;

      // Curve offset to prevent overlapping edge lines
      const curveMagnitude = ((edgeIndex % 3) - 1) * 26;
      const cx1 = srcX + dx * 0.35 + nx * curveMagnitude;
      const cy1 = srcY + dy * 0.35 + ny * curveMagnitude;
      const cx2 = srcX + dx * 0.65 + nx * curveMagnitude;
      const cy2 = srcY + dy * 0.65 + ny * curveMagnitude;

      const midX = (srcX + tgtX) / 2 + nx * (curveMagnitude * 0.7);
      const midY = (srcY + tgtY) / 2 + ny * (curveMagnitude * 0.7);

      const pathData = `M ${srcX} ${srcY} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${tgtX} ${tgtY}`;

      const isDown = edge.data?.status === 'down';
      const isAlternate = !!edge.data?.isAlternate;
      const isDegraded = edge.data?.status === 'degraded';

      const strokeColor =
        (edge.style?.stroke as string) ||
        (isDown
          ? '#ef4444'
          : isAlternate
          ? '#38bdf8'
          : isDegraded
          ? '#f59e0b'
          : '#10b981');

      const isAnimated = !!((edge.animated || edge.data?.animated) && !isDown);

      const labelStr = edge.label ? String(edge.label) : '';
      const badgeWidth = Math.max(56, labelStr.length * 8.5 + 20);
      const badgeHalf = badgeWidth / 2;

      const badgeFill = isDown
        ? '#220808'
        : isAlternate
        ? '#042230'
        : isDegraded
        ? '#241403'
        : '#061a12';

      const labelTextColor = isDown
        ? '#fca5a5'
        : isAlternate
        ? '#7dd3fc'
        : isDegraded
        ? '#fcd34d'
        : '#6ee7b7';

      list.push({
        edge,
        pathData,
        strokeColor,
        isDown,
        isAlternate,
        isAnimated,
        midX,
        midY,
        labelStr,
        badgeWidth,
        badgeHalf,
        badgeFill,
        labelTextColor,
      });
    });
    return list;
  }, [edges, nodeMap, draggedPositions]);

  return (
    <FlowingerContext.Provider value={{ zoom, pan, zoomIn, zoomOut, resetView, fitView }}>
      <div
        ref={containerRef}
        className={`relative w-full h-full overflow-hidden select-none bg-gray-950 ${
          activeDragNodeId
            ? 'cursor-grabbing'
            : isDragging
            ? 'cursor-grabbing'
            : 'cursor-grab'
        } ${className}`}
        style={style}
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
      >
        {children}

        {/* Scaled/Panned Graph Layer */}
        <div
          className="absolute inset-0 origin-top-left"
          style={{
            transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
            willChange: 'transform',
          }}
        >
          {/* SVG Edges Layer */}
          <svg className="absolute inset-0 w-[5000px] h-[5000px] pointer-events-none overflow-visible">
            <defs>
              <filter id="badge-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#000000" floodOpacity="0.8" />
              </filter>
              <marker
                id="arrowhead-up"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <polygon points="0 1, 8 4, 0 7" fill="#10b981" />
              </marker>
              <marker
                id="arrowhead-down"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <polygon points="0 1, 8 4, 0 7" fill="#ef4444" />
              </marker>
              <marker
                id="arrowhead-degraded"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <polygon points="0 1, 8 4, 0 7" fill="#f59e0b" />
              </marker>
              <marker
                id="arrowhead-alternate"
                markerWidth="8"
                markerHeight="8"
                refX="7"
                refY="4"
                orient="auto"
              >
                <polygon points="0 1, 8 4, 0 7" fill="#38bdf8" />
              </marker>
            </defs>

            {/* Layer 1: Edge Path Lines */}
            <g className="flowinger-edge-paths">
              {computedEdges.map((item) => {
                if (!item) return null;
                const { edge, pathData, strokeColor, isAlternate, isDown, isAnimated } = item;
                return (
                  <g key={`path-${edge.id}`}>
                    <path
                      d={pathData}
                      fill="none"
                      stroke="#020617"
                      strokeWidth={isAlternate ? 8 : isDown ? 6 : 5}
                      opacity="0.9"
                    />
                    <path
                      d={pathData}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={isAlternate ? 4 : isDown ? 3 : 2.5}
                      strokeDasharray={isDown ? '8 6' : isAnimated ? '6 4' : undefined}
                      className={isAnimated ? 'animate-[dash_1s_linear_infinite]' : ''}
                      opacity={1}
                    />
                  </g>
                );
              })}
            </g>

            {/* Layer 2: Edge Label Badges (Rendered over paths so no line cuts through them) */}
            <g className="flowinger-edge-labels">
              {computedEdges.map((item) => {
                if (!item || !item.labelStr) return null;
                const {
                  edge,
                  midX,
                  midY,
                  labelStr,
                  badgeWidth,
                  badgeHalf,
                  strokeColor,
                  isDown,
                  isAlternate,
                  badgeFill,
                  labelTextColor,
                } = item;
                return (
                  <g
                    key={`label-${edge.id}`}
                    transform={`translate(${midX}, ${midY})`}
                    className="pointer-events-none select-none"
                  >
                    <rect
                      x={-badgeHalf}
                      y="-11"
                      width={badgeWidth}
                      height="22"
                      rx="6"
                      fill={badgeFill}
                      stroke={strokeColor}
                      strokeWidth={isDown || isAlternate ? '2' : '1.5'}
                      strokeOpacity="0.95"
                      filter="url(#badge-shadow)"
                    />
                    <text
                      x="0"
                      y="0"
                      dominantBaseline="central"
                      textAnchor="middle"
                      fill={labelTextColor}
                      fontSize="11"
                      fontFamily="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
                      fontWeight="700"
                      letterSpacing="0.02em"
                    >
                      {labelStr}
                    </text>
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Nodes Layer */}
          {nodes.map((node) => {
            const CustomComponent = node.type && nodeTypes ? nodeTypes[node.type] : null;
            const isSelected = selectedNodeId === node.id;
            const isBeingDragged = activeDragNodeId === node.id;
            const pos = draggedPositions[node.id] || node.position;

            return (
              <div
                key={node.id}
                className={`flowinger-node absolute select-none ${
                  isBeingDragged
                    ? 'z-50 cursor-grabbing shadow-2xl scale-[1.02]'
                    : isSelected
                    ? 'z-30 cursor-grab ring-2 ring-blue-500/50'
                    : 'z-10 cursor-grab hover:z-20'
                } ${node.className || ''}`}
                style={{
                  transform: `translate(${pos.x}px, ${pos.y}px)`,
                  ...node.style,
                }}
                onMouseDown={(e) => handleNodeMouseDown(e, node)}
              >
                {CustomComponent ? (
                  <CustomComponent id={node.id} data={node.data} selected={isSelected} />
                ) : (
                  <div
                    className={`px-4 py-2.5 rounded-xl border shadow-lg backdrop-blur bg-gray-900/90 text-sm font-medium ${
                      isSelected
                        ? 'border-blue-500 ring-2 ring-blue-500/30'
                        : 'border-gray-700 hover:border-gray-500'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-3 h-3 rounded-full ${
                          node.data?.status === 'down'
                            ? 'bg-red-500'
                            : node.data?.status === 'degraded'
                            ? 'bg-amber-500'
                            : 'bg-emerald-500'
                        }`}
                      />
                      <span className="text-gray-200">{node.data?.label || node.id}</span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </FlowingerContext.Provider>
  );
};

export const Background: React.FC<{
  color?: string;
  gap?: number;
  size?: number;
}> = ({ color = '#334155', gap = 24, size = 1 }) => {
  return (
    <div
      className="absolute inset-0 pointer-events-none opacity-20"
      style={{
        backgroundImage: `radial-gradient(${color} ${size}px, transparent ${size}px)`,
        backgroundSize: `${gap}px ${gap}px`,
      }}
    />
  );
};

export const Controls: React.FC<{
  className?: string;
  showZoom?: boolean;
  showFit?: boolean;
  showReset?: boolean;
}> = ({ className = '', showZoom = true, showFit = true, showReset = true }) => {
  const context = useContext(FlowingerContext);
  if (!context) return null;

  return (
    <div
      className={`flowinger-controls absolute bottom-4 left-4 z-20 flex flex-col gap-1.5 bg-gray-900/90 border border-gray-700/80 p-1.5 rounded-lg shadow-xl backdrop-blur ${className}`}
    >
      {showZoom && (
        <>
          <button
            onClick={context.zoomIn}
            title="Zoom In"
            className="w-8 h-8 flex items-center justify-center text-gray-300 hover:text-white hover:bg-gray-800 rounded transition-colors text-lg font-bold"
          >
            +
          </button>
          <button
            onClick={context.zoomOut}
            title="Zoom Out"
            className="w-8 h-8 flex items-center justify-center text-gray-300 hover:text-white hover:bg-gray-800 rounded transition-colors text-lg font-bold"
          >
            −
          </button>
        </>
      )}
      {showFit && (
        <button
          onClick={context.fitView}
          title="Fit View"
          className="w-8 h-8 flex items-center justify-center text-gray-300 hover:text-white hover:bg-gray-800 rounded transition-colors text-xs font-semibold"
        >
          [ ]
        </button>
      )}
      {showReset && (
        <button
          onClick={context.resetView}
          title="Reset View"
          className="w-8 h-8 flex items-center justify-center text-gray-300 hover:text-white hover:bg-gray-800 rounded transition-colors text-xs font-semibold"
        >
          1:1
        </button>
      )}
    </div>
  );
};

export const VERSION = '1.0.0-rc.1';

export const useFlowinger = () => {
  const context = useContext(FlowingerContext);
  if (!context) {
    throw new Error('useFlowinger must be used within a Flowinger provider');
  }
  return context;
};

export default Flowinger;
