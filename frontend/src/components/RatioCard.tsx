import type { RatioResult } from "../api/types";

interface Props {
  ratio: RatioResult;
}

/**
 * Card for a single ratio result.
 *
 * When status is "ok": shows value + unit.
 * When status is "unavailable" or "undefined": shows "N/A" with a clear
 * explanation of which inputs are missing — never a blank or wrong number.
 */
export default function RatioCard({ ratio }: Props) {
  const isOk = ratio.status === "ok";

  return (
    <div className={`ratio-card status-${ratio.status}`}>
      <div className="ratio-name">{ratio.name}</div>

      {isOk && ratio.value != null ? (
        <div className="ratio-value">
          {formatRatioValue(ratio.value, ratio.unit)}
          {ratio.unit && ratio.unit !== "x" && ratio.unit !== "%" && (
            <span className="ratio-unit"> {ratio.unit}</span>
          )}
          {(ratio.unit === "%" || ratio.unit === "x") && (
            <span className="ratio-unit">{ratio.unit}</span>
          )}
        </div>
      ) : (
        <div className="ratio-na">N/A</div>
      )}

      {!isOk && ratio.missing_inputs.length > 0 && (
        <div className="ratio-missing">
          Missing: {ratio.missing_inputs.join(", ")}
        </div>
      )}

      {ratio.detail && <div className="ratio-detail">{ratio.detail}</div>}
    </div>
  );
}

/**
 * Format a ratio value for display. Percentages get 1 dp; multipliers and
 * dimensionless ratios get 2 dp; large currency values get commas.
 */
export function formatRatioValue(value: number, unit: string): string {
  if (unit === "%") return value.toFixed(1);
  if (unit === "x") return value.toFixed(2);
  // Large monetary values
  if (Math.abs(value) >= 1_000_000) {
    return (value / 1_000_000).toFixed(2) + "M";
  }
  if (Math.abs(value) >= 1_000) {
    return (value / 1_000).toFixed(1) + "K";
  }
  // Plain ratio / days
  return value.toFixed(2);
}
