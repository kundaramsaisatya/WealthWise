
const { calculateGoalPlan } = require("./goalCalculator");

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

    // Existing savings and assigned investments are
    // separate sources of funding for this goal.

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

    // Future value of monthly contributions.
    // Contributions are assumed to happen at month-end.

    let futureContributions = 0;

    if (months > 0 && monthlyContribution > 0) {

        if (monthlyReturn === 0) {

            futureContributions =
                monthlyContribution * months;

        } else {

            futureContributions =
                monthlyContribution *
                (
                    Math.pow(1 + monthlyReturn, months) - 1
                ) / monthlyReturn;

        }
    }

    const projectedTotal =
        plan.projected_existing_savings +
        futureContributions;

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

    // Transparent assessment findings.

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

    const highRiskFlags = riskFlags.filter(
        flag => flag.severity === "High"
    );

    if (highRiskFlags.length > 0) {

        findings.push({
            type: "Portfolio Risk",
            severity: "High",
            message:
                `${highRiskFlags.length} high-severity portfolio risk flag(s) require review.`
        });

    }

    return {

        goal_name: goal.name,

        status,

        future_target: plan.future_target,

        current_savings: currentSavings,

        portfolio_allocated_amount:
            portfolioAllocatedAmount,

        starting_capital: startingCapital,

        projected_existing_funds:
            plan.projected_existing_savings,

        planned_monthly_contribution:
            monthlyContribution,

        projected_contributions:
            Number(futureContributions.toFixed(2)),

        projected_total:
            Number(projectedTotal.toFixed(2)),

        projected_funding_percentage:
            Number(fundingRatio.toFixed(2)),

        funding_gap:
            Number(fundingGap.toFixed(2)),

        required_monthly_investment:
            plan.required_monthly_investment,

        additional_monthly_requirement:
            Number(Math.max(
                0,
                plan.required_monthly_investment -
                monthlyContribution
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
}

module.exports = {
    calculateGoalAssessment
};
