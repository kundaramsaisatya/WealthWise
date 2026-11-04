
const { calculateGoalPlan } = require("./goalCalculator");

function buildGoalRecommendations(assessment, riskFlags = []) {
    const recommendations = [];

    // Rule 1: Funding gap
    if (assessment.funding_gap > 0) {
        if (assessment.months_remaining > 0) {
            recommendations.push({
                priority: "High",
                category: "Goal Funding",
                title: "Review your monthly contribution",
                reason:
                    `Your projected funding gap is ₹${assessment.funding_gap.toFixed(2)}.`,
                action:
                    `Your plan requires approximately ₹${assessment.additional_monthly_requirement.toFixed(2)} more per month than your current contribution. Review whether this is affordable or whether the target date needs adjustment.`,
                basis: {
                    funding_gap: assessment.funding_gap,
                    additional_monthly_requirement:
                        assessment.additional_monthly_requirement,
                    months_remaining: assessment.months_remaining
                }
            });
        } else {
            recommendations.push({
                priority: "High",
                category: "Goal Funding",
                title: "Revisit your goal timeline",
                reason:
                    "The target date has been reached with a projected funding shortfall.",
                action:
                    "Review the target amount, available savings and whether the goal timeline can be revised."
            });
        }
    }

    // Rule 2: Portfolio risk flags
    for (const flag of riskFlags) {
        if (!flag || !["High", "Medium"].includes(flag.severity)) {
            continue;
        }

        let title = "Review allocated portfolio risk";
        let action =
            "Discuss this flagged risk with a qualified financial adviser before making changes.";

       if (flag.type === "Concentration") {
            title = "Review holding concentration";

            if (flag.holding_name) {
                action =
                    "Review whether this holding is too heavily weighted in the goal allocation. Consider the impact of reducing concentration with a qualified financial adviser.";
            } else {
                action =
                    "Review whether too much of this goal's allocated value depends on a small number of holdings.";
            }
        } else if (flag.type === "Liquidity") {
            title = "Review liquidity allocation";
            action =
                "Review whether the allocated holdings provide sufficient liquidity for this goal's timeline.";
        } else if (flag.type === "Data Quality") {
            title = "Verify portfolio data";
            action =
                "Check the original statements and confirm that the holding information is complete and up to date.";
        } else if (flag.type === "Allocation") {
            title = "Review asset allocation";
            action =
                "Discuss the flagged allocation against the configured investor-profile threshold with a qualified adviser.";
        }
        else if (flag.type === "Goal Horizon Risk") {
            title = "Review goal-horizon risk";
            action =
                "This goal has a short investment timeline. Equity prices can fluctuate significantly over short periods. Review whether the allocated holdings match the time available before the goal, and discuss alternatives with a qualified financial adviser.";
        }

        recommendations.push({
            priority: flag.severity,
            category: flag.type || "Portfolio Risk",
            title,
            reason: flag.message,
            action
        });
    }

    // Rule 3: No configured risk thresholds breached
    if (
        !riskFlags.some(flag =>
            flag && ["High", "Medium"].includes(flag.severity)
        )
    ) {
        recommendations.push({
            priority: "Low",
            category: "Portfolio Review",
            title: "Continue periodic reviews",
            reason:
                "No high- or medium-severity configured risk flags were returned.",
            action:
                "Continue reviewing your goal allocation periodically. This does not mean the portfolio is risk-free."
        });
    }

    return recommendations;
}

function calculateGoalAssessment(goal, riskFlags = []) {
    const portfolioAllocatedAmount =
        Number(goal.portfolioAllocatedAmount || 0);

    const currentSavings =
        Number(goal.currentSavings || 0);

    const monthlyContribution =
        Number(goal.monthlyContribution || 0);

    if (
        !Number.isFinite(portfolioAllocatedAmount) ||
        portfolioAllocatedAmount < 0 ||
        !Number.isFinite(currentSavings) ||
        currentSavings < 0 ||
        !Number.isFinite(monthlyContribution) ||
        monthlyContribution < 0
    ) {
        throw new Error("Invalid goal funding amounts.");
    }

    const startingCapital =
        currentSavings + portfolioAllocatedAmount;

    const plan = calculateGoalPlan({
        ...goal,
        currentSavings: startingCapital
    });

    const months = plan.months_remaining;

    const annualReturn =
        Number(goal.expectedAnnualReturn || 0) / 100;

    const monthlyReturn =
        Math.pow(1 + annualReturn, 1 / 12) - 1;

    let futureContributions = 0;

    if (months > 0 && monthlyContribution > 0) {
        if (monthlyReturn === 0) {
            futureContributions = monthlyContribution * months;
        } else {
            futureContributions =
                monthlyContribution *
                (Math.pow(1 + monthlyReturn, months) - 1) /
                monthlyReturn;
        }
    }

    const projectedTotal =
        plan.projected_existing_savings + futureContributions;

    const fundingRatio =
        plan.future_target > 0
            ? projectedTotal / plan.future_target * 100
            : 0;

    const fundingGap = Math.max(
        0,
        plan.future_target - projectedTotal
    );

    let status;

    if (months === 0 && fundingGap > 0) {
        status = "Target date reached - shortfall";
    } else if (fundingRatio >= 100) {
        status = "Projected on track";
    } else {
        status = "Projected funding gap";
    }

    const findings = [];

    if (fundingGap > 0) {
        findings.push({
            type: "Funding Gap",
            severity: "High",
            message:
                `Projected funding is short by ₹${fundingGap.toFixed(2)}.`
        });
    } else {
        findings.push({
            type: "Goal Funding",
            severity: "Low",
            message:
                "Projected funding meets or exceeds the estimated goal."
        });
    }

    const relevantRiskFlags = riskFlags.filter(
        flag => flag &&
            ["High", "Medium"].includes(flag.severity)
    );

    if (relevantRiskFlags.length > 0) {
        findings.push({
            type: "Portfolio Risk",
            severity: relevantRiskFlags.some(
                flag => flag.severity === "High"
            ) ? "High" : "Medium",
            message:
                `${relevantRiskFlags.length} high- or medium-severity portfolio risk flag(s) require review.`
        });
    }

    const result = {
        goal_name: goal.name,
        status,
        future_target: plan.future_target,
        current_savings: currentSavings,
        portfolio_allocated_amount: portfolioAllocatedAmount,
        starting_capital: startingCapital,
        projected_existing_funds: plan.projected_existing_savings,
        planned_monthly_contribution: monthlyContribution,
        projected_contributions:
            Number(futureContributions.toFixed(2)),
        projected_total: Number(projectedTotal.toFixed(2)),
        projected_funding_percentage:
            Number(fundingRatio.toFixed(2)),
        funding_gap: Number(fundingGap.toFixed(2)),
        required_monthly_investment:
            plan.required_monthly_investment,
        additional_monthly_requirement: Number(Math.max(
            0,
            plan.required_monthly_investment - monthlyContribution
        ).toFixed(2)),
        months_remaining: months,
        findings,
        assumptions: {
            inflation_rate: goal.inflationRate,
            expected_annual_return: goal.expectedAnnualReturn,
            compounding: "Monthly",
            contribution_timing: "End of each month",
            portfolio_allocation_is_goal_specific: true
        },
        limitations: [
            "Returns are assumed constant and are not guaranteed.",
            "Portfolio risk flags are warnings, not a complete suitability assessment.",
            "Taxes, fees and investment volatility are not modelled."
        ]
    };

    result.recommendations =
        buildGoalRecommendations(result, riskFlags);

    return result;
}

module.exports = {
    calculateGoalAssessment
};
