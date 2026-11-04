
const {
    calculateGoalAssessment
} = require("./utils/goalAssessment");

const goal = {
    name: "Buy a House",
    targetAmount: 5000000,

    currentSavings: 500000,
    portfolioAllocatedAmount: 1000000,

    monthlyContribution: 25000,

    targetDate: new Date("2034-11-04T00:00:00"),

    inflationRate: 6,
    expectedAnnualReturn: 10
};

const riskFlags = [
    {
        type: "Concentration",
        severity: "High",
        message: "One holding has high concentration."
    }
];

const result = calculateGoalAssessment(
    goal,
    riskFlags
);

console.log("GOAL-BASED PORTFOLIO ASSESSMENT");
console.log(JSON.stringify(result, null, 2));
