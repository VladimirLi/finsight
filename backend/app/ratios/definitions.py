"""Declarative catalogue of financial ratios.

Every entry is a :class:`~app.ratios.base.RatioDefinition`: a key, a human name, a
category, the *exact* canonical line-item keys it requires, and a pure ``compute``
function. The engine (``app.ratios.engine``) screens for missing inputs and zero
denominators BEFORE calling ``compute``, so each formula here can assume all of its
inputs are present and just do the arithmetic. This keeps every formula a trivially
auditable one-liner — the deterministic heart of finsight.

Conventions
-----------
* ``unit`` is one of "ratio" | "percent" | "days" | "currency" | "x".
* Percentage ratios multiply by 100 here so the value is already on a 0..100 scale
  (e.g. a 25% net margin returns ``25.0``, not ``0.25``).
* ``higher_is_better`` is set only where the direction is unambiguous; metrics like
  days-outstanding (lower is better) are marked ``False`` and left ``None`` when the
  interpretation depends on context.

Sign conventions for cash-flow items (documented because they affect the formulas)
----------------------------------------------------------------------------------
* ``capital_expenditures`` is stored AS REPORTED on the cash-flow statement, which is
  conventionally NEGATIVE (a use of cash). Free Cash Flow is therefore
  ``operating_cash_flow + capital_expenditures`` (adding a negative number), NOT a
  subtraction. ``capex_to_revenue`` reports the magnitude (absolute value) so the
  ratio reads as a positive intensity figure.

Return on Invested Capital (ROIC) note
--------------------------------------
A textbook ROIC uses NOPAT = operating_income * (1 - tax_rate). Because a reliable
effective tax rate is frequently unavailable from a single statement, this catalogue
defines ROIC pragmatically as ``operating_income / (long_term_debt + total_equity)``
(pre-tax return on invested capital). This keeps the required inputs minimal and the
result deterministic; it is documented as a pre-tax approximation in the description.
"""

from __future__ import annotations

from app.ratios.base import RatioCategory, RatioDefinition

# ---------------------------------------------------------------------------
# Liquidity
# ---------------------------------------------------------------------------

_LIQUIDITY = [
    RatioDefinition(
        key="current_ratio",
        name="Current Ratio",
        category=RatioCategory.liquidity,
        inputs=["total_current_assets", "total_current_liabilities"],
        compute=lambda f: f["total_current_assets"] / f["total_current_liabilities"],
        unit="ratio",
        higher_is_better=True,
        description="Current assets divided by current liabilities; ability to cover short-term obligations.",
    ),
    RatioDefinition(
        key="quick_ratio",
        name="Quick Ratio (Acid Test)",
        category=RatioCategory.liquidity,
        inputs=[
            "cash_and_equivalents",
            "short_term_investments",
            "accounts_receivable",
            "total_current_liabilities",
        ],
        compute=lambda f: (
            (f["cash_and_equivalents"] + f["short_term_investments"] + f["accounts_receivable"])
            / f["total_current_liabilities"]
        ),
        unit="ratio",
        higher_is_better=True,
        description="(Cash + short-term investments + receivables) / current liabilities; liquidity excluding inventory.",
    ),
    RatioDefinition(
        key="cash_ratio",
        name="Cash Ratio",
        category=RatioCategory.liquidity,
        inputs=[
            "cash_and_equivalents",
            "short_term_investments",
            "total_current_liabilities",
        ],
        compute=lambda f: (
            (f["cash_and_equivalents"] + f["short_term_investments"])
            / f["total_current_liabilities"]
        ),
        unit="ratio",
        higher_is_better=True,
        description="(Cash + short-term investments) / current liabilities; most conservative liquidity measure.",
    ),
    RatioDefinition(
        key="working_capital",
        name="Working Capital",
        category=RatioCategory.liquidity,
        inputs=["total_current_assets", "total_current_liabilities"],
        compute=lambda f: f["total_current_assets"] - f["total_current_liabilities"],
        unit="currency",
        higher_is_better=True,
        description="Current assets minus current liabilities; absolute short-term financial cushion.",
    ),
]

# ---------------------------------------------------------------------------
# Leverage / solvency
# ---------------------------------------------------------------------------

_LEVERAGE = [
    RatioDefinition(
        key="debt_to_equity",
        name="Debt-to-Equity",
        category=RatioCategory.leverage,
        inputs=["total_liabilities", "total_equity"],
        compute=lambda f: f["total_liabilities"] / f["total_equity"],
        unit="ratio",
        higher_is_better=False,
        description="Total liabilities / total shareholders' equity; overall financial leverage.",
    ),
    RatioDefinition(
        key="debt_ratio",
        name="Debt Ratio",
        category=RatioCategory.leverage,
        inputs=["total_liabilities", "total_assets"],
        compute=lambda f: f["total_liabilities"] / f["total_assets"],
        unit="ratio",
        higher_is_better=False,
        description="Total liabilities / total assets; share of assets financed by debt.",
    ),
    RatioDefinition(
        key="equity_ratio",
        name="Equity Ratio",
        category=RatioCategory.leverage,
        inputs=["total_equity", "total_assets"],
        compute=lambda f: f["total_equity"] / f["total_assets"],
        unit="ratio",
        higher_is_better=True,
        description="Total equity / total assets; share of assets financed by owners.",
    ),
    RatioDefinition(
        key="long_term_debt_to_equity",
        name="Long-Term Debt-to-Equity",
        category=RatioCategory.leverage,
        inputs=["long_term_debt", "total_equity"],
        compute=lambda f: f["long_term_debt"] / f["total_equity"],
        unit="ratio",
        higher_is_better=False,
        description="Long-term debt / total equity; long-horizon capital-structure leverage.",
    ),
    RatioDefinition(
        key="interest_coverage",
        name="Interest Coverage",
        category=RatioCategory.leverage,
        inputs=["operating_income", "interest_expense"],
        compute=lambda f: f["operating_income"] / f["interest_expense"],
        unit="x",
        higher_is_better=True,
        description="Operating income (EBIT) / interest expense; how many times earnings cover interest.",
    ),
]

# ---------------------------------------------------------------------------
# Profitability (percent, scaled to 0..100)
# ---------------------------------------------------------------------------

_PROFITABILITY = [
    RatioDefinition(
        key="gross_margin",
        name="Gross Margin",
        category=RatioCategory.profitability,
        inputs=["gross_profit", "revenue"],
        compute=lambda f: f["gross_profit"] / f["revenue"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="Gross profit as a percentage of revenue.",
    ),
    RatioDefinition(
        key="operating_margin",
        name="Operating Margin",
        category=RatioCategory.profitability,
        inputs=["operating_income", "revenue"],
        compute=lambda f: f["operating_income"] / f["revenue"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="Operating income (EBIT) as a percentage of revenue.",
    ),
    RatioDefinition(
        key="net_margin",
        name="Net Profit Margin",
        category=RatioCategory.profitability,
        inputs=["net_income", "revenue"],
        compute=lambda f: f["net_income"] / f["revenue"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="Net income as a percentage of revenue.",
    ),
    RatioDefinition(
        key="return_on_assets",
        name="Return on Assets (ROA)",
        category=RatioCategory.profitability,
        inputs=["net_income", "total_assets"],
        compute=lambda f: f["net_income"] / f["total_assets"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="Net income as a percentage of total assets; how efficiently assets generate profit.",
    ),
    RatioDefinition(
        key="return_on_equity",
        name="Return on Equity (ROE)",
        category=RatioCategory.profitability,
        inputs=["net_income", "total_equity"],
        compute=lambda f: f["net_income"] / f["total_equity"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="Net income as a percentage of shareholders' equity.",
    ),
    RatioDefinition(
        key="return_on_invested_capital",
        name="Return on Invested Capital (ROIC, pre-tax approx.)",
        category=RatioCategory.profitability,
        inputs=["operating_income", "long_term_debt", "total_equity"],
        compute=lambda f: f["operating_income"] / (f["long_term_debt"] + f["total_equity"]) * 100.0,
        unit="percent",
        higher_is_better=True,
        description=(
            "Operating income / (long-term debt + equity), as a percentage. Pre-tax "
            "approximation of ROIC: a reliable effective tax rate is rarely available "
            "from a single statement, so NOPAT is not used."
        ),
    ),
    RatioDefinition(
        key="ebitda_margin",
        name="EBITDA Margin",
        category=RatioCategory.profitability,
        inputs=["ebitda", "revenue"],
        compute=lambda f: f["ebitda"] / f["revenue"] * 100.0,
        unit="percent",
        higher_is_better=True,
        description="EBITDA as a percentage of revenue.",
    ),
]

# ---------------------------------------------------------------------------
# Efficiency / activity
# ---------------------------------------------------------------------------

_EFFICIENCY = [
    RatioDefinition(
        key="asset_turnover",
        name="Asset Turnover",
        category=RatioCategory.efficiency,
        inputs=["revenue", "total_assets"],
        compute=lambda f: f["revenue"] / f["total_assets"],
        unit="x",
        higher_is_better=True,
        description="Revenue / total assets; revenue generated per unit of assets.",
    ),
    RatioDefinition(
        key="inventory_turnover",
        name="Inventory Turnover",
        category=RatioCategory.efficiency,
        inputs=["cost_of_goods_sold", "inventory"],
        compute=lambda f: f["cost_of_goods_sold"] / f["inventory"],
        unit="x",
        higher_is_better=True,
        description="COGS / inventory; how many times inventory is sold and replaced.",
    ),
    RatioDefinition(
        key="receivables_turnover",
        name="Receivables Turnover",
        category=RatioCategory.efficiency,
        inputs=["revenue", "accounts_receivable"],
        compute=lambda f: f["revenue"] / f["accounts_receivable"],
        unit="x",
        higher_is_better=True,
        description="Revenue / accounts receivable; how quickly credit sales are collected.",
    ),
    RatioDefinition(
        key="days_sales_outstanding",
        name="Days Sales Outstanding (DSO)",
        category=RatioCategory.efficiency,
        inputs=["revenue", "accounts_receivable"],
        compute=lambda f: 365.0 / (f["revenue"] / f["accounts_receivable"]),
        unit="days",
        higher_is_better=False,
        description="365 / receivables turnover; average days to collect receivables.",
    ),
    RatioDefinition(
        key="days_inventory_outstanding",
        name="Days Inventory Outstanding (DIO)",
        category=RatioCategory.efficiency,
        inputs=["cost_of_goods_sold", "inventory"],
        compute=lambda f: 365.0 / (f["cost_of_goods_sold"] / f["inventory"]),
        unit="days",
        higher_is_better=False,
        description="365 / inventory turnover; average days inventory is held before sale.",
    ),
]

# ---------------------------------------------------------------------------
# Cash flow
# ---------------------------------------------------------------------------

_CASH_FLOW = [
    RatioDefinition(
        key="operating_cash_flow_ratio",
        name="Operating Cash Flow Ratio",
        category=RatioCategory.cash_flow,
        inputs=["operating_cash_flow", "total_current_liabilities"],
        compute=lambda f: f["operating_cash_flow"] / f["total_current_liabilities"],
        unit="ratio",
        higher_is_better=True,
        description="Operating cash flow / current liabilities; cash-based short-term coverage.",
    ),
    RatioDefinition(
        key="free_cash_flow",
        name="Free Cash Flow",
        category=RatioCategory.cash_flow,
        inputs=["operating_cash_flow", "capital_expenditures"],
        # capital_expenditures is stored as reported (negative), so we ADD it.
        compute=lambda f: f["operating_cash_flow"] + f["capital_expenditures"],
        unit="currency",
        higher_is_better=True,
        description=(
            "Operating cash flow plus capital expenditures. Capex is stored as reported "
            "(conventionally negative), so it is added rather than subtracted."
        ),
    ),
    RatioDefinition(
        key="fcf_margin",
        name="Free Cash Flow Margin",
        category=RatioCategory.cash_flow,
        inputs=["operating_cash_flow", "capital_expenditures", "revenue"],
        compute=lambda f: (
            (f["operating_cash_flow"] + f["capital_expenditures"]) / f["revenue"] * 100.0
        ),
        unit="percent",
        higher_is_better=True,
        description="Free cash flow (OCF + reported capex) as a percentage of revenue.",
    ),
    RatioDefinition(
        key="capex_to_revenue",
        name="Capex to Revenue",
        category=RatioCategory.cash_flow,
        inputs=["capital_expenditures", "revenue"],
        # Magnitude of capex relative to revenue; abs() so the intensity reads positive.
        compute=lambda f: abs(f["capital_expenditures"]) / f["revenue"] * 100.0,
        unit="percent",
        higher_is_better=None,
        description="Absolute capital expenditures as a percentage of revenue; reinvestment intensity.",
    ),
]

# ---------------------------------------------------------------------------
# Per-share / valuation (valuation ratios need market price)
# ---------------------------------------------------------------------------

_PER_SHARE_AND_VALUATION = [
    RatioDefinition(
        key="eps",
        name="Earnings Per Share (Diluted)",
        category=RatioCategory.per_share,
        inputs=["net_income", "shares_outstanding_diluted"],
        compute=lambda f: f["net_income"] / f["shares_outstanding_diluted"],
        unit="currency",
        higher_is_better=True,
        description="Net income / diluted shares outstanding.",
    ),
    RatioDefinition(
        key="book_value_per_share",
        name="Book Value Per Share",
        category=RatioCategory.per_share,
        inputs=["total_equity", "shares_outstanding_diluted"],
        compute=lambda f: f["total_equity"] / f["shares_outstanding_diluted"],
        unit="currency",
        higher_is_better=True,
        description="Total equity / diluted shares outstanding; net asset value per share.",
    ),
    RatioDefinition(
        key="dividend_payout_ratio",
        name="Dividend Payout Ratio",
        category=RatioCategory.per_share,
        inputs=["dividends_paid", "net_income"],
        # dividends_paid is stored as reported (negative cash outflow); abs() for payout.
        compute=lambda f: abs(f["dividends_paid"]) / f["net_income"] * 100.0,
        unit="percent",
        higher_is_better=None,
        description="Dividends paid (absolute) as a percentage of net income.",
    ),
    RatioDefinition(
        key="pe_ratio",
        name="Price-to-Earnings (P/E)",
        category=RatioCategory.valuation,
        inputs=["net_income", "shares_outstanding_diluted"],
        market_inputs=["market_price"],
        compute=lambda f: f["market_price"] / (f["net_income"] / f["shares_outstanding_diluted"]),
        unit="x",
        higher_is_better=None,
        description="Market price per share / earnings per share.",
    ),
    RatioDefinition(
        key="pb_ratio",
        name="Price-to-Book (P/B)",
        category=RatioCategory.valuation,
        inputs=["total_equity", "shares_outstanding_diluted"],
        market_inputs=["market_price"],
        compute=lambda f: f["market_price"] / (f["total_equity"] / f["shares_outstanding_diluted"]),
        unit="x",
        higher_is_better=None,
        description="Market price per share / book value per share.",
    ),
]


# The full, ordered catalogue consumed by the engine.
RATIO_DEFINITIONS: list[RatioDefinition] = [
    *_LIQUIDITY,
    *_LEVERAGE,
    *_PROFITABILITY,
    *_EFFICIENCY,
    *_CASH_FLOW,
    *_PER_SHARE_AND_VALUATION,
]
