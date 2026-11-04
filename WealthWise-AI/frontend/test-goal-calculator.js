
const {
    calculateGoalPlan
} = require("./utils/goalCalculator");

const goal = {
    targetAmount: 5000000,
    currentSavings: 500000,
    targetDate: new Date("2034-11-04T00:00:00"),
    inflationRate: 6,
    expectedAnnualReturn: 10
};

const result = calculateGoalPlan(
    goal,
    new Date("2026-11-04T00:00:00")
);

console.log("Financial Goal Calculation:");
console.log(result);
