import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, RotateCcw, Download, Maximize2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

mermaid.initialize({
  startOnLoad: false,
  theme: "base",
  securityLevel: "strict",
  themeVariables: {
    primaryColor: "#0366D6",
    primaryTextColor: "#ffffff",
    primaryBorderColor: "#0256b9",
    secondaryColor: "#f6f8fa",
    secondaryTextColor: "#24292f",
    secondaryBorderColor: "#d0d7de",
    tertiaryColor: "#ddf4ff",
    tertiaryTextColor: "#0969da",
    tertiaryBorderColor: "#54aeff",
    lineColor: "#57606a",
    textColor: "#24292f",
    mainBkg: "#ffffff",
    nodeBorder: "#d0d7de",
    clusterBkg: "#f6f8fa",
    clusterBorder: "#d0d7de",
    titleColor: "#24292f",
    edgeLabelBackground: "#ffffff",
    nodeTextColor: "#24292f",
  },
  flowchart: {
    useMaxWidth: false,
    htmlLabels: true,
    curve: "basis",
    padding: 20,
    nodeSpacing: 50,
    rankSpacing: 80,
    diagramPadding: 20,
  },
});

export function MermaidDiagram({ chart, className = "" }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgContainerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const renderDiagram = async () => {
      if (!containerRef.current || !chart) return;

      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        
        const styledSvg = renderedSvg
          .replace(/<svg /, '<svg style="max-width: none; height: auto;" ')
          .replace(/class="node default/g, 'class="node default professional-node');
        
        setSvg(styledSvg);
        setError(null);
      } catch (err) {
        console.error("Mermaid rendering error:", err);
        setError("Failed to render diagram. The diagram syntax may need regeneration.");
      }
    };

    renderDiagram();
  }, [chart]);

  const handleZoomIn = () => {
    setZoom((prev) => Math.min(prev + 0.25, 3));
  };

  const handleZoomOut = () => {
    setZoom((prev) => Math.max(prev - 0.25, 0.25));
  };

  const handleReset = () => {
    setZoom(1);
  };

  const handleDownload = () => {
    if (!svg) return;
    
    const blob = new Blob([svg], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "business-flow-diagram.svg";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleFullscreen = () => {
    if (!svgContainerRef.current) return;
    
    if (!isFullscreen) {
      if (svgContainerRef.current.requestFullscreen) {
        svgContainerRef.current.requestFullscreen();
      }
    } else {
      if (document.exitFullscreen) {
        document.exitFullscreen();
      }
    }
    setIsFullscreen(!isFullscreen);
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  if (error) {
    return (
      <div className={cn("rounded-lg border border-destructive/30 bg-destructive/5 p-6", className)}>
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center">
            <span className="text-destructive text-xl">!</span>
          </div>
          <div>
            <p className="font-medium text-destructive">{error}</p>
            <p className="text-sm text-muted-foreground mt-1">
              Click the "Regenerate" button above to create a new diagram.
            </p>
          </div>
          <details className="w-full mt-4">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
              View diagram source
            </summary>
            <pre className="mt-2 text-xs overflow-auto bg-muted p-3 rounded-md text-left max-h-40">
              {chart}
            </pre>
          </details>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={handleZoomOut}
            disabled={zoom <= 0.25}
            data-testid="button-zoom-out"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <div className="px-3 py-1.5 text-sm font-medium bg-muted rounded-md min-w-[60px] text-center">
            {Math.round(zoom * 100)}%
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={handleZoomIn}
            disabled={zoom >= 3}
            data-testid="button-zoom-in"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            data-testid="button-zoom-reset"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={handleFullscreen}
            data-testid="button-fullscreen"
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDownload}
            data-testid="button-download-diagram"
          >
            <Download className="h-4 w-4 mr-1" />
            SVG
          </Button>
        </div>
      </div>

      <div
        ref={svgContainerRef}
        className={cn(
          "relative rounded-lg border bg-white dark:bg-slate-900 overflow-auto",
          "shadow-sm",
          isFullscreen && "fixed inset-0 z-50 rounded-none"
        )}
        style={{ minHeight: "400px" }}
      >
        <div
          ref={containerRef}
          className="p-8 transition-transform duration-200 origin-top-left"
          style={{
            transform: `scale(${zoom})`,
            minWidth: "fit-content",
          }}
          dangerouslySetInnerHTML={{ __html: svg }}
          data-testid="mermaid-diagram"
        />
      </div>

      <div className="flex items-center justify-center gap-6 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-sm bg-primary" />
          <span>Primary Process</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-sm bg-secondary border" />
          <span>Sub-process</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full border-2 border-primary" />
          <span>Decision Point</span>
        </div>
      </div>
    </div>
  );
}
