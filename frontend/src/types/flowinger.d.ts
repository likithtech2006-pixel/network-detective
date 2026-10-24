declare module 'flowinger' {
  import React from 'react';

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

  export interface FlowingerProps {
    nodes: FlowingerNode[];
    edges: FlowingerEdge[];
    onNodeClick?: (event: React.MouseEvent, node: FlowingerNode) => void;
    nodeTypes?: Record<string, React.ComponentType<{ id: string; data: any; selected?: boolean }>>;
    children?: React.ReactNode;
    className?: string;
    style?: React.CSSProperties;
  }

  export const Flowinger: React.FC<FlowingerProps>;
  export const Background: React.FC<{ color?: string; gap?: number; size?: number }>;
  export const Controls: React.FC<{
    className?: string;
    showZoom?: boolean;
    showFit?: boolean;
    showReset?: boolean;
  }>;

  export default Flowinger;
}
