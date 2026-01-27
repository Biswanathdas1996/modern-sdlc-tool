import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

interface MermaidDiagramProps {
  chart: string;
  className?: string;
}

mermaid.initialize({
  startOnLoad: false,
  theme: "default",
  securityLevel: "loose",
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
    curve: "basis",
  },
});

export function MermaidDiagram({ chart, className = "" }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const renderDiagram = async () => {
      if (!containerRef.current || !chart) return;

      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        setSvg(renderedSvg);
        setError(null);
      } catch (err) {
        console.error("Mermaid rendering error:", err);
        setError("Failed to render diagram");
      }
    };

    renderDiagram();
  }, [chart]);

  if (error) {
    return (
      <div className={`p-4 bg-destructive/10 text-destructive rounded-md ${className}`}>
        <p className="text-sm">{error}</p>
        <pre className="mt-2 text-xs overflow-auto bg-muted p-2 rounded">{chart}</pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`overflow-auto ${className}`}
      dangerouslySetInnerHTML={{ __html: svg }}
      data-testid="mermaid-diagram"
    />
  );
}
