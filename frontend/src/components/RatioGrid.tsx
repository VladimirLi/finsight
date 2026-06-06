import type { RatioResult } from "../api/types";
import RatioCard from "./RatioCard";

interface Props {
  results: RatioResult[];
}

/**
 * Renders all ratio results grouped by their "category" field.
 * Unavailable ratios are shown with clear N/A treatment inside RatioCard.
 */
export default function RatioGrid({ results }: Props) {
  if (results.length === 0) {
    return (
      <div className="empty-state">
        <div className="empty-state-icon">&#x1F4CA;</div>
        <div className="empty-state-title">No ratios computed</div>
        <p>Complete the data review to generate ratio analysis.</p>
      </div>
    );
  }

  // Group by category, preserving insertion order (server sends a stable list)
  const grouped = new Map<string, RatioResult[]>();
  for (const r of results) {
    let group = grouped.get(r.category);
    if (!group) {
      group = [];
      grouped.set(r.category, group);
    }
    group.push(r);
  }

  return (
    <div>
      {Array.from(grouped.entries()).map(([category, ratios]) => (
        <section key={category}>
          <div className="ratio-category-header">{category}</div>
          <div className="ratio-grid">
            {ratios.map((r) => (
              <RatioCard key={r.key} ratio={r} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
