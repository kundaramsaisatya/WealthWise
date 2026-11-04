
function calculateGoalPlan(goal, asOfDate = new Date()) {

    const {
        targetAmount,
        currentSavings = 0,
        targetDate,
        inflationRate = 6,
        expectedAnnualReturn = 10
    } = goal;

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

    const months = Math.max(
        0,
        (
            (targetDate.getFullYear() - asOfDate.getFullYear()) * 12
            + targetDate.getMonth()
            - asOfDate.getMonth()
        )
    );

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
        currentSavings * Math.pow(1 + monthlyReturn, months);

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

    const projectedProgress =
        futureTarget > 0
            ? Math.min(
                100,
                futureSavings / futureTarget * 100
            )
            : 0;

    return {
        months_remaining: months,
        years_remaining: Number(years.toFixed(2)),
        future_target: Number(futureTarget.toFixed(2)),
        projected_existing_savings: Number(
            futureSavings.toFixed(2)
        ),
        remaining_amount: Number(remainingAmount.toFixed(2)),
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
            contribution_timing: "End of each month"
        }
    };
}

module.exports = {
    calculateGoalPlan
};
