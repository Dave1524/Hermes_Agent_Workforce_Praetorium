import type { RunArtifact } from "@/model/run";

const isHttp = (uri: string) => uri.startsWith("https://") || uri.startsWith("http://");

export default function ArtifactLink({ artifact }: { artifact: RunArtifact | null }) {
  if (!artifact) return <span className="text-muted text-xs">—</span>;
  const label = artifact.title ?? artifact.uri ?? artifact.kind ?? "artifact";
  if (artifact.uri && isHttp(artifact.uri)) {
    return (
      <a href={artifact.uri} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
        {label}
      </a>
    );
  }
  return <span title={artifact.uri ?? undefined}>{label}</span>;
}
