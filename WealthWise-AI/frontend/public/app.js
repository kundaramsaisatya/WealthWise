
document.addEventListener("DOMContentLoaded", () => {

    // =========================================
    // ELEMENT REFERENCES
    // =========================================

    const sidebar = document.getElementById("sidebar");
    const mobileMenuBtn = document.getElementById("mobile-menu-btn");

    const chatForm = document.getElementById("chat-form");
    const chatBox = document.getElementById("chat-box");
    const questionInput = document.getElementById("question");

    const explainButton = document.getElementById("explain-risk-btn");
    const explanationResult = document.getElementById("risk-explanation-result");

    const historyButton = document.getElementById("load-history-btn");
    const historyContainer = document.getElementById("chat-history");

    const documentContainer = document.getElementById("document-list");
    const documentCount = document.getElementById("document-count");

    const uploadForm = document.getElementById("upload-form");


    // =========================================
    // COMMON HELPERS
    // =========================================

    async function apiRequest(url, options = {}) {

        const response = await fetch(url, {
            credentials: "same-origin",
            ...options
        });

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error("Invalid server response.");
        }

        if (!response.ok) {
            throw new Error(
                data.error ||
                data.message ||
                `Request failed (${response.status}).`
            );
        }

        return data;
    }

    async function loadPortfolioPerformance() {
    const message = document.getElementById("performance-message");
    const canvas = document.getElementById("performanceChart");

    if (!message || !canvas) return;

    try {
        const data = await apiRequest("/performance");
        const performance = data.performance;

        if (
            !performance ||
            !Array.isArray(performance.history) ||
            performance.history.length < 2
        ) {
            message.textContent =
                "At least two valid historical statements are required.";
            canvas.style.display = "none";
            return;
        }

        message.textContent = "";

        new Chart(canvas, {
            type: "line",
            data: {
                labels: performance.history.map(item =>
                    item.report_date
                ),
                datasets: [{
                    label: "Portfolio Value (₹)",
                    data: performance.history.map(item =>
                        Number(item.portfolio_value)
                    ),
                    tension: 0.3,
                    fill: false
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false
                    }
                }
            }
        });

    } catch (error) {
        message.textContent = error.message;
        canvas.style.display = "none";
    }
}


    function createElement(tag, className, text) {

        const element = document.createElement(tag);

        if (className) {
            element.className = className;
        }

        if (text !== undefined && text !== null) {
            element.textContent = String(text);
        }

        return element;
    }


    function cleanMarkdown(text) {

        return String(text || "")
            .replace(/\*\*(.*?)\*\*/g, "$1")
            .replace(/\*(.*?)\*/g, "$1")
            .replace(/^#{1,6}\s/gm, "")
            .trim();
    }


    function formatDate(date) {

        if (!date) return "Date unavailable";

        const parsedDate = new Date(date);

        if (Number.isNaN(parsedDate.getTime())) {
            return "Date unavailable";
        }

        return parsedDate.toLocaleString("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        });
    }


    // =========================================
    // MOBILE SIDEBAR
    // =========================================

    if (mobileMenuBtn && sidebar) {

        mobileMenuBtn.addEventListener("click", () => {
            sidebar.classList.toggle("open");
        });

        document.addEventListener("click", event => {

            const clickedInsideSidebar = sidebar.contains(event.target);
            const clickedMenuButton = mobileMenuBtn.contains(event.target);

            if (
                window.innerWidth <= 650 &&
                !clickedInsideSidebar &&
                !clickedMenuButton
            ) {
                sidebar.classList.remove("open");
            }
        });

    }


    // =========================================
    // SIDEBAR NAVIGATION
    // =========================================

    const navLinks = document.querySelectorAll(".nav-link");

    function updateActiveNavigation() {

        const currentHash = window.location.hash || "#overview";

        navLinks.forEach(link => {

            link.classList.toggle(
                "active",
                link.getAttribute("href") === currentHash
            );

        });

    }


    navLinks.forEach(link => {

        link.addEventListener("click", () => {

            navLinks.forEach(item => {
                item.classList.remove("active");
            });

            link.classList.add("active");

            if (sidebar) {
                sidebar.classList.remove("open");
            }

        });

    });


    window.addEventListener("hashchange", updateActiveNavigation);

    updateActiveNavigation();


    // =========================================
    // AI CHAT
    // =========================================

    function removeAssistantWelcome() {

        const welcome = chatBox?.querySelector(".assistant-welcome");

        if (welcome) {
            welcome.remove();
        }

    }


    function addChatMessage(role, content, isError = false) {

        if (!chatBox) return null;

        removeAssistantWelcome();

        const message = createElement(
            "div",
            `chat-message ${role}${isError ? " error" : ""}`,
            cleanMarkdown(content)
        );

        chatBox.appendChild(message);

        chatBox.scrollTop = chatBox.scrollHeight;

        return message;
    }


    function addChatSources(sources) {

        if (!chatBox || !Array.isArray(sources) || !sources.length) {
            return;
        }

        const sourceContainer = createElement(
            "div",
            "chat-sources"
        );

        const heading = createElement(
            "strong",
            "",
            "Sources"
        );

        sourceContainer.appendChild(heading);

        sources.forEach(source => {

            const filename =
                source.source ||
                source.filename ||
                source.file ||
                "Uploaded document";

            let location = "";

            if (source.sheet) {
                location = ` · Sheet: ${source.sheet}`;
            } else if (source.page != null) {
                location = ` · Page: ${source.page}`;
            } else if (source.record != null) {
                location = ` · Record: ${source.record}`;
            }

            const item = createElement(
                "div",
                "",
                `${filename}${location}`
            );

            sourceContainer.appendChild(item);

        });

        chatBox.appendChild(sourceContainer);

        chatBox.scrollTop = chatBox.scrollHeight;

    }


    if (chatForm && chatBox && questionInput) {

        chatForm.addEventListener("submit", async event => {

            event.preventDefault();

            const question = questionInput.value.trim();

            if (!question) return;

            const submitButton = chatForm.querySelector(
                'button[type="submit"]'
            );

            addChatMessage("user", question);

            questionInput.value = "";
            questionInput.disabled = true;

            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = "Thinking...";
            }

            const loadingMessage = addChatMessage(
                "assistant",
                "WealthWise AI is analyzing your documents..."
            );

            try {

                const data = await apiRequest("/chat", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ question })
                });

                const answer =
                    data.answer ||
                    data.error ||
                    "No answer received.";

                if (loadingMessage) {
                    loadingMessage.textContent = cleanMarkdown(answer);
                }

                addChatSources(data.sources);

            } catch (error) {

                if (loadingMessage) {
                    loadingMessage.textContent = error.message;
                    loadingMessage.classList.add("error");
                }

            } finally {

                questionInput.disabled = false;

                if (submitButton) {
                    submitButton.disabled = false;
                    submitButton.textContent = "Ask AI →";
                }

                questionInput.focus();

                chatBox.scrollTop = chatBox.scrollHeight;

            }

        });

    }


    // =========================================
    // AI RISK EXPLANATION
    // =========================================

    if (explainButton && explanationResult) {

        explainButton.addEventListener("click", async () => {

            explainButton.disabled = true;
            explainButton.textContent = "Generating explanation...";

            explanationResult.textContent =
                "WealthWise AI is analyzing your portfolio metrics...";

            try {

                const data = await apiRequest("/risk/explanation", {
                    method: "POST"
                });

                explanationResult.textContent = cleanMarkdown(
                    data.explanation || "No explanation received."
                );

            } catch (error) {

                explanationResult.textContent =
                    `Unable to generate explanation: ${error.message}`;

            } finally {

                explainButton.disabled = false;
                explainButton.textContent = "Generate explanation";

            }

        });

    }


    // =========================================
    // CHAT HISTORY
    // =========================================

    if (historyButton && historyContainer) {

        historyButton.addEventListener("click", async () => {

            historyButton.disabled = true;
            historyButton.textContent = "Loading...";

            try {

                const data = await apiRequest("/chat/history");

                const messages = Array.isArray(data.messages)
                    ? data.messages
                    : [];

                historyContainer.replaceChildren();

                if (!messages.length) {

                    historyContainer.textContent =
                        "No previous conversations.";

                    return;

                }

                messages.forEach(message => {

                    const item = createElement(
                        "div",
                        "message"
                    );

                    const heading = createElement(
                        "strong",
                        "",
                        message.role === "user"
                            ? "You"
                            : "WealthWise AI"
                    );

                    const content = createElement(
                        "div",
                        "",
                        cleanMarkdown(message.content)
                    );

                    item.append(heading, content);

                    historyContainer.appendChild(item);

                });

            } catch (error) {

                historyContainer.textContent =
                    `Unable to load chat history: ${error.message}`;

            } finally {

                historyButton.disabled = false;
                historyButton.textContent = "View history";

            }

        });

    }


    // =========================================
    // DOCUMENT LIBRARY
    // =========================================

    async function loadDocuments() {

        if (!documentContainer) return;

        documentContainer.replaceChildren();

        documentContainer.appendChild(
            createElement("div", "loading-state", "Loading documents...")
        );

        try {

            const data = await apiRequest("/documents");

            const documents = Array.isArray(data.documents)
                ? data.documents
                : [];

            documentContainer.replaceChildren();

            if (documentCount) {
                documentCount.textContent =
                    `${documents.length} documents`;
            }

            if (!documents.length) {

                documentContainer.appendChild(
                    createElement(
                        "div",
                        "empty-state",
                        ""
                    )
                );

                const emptyState = documentContainer.lastElementChild;

                emptyState.appendChild(
                    createElement("span", "", "▤")
                );

                emptyState.appendChild(
                    createElement(
                        "p",
                        "",
                        "No financial documents uploaded yet."
                    )
                );

                return;

            }

            documents.forEach(doc => {

                const item = createElement(
                    "div",
                    "document-item"
                );

                const info = createElement(
                    "div",
                    "document-info"
                );

                const name = createElement(
                    "strong",
                    "",
                    doc.name || "Untitled document"
                );

                const details = createElement(
                    "p",
                    "",
                    `${doc.type || "Document"} · ${doc.chunks ?? 0} chunks`
                );

                const date = createElement(
                    "p",
                    "",
                    `Uploaded: ${formatDate(doc.uploadedAt)}`
                );

                info.append(name, details, date);


                const actions = createElement(
                    "div",
                    "document-actions"
                );

                const statusValue = String(
                    doc.status || "unknown"
                ).toLowerCase();

                const status = createElement(
                    "span",
                    `document-status ${
                        ["failed", "processing"].includes(statusValue)
                            ? statusValue
                            : ""
                    }`,
                    statusValue.toUpperCase()
                );

                const deleteButton = createElement(
                    "button",
                    "delete-document-btn",
                    "Delete"
                );

                deleteButton.type = "button";
                deleteButton.disabled = !doc.id;

                deleteButton.addEventListener("click", async () => {

                    await deleteDocument(doc.id, deleteButton);

                });

                actions.append(status, deleteButton);

                item.append(info, actions);

                documentContainer.appendChild(item);

            });

        } catch (error) {

            documentContainer.replaceChildren();

            documentContainer.appendChild(
                createElement(
                    "div",
                    "empty-state",
                    error.message
                )
            );

        }

    }


    // =========================================
    // DELETE DOCUMENT
    // =========================================

    async function deleteDocument(documentId, button) {

        if (!documentId) return;

        const confirmed = window.confirm(
            "Are you sure you want to delete this financial document?\n\n" +
            "Its original file, extracted records and searchable chunks will be removed."
        );

        if (!confirmed) return;

        button.disabled = true;
        button.textContent = "Deleting...";

        try {

            await apiRequest(
                `/documents/${encodeURIComponent(documentId)}`,
                {
                    method: "DELETE"
                }
            );

            await loadDocuments();
            window.location.reload();

        } catch (error) {

            window.alert(error.message);

            button.disabled = false;
            button.textContent = "Delete";

        }

    }


    // =========================================
    // DOCUMENT UPLOAD
    // =========================================

    if (uploadForm) {

        uploadForm.addEventListener("submit", event => {

            const fileInput = uploadForm.querySelector(
                'input[type="file"]'
            );

            if (!fileInput || !fileInput.files.length) {
                event.preventDefault();
                return;
            }

            const files = Array.from(fileInput.files);

            const invalidFile = files.find(file => {

                const extension = file.name
                    .split(".")
                    .pop()
                    .toLowerCase();

                return (
                    !["pdf", "xlsx"].includes(extension) ||
                    file.size > 10 * 1024 * 1024
                );

            });

            if (invalidFile) {

                event.preventDefault();

                window.alert(
                    "Only PDF and XLSX files up to 10 MB each are supported."
                );

                return;

            }

            const submitButton = uploadForm.querySelector(
                'button[type="submit"]'
            );

            if (submitButton) {

                submitButton.disabled = true;
                submitButton.textContent = "Uploading documents...";

            }

        });

    }


    // =========================================
    // INITIALIZE
    // =========================================

    loadDocuments();
    loadPortfolioPerformance();

});
function initializePortfolioCharts() {
    const chartData = window.wealthWiseData || {};

    if (typeof Chart === "undefined") {
        console.error("Chart.js is not loaded.");
        return;
    }

    // Allocation doughnut chart
    const allocationCanvas = document.getElementById("allocationChart");
    const allocation = chartData.allocation || [];

    if (allocationCanvas && allocation.length > 0) {
        const labels = allocation.map(item =>
            item.asset_class || item.assetClass || item.name || "Other"
        );

        const values = allocation.map(item =>
            Number(item.value ?? item.current_value ?? item.amount ?? 0)
        );

        new Chart(allocationCanvas, {
            type: "doughnut",
            data: {
                labels,
                datasets: [{
                    data: values,
                    borderWidth: 2,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "65%",
                plugins: {
                    legend: {
                        position: "bottom"
                    }
                }
            }
        });
    }

    // Top holdings bar chart
    const holdingsCanvas = document.getElementById("holdingsChart");
    const holdings = chartData.holdings || [];

    if (holdingsCanvas && holdings.length > 0) {
        const topHoldings = [...holdings]
            .sort((a, b) =>
                Number(b.current_value || b.currentValue || 0) -
                Number(a.current_value || a.currentValue || 0)
            )
            .slice(0, 8);

        new Chart(holdingsCanvas, {
            type: "bar",
            data: {
                labels: topHoldings.map(item =>
                    item.name || item.holding_name || "Unknown"
                ),
                datasets: [{
                    label: "Current Value",
                    data: topHoldings.map(item =>
                        Number(item.current_value || item.currentValue || 0)
                    ),
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true
                    }
                }
            }
        });
    }
}

initializePortfolioCharts();