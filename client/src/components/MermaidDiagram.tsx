import { useEffect, useRef, useState, useCallback } from "react";
import mermaid from "mermaid";
import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, Maximize2, RotateCcw } from "lucide-react";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

mermaid.initialize({
  startOnLoad: false,
  theme: "base",
  securityLevel: "strict",
  themeVariables: {
    primaryColor: "#3b82f6",
    primaryTextColor: "#ffffff",
    primaryBorderColor: "#2563eb",
    lineColor: "#64748b",
    secondaryColor: "#f1f5f9",
    tertiaryColor: "#e2e8f0",
    background: "#ffffff",
    mainBkg: "#f8fafc",
    nodeBorder: "#cbd5e1",
    clusterBkg: "#f1f5f9",
    clusterBorder: "#e2e8f0",
    titleColor: "#1e293b",
    edgeLabelBackground: "#ffffff",
  },
  flowchart: {
    useMaxWidth: false,
    htmlLabels: false,
    curve: "basis",
    padding: 20,
    nodeSpacing: 50,
    rankSpacing: 60,
  },
});

export function MermaidDiagram({ chart, className = "" }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const renderDiagram = async () => {
      if (!chart) return;

      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        setSvg(renderedSvg);
        setError(null);
        setZoom(1);
        setPosition({ x: 0, y: 0 });
      } catch (err) {
        console.error("Mermaid rendering error:", err);
        setError("Failed to render diagram");
      }
    };

    renderDiagram();
  }, [chart]);

  const handleZoomIn = useCallback(() => {
    setZoom((prev) => Math.min(prev + 0.25, 3));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((prev) => Math.max(prev - 0.25, 0.25));
  }, []);

  const handleReset = useCallback(() => {
    setZoom(1);
    setPosition({ x: 0, y: 0 });
  }, []);

  const handleFitToView = useCallback(() => {
    if (containerRef.current && viewportRef.current) {
      const content = containerRef.current.querySelector("svg");
      if (content) {
        const viewportWidth = viewportRef.current.clientWidth;
        const viewportHeight = viewportRef.current.clientHeight;
        const contentWidth = content.getBoundingClientRect().width / zoom;
        const contentHeight = content.getBoundingClientRect().height / zoom;
        
        const scaleX = (viewportWidth - 40) / contentWidth;
        const scaleY = (viewportHeight - 40) / contentHeight;
        const newZoom = Math.min(scaleX, scaleY, 1.5);
        
        setZoom(Math.max(0.25, newZoom));
        setPosition({ x: 0, y: 0 });
      }
    }
  }, [zoom]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    }
  }, [position]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging) {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.1 : 0.1;
      setZoom((prev) => Math.min(Math.max(prev + delta, 0.25), 3));
    }
  }, []);

  if (error) {
    return (
      <div className={`p-4 bg-destructive/10 text-destructive rounded-lg border border-destructive/20 ${className}`}>
        <p className="text-sm font-medium">Failed to render diagram</p>
        <p className="text-xs text-muted-foreground mt-1">Try clicking "Regenerate" to create a new diagram</p>
        <details className="mt-3">
          <summary className="text-xs cursor-pointer hover:text-destructive/80">View raw diagram code</summary>
          <pre className="mt-2 text-xs overflow-auto bg-muted p-3 rounded-md max-h-[200px]">{chart}</pre>
        </details>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1 bg-background/95 backdrop-blur-sm rounded-lg border shadow-sm p-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleZoomOut}
          disabled={zoom <= 0.25}
          title="Zoom out"
          data-testid="button-zoom-out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <span className="text-xs font-medium text-muted-foreground min-w-[3rem] text-center">
          {Math.round(zoom * 100)}%
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleZoomIn}
          disabled={zoom >= 3}
          title="Zoom in"
          data-testid="button-zoom-in"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <div className="w-px h-4 bg-border mx-1" />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleFitToView}
          title="Fit to view"
          data-testid="button-fit-view"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={handleReset}
          title="Reset view"
          data-testid="button-reset-view"
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
      </div>

      <div
        ref={viewportRef}
        className="overflow-hidden rounded-lg border bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900 dark:to-slate-800 cursor-grab active:cursor-grabbing"
        style={{ minHeight: "450px" }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        data-testid="mermaid-viewport"
      >
        <div
          ref={containerRef}
          className="p-8 transition-transform duration-100 ease-out"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
            transformOrigin: "center center",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
          data-testid="mermaid-diagram"
        />
      </div>

      <p className="text-xs text-muted-foreground mt-2 text-center">
        Drag to pan. Use Ctrl/Cmd + scroll to zoom.
      </p>
    </div>
  );
}
