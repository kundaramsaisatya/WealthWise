
function calculateGoalPlan(goal, asOfDate = new Date()) {

    const {
        targetAmount,
        currentSavings = 0,
        targetDate,
        inflationRate = 6,
        expectedAnnualReturn = 10
    } = goal;

    // Validate inputs
    const values = [
        targetAmount,
        currentSavings,
        inflationRate,
        expectedAnnualReturn
    ];

    if (
        values.some(value =>
            typeof value !== "number" ||
            !Number.isFinite(value) ||
            value < 0
        ) ||
        targetAmount <= 0 ||
        !(targetDate instanceof Date) ||
        Number.isNaN(targetDate.getTime()) ||
        !(asOfDate instanceof Date) ||
        Number.isNaN(asOfDate.getTime())
    ) {
        throw new Error("Invalid financial goal data.");
    }

    // Calculate exact days remaining
    const startOfToday = new Date(
        asOfDate.getFullYear(),
        asOfDate.getMonth(),
        asOfDate.getDate()
    );

    const target = new Date(
        targetDate.getFullYear(),
        targetDate.getMonth(),
        targetDate.getDate()
    );

    const daysRemaining = Math.max(
        0,
        Math.ceil(
            (target - startOfToday) /
            (1000 * 60 * 60 * 24)
        )
    );

    // Convert remaining days into approximate months
    const months = Math.ceil(daysRemaining / 30.4375);

    const years = months / 12;

    const inflation = inflationRate / 100;
    const annualReturn = expectedAnnualReturn / 100;

    const monthlyReturn = Math.pow(
        1 + annualReturn,
        1 / 12
    ) - 1;

    // Inflation-adjusted future target
    const futureTarget =
        targetAmount * Math.pow(1 + inflation, years);

    // Future value of existing savings
    const futureSavings =
        currentSavings *
        Math.pow(1 + monthlyReturn, months);

    const remainingAmount = Math.max(
        0,
        futureTarget - futureSavings
    );

    // Required monthly investment
    let requiredMonthlyInvestment = 0;

    if (remainingAmount > 0 && months > 0) {

        if (monthlyReturn === 0) {

            requiredMonthlyInvestment =
                remainingAmount / months;

        } else {

            requiredMonthlyInvestment =
                remainingAmount * monthlyReturn /
                (Math.pow(1 + monthlyReturn, months) - 1);
        }
    }

    // Projected progress
    const projectedProgress =
        futureTarget > 0
            ? Math.min(
                100,
                futureSavings / futureTarget * 100
            )
            : 0;

    return {

        days_remaining: daysRemaining,

        months_remaining: months,

        years_remaining: Number(years.toFixed(2)),

        future_target: Number(
            futureTarget.toFixed(2)
        ),

        projected_existing_savings: Number(
            futureSavings.toFixed(2)
        ),

        remaining_amount: Number(
            remainingAmount.toFixed(2)
        ),

        required_monthly_investment: Number(
            requiredMonthlyInvestment.toFixed(2)
        ),

        projected_progress_percentage: Number(
            projectedProgress.toFixed(2)
        ),

        assumptions: {
            inflation_rate: inflationRate,
            expected_annual_return: expectedAnnualReturn,
            compounding: "Monthly",
            contribution_timing: "End of each month",
            time_calculation: "Actual days converted to approximate months"
        }
    };
}

module.exports = {
    calculateGoalPlan
};
