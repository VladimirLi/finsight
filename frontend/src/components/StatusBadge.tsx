import type { DocStatus } from "../api/types";

const LABELS: Record<DocStatus, string> = {
  uploaded: "Uploaded",
  parsing: "Parsing",
  extracting: "Extracting",
  needs_review: "Needs Review",
  ready: "Ready",
  failed: "Failed",
};

interface Props {
  status: DocStatus;
}

/**
 * Pill badge for document pipeline status.
 */
export default function StatusBadge({ status }: Props) {
  return (
    <span className={`badge badge-${status}`}>
      <span className={`badge-dot badge-dot-${status}`} />
      {LABELS[status]}
    </span>
  );
}
